"""Tests of the eval suite under evals/ and of scripts/run-evals.sh, with no Claude call (roadmap I1).

- every case.yaml has the shape Claude Code 2.1.310's strict schema accepts, and a free grader that decides it;
- every scaffold.sh builds its repository as an eval run would (a reduced environment, no network), with the planted
  defect in place and the review folder as /factory-review writes it;
- no fixture file holds what the content guard flags (the planted key is assembled at run time);
- run-evals.sh passes the right options to claude, here a fake one, on Linux and on Windows.

Run: python3 -m unittest discover -s scripts/tests
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

sys.path.insert(0, str(support.SCRIPTS))
import check_content  # noqa: E402  (after the sys.path line above)

try:
    import yaml
except ImportError:   # the self-test installs PyYAML for the docs drift tests too
    yaml = None
needs_yaml = unittest.skipUnless(yaml, "PyYAML not installed")

EVALS = support.FACTORY / "evals"
CASES = sorted(p.parent for p in EVALS.glob("*/case.yaml"))

# The case schema of Claude Code 2.1.310 (strict: an unknown key fails the whole suite)
CASE_KEYS = {"schema_version", "name", "description", "tags", "plugins", "context", "execution", "runs", "graders",
             "expected_outcome"}
CONTEXT_KEYS = {"scaffold_script", "history_file", "add_dirs"}
EXECUTION_KEYS = {"prompt", "max_turns", "timeout_seconds", "model", "allowed_tools", "disallowed_tools",
                  "append_system_prompt", "env"}
COMMON = {"type", "name", "weight", "arm"}
GRADER_KEYS = {"regex": COMMON | {"target", "pattern", "flags", "match"},
               "tool_used": COMMON | {"tool", "input_match", "min", "max"},
               "tool_order": COMMON | {"before", "after"},
               "file_exists": COMMON | {"path", "exists"},
               "llm": COMMON | {"criteria", "focus"},
               "baseline": COMMON | {"baseline_file", "criteria"}}
FREE = {"regex", "tool_used", "tool_order", "file_exists"}

# What each scaffold must give: branch, commits on it beyond main, the planted file and line, a review folder, the
# fixture's test command and whether its tests pass
SCAFFOLDS = {
    "reviewer-finds-off-by-one": ("feat/paginate", 1, "catalog/paginate.py", "return items[start:last]", True,
                                  ["-m", "unittest"], True),
    "reviewer-approves-clean-change": ("feat/paginate", 1, "catalog/paginate.py", "return items[start:start + size]",
                                       True, ["-m", "unittest"], True),
    "security-finds-key-and-sqli": ("feat/find-user", 1, "accounts/users.py", "WHERE name = '{name}'", True,
                                    ["-m", "unittest"], True),
    "security-passes-clean-change": ("feat/find-user", 1, "accounts/users.py", "WHERE name = ?", True,
                                     ["-m", "unittest"], True),
    "planner-writes-testable-criteria": ("feat/list-limit", 0, "src/cli.py",
                                         "for number, text in enumerate(tasks, start=1):", False,
                                         ["-m", "unittest", "discover", "-s", "tests"], True),
    "tester-reports-instead-of-fixing-src": ("feat/average", 1, "src/calc.py", "return total(numbers) // len(numbers)",
                                             False, ["-m", "unittest", "discover", "-s", "tests"], False),
    "factory-build-not-started-by-request": ("feat/verbose-flag", 0, "src/cli.py", "def main(", False,
                                             ["-m", "unittest", "discover", "-s", "tests"], True),
    "factory-review-starts-from-request": ("feat/paginate", 1, "catalog/paginate.py", "return items[start:last]", False,
                                           ["-m", "unittest"], True),
}


def load(case_dir):
    return yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))


def scaffold(case_dir, workdir):
    """Run a case's scaffold.sh as `claude plugin eval --scaffold` does: bash, the run's folder as working directory,
    a reduced environment (PATH, a sandbox HOME, GIT_CONFIG_NOSYSTEM)."""
    home = Path(workdir).parent / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")   # Windows programs need it to start
    return subprocess.run([support.BASH, support.posix(case_dir / "scaffold.sh")], cwd=workdir, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True, env=support.environment()).stdout


class Cases(unittest.TestCase):
    def test_the_suite(self):
        names = {c.name for c in CASES}
        self.assertEqual(set(SCAFFOLDS) | {"_probe"}, names)
        self.assertFalse((EVALS / "_lib" / "case.yaml").exists())
        # a prompt.md is a case too (the CLI's other case format); none must hide among the fixtures
        self.assertEqual([], [p for p in EVALS.rglob("prompt.md")])

    @needs_yaml
    def test_every_case_matches_the_schema(self):
        for case_dir in CASES:
            with self.subTest(case=case_dir.name):
                case = load(case_dir)
                self.assertLessEqual(set(case), CASE_KEYS)
                self.assertLessEqual(set(case.get("context") or {}), CONTEXT_KEYS)
                self.assertLessEqual(set(case["execution"]), EXECUTION_KEYS)
                self.assertEqual("1.0", case["schema_version"])
                self.assertEqual(case_dir.name, case["name"])
                self.assertTrue(case["tags"])
                self.assertTrue(case["execution"]["prompt"].strip())
                self.assertLessEqual(case["execution"]["max_turns"], 200)
                self.assertLessEqual(case["execution"]["timeout_seconds"], 3600)
                self.assertTrue((case_dir / case["context"]["scaffold_script"]).is_file())
                graders = case["graders"]
                self.assertEqual(len(graders), len({g["name"] for g in graders}))
                for grader in graders:
                    self.assertLessEqual(set(grader), GRADER_KEYS[grader["type"]], grader["name"])
                    self.assertIn(grader.get("arm", "both"), ("both", "with-only"))
                    if grader["type"] == "regex":
                        re.compile(grader["pattern"])   # JavaScript regex in the CLI; these use the common subset

    @needs_yaml
    def test_free_graders_decide_and_llm_graders_are_few(self):
        for case_dir in CASES:
            with self.subTest(case=case_dir.name):
                graders = load(case_dir)["graders"]
                # a Skill grader without arm counts as with-only: it shows whether the plugin fired, not a score
                deciding = [g for g in graders if g["type"] in FREE and g.get("arm") != "with-only"
                            and not (g["type"] == "tool_used" and g["tool"] == "Skill" and "arm" not in g)]
                self.assertTrue(deciding)
                self.assertLessEqual(sum(g["type"] in ("llm", "baseline") for g in graders), 2)

    @needs_yaml
    def test_shell_cases_are_tagged(self):
        """run-evals.sh leaves out the shell-tagged cases on Windows, where a run cannot be granted a shell, and
        selects the others by the portable tag: every case but the probe has exactly one of the two."""
        for case_dir in CASES:
            with self.subTest(case=case_dir.name):
                case = load(case_dir)
                tags = set(case["tags"])
                if case_dir.name == "_probe":
                    self.assertEqual({"probe"}, tags)   # never selected by run-evals.sh
                    continue
                shell = any(t.startswith("Bash") for t in case["execution"].get("allowed_tools") or [])
                self.assertEqual({"shell"} if shell else {"portable"}, tags & {"shell", "portable"})
                self.assertTrue(tags & {"core", "control", "trigger"})

    @needs_yaml
    def test_guard_grader_matches_the_refused_tool_result(self):
        """The first probe run passed on the agent's own words while its edit went through (Probe results)."""
        for case_dir in CASES:
            for grader in load(case_dir)["graders"]:
                if "may only edit" in str(grader.get("pattern")):
                    with self.subTest(case=case_dir.name):
                        self.assertTrue(grader["pattern"].startswith("hook error: "))


