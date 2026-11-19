"""Tests of claude/hooks/agent_guard.py, the PreToolUse hook that keeps each factory agent to what it may do.

Every case runs the guard as Claude Code does: the tool call as JSON on stdin, the decision as JSON on stdout.
Run: python3 -m unittest discover -s scripts/tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

GUARD = support.FACTORY / "claude" / "hooks" / "agent_guard.py"


def decide(agent, tool, tool_input, cwd):
    """The deny reason, or None when the call is allowed."""
    call = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(cwd)})
    out = subprocess.run([sys.executable, "-I", str(GUARD), agent], input=call, capture_output=True, text=True,
                         check=True).stdout.strip()
    if not out:
        return None
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny", decision
    return decision["permissionDecisionReason"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=str(support.FACTORY.parent))   # not under the system temp folder
        self.root = Path(self.tmp.name) / "project"
        (self.root / "src").mkdir(parents=True)
        support.git(self.root, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, agent, path, tool="Edit"):
        return decide(agent, tool, {"file_path": str(path)}, self.root)

    def bash(self, agent, command):
        return decide(agent, "Bash", {"command": command}, self.root)


class Paths(Base):
    def test_tester_edits_tests_only(self):
        for path in ("tests/test_app.py", "test/x.js", "src/app.test.ts", "src/__tests__/a.js", "pkg/a_test.go",
                     "web/b.spec.tsx", "test_root.py", "pkg/testdata/in.json", "tests/fixtures/f.json"):
            with self.subTest(path):
                self.assertIsNone(self.edit("tester", path))
        reason = self.edit("tester", "src/app.ts")
        self.assertIn("tester may only edit test files", reason)
        self.assertIn("src/app.ts is not one", reason)
        # * stays within one folder: these are production code, not tests (review of #24)
        for path in ("src/test_runner/app.py", "src/a.test.d/evil.py", "src/a.spec/x.js"):
            with self.subTest(path):
                self.assertIsNotNone(self.edit("tester", path))

    def test_docs_writer_edits_docs_only(self):
        for path in ("README.md", "src/README.md", "CHANGELOG.md", "docs/guide/a.md", "NOTES.md", ".env.example"):
            with self.subTest(path):
                self.assertIsNone(self.edit("docs-writer", path, tool="Write"))
        for path in ("src/app.py", "src/notes.md", ".env", "package.json"):
            with self.subTest(path):
                self.assertIn("docs-writer may only edit documentation", self.edit("docs-writer", path))

    def test_planner_writes_plans_only(self):
        self.assertIsNone(self.edit("planner", "docs/plans/2026-11-19-x.md", tool="Write"))
        self.assertIn("planner may only edit plans", self.edit("planner", "docs/other.md", tool="Write"))

    def test_implementer_edits_anything_in_the_project(self):
        self.assertIsNone(self.edit("implementer", "src/app.py"))

    def test_absolute_and_dotdot_paths_are_resolved(self):
        self.assertIsNone(self.edit("tester", self.root / "tests" / "a_test.py"))
        self.assertIn("src/x.py is not one", self.edit("tester", "tests/../src/x.py"))
        self.assertIn("outside", self.edit("tester", self.root.parent / "elsewhere" / "tests" / "a.py"))

    def test_temp_folder_is_allowed(self):
        self.assertIsNone(self.edit("tester", Path(tempfile.gettempdir()) / "scratch.py"))

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_symlink_into_production_code_is_followed(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "link.py").symlink_to(self.root / "src" / "app.py")
        self.assertIn("src/app.py is not one", self.edit("tester", "tests/link.py"))

    def test_notebook_path_is_checked(self):
        reason = decide("tester", "NotebookEdit", {"notebook_path": "src/a.ipynb"}, self.root)
        self.assertIn("src/a.ipynb is not one", reason)


class Git(Base):
    def test_history_and_branch_changes_are_refused(self):
        for command in ("git push", "git commit -am x", "git reset --hard HEAD~1", "git checkout -b x",
                        "git switch main", "git rebase main", "git stash", "git add -A", "git tag v1",
                        "git branch -D old", "git branch --delete old", "git restore --staged a.py",
                        "git clean -fd", "git pull"):
            with self.subTest(command):
                self.assertIn("conductor does all git work", self.bash("implementer", command))

    def test_disguised_git_writes_are_refused(self):
        for command in ("git -C . push origin HEAD", "git -c push.default=current push", "git --no-pager commit",
                        "npm test && git push", "true; git push", "make\ngit push", "GIT_DIR=.git git push",
                        "env FOO=1 git commit -m x", 'bash -c "git push --force"', "/usr/bin/git push",
                        "echo ok | xargs git push",
                        # wrappers and shells with options, backticks, $( ) and eval (review of #24)
                        "env -i git push", "nice -n 5 git push", "sudo -u me git push", "timeout 10 git push",
                        'bash -lc "git push"', 'sh -ec "git commit -m x"', "echo `git push`", "x=$(git push)",
                        'eval "git push"', "eval git push", "env -S 'git push'",
                        "git update-index --assume-unchanged a.py", "git symbolic-ref HEAD refs/heads/x",
                        # aliases and commands the guard does not know: only known reads pass (review of #24)
                        "git -c alias.x=push x", "git config alias.p push", "git p", "git co main",
                        "git notes add -m x", "git reflog expire --all", "git branch new-feature", "git stash",
                        "git -c core.pager=less log", "git -c core.fsmonitor=./evil.sh status",
                        "git config user.email x@example.org",
                        # xargs gives git its subcommand at run time; a read form must not hide a write after it
                        "echo push | xargs git", "printf 'push' | xargs -n1 git", "git remote -v add up https://x",
                        "git remote -v set-url origin https://x", "git remote add up https://x",
                        "git tag -l -d v1", "git tag -a v2 -m x"):
            with self.subTest(command):
                self.assertIsNotNone(self.bash("tester", command))

    def test_quoting_a_writing_git_command_is_refused_too(self):
        """The text layer is strict on purpose: it cannot tell an echo from an eval, so both are refused."""
        self.assertIsNotNone(self.bash("tester", 'echo "next: git push"'))

    def test_read_only_git_and_project_commands_are_allowed(self):
        for command in ("git status", "git diff main...HEAD", "git log --oneline -5", "git show HEAD:a.py",
                        "git -c core.pager=cat log", "git branch --show-current", "git branch -a",
                        "git restore src/a.py", "npm test", "pytest -q", "git tag -l", "git tag --list 'v*'",
                        "git stash list", "git stash show -p", "echo \"pushing is the conductor's job\"",
                        "nice -n 5 npm test", "env -i PATH=/usr/bin pytest", 'bash -lc "npm test"',
                        "gitk --all", "mygit push", "git config --get user.name", "git config --list",
                        "git remote -v", "git remote", "git reflog", "git branch --contains HEAD",
                        "git branch --merged main", "git tag", "git -c core.pager=cat log", "git notes list",
                        "git worktree list", "git grep -n TODO", "git rev-parse --show-toplevel",
                        "git remote show origin", "git remote get-url origin", "git remote --verbose",
                        "ls | xargs wc -l"):
            with self.subTest(command):
                self.assertIsNone(self.bash("tester", command))

    def test_unparseable_command_that_mentions_git_is_refused(self):
        self.assertIn("could not parse", self.bash("docs-writer", 'echo "unbalanced; git push'))
        self.assertIsNone(self.bash("docs-writer", 'echo "unbalanced'))


class CommandLine(unittest.TestCase):
    def run_guard(self, *args, stdin="{}"):
        return subprocess.run([sys.executable, "-I", str(GUARD), *args], input=stdin, capture_output=True, text=True)

    def test_unknown_agent_is_a_usage_error(self):
        self.assertEqual(2, self.run_guard("reviewer").returncode)
        self.assertEqual(2, self.run_guard().returncode)

    def test_unreadable_input_is_refused(self):
        """A crash would exit 1, which Claude Code treats as non-blocking: the guard must refuse instead."""
        for stdin in ("not json", "[1, 2]", '"text"', '{"tool_name": "Bash", "tool_input": "git push"}'):
            with self.subTest(stdin):
                done = self.run_guard("tester", stdin=stdin)
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual("deny", json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"])

    def test_other_tools_are_allowed(self):
        call = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "src/a.py"}, "cwd": "."})
        self.assertEqual("", self.run_guard("tester", stdin=call).stdout.strip())


if __name__ == "__main__":
    unittest.main()
