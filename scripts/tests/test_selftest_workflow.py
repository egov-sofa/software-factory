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

    def test_actions_pinned_by_sha(self):
        uses = USES_RE.findall(self.text)
        self.assertTrue(uses)
        for action, comment in uses:
            with self.subTest(action):
                self.assertRegex(action, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
                self.assertRegex(comment, r"#\s*v\d")


if __name__ == "__main__":
    unittest.main()