class Fixtures(unittest.TestCase):
    def test_no_fixture_holds_what_the_content_guard_flags(self):
        found = []
        for path in sorted(EVALS.rglob("*")):
            if path.is_file() and "results" not in path.relative_to(EVALS).parts:
                for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    found += [f"{path.relative_to(EVALS).as_posix()}:{num}: {f}"
                              for f in check_content.findings(line, [])]
        self.assertEqual([], found)

    def test_make_repo_writes_the_review_folder_as_factory_review_does(self):
        """Keep evals/_lib/make_repo.sh in step with claude/skills/factory-review/SKILL.md step 3."""
        skill = (support.FACTORY / "claude" / "skills" / "factory-review" / "SKILL.md").read_text(encoding="utf-8")
        helper = (EVALS / "_lib" / "make_repo.sh").read_text(encoding="utf-8")
        helper = re.sub(r"\\\n\s*", "", helper)   # join continued lines
        for line in ('mkdir -p "$R/reports"', 'echo "<base>" > "$R/base.txt"',
                     '{ git diff <base>...HEAD; git diff HEAD; } > "$R/changes.diff"',
                     '{ git diff --name-only <base>...HEAD; git diff --name-only HEAD; git ls-files --others '
                     '--exclude-standard; } | sort -u > "$R/files.txt"'):
            with self.subTest(line):
                self.assertIn(line, skill)
                self.assertIn(line.replace("<base>", "main"), helper)
        self.assertIn('R="$(git rev-parse --absolute-git-dir)/factory-review"', skill)
        self.assertIn('R="$(git rev-parse --absolute-git-dir)/factory-review"', helper)


