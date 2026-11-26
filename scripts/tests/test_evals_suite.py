"""Tests of the eval suite under evals/ and of scripts/run-evals.sh, with no Claude call (roadmap I1).

- every case.yaml has the shape Claude Code 2.1.310's strict schema accepts, and a free grader that decides it;
- every scaffold.sh builds its repository as an eval run would (a reduced environment, no network), with the planted
  defect in place and the review folder as /factory-review writes it;
- no fixture file holds what the content guard flags (the planted key is random, made at run time);
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
import eval_summary  # noqa: E402

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
        """run-evals.sh selects cases by tag: portable everywhere; shell where a run can be granted a shell (not on
        Windows); shell-commands where shell commands also run (a nested sandbox: not on GitHub's runners). Every case
        but the probe has exactly one of the three, and a case granted Bash is shell or shell-commands."""
        for case_dir in CASES:
            with self.subTest(case=case_dir.name):
                case = load(case_dir)
                tags = set(case["tags"])
                if case_dir.name == "_probe":
                    self.assertEqual({"probe"}, tags)   # never selected by run-evals.sh
                    continue
                shell = any(t.startswith("Bash") for t in case["execution"].get("allowed_tools") or [])
                kind = tags & {"shell", "shell-commands", "portable"}
                self.assertEqual(1, len(kind), tags)
                self.assertEqual(shell, kind != {"portable"})
                self.assertTrue(tags & {"core", "control", "trigger"})
        # factory-review prepares the review folder with git: its commands must really run
        self.assertIn("shell-commands", load(EVALS / "factory-review-starts-from-request")["tags"])

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
        """Keep evals/_lib/make_repo.sh in step with claude/skills/factory-review/SKILL.md step 3, and both skills with
        each other (factory-build Stage 5 writes the same folder)."""
        skills = {name: (support.FACTORY / "claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                  for name in ("factory-review", "factory-build")}
        helper = (EVALS / "_lib" / "make_repo.sh").read_text(encoding="utf-8")
        helper = re.sub(r"\\\n\s*", "", helper)   # join continued lines
        for line in ('R="$(git rev-parse --absolute-git-dir)/factory-review"',
                     'rm -f "${R:?}/round.diff" "${R:?}/checks.txt" "${R:?}/reports/reviewer.md" '
                     '"${R:?}/reports/security-auditor.md"',
                     'mkdir -p "$R/reports"', 'echo "<base>" > "$R/base.txt"',
                     '{ git diff <base>...HEAD; git diff HEAD; } > "$R/changes.diff"',
                     '{ git diff --name-only <base>...HEAD; git diff --name-only HEAD; git ls-files --others '
                     '--exclude-standard; } | sort -u > "$R/files.txt"'):
            with self.subTest(line):
                for name, skill in skills.items():
                    self.assertIn(line, skill, name)
                self.assertIn(line.replace("<base>", "main"), helper)

    def test_the_cleanup_never_runs_without_r(self):
        """Review of #41: the skills set R in their prose, so a block run in another shell call had R unset and
        `rm -rf "$R/reports"` would have meant /reports. R is set inside the block, and ${R:?} stops the line
        without it."""
        for name in ("factory-review", "factory-build"):
            with self.subTest(skill=name):
                text = (support.FACTORY / "claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertRegex(text, r'```bash\n *R="\$\(git rev-parse --absolute-git-dir\)/factory-review"\n'
                                       r' *rm -f "\$\{R:\?\}/round\.diff"')
        done = subprocess.run([support.BASH, "-c", 'unset R; rm -rf "${R:?}/reports"; echo ran'], capture_output=True,
                              text=True, check=False)
        self.assertNotEqual(0, done.returncode)
        self.assertNotIn("ran", done.stdout)

    def test_the_skills_stop_when_the_review_folder_cannot_be_written(self):
        """Seen in an eval run: the folder could not be written, and the model reviewed the diff itself, without the
        factory's agents or report format. Both skills say to stop and show the error instead."""
        for name in ("factory-review", "factory-build"):
            with self.subTest(skill=name):
                text = (support.FACTORY / "claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                text = " ".join(text.split())
                self.assertIn("**If `R=` or any of these writes fails**, stop: show the user the error", text)
                self.assertIn("do not review the diff yourself instead", text)


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

    def test_a_new_round_leaves_no_stale_input(self):
        """Each round clears the last round's round.diff, reports and checks.txt with fixed paths: a glob such as
        reports/*.md fails under zsh (macOS's default shell) when reports/ is empty, as it is on a first round."""
        for shell in ("bash", "zsh"):
            program = support.BASH if shell == "bash" else shutil.which("zsh")
            with self.subTest(shell=shell):
                if not program:
                    self.skipTest("zsh is not installed")
                work = Path(self.tmp.name) / f"stale-{shell}"
                work.mkdir()
                self.assertEqual(0, scaffold(EVALS / "reviewer-finds-off-by-one", work).returncode)
                folder = Path(git(work, "rev-parse", "--absolute-git-dir").strip()) / "factory-review"
                script = (f'. "{support.posix(EVALS / "_lib" / "make_repo.sh")}"; '
                          f'review_folder "{support.posix(EVALS / "reviewer-finds-off-by-one")}"')
                done = subprocess.run([program, "-c", script], cwd=work, capture_output=True, text=True,
                                      env=support.environment(), check=False)   # reports/ is empty: the first round
                self.assertEqual(0, done.returncode, done.stderr)
                (folder / "round.diff").write_bytes(b"stale\n")
                (folder / "reports" / "reviewer.md").write_bytes(b"stale\n")
                (folder / "reports" / "security-auditor.md").write_bytes(b"stale\n")
                (folder / "reports" / "tester.md").write_bytes(b"Result: PASS\n")   # factory-build Stage 4's
                (folder / "checks.txt").write_bytes(b"stale\n")
                done = subprocess.run([program, "-c", script], cwd=work, capture_output=True, text=True,
                                      env=support.environment(), check=False)
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertFalse((folder / "round.diff").exists())
                # the reviewers' reports go; the tester's, which checks.txt is written from, stays (review of #41)
                self.assertEqual(["tester.md"], sorted(p.name for p in (folder / "reports").iterdir()))
                self.assertNotEqual(b"stale\n", (folder / "checks.txt").read_bytes())

    def test_the_key_is_random_and_made_at_run_time(self):
        """Review of #35: no key-shaped value may be stored in the repository, whole or in parts. Two builds give two
        different keys, each one the content guard flags as a key."""
        settings = []
        for n in range(2):
            work = Path(self.tmp.name) / f"key-{n}"
            work.mkdir()
            done = scaffold(EVALS / "security-finds-key-and-sqli", work)
            self.assertEqual(0, done.returncode, done.stderr)
            text = (work / "accounts" / "settings.py").read_text(encoding="utf-8")
            kinds = [f for line in text.splitlines() for f in check_content.findings(line, [])]
            self.assertEqual(["possible secret (AWS access key ID)", "possible secret (AWS secret access key)"], kinds)
            self.assertIn("accounts/settings.py", (work / ".git" / "factory-review" / "changes.diff").read_text(
                encoding="utf-8"))
            settings.append(text)
        self.assertNotEqual(settings[0], settings[1])

    def test_the_probe_scaffold(self):
        work = self.build("_probe")
        self.assertEqual("PROBE-7731-OK\n",
                         (work / ".git" / "factory-review" / "probe.txt").read_text(encoding="utf-8"))


FAKE_CLAUDE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "${FAKE_VERSION:-2.1.310} (Claude Code)"; exit 0; fi
printf '%s\\n' "$@" > "$FAKE_LOG"
json="" name="" ceiling=""
while [ $# -gt 0 ]; do
  case "$1" in
    --json) json="$2" ;;
    --case) name="$2" ;;
    --max-cost-usd) ceiling="$2" ;;
  esac
  shift
