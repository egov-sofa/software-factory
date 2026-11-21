"""Tests of the factory's workflows and actions as shared services: every action pinned by SHA, and the guards of the
Claude review that keep secrets away from fork code.

Run: python3 -m unittest discover -s scripts/tests
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

import support

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


class FactoryUpdate(unittest.TestCase):
    """The weekly update job: the caller asks for exactly what it needs, and the action runs nothing from the project
    and gives the token only to the step that pushes and calls gh."""

    def setUp(self):
        self.caller = (GITHUB.parent / "templates" / "_shared" / ".github" / "workflows" / "factory-update.yml"
                       ).read_text(encoding="utf-8")
        self.action = (GITHUB / "actions" / "factory-update" / "action.yml").read_text(encoding="utf-8")
        self.steps = re.split(r"\n    - ", self.action.split("\n  steps:\n", 1)[1])

    def run_text(self, step):
        """The run: script of a step (one line or a | block)."""
        lines = step.splitlines()
        start = next((n for n, line in enumerate(lines) if line.startswith("      run:")), None)
        if start is None:
            return ""
        value = lines[start][len("      run:"):].strip()
        if value not in ("|", ">-", ">"):
            return value
        return "\n".join(line for line in lines[start + 1:] if line.startswith("        "))

    def test_caller_permissions_timeout_and_no_secrets(self):
        block = re.search(r"\npermissions:\n((?:  .*\n)+)", self.caller).group(1)
        self.assertEqual(["contents: write", "pull-requests: write", "issues: write"],
                         [line.strip() for line in block.splitlines()])
        self.assertEqual(1, self.caller.count("permissions:"))   # no job-level widening
        self.assertNotIn("secrets.", self.caller)
        self.assertRegex(self.caller, r"\n    timeout-minutes: 10\n")
        self.assertIn("uses: {{FACTORY_REPO}}/.github/actions/factory-update@v1\n", self.caller)
        self.assertIn("workflow_dispatch:", self.caller)
        self.assertRegex(self.caller, r'cron: "\d+ \d+ \* \* 1"')   # Mondays

    def test_caller_runs_one_at_a_time(self):
        """Seen on a real repository: a run seconds after another did not see the issue it had just opened (GitHub
        lists new items late) and opened a second one. Queued runs are a minute apart, long enough."""
        block = re.search(r"\nconcurrency:\n((?:  .*\n)+)", self.caller).group(1)
        self.assertIn("  group: factory-update\n", block)
        self.assertIn("  cancel-in-progress: false\n", block)

    def test_caller_is_a_merged_file(self):
        sys.path.insert(0, str(GITHUB.parent / "scripts"))
        import factory_update   # noqa: E402
        rules = factory_update.parse_kinds((GITHUB.parent / "templates" / "file-kinds.txt").read_text(encoding="utf-8"))
        self.assertEqual("merged", factory_update.kind_of(".github/workflows/factory-update.yml", rules))

    def test_runs_its_own_script_isolated_and_no_expression_in_run(self):
        runs = [self.run_text(step) for step in self.steps]
        scripts = [r for r in runs if "factory_update_job.py" in r]
        self.assertEqual(2, len(scripts))
        for script in scripts:
            self.assertIn('python3 -I "$GITHUB_ACTION_PATH/../../../scripts/factory_update_job.py"', script)
        for run in runs:
            self.assertNotIn("${{", run)   # values reach scripts through env, never pasted into the code
        self.assertNotIn("git commit", self.action)   # the script commits, with hooks off

    def test_token_only_where_it_is_needed(self):
        (checkout,) = [s for s in self.steps if "actions/checkout@" in s]
        self.assertIn("persist-credentials: false", checkout)
        with_token = [s for s in self.steps if "github.token" in s]
        self.assertEqual(1, len(with_token))
        self.assertIn(" publish ", with_token[0])
        self.assertIn("GH_TOKEN: ${{ github.token }}", with_token[0])
        (prepare,) = [s for s in self.steps if " prepare " in s]
        self.assertNotIn("env:", prepare)
        self.assertNotIn("secrets.", self.action)

    def test_skips_without_answers_file(self):
        self.assertIn("if [ -f .factory/answers.yml ]; then", self.action)
        self.assertIn("::notice::no .factory/answers.yml", self.action)

    def test_the_script_commits_with_hooks_off(self):
        script = (GITHUB.parent / "scripts" / "factory_update_job.py").read_text(encoding="utf-8")
        self.assertIn('GIT = ["git", "-c", "core.hooksPath=/dev/null"', script)
        self.assertIn('"commit", "--no-verify"', script)


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


class Evals(unittest.TestCase):
    """The manual Evals job (roadmap I1): it costs money, so it runs only by hand, on main, one at a time, under a
    ceiling, with a federation rule of its own and no stored key."""

    def setUp(self):
        self.text = (GITHUB / "workflows" / "evals.yml").read_text(encoding="utf-8")
        self.steps = re.split(r"\n      - (?=uses:|name:)", self.text)

    def step(self, start):
        (step,) = [s for s in self.steps if s.startswith(start)]
        return step

    def test_by_hand_only_with_its_inputs(self):
        on = self.text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(["workflow_dispatch:"], [line.strip() for line in on.splitlines() if re.match(r"^  \S", line)])
        for name, kind in (("smoke", "boolean"), ("case", "string"), ("max-cost-usd", "number")):
            self.assertRegex(on, rf"\n      {name}:\n(?:        .*\n)*?        type: {kind}\n")

    def test_permissions_timeout_and_concurrency(self):
        self.assertIn("\npermissions:\n  contents: read\n", self.text)
        self.assertIn("    permissions:\n      contents: read\n      id-token: write", self.text)
        self.assertIn("    timeout-minutes: 90\n", self.text)
        self.assertIn("\nconcurrency:\n  group: evals\n  cancel-in-progress: false\n", self.text)
        self.assertNotIn("secrets.", self.text)   # no API key: federation only

    def test_main_and_the_rule_are_checked_before_any_spend(self):
        guard = self.step("name: Only on main, with the evals rule set")
        self.assertIn('if [ "$REF" != refs/heads/main ]; then', guard)
        self.assertIn("RULE: ${{ vars.ANTHROPIC_EVALS_FEDERATION_RULE_ID }}", guard)
        self.assertIn("docs/CLAUDE-SERVICES-AUTH.md", guard)
        self.assertIs(self.steps[1], guard)   # the first step, before the checkout and the install

    def test_federation_with_a_refreshed_token(self):
        run = self.step("name: Run the evals")
        self.assertIn("ANTHROPIC_FEDERATION_RULE_ID: ${{ vars.ANTHROPIC_EVALS_FEDERATION_RULE_ID }}", run)
        for var in ("ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_SERVICE_ACCOUNT_ID"):
            self.assertIn(f"{var}: ${{{{ vars.{var} }}}}", run)
        self.assertIn("audience=https://api.anthropic.com", run)
        self.assertIn("while sleep 240; do fetch_token", run)   # tokens live about ten minutes
        self.assertIn('export ANTHROPIC_IDENTITY_TOKEN_FILE="$token_file"', run)
        self.assertNotIn("ANTHROPIC_API_KEY", self.text)

    @support.needs_bash
    def test_a_failed_refresh_keeps_the_token(self):
        """Review of #35: a failed curl went on to replace a good token with an empty file. The workflow's own
        fetch_token runs here with stand-ins for curl and jq."""
        body = re.search(r"\n( *)fetch_token\(\) \{\n.*?\n\1\}\n", self.step("name: Run the evals"), re.S)
        function = "\n".join(line[len(body.group(1)):] for line in body.group(0).strip("\n").splitlines())
        stand_ins = ('curl() { [ "$FAKE" = fail ] && return 22; [ "$FAKE" = empty ] && { echo "{}"; return 0; }; '
                     'echo \'{"value":"tok-new"}\'; }\n'
                     "jq() { sed -n 's/.*\"value\":\"\\([^\"]*\\)\".*/\\1/p' | grep .; }\n")
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "oidc-token"
            script = Path(tmp) / "t.sh"
            script.write_bytes((stand_ins + function + '\ntoken_file="$1"\nfetch_token\n').encode("utf-8"))
            for fake, code, after in (("fail", 1, "tok-old"), ("empty", 1, "tok-old"), ("ok", 0, "tok-new")):
                with self.subTest(fake=fake):
                    token.write_bytes(b"tok-old")
                    done = support.run(script, support.posix(token), env={"FAKE": fake})
                    self.assertEqual(code, done.returncode, done.stderr)
                    self.assertEqual(after, token.read_text(encoding="utf-8"))

    def test_runs_the_script_with_the_ceiling_and_never_publishes(self):
        run = self.step("name: Run the evals")
        self.assertIn('bash scripts/run-evals.sh "${args[@]}"', run)
        self.assertIn('args+=(--max-cost-usd "$MAX_COST")', run)
        script = (GITHUB.parent / "scripts" / "run-evals.sh").read_text(encoding="utf-8")
        for flag in ("--no-publish", '--max-cost-usd "$max_cost"', "--scaffold", "--trust-plugin"):
            self.assertIn(flag, script)

    def test_inputs_reach_scripts_through_env_only(self):
        for line in self.text.splitlines():
            if "${{ inputs." in line:
                self.assertRegex(line, r"^\s+[A-Z_]+: \$\{\{ inputs\.[\w-]+ \}\}$")

    def test_cli_is_pinned_to_the_version_the_script_needs(self):
        version = re.search(r'CLAUDE_CODE_VERSION: "([\d.]+)"', self.text).group(1)
        script = (GITHUB.parent / "scripts" / "run-evals.sh").read_text(encoding="utf-8")
        self.assertIn(f'CLAUDE_VERSION="{version}"', script)
        self.assertIn('npm install -g "@anthropic-ai/claude-code@$CLAUDE_CODE_VERSION"', self.text)

    def test_the_shell_cases_get_a_sandbox_before_the_run(self):
        """The first Actions run: every run failed with "a shell tool was granted but this machine cannot confine
        it". Claude Code sandboxes Bash on Linux with bubblewrap and socat, and the check fails before any spend."""
        sandbox = self.step("name: Sandbox for the shell cases")
        self.assertIn("apt-get install -y -qq bubblewrap socat", sandbox)
        self.assertIn("kernel.apparmor_restrict_unprivileged_userns=0", sandbox)
        self.assertIn("bwrap ", sandbox)
        names = [s.split("\n", 1)[0] for s in self.steps]
        self.assertLess(names.index("name: Sandbox for the shell cases"), names.index("name: Run the evals"))

    def test_summary_and_results_are_kept(self):
        self.assertIn('python scripts/eval_summary.py "$RUNNER_TEMP/evals/result.json" >> "$GITHUB_STEP_SUMMARY"',
                      self.step("name: Summary"))
        upload = self.step("uses: actions/upload-artifact@")
        self.assertIn("if: always()", upload)
        self.assertIn("retention-days: 30", upload)
        for path in ("result.json", "report.html", "traces/"):
            self.assertIn(f"${{{{ runner.temp }}}}/evals/{path}", upload)

    def test_not_a_release_gate(self):
        release = (GITHUB / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertNotIn("evals", release.lower())


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