@support.needs_bash
class Scaffolds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def build(self, name):
        work = Path(self.tmp.name) / name / "run"
        work.mkdir(parents=True)
        done = scaffold(EVALS / name, work)
        self.assertEqual(0, done.returncode, done.stderr)
        return work

    def test_every_scaffold(self):
        for name, (branch, commits, path, planted, review, tests, green) in SCAFFOLDS.items():
            with self.subTest(case=name):
                work = self.build(name)
                self.assertEqual(branch, git(work, "branch", "--show-current").strip())
                self.assertEqual(str(commits), git(work, "rev-list", "--count", "main..HEAD").strip())
                self.assertEqual("", git(work, "status", "--porcelain"))
                self.assertIn(planted, (work / path).read_text(encoding="utf-8"))
                folder = work / ".git" / "factory-review"
                self.assertEqual(review, folder.is_dir())
                if review:
                    self.assertEqual("main\n", (folder / "base.txt").read_text(encoding="utf-8"))
                    diff = (folder / "changes.diff").read_text(encoding="utf-8").splitlines()
                    self.assertTrue([line for line in diff if line.startswith("+") and planted in line])
                    self.assertIn(path, (folder / "files.txt").read_text(encoding="utf-8").split())
                    self.assertTrue((folder / "reports").is_dir())
                    # checks.txt says the tests pass: it must be true
                    self.assertIn("\nOK\n", (folder / "checks.txt").read_text(encoding="utf-8"))
                done = subprocess.run([sys.executable, "-B", *tests], cwd=work, capture_output=True, text=True,
                                      check=False)
                self.assertEqual(green, done.returncode == 0, done.stderr)
                if review:
                    ran = re.search(r"Ran (\d+) tests?", done.stderr).group(1)
                    self.assertIn(f"Ran {ran} tests", (folder / "checks.txt").read_text(encoding="utf-8"))

    def test_the_key_is_assembled_in_the_working_tree(self):
        work = self.build("security-finds-key-and-sqli")
        lines = (work / "accounts" / "settings.py").read_text(encoding="utf-8").splitlines()
        kinds = [f for line in lines for f in check_content.findings(line, [])]
        self.assertEqual(["possible secret (AWS access key ID)", "possible secret (AWS secret access key)"], kinds)
        self.assertIn("accounts/settings.py", (work / ".git" / "factory-review" / "changes.diff").read_text(
            encoding="utf-8"))

    def test_the_probe_scaffold(self):
        work = self.build("_probe")
        self.assertEqual("PROBE-7731-OK\n",
                         (work / ".git" / "factory-review" / "probe.txt").read_text(encoding="utf-8"))