done
if [ -n "${FAKE_CALLS:-}" ]; then echo "claude $name $ceiling" >> "$FAKE_CALLS"; fi
if [ -n "${FAKE_RESULT:-}" ]; then   # the result file a real run writes at --json
  mkdir -p "$(dirname "$json")"; cp "$FAKE_RESULT" "$json"
fi
code=0
if [ -n "${FAKE_COST:-}" ]; then   # a one-case result: it costs FAKE_COST, and fails when its name matches FAKE_BELOW
  score=1 passed=1 delta=0.5 cost="$FAKE_COST" partial='"partial": false'
  case "$name" in ${FAKE_BELOW:-no-such-case}) code=1 score=0.5 passed=0 delta=0 ;; esac
  if awk -v c="$cost" -v m="$ceiling" 'BEGIN { exit !(c > m) }'; then   # the CLI stops at its ceiling
    code=2 cost="$ceiling" partial='"partial": true, "partialReason": "cost_ceiling"'
  fi
  mkdir -p "$(dirname "$json")"
  printf '{"schemaVersion": 1, "claudeVersion": "2.1.310", "startedAt": "t-%s", "durationSeconds": 10, ' \\
    "$name" > "$json"
  printf '"costUsd": %s, %s, "suite": {"threshold": 0.66, "ablation": "with-without"}, ' "$cost" "$partial" >> "$json"
  printf '"cases": [{"name": "%s", "arms": {}, "aggregates": {"score": %s, "passRate": %s, "scoreWithout": 0.5, ' \\
    "$name" "$score" "$passed" >> "$json"
  printf '"delta": %s}}], "aggregates": {"casesTotal": 1, "casesPassed": %s}}\\n' "$delta" "$passed" >> "$json"
