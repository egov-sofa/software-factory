"""Tests of scripts/claude_federation.py: the rules it builds, how it reads the OIDC subject, the preview, and
--apply against a fake Admin API client (no network, no Anthropic SDK needed).

Run: python3 -m unittest discover -s scripts/tests
"""
import contextlib
import functools
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "claude_federation.py"
sys.path.insert(0, str(SCRIPT.parent))
import claude_federation as fed  # noqa: E402  (after the sys.path line above)

ARGS = ["--repo", "egov-sofa/software-factory", "--service-account", "svac_123", "--workspace", "wrkspc_456"]
PREFIX = "repo:egov-sofa@1/software-factory@2"
OWNER_ID = "1"


class Rules(unittest.TestCase):
    def test_review_rule_matches_pull_requests_of_the_repository_only(self):
        (rule,) = fed.build_rules(fed.parse_args(ARGS), PREFIX, OWNER_ID)
        self.assertEqual("ANTHROPIC_FEDERATION_RULE_ID", rule["variable"])
        p = rule["payload"]
        self.assertEqual("software-factory-pr-review", p["name"])
        self.assertEqual(PREFIX + ":pull_request", p["match"]["subject_prefix"])
        self.assertEqual("https://api.anthropic.com", p["match"]["audience"])
        # owner pinned by name and numeric ID, the event named; no ref claim (pull requests use refs/pull/<n>/merge)
        self.assertEqual({"repository_owner": "egov-sofa", "repository_owner_id": OWNER_ID,
                          "event_name": "pull_request"}, p["match"]["claims"])
        self.assertEqual({"type": "service_account", "service_account_id": "svac_123"}, p["target"])
        self.assertEqual(("wrkspc_456", "workspace:developer", 600),
                         (p["workspace_id"], p["oauth_scope"], p["token_lifetime_seconds"]))

    def test_mention_rule_is_pinned_to_main_and_issue_comment(self):
        args = fed.parse_args(ARGS + ["--mention", "--mention-workflow-ref", "x/y/.github/workflows/z.yml@refs/heads/main"])
        review, mention = fed.build_rules(args, PREFIX, OWNER_ID)
        p = mention["payload"]
        self.assertEqual("ANTHROPIC_MENTION_FEDERATION_RULE_ID", mention["variable"])
        self.assertEqual(PREFIX + ":ref:refs/heads/main", p["match"]["subject_prefix"])
        self.assertEqual({"repository_owner": "egov-sofa", "repository_owner_id": OWNER_ID,
                          "event_name": "issue_comment",
                          "job_workflow_ref": "x/y/.github/workflows/z.yml@refs/heads/main"}, p["match"]["claims"])
        self.assertNotEqual(review["payload"]["name"], p["name"])

    def test_review_rule_can_be_pinned_to_the_reusable_workflow(self):
        ref = "egov-sofa/software-factory/.github/workflows/reusable-claude-review.yml@refs/tags/v1"
        (rule,) = fed.build_rules(fed.parse_args(ARGS + ["--review-workflow-ref", ref]), PREFIX, OWNER_ID)
        self.assertEqual({"repository_owner": "egov-sofa", "repository_owner_id": OWNER_ID, "event_name": "pull_request",
                          "job_workflow_ref": ref}, rule["payload"]["match"]["claims"])

    def test_preview_explains_an_unpinned_review_rule(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(0, fed.main(ARGS + ["--sub-prefix", PREFIX, "--owner-id", OWNER_ID]))
        self.assertIn("--review-workflow-ref", err.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            fed.main(ARGS + ["--sub-prefix", PREFIX, "--owner-id", OWNER_ID, "--review-workflow-ref", "o/r/.github/workflows/w.yml@refs/tags/v1"])
        self.assertNotIn("--review-workflow-ref", err.getvalue())

    def test_rule_prefix_renames_the_rules(self):
        (rule,) = fed.build_rules(fed.parse_args(ARGS + ["--rule-prefix", "factory"]), PREFIX, OWNER_ID)
        self.assertEqual("factory-pr-review", rule["payload"]["name"])

    def test_bad_arguments_are_refused(self):
        for bad in (["--repo", "no-slash"], ["--service-account", "wrkspc_1"], ["--workspace", "svac_1"],
                    ["--token-lifetime", "5"], ["--owner-id", "egov-sofa"]):
            with self.subTest(bad=bad), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ex:
                fed.parse_args(ARGS + bad)
            self.assertEqual(2, ex.exception.code)


class Defaults(unittest.TestCase):
    def test_service_account_and_workspace_come_from_the_environment(self):
        env = {"FACTORY_CLAUDE_SERVICE_ACCOUNT": "svac_env", "FACTORY_CLAUDE_WORKSPACE": "wrkspc_env"}
        with mock.patch.dict(os.environ, env):
            args = fed.parse_args(["--repo", "o/r"])
        self.assertEqual(("svac_env", "wrkspc_env"), (args.service_account, args.workspace))

    def test_an_argument_wins_over_the_environment(self):
        with mock.patch.dict(os.environ, {"FACTORY_CLAUDE_SERVICE_ACCOUNT": "svac_env"}):
            self.assertEqual("svac_123", fed.parse_args(ARGS).service_account)

    def test_missing_service_account_names_the_variable(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("FACTORY_CLAUDE_")}
        err = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit):
            fed.parse_args(["--repo", "o/r", "--workspace", "wrkspc_1"])
        self.assertIn("FACTORY_CLAUDE_SERVICE_ACCOUNT", err.getvalue())


class Variables(unittest.TestCase):
    VALUES = [("ANTHROPIC_FEDERATION_RULE_ID", "fdrl_1"), ("ANTHROPIC_ORGANIZATION_ID", "org-uuid"),
              ("CLAUDE_REVIEW_ENABLED", "true")]

    @staticmethod
    def gh(fail_on=None, secrets="", secret_list_fails=False):
        """A fake subprocess.run for gh: records the calls, fails `variable set` for one name if asked."""
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[1:3] == ["variable", "set"] and cmd[3] == fail_on:
                return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 403")
            if cmd[1:3] == ["secret", "list"]:
                return SimpleNamespace(returncode=1 if secret_list_fails else 0, stdout=secrets, stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return run, calls

    def test_review_is_turned_on_last(self):
        names = [n for n, _ in fed.variable_values({"ANTHROPIC_FEDERATION_RULE_ID": "fdrl_1"}, "org-uuid",
                                                    fed.parse_args(ARGS))]
        self.assertEqual("CLAUDE_REVIEW_ENABLED", names[-1])
        self.assertEqual(5, len(names))

    def test_variables_are_set_in_order_without_a_shell(self):
        run, calls = self.gh()
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                contextlib.redirect_stdout(io.StringIO()):
            fed.set_variables("o/r", self.VALUES, run=run)
        self.assertEqual(["secret", "list"], calls[0][1:3])   # checked before anything is set
        sets = [c for c in calls if c[1:3] == ["variable", "set"]]
        self.assertEqual([n for n, _ in self.VALUES], [c[3] for c in sets])
        self.assertEqual(["gh", "variable", "set", "ANTHROPIC_FEDERATION_RULE_ID", "--repo", "o/r", "--body", "fdrl_1"],
                         sets[0])

    def test_a_failure_stops_before_the_review_is_turned_on(self):
        run, calls = self.gh(fail_on="ANTHROPIC_ORGANIZATION_ID")
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(fed.SetupError, "admin access"):
            fed.set_variables("o/r", self.VALUES, run=run)
        self.assertNotIn("CLAUDE_REVIEW_ENABLED", [c[3] for c in calls if c[1:3] == ["variable", "set"]])

    def test_an_overriding_secret_keeps_the_review_off(self):
        run, calls = self.gh(secrets="CONTENT_DENYLIST\nANTHROPIC_API_KEY\n")
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(fed.SetupError, "ANTHROPIC_API_KEY.*not turned on"):
            fed.set_variables("o/r", self.VALUES, run=run)
        sets = [c[3] for c in calls if c[1:3] == ["variable", "set"]]
        self.assertEqual(["ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_ORGANIZATION_ID"], sets)   # IDs set, switch not

    def test_the_main_command_fails_when_a_secret_keeps_the_review_off(self):
        run, _ = self.gh(secrets="CLAUDE_CODE_OAUTH_TOKEN\n")
        err = io.StringIO()
        with mock.patch.object(fed, "make_client", return_value=FakeAdmin(issuers=[GH_ISSUER])), \
                mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(fed, "set_variables", functools.partial(fed.set_variables, run=run)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(1, fed.main(ARGS + ["--sub-prefix", PREFIX, "--owner-id", OWNER_ID, "--apply",
                                                 "--set-variables"]))
        self.assertIn("gh secret delete", err.getvalue())

    def test_unreadable_secrets_are_a_note_not_an_error(self):
        run, calls = self.gh(secret_list_fails=True)
        err = io.StringIO()
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            fed.set_variables("o/r", self.VALUES, run=run)
        self.assertIn("check by hand", err.getvalue())
        self.assertIn("CLAUDE_REVIEW_ENABLED", [c[3] for c in calls if c[1:3] == ["variable", "set"]])

    def test_apply_with_set_variables_sets_them_instead_of_printing(self):
        out = io.StringIO()
        with mock.patch.object(fed, "make_client", return_value=FakeAdmin(issuers=[GH_ISSUER])), \
                mock.patch.object(fed, "set_variables", return_value=None) as setter, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, fed.main(ARGS + ["--sub-prefix", PREFIX, "--owner-id", OWNER_ID, "--apply",
                                                 "--set-variables"]))
        repo, values = setter.call_args.args
        self.assertEqual("egov-sofa/software-factory", repo)
        self.assertEqual(("CLAUDE_REVIEW_ENABLED", "true"), values[-1])
        self.assertNotIn("gh variable set", out.getvalue())
        self.assertIn("is set up", out.getvalue())

    def test_preview_with_set_variables_says_what_would_be_set(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            fed.main(ARGS + ["--sub-prefix", PREFIX, "--owner-id", OWNER_ID, "--set-variables"])
        self.assertIn("--set-variables then sets these repository variables", out.getvalue())


class Subject(unittest.TestCase):
    def test_immutable_prefix_is_used_as_is(self):
        self.assertEqual((PREFIX, None), fed.sub_prefix_from_api("o/r", {"sub_claim_prefix": PREFIX + ":"}))

    def test_default_format_falls_back_with_a_warning(self):
        prefix, warning = fed.sub_prefix_from_api("o/r", {"use_default": True})
        self.assertEqual("repo:o/r", prefix)
        self.assertIn("--sub-prefix", warning)

    def test_owner_id_is_read_with_gh(self):
        answered = lambda *a, **k: SimpleNamespace(returncode=0, stdout="987654\n", stderr="")  # noqa: E731
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"):
            self.assertEqual("987654", fed.read_owner_id("egov-sofa", run=answered))

    def test_owner_id_that_is_not_a_number_is_refused(self):
        odd = lambda *a, **k: SimpleNamespace(returncode=0, stdout="null\n", stderr="")  # noqa: E731
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                self.assertRaisesRegex(fed.SetupError, "--owner-id"):
            fed.read_owner_id("egov-sofa", run=odd)

    def test_gh_failure_is_reported(self):
        failed = lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404")  # noqa: E731
        with mock.patch.object(fed.shutil, "which", return_value="/usr/bin/gh"), \
                self.assertRaisesRegex(fed.SetupError, "HTTP 404"):
            fed.read_sub_prefix("o/r", run=failed)


class FakeAdmin:
    """Just enough of client.beta.organization for apply()."""

    def __init__(self, issuers=(), rules=()):
        self.created = []
        self.issuers = list(issuers)
        self.rules = list(rules)
        org = SimpleNamespace(
            federation=SimpleNamespace(
                issuers=SimpleNamespace(list=lambda: self.issuers, create=self._create_issuer),
                rules=SimpleNamespace(list=lambda issuer_id: [r for r in self.rules if r.issuer_id == issuer_id],
                                      create=self._create_rule)),
            retrieve=lambda: SimpleNamespace(id="org-uuid"))
        self.beta = SimpleNamespace(organization=org)

    def _create_issuer(self, **kw):
        issuer = SimpleNamespace(id="fdis_new", archived_at=None, **kw)
        self.issuers.append(issuer)
        return issuer

    def _create_rule(self, **kw):
        self.created.append(kw)
        return SimpleNamespace(id=f"fdrl_{len(self.created)}", archived_at=None, **kw)


GH_ISSUER = SimpleNamespace(id="fdis_1", name="github-actions", issuer_url=fed.GITHUB_ISSUER, archived_at=None)


class Apply(unittest.TestCase):
    def run_apply(self, client, extra=()):
        args = fed.parse_args(ARGS + list(extra))
        with contextlib.redirect_stdout(io.StringIO()):
            return fed.apply(client, args, fed.build_rules(args, PREFIX, OWNER_ID))

    def test_creates_rules_on_the_existing_issuer(self):
        client = FakeAdmin(issuers=[GH_ISSUER])
        ids, org_id = self.run_apply(client, ["--mention"])
        self.assertEqual({"ANTHROPIC_FEDERATION_RULE_ID": "fdrl_1", "ANTHROPIC_MENTION_FEDERATION_RULE_ID": "fdrl_2"}, ids)
        self.assertEqual("org-uuid", org_id)
        self.assertTrue(all(c["issuer_id"] == "fdis_1" for c in client.created))

    def test_existing_rule_is_reused_not_duplicated(self):
        old = SimpleNamespace(id="fdrl_old", name="software-factory-pr-review", issuer_id="fdis_1", archived_at=None)
        client = FakeAdmin(issuers=[GH_ISSUER], rules=[old])
        ids, _ = self.run_apply(client)
        self.assertEqual({"ANTHROPIC_FEDERATION_RULE_ID": "fdrl_old"}, ids)
        self.assertEqual([], client.created)

    def test_missing_issuer_is_an_error_unless_asked_to_create(self):
        with self.assertRaisesRegex(fed.SetupError, "--create-issuer"):
            self.run_apply(FakeAdmin())
        client = FakeAdmin()
        self.run_apply(client, ["--create-issuer"])
        self.assertEqual("fdis_new", client.created[0]["issuer_id"])

    def test_api_key_in_the_environment_is_refused(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x", "ANTHROPIC_AUTH_TOKEN": "y"}), \
                self.assertRaisesRegex(fed.SetupError, "unset ANTHROPIC_API_KEY"):
            fed.make_client()

    def test_missing_token_is_explained(self):
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        with mock.patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(fed.SetupError, "org:admin"):
            fed.make_client()


class CommandLine(unittest.TestCase):
    def test_preview_creates_nothing_and_prints_the_variables(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), *ARGS, "--sub-prefix", PREFIX, "--owner-id", "42", "--mention"],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("nothing is created", done.stdout)
        self.assertIn(f'"subject_prefix": "{PREFIX}:pull_request"', done.stdout)
        self.assertIn('"repository_owner_id": "42"', done.stdout)
        self.assertIn("gh variable set ANTHROPIC_MENTION_FEDERATION_RULE_ID --repo egov-sofa/software-factory",
                      done.stdout)
        self.assertIn("gh variable set CLAUDE_REVIEW_ENABLED --repo egov-sofa/software-factory --body true",
                      done.stdout)
        json.loads(done.stdout.split("\n\n", 1)[1].split("\n}\n")[0] + "\n}")   # the first payload is valid JSON


if __name__ == "__main__":
    unittest.main()