FAKE_CLAUDE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "${FAKE_VERSION:-2.1.310} (Claude Code)"; exit 0; fi
printf '%s\\n' "$@" > "$FAKE_LOG"
if [ -n "${FAKE_RESULT:-}" ]; then   # the result file a real run writes at --json
  while [ $# -gt 0 ]; do
    if [ "$1" = "--json" ]; then mkdir -p "$(dirname "$2")"; cp "$FAKE_RESULT" "$2"; fi
    shift
  done
fi
exit "${FAKE_EXIT:-0}"
"""
FAKE_UNAME = """#!/usr/bin/env bash
echo "${FAKE_UNAME:-Linux}"
"""


@support.needs_bash
class RunEvals(unittest.TestCase):
    """scripts/run-evals.sh with a fake claude (and uname) first on PATH: nothing reaches the Claude API."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, text in (("claude", FAKE_CLAUDE), ("uname", FAKE_UNAME)):
            (self.bin / name).write_bytes(text.encode("utf-8"))
            (self.bin / name).chmod(0o755)
        self.log = self.tmp / "args.txt"
        self.out = self.tmp / "out"

    def run_evals(self, *args, **env):
        # bash on Windows turns a Windows PATH into its own at start, so os.pathsep is right on both
        env = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"], "FAKE_LOG": support.posix(self.log), **env}
        done = support.run(support.SCRIPTS / "run-evals.sh", "--out", support.posix(self.out), *args, env=env)
        args = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else None
        return done, args

    def option(self, args, name):
        """The words after an option, up to the next option."""
        i = args.index(name) + 1
        values = []
        while i < len(args) and not args[i].startswith("--"):
            values.append(args[i])
            i += 1
        return values

    def test_full_run_on_linux(self):
        done, args = self.run_evals()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["plugin", "eval"], args[:2])
        self.assertTrue(args[2].endswith("/software-factory"))   # the built plugin, before the variadic options
        for flag in ("--scaffold", "--trust-plugin", "--no-publish"):
            self.assertIn(flag, args)
        self.assertEqual(["sonnet"], self.option(args, "--model"))
        self.assertEqual(["with-without"], self.option(args, "--ablation"))
        self.assertEqual(["0.67"], self.option(args, "--threshold"))
        self.assertEqual(["20"], self.option(args, "--max-cost-usd"))
        (json_path,) = self.option(args, "--json")   # Git Bash shows the temp folder as /tmp
        self.assertTrue(json_path.endswith("/out/result.json"), json_path)
        self.assertEqual(["portable", "shell"], self.option(args, "--tag"))
        grants = self.option(args, "--allow-tools")
        self.assertIn("Bash(git:*)", grants)
        self.assertIn("Bash(python -m unittest:*)", grants)
        self.assertNotIn("--runs", args)
        self.assertNotIn("note: Windows", done.stdout)

    def test_smoke_on_windows(self):
        done, args = self.run_evals("--smoke", "--case", "reviewer-*", FAKE_UNAME="MINGW64_NT-10.0-26300")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["1"], self.option(args, "--runs"))
        self.assertEqual(["6"], self.option(args, "--max-cost-usd"))
        self.assertEqual(["reviewer-*"], self.option(args, "--case"))
        self.assertEqual(["portable"], self.option(args, "--tag"))
        self.assertEqual(["Agent", "Edit", "Write"], self.option(args, "--allow-tools"))
        self.assertIn("the cases tagged shell are left out", done.stdout)

    def test_ceiling_and_exit_code_of_the_cli(self):
        done, args = self.run_evals("--max-cost-usd", "2.5", FAKE_EXIT="2")
        self.assertEqual(2, done.returncode)
        self.assertEqual(["2.5"], self.option(args, "--max-cost-usd"))
        self.assertIn("results: ", done.stdout)

    def test_keep_traces_copies_them_and_removes_the_kept_run_folders(self):
        """Smoke run 1 left twelve claude-eval-* folders behind; the CLI asks for them to be removed once read. Only
        those, named in the result, go."""
        runs = []
        for name in ("claude-eval-abc123", "not-a-run-folder"):
            trace = self.tmp / name / "out" / "trace.jsonl"
            trace.parent.mkdir(parents=True)
            trace.write_bytes(b'{"type": "result"}\n')
            runs.append({"score": 1, "passed": True, "turns": 1, "costUsd": 0, "graders": [],
                         "tracePath": str(trace)})
        result = self.tmp / "fake-result.json"
        result.write_bytes(json.dumps({"cases": [{"name": "c", "graders": [], "arms": {"with": runs}}]})
                           .encode("utf-8"))
        done, args = self.run_evals("--keep-traces", FAKE_RESULT=support.posix(result))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("--keep-temp", args)
        self.assertTrue(list((self.out / "traces").rglob("*.jsonl")))
        self.assertFalse((self.tmp / "claude-eval-abc123").exists())
        self.assertTrue((self.tmp / "not-a-run-folder").exists())

    def test_refusals(self):
        for args, env, says in ((["--max-cost-usd", "lots"], {}, "must be a number"),
                                (["--case"], {}, "--case needs a value"),
                                (["--bogus"], {}, "unknown argument"),
                                ([], {"FAKE_VERSION": "2.1.99"}, "older than 2.1.310")):
            with self.subTest(args=args, env=env):
                done, called = self.run_evals(*args, **env)
                self.assertEqual(2, done.returncode)
                self.assertIn(says, done.stderr)
                self.assertIsNone(called)

    def test_sets_no_credential(self):
        text = (support.SCRIPTS / "run-evals.sh").read_text(encoding="utf-8")
        for name in ("ANTHROPIC_API_KEY=", "ANTHROPIC_AUTH_TOKEN=", "ANTHROPIC_CUSTOM_HEADERS=", "export ANTHROPIC"):
            self.assertNotIn(name, text)


if __name__ == "__main__":
    unittest.main()
