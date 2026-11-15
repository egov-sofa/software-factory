"""Tests of scripts/claude_federation.py: the rules it builds, how it reads the OIDC subject, the preview, and
--apply against a fake Admin API client (no network, no Anthropic SDK needed).

Run: python3 -m unittest discover -s scripts/tests
"""
import contextlib
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


class Rules(unittest.TestCase):
    def test_review_rule_matches_pull_requests_of_the_repository_only(self):
        (rule,) = fed.build_rules(fed.parse_args(ARGS), PREFIX)
        self.assertEqual("ANTHROPIC_FEDERATION_RULE_ID", rule["variable"])
        p = rule["payload"]
        self.assertEqual("software-factory-pr-review", p["name"])
        self.assertEqual(PREFIX + ":pull_request", p["match"]["subject_prefix"])
        self.assertEqual("https://api.anthropic.com", p["match"]["audience"])
        self.assertEqual({"repository_owner": "egov-sofa"}, p["match"]["claims"])   # no ref claim
        self.assertEqual({"type": "service_account", "service_account_id": "svac_123"}, p["target"])
        self.assertEqual(("wrkspc_456", "workspace:developer", 600),
                         (p["workspace_id"], p["oauth_scope"], p["token_lifetime_seconds"]))

    def test_mention_rule_is_pinned_to_main_and_issue_comment(self):
        args = fed.parse_args(ARGS + ["--mention", "--mention-workflow-ref", "x/y/.github/workflows/z.yml@refs/heads/main"])
        review, mention = fed.build_rules(args, PREFIX)
        p = mention["payload"]
        self.assertEqual("ANTHROPIC_MENTION_FEDERATION_RULE_ID", mention["variable"])
        self.assertEqual(PREFIX + ":ref:refs/heads/main", p["match"]["subject_prefix"])
        self.assertEqual({"repository_owner": "egov-sofa", "event_name": "issue_comment",
                          "job_workflow_ref": "x/y/.github/workflows/z.yml@refs/heads/main"}, p["match"]["claims"])
        self.assertNotEqual(review["payload"]["name"], p["name"])

    def test_rule_prefix_renames_the_rules(self):
        (rule,) = fed.build_rules(fed.parse_args(ARGS + ["--rule-prefix", "factory"]), PREFIX)
        self.assertEqual("factory-pr-review", rule["payload"]["name"])

    def test_bad_arguments_are_refused(self):
        for bad in (["--repo", "no-slash"], ["--service-account", "wrkspc_1"], ["--workspace", "svac_1"],
                    ["--token-lifetime", "5"]):
            with self.subTest(bad=bad), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ex:
                fed.parse_args(ARGS + bad)
            self.assertEqual(2, ex.exception.code)


class Subject(unittest.TestCase):
    def test_immutable_prefix_is_used_as_is(self):
        self.assertEqual((PREFIX, None), fed.sub_prefix_from_api("o/r", {"sub_claim_prefix": PREFIX + ":"}))

    def test_default_format_falls_back_with_a_warning(self):
        prefix, warning = fed.sub_prefix_from_api("o/r", {"use_default": True})
        self.assertEqual("repo:o/r", prefix)
        self.assertIn("--sub-prefix", warning)

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
            return fed.apply(client, args, fed.build_rules(args, PREFIX))

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
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), *ARGS, "--sub-prefix", PREFIX, "--mention"],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("nothing is created", done.stdout)
        self.assertIn(f'"subject_prefix": "{PREFIX}:pull_request"', done.stdout)
        self.assertIn("gh variable set ANTHROPIC_MENTION_FEDERATION_RULE_ID --repo egov-sofa/software-factory",
                      done.stdout)
        self.assertIn("gh variable set CLAUDE_REVIEW_ENABLED --repo egov-sofa/software-factory --body true",
                      done.stdout)
        json.loads(done.stdout.split("\n\n", 1)[1].split("\n}\n")[0] + "\n}")   # the first payload is valid JSON


if __name__ == "__main__":
    unittest.main()
