"""Tests of .github/workflows/factory-selftest.yml: it runs the validator and the script tests, with pinned actions.

Run: python3 -m unittest discover -s scripts/tests
"""
import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "factory-selftest.yml"
USES_RE = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$", re.M)


class SelftestWorkflow(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_validator_and_all_script_tests(self):
        runs = [line.strip() for line in self.text.splitlines() if line.strip().startswith("run:")]
        self.assertIn("run: python scripts/validate.py", runs)
        self.assertIn("run: python -m unittest discover -s scripts/tests -v", runs)
        self.assertLess(self.text.index("scripts/validate.py"), self.text.index("unittest discover"))

    def test_shellcheck_covers_the_eval_scripts(self):
        """run-evals.sh is in scripts/*.sh; the scaffolds source the shared helper, which -x follows."""
        (line,) = [line.strip() for line in self.text.splitlines() if "run: shellcheck" in line]
        for part in ("-x", "scripts/*.sh", "evals/_lib/*.sh", "evals/*/scaffold.sh"):
            self.assertIn(f" {part}", line)

    def test_actions_pinned_by_sha(self):
        uses = USES_RE.findall(self.text)
        self.assertTrue(uses)
        for action, comment in uses:
            if action.startswith("./"):
                continue   # this repository's own workflow or action, at the commit being tested
            with self.subTest(action):
                self.assertRegex(action, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
                self.assertRegex(comment, r"#\s*v\d")

    def test_runs_the_real_shared_services(self):
        """The reusable workflows and the content-guard action are exercised from this commit, not copied."""
        for local in ("./.github/workflows/reusable-node.yml", "./.github/workflows/reusable-python.yml",
                      "./.github/workflows/reusable-generic.yml", "./.github/actions/content-guard"):
            with self.subTest(local):
                self.assertIn(f"uses: {local}", self.text)

    def test_scaffolds_are_checked_against_the_renderer(self):
        """After scaffolding, factory_update.py check passes: new-project.sh and the update renderer agree."""
        self.assertIn('"$PY" scripts/factory_update.py check --project "$APP" || [ $? -eq 3 ]', self.text)
        self.assertIn('test -f "$APP/.factory/standards/SECURITY.md"', self.text)
        self.assertLess(self.text.index("bash scripts/new-project.sh"), self.text.index("factory_update.py check"))

    def test_other_systems_outside_pull_requests(self):
        """Linux on every pull request; macOS and Windows on main, weekly and on demand (inside the release gate)."""
        self.assertIn('\'["ubuntu-latest", "macos-latest", "windows-latest"]\'', self.text)
        self.assertIn("schedule:", self.text)
        self.assertIn("workflow_dispatch:", self.text)


if __name__ == "__main__":
    unittest.main()
