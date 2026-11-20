"""Tests of the factory's workflows and actions as shared services: every action pinned by SHA, and the guards of the
Claude review that keep secrets away from fork code.

Run: python3 -m unittest discover -s scripts/tests
"""
import re
import sys
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

    def test_standards_come_from_the_base_commit_never_the_head(self):
        """A pull request must not weaken the standards it is reviewed against."""
        steps = re.split(r"\n      - (?=uses:|name:)", self.text)
        (step,) = [s for s in steps if s.startswith("name: Project standards from the base commit")]
        self.assertIn("BASE_SHA: ${{ github.event.pull_request.base.sha }}", step)
        for head in ("pull_request.head", "github.sha", "HEAD", "github.ref"):
            self.assertNotIn(head, step)
        self.assertIn('git fetch --quiet --no-tags --depth=1 origin "$BASE_SHA"', step)
        self.assertIn('git show "$BASE_SHA:$path" > "$dest/', step)
        self.assertIn('dest="$RUNNER_TEMP/factory-standards"', step)
        for forbidden in ("git checkout", "git switch", "git worktree", "git reset", "actions/checkout"):
            self.assertNotIn(forbidden, step)
        # the only checkout is the pull request's own, as before, and the standards step comes after it
        self.assertEqual(1, self.text.count("actions/checkout@"))
        self.assertLess(self.text.index("actions/checkout@"), self.text.index("Project standards from the base"))
        self.assertIn("${{ runner.temp }}/factory-standards/ holds files", self.text)
        self.assertIn("--add-dir ${{ runner.temp }}/factory-standards", self.text)

    def test_inputs_unchanged(self):
        """@v1 callers: the standards step added no input and removed none."""
        sys.path.insert(0, str(GITHUB.parent / "scripts"))
        import stacks   # noqa: E402  (the reusable workflow input reader)
        self.assertEqual({"checklist", "max-turns", "timeout-minutes", "max-budget-usd", "federation-rule-id",
                          "organization-id", "service-account-id", "workspace-id", "debug"},
                         stacks.workflow_inputs(GITHUB / "workflows" / "reusable-claude-review.yml"))


class ClaudeComments(unittest.TestCase):
    """Text injected into a pull request must not make Claude comment on another one."""

    def test_comment_tool_is_limited_to_the_current_pull_request(self):
        for name, number in (("reusable-claude-review.yml", "github.event.pull_request.number"),
                             ("reusable-claude-mention.yml", "github.event.issue.number")):
            with self.subTest(name):
                text = (GITHUB / "workflows" / name).read_text(encoding="utf-8")
                self.assertNotIn("Bash(gh pr comment:*)", text)
                # with --body-file after the number, the rule for #12 cannot match #123
                self.assertIn(f"Bash(gh pr comment ${{{{ {number} }}}} --body-file:*)", text)
                self.assertIn(f"gh pr comment ${{{{ {number} }}}} --body-file - <<'EOF'", text)


class ClaudeCosts(unittest.TestCase):
    """Every Claude run has a ceiling on time, turns and money, which a caller can change but not forget."""

    def test_budget_turns_and_timeout_are_inputs_and_used(self):
        for name in ("reusable-claude-review.yml", "reusable-claude-mention.yml"):
            with self.subTest(name):
                text = (GITHUB / "workflows" / name).read_text(encoding="utf-8")
                for option in ("max-budget-usd", "max-turns", "timeout-minutes"):
                    self.assertRegex(text, rf"\n      {option}:\n(?:        .*\n)*?        default: \d+\n")
                self.assertIn("--max-budget-usd ${{ inputs.max-budget-usd }}", text)
                self.assertIn("--max-turns ${{ inputs.max-turns }}", text)
                self.assertIn("timeout-minutes: ${{ inputs.timeout-minutes }}", text)


class GenericCI(unittest.TestCase):
    def test_working_directory_is_an_input_that_defaults_to_the_root(self):
        """Added for the self-test's fixture and for projects in a subfolder; existing callers are unchanged."""
        text = (GITHUB / "workflows" / "reusable-generic.yml").read_text(encoding="utf-8")
        lines = text.splitlines()
        start = lines.index("      working-directory:")
        self.assertIn('        default: "."', lines[start + 1:start + 4])
        self.assertIn("working-directory: ${{ inputs.working-directory }}", text)


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
