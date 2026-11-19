"""Tests of the factory's workflows and actions as shared services: every action pinned by SHA, and the guards of the
Claude review that keep secrets away from fork code.

Run: python3 -m unittest discover -s scripts/tests
"""
import re
import unittest
from pathlib import Path

GITHUB = Path(__file__).resolve().parents[2] / ".github"
USES_RE = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$", re.M)


def workflow_files():
    return sorted([*GITHUB.glob("workflows/*.yml"), *GITHUB.glob("actions/*/action.yml")])


class AllWorkflows(unittest.TestCase):
    def test_actions_pinned_by_sha(self):
        files = workflow_files()
        self.assertTrue(files)
        for path in files:
            for action, comment in USES_RE.findall(path.read_text(encoding="utf-8")):
                if action.startswith("./"):
                    continue   # a workflow or action of this repository, at the caller's commit
                with self.subTest(file=path.name, action=action):
                    self.assertRegex(action, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
                    self.assertRegex(comment, r"#\s*v\d")


class ClaudeReview(unittest.TestCase):
    def setUp(self):
        self.text = (GITHUB / "workflows" / "reusable-claude-review.yml").read_text(encoding="utf-8")

    def test_runs_on_pull_request_only(self):
        # pull_request_target carries a pull request too, with the base repository's secrets and OIDC token
        self.assertIn("if: github.event_name != 'pull_request'\n", self.text)
        self.assertNotIn("!github.event.pull_request", self.text)

    def test_skips_fork_pull_requests(self):
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", self.text)

    def test_checkout_keeps_no_token(self):
        steps = re.split(r"\n\s*- (?=uses:|name:|if:|run:)", self.text)
        (checkout,) = [s for s in steps if "actions/checkout@" in s]
        self.assertIn("persist-credentials: false", checkout)


class PythonCI(unittest.TestCase):
    """Existing @v1 callers keep pip; uv is chosen by the caller, never switched on by a file in the repository."""

    def setUp(self):
        self.text = (GITHUB / "workflows" / "reusable-python.yml").read_text(encoding="utf-8")

    def test_pip_is_the_default(self):
        lines = self.text.splitlines()
        start = lines.index("      package-manager:")   # the input, under workflow_call.inputs
        self.assertIn("        default: pip", lines[start + 1:start + 4])

    def test_uv_is_not_chosen_by_the_lockfile_alone(self):
        self.assertNotIn("if [ -f uv.lock ]; then echo \"uv=true\"", self.text)

    def test_template_opts_in_to_uv(self):
        template = GITHUB.parent / "templates" / "python" / ".github" / "workflows" / "ci.yml"
        self.assertIn("package-manager: uv", template.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