fi
exit "${FAKE_EXIT:-$code}"
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

    def test_full_run_on_linux_where_the_sandbox_nests(self):
        """EVALS_NESTED_SANDBOX=yes, as in WSL: every case, and plain Bash for the shell-commands case."""
        done, args = self.run_evals(EVALS_SANDBOX="yes", EVALS_NESTED_SANDBOX="yes")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["plugin", "eval"], args[:2])
        self.assertTrue(args[2].endswith("/software-factory"))   # the built plugin, before the variadic options
        for flag in ("--scaffold", "--trust-plugin", "--no-publish"):
            self.assertIn(flag, args)
        self.assertEqual(["sonnet"], self.option(args, "--model"))
        self.assertEqual(["with-without"], self.option(args, "--ablation"))
        self.assertEqual(["0.66"], self.option(args, "--threshold"))   # two of three passes (0.666…)
        self.assertEqual(["20"], self.option(args, "--max-cost-usd"))
        (json_path,) = self.option(args, "--json")   # Git Bash shows the temp folder as /tmp
        self.assertTrue(json_path.endswith("/out/result.json"), json_path)
        self.assertEqual(["portable", "shell", "shell-commands"], self.option(args, "--tag"))
        grants = self.option(args, "--allow-tools")
        self.assertIn("Bash(git:*)", grants)
        self.assertIn("Bash(python -m unittest:*)", grants)
        self.assertIn("Bash", grants)
        self.assertNotIn("--runs", args)
        # the factory-review case runs, though it fails under plugin eval for now: the note says so
        self.assertIn("known to fail under plugin eval", done.stdout)

    def test_linux_leaves_out_shell_commands_unless_asked(self):
        """GitHub's Ubuntu runners: the run starts, but every shell command fails (smoke run of 2026-11-21). No
        check tells them from WSL, where it works, so the shell-commands cases are opt-in on Linux."""
        for nested in (None, "no", "maybe"):
            with self.subTest(EVALS_NESTED_SANDBOX=nested):
                env = {"EVALS_SANDBOX": "yes", **({"EVALS_NESTED_SANDBOX": nested} if nested else {})}
                done, args = self.run_evals(**env)
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual(["portable", "shell"], self.option(args, "--tag"))
                grants = self.option(args, "--allow-tools")
                self.assertIn("Bash(git:*)", grants)
                self.assertNotIn("Bash", grants)   # plain Bash only for the shell-commands case
                self.assertIn("set EVALS_NESTED_SANDBOX=yes", done.stdout)

    def test_macos_runs_every_case(self):
        """Review of #38: Claude Code sandboxes with Seatbelt on macOS, so the bubblewrap checks do not apply."""
        done, args = self.run_evals(FAKE_UNAME="Darwin", EVALS_SANDBOX="no", EVALS_NESTED_SANDBOX="no")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["portable", "shell", "shell-commands"], self.option(args, "--tag"))
        self.assertIn("Bash", self.option(args, "--allow-tools"))
        self.assertNotIn("note:", done.stdout)

    def test_linux_without_bubblewrap(self):
        """A Bash grant without a sandbox fails every run, portable ones too (the first Actions run)."""
        done, args = self.run_evals(EVALS_SANDBOX="no")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["portable"], self.option(args, "--tag"))
        self.assertEqual(["Agent", "Edit", "Write"], self.option(args, "--allow-tools"))
        self.assertIn("note: no working bubblewrap and socat", done.stdout)

    def test_smoke_on_windows(self):
        done, args = self.run_evals("--smoke", "--case", "reviewer-*", FAKE_UNAME="MINGW64_NT-10.0-26300")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["1"], self.option(args, "--runs"))
        self.assertEqual(["6"], self.option(args, "--max-cost-usd"))
        self.assertEqual(["reviewer-*"], self.option(args, "--case"))
        self.assertEqual(["portable"], self.option(args, "--tag"))
        self.assertEqual(["Agent", "Edit", "Write"], self.option(args, "--allow-tools"))
        self.assertIn("note: Windows: the cases tagged shell or shell-commands are left out", done.stdout)

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
            if name.startswith("claude-eval-"):   # sealed as on Linux: a mode-000 folder in a read-only one
                (trace.parent.parent / "sealed").mkdir()
                (trace.parent.parent / "sealed").chmod(0)
                trace.parent.parent.chmod(0o555)
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

    def one_at_a_time(self, *args, **env):
        """run-evals.sh --one-at-a-time; its claude calls as `claude <case> <ceiling>` (and what EVALS_BEFORE_EACH
        writes to $FAKE_CALLS), the merged result.json or None, and the last call's words."""
        calls = self.tmp / "calls.txt"
        done, last = self.run_evals("--one-at-a-time", *args, FAKE_CALLS=support.posix(calls), **env)
        merged = self.out / "result.json"
        return (done, calls.read_text(encoding="utf-8").splitlines() if calls.exists() else [],
                json.loads(merged.read_text(encoding="utf-8")) if merged.exists() else None, last)

    def test_one_at_a_time_runs_each_case_alone(self):
        """The Evals workflow (2026-11-25): a token refreshed during one long plugin eval was refused as reused, so
        each case is its own plugin eval with the options of a whole run and its own results folder."""
        done, calls, merged, last = self.one_at_a_time(EVALS_SANDBOX="yes", FAKE_COST="0.5")
        self.assertEqual(0, done.returncode, done.stderr)
        names = ["factory-build-not-started-by-request", "planner-writes-testable-criteria",
                 "reviewer-approves-clean-change", "reviewer-finds-off-by-one", "security-finds-key-and-sqli",
                 "security-passes-clean-change", "tester-reports-instead-of-fixing-src"]   # no probe, no shell-commands
        self.assertEqual([line.split()[1] for line in calls], names)
        # one ceiling for the whole run: each case gets what the ones before it left
        self.assertEqual(["20.00", "19.50", "19.00", "18.50", "18.00", "17.50", "17.00"],
                         [line.split()[2] for line in calls])
        self.assertEqual(["tester-reports-instead-of-fixing-src"], self.option(last, "--case"))
        self.assertTrue(last[2].endswith("/software-factory"))
        for flag in ("--scaffold", "--trust-plugin", "--no-publish"):
            self.assertIn(flag, last)
        self.assertEqual(["with-without"], self.option(last, "--ablation"))
        self.assertEqual(["portable", "shell"], self.option(last, "--tag"))
        self.assertIn("Bash(git:*)", self.option(last, "--allow-tools"))
        dest = "/out/cases/tester-reports-instead-of-fixing-src"
        (json_path,) = self.option(last, "--json")
        self.assertTrue(json_path.endswith(f"{dest}/result.json"), json_path)
        self.assertTrue(self.option(last, "--report")[0].endswith(f"{dest}/report.html"))
        self.assertTrue(self.option(last, "--output-dir")[0].endswith(dest))
        for name in names:
            self.assertTrue((self.out / "cases" / name / "result.json").is_file(), name)
        self.assertEqual(names, [case["name"] for case in merged["cases"]])

    def test_one_at_a_time_keeps_the_tag_rules_and_the_glob(self):
        for args, names in (([], ["factory-build-not-started-by-request", "planner-writes-testable-criteria",
                                  "reviewer-approves-clean-change", "reviewer-finds-off-by-one",
                                  "security-finds-key-and-sqli", "security-passes-clean-change"]),
                            (["--case", "security-*"], ["security-finds-key-and-sqli",
                                                        "security-passes-clean-change"])):
            with self.subTest(args=args):
                done, calls, _, last = self.one_at_a_time(*args, FAKE_UNAME="MINGW64_NT-10.0-26300", FAKE_COST="0")
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual(names, [line.split()[1] for line in calls])   # on Windows only the portable ones
                self.assertEqual(["portable"], self.option(last, "--tag"))
                (self.tmp / "calls.txt").unlink()
        done, calls, _, _ = self.one_at_a_time("--case", "nothing-*", FAKE_UNAME="MINGW64_NT-10.0-26300")
        self.assertEqual(2, done.returncode)
        self.assertIn("no case has the tags portable and matches nothing-*", done.stderr)
        self.assertEqual([], calls)

    def test_one_at_a_time_runs_the_before_each_command_first(self):
        """The workflow fetches a fresh OIDC token there: each one is accepted once and lives 300 s."""
        done, calls, _, _ = self.one_at_a_time("--case", "security-*", EVALS_SANDBOX="no", FAKE_COST="0.1",
                                               EVALS_BEFORE_EACH='echo before >> "$FAKE_CALLS"')
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["before", "claude security-finds-key-and-sqli 20.00",
                          "before", "claude security-passes-clean-change 19.90"], calls)

    def test_one_at_a_time_stops_when_the_before_each_command_fails(self):
        mark = support.posix(self.tmp / "fetched-once")
        first_only = f'[ ! -f "{mark}" ] && touch "{mark}"'   # succeeds once, then fails
        for before, ran in (("exit 3", []), (first_only, ["reviewer-approves-clean-change"])):
            with self.subTest(before=before):
                done, calls, merged, _ = self.one_at_a_time("--case", "reviewer-*", EVALS_SANDBOX="no",
                                                            FAKE_COST="0.1", EVALS_BEFORE_EACH=before)
                self.assertEqual(2, done.returncode)
                self.assertIn("error: EVALS_BEFORE_EACH failed before the case", done.stderr)
                self.assertEqual(ran, [line.split()[1] for line in calls])
                self.assertEqual(ran, [case["name"] for case in merged["cases"]])
                self.assertEqual((True, "interrupted"), (merged["partial"], merged["partialReason"]))
                (self.tmp / "calls.txt").unlink(missing_ok=True)

    def test_one_at_a_time_stops_at_the_ceiling(self):
        # 2.00 - 3 x 0.60 leaves 0.20: the fourth case starts with it, and the CLI stops there (exit 2);
        # 1.23 - 2 x 0.60 leaves 0.03, less than one cheap run: the third case never starts
        for ceiling, ceilings, spent in (("2", ["2.00", "1.40", "0.80", "0.20"], 2.0),
                                         ("1.23", ["1.23", "0.63"], 1.2)):
            with self.subTest(ceiling=ceiling):
                done, calls, merged, _ = self.one_at_a_time("--max-cost-usd", ceiling, FAKE_COST="0.6",
                                                            FAKE_UNAME="MINGW64_NT-10.0-26300")
                self.assertEqual(2, done.returncode, done.stderr)
                self.assertEqual(ceilings, [line.split()[2] for line in calls])
                self.assertEqual((True, "cost_ceiling"), (merged["partial"], merged["partialReason"]))
                self.assertEqual(len(ceilings), merged["aggregates"]["casesTotal"])
                self.assertAlmostEqual(spent, merged["costUsd"])
                self.assertIn(f"the cost ceiling of ${ceiling} is reached", done.stdout)
                (self.tmp / "calls.txt").unlink()

    def test_one_at_a_time_merges_the_results_and_exits_with_the_worst(self):
        done, _, merged, _ = self.one_at_a_time(FAKE_COST="0.25", FAKE_BELOW="reviewer-*",
                                                FAKE_UNAME="MINGW64_NT-10.0-26300")
        self.assertEqual(1, done.returncode, done.stderr)   # two cases below the threshold, none at the ceiling
        self.assertEqual("t-factory-build-not-started-by-request", merged["startedAt"])   # from the first case
        self.assertEqual((1, "2.1.310", 0.66), (merged["schemaVersion"], merged["claudeVersion"],
                                                merged["suite"]["threshold"]))
        self.assertEqual((1.5, 60, False), (merged["costUsd"], merged["durationSeconds"], merged["partial"]))
        self.assertNotIn("partialReason", merged)
        totals = merged["aggregates"]
        self.assertEqual((6, 4), (totals["casesTotal"], totals["casesPassed"]))
        self.assertAlmostEqual(5 / 6, totals["overallScore"])   # four at 1.0 and two at 0.5
        self.assertAlmostEqual(4 / 6, totals["overallPassRate"])
        self.assertAlmostEqual(2 / 6, totals["meanDelta"])
        # the Evals job's summary reads the merged result unchanged
        self.assertIn("Cases passed: 4 of 6; overall score 0.83, mean difference +0.33",
                      eval_summary.summary(merged))

    def test_one_at_a_time_stops_when_a_case_writes_no_result(self):
        """Without its result the cost of a case is unknown, so the next one's budget would be a guess."""
        done, calls, merged, _ = self.one_at_a_time(FAKE_UNAME="MINGW64_NT-10.0-26300", FAKE_EXIT="1")
        self.assertEqual(2, done.returncode)
        self.assertIn("wrote no result.json (claude exited 1)", done.stderr)
        self.assertEqual(1, len(calls))
        self.assertEqual(([], "interrupted"), (merged["cases"], merged["partialReason"]))

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
