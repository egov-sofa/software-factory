"""Tests of scripts/docs_drift.py, the docs drift check shared with every project.

Local repositories are real git repositories in a temporary folder, with commit dates set by hand. The GitHub API is
replaced by a fake. Run: python3 -m unittest discover -s scripts/tests
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docs_drift.py"
sys.path.insert(0, str(SCRIPT.parent))
import docs_drift  # noqa: E402  (after the sys.path line above)

try:
    import yaml  # noqa: F401
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
needs_yaml = unittest.skipUnless(HAS_YAML, "PyYAML not installed")

DAY = 86400
T0 = 1_700_000_000


class Repo:
    """A throwaway git repository whose commits get the dates we choose."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="docs-drift-test-")
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, when=None):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        if when is not None:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{when} +0000"
        return subprocess.run(["git", "-C", str(self.root), *args], env=env, check=True,
                              capture_output=True, text=True).stdout

    def commit(self, files, when):
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change", when=when)

    def close(self):
        self.tmp.cleanup()


class FakeGitHub:
    """last_change answers from a table {(repo, path): (time, sha)}; unknown repositories cannot be read."""

    def __init__(self, table, readable):
        self.table, self.readable = table, set(readable)

    def last_change(self, repo, path, ref=None):
        if repo not in self.readable:
            return f"cannot read {repo} (404)"
        return self.table.get((repo, path))


DOCS = [{"id": "sad", "title": "System SAD", "path": "docs/sad.md", "review_every_days": 30,
         "sources": [{"path": "docs/sketches/"}, {"path": "src/**/*.py"}]}]


class Manifest(unittest.TestCase):
    def test_a_valid_manifest_passes(self):
        docs_drift.check_manifest({"version": 1, "docs": DOCS})

    def test_errors_name_the_problem(self):
        cases = {
            "version: 1": {"docs": DOCS},
            "non-empty list": {"version": 1, "docs": []},
            "needs 'path'": {"version": 1, "docs": [{"id": "a"}]},
            "used twice": {"version": 1, "docs": [{"id": "a", "path": "x"}, {"id": "a", "path": "y"}]},
            "OWNER/NAME": {"version": 1, "docs": [{"id": "a", "path": "x", "sources": [{"repo": "x", "path": "y"}]}]},
            "inside the repository": {"version": 1, "docs": [{"id": "a", "path": "x", "sources": [{"path": "../y"}]}]},
            "whole number": {"version": 1, "docs": [{"id": "a", "path": "x", "review_every_days": True}]},
        }
        for message, data in cases.items():
            with self.subTest(message), self.assertRaisesRegex(docs_drift.ManifestError, message):
                docs_drift.check_manifest(data)

    @needs_yaml
    def test_yaml_is_parsed(self):
        text = textwrap.dedent("""\
            version: 1
            docs:
              - id: a
                path: docs/a.md
            """)
        self.assertEqual(docs_drift.parse_manifest(text)["docs"][0]["id"], "a")


class Patterns(unittest.TestCase):
    def test_folders_globs_and_files(self):
        self.assertTrue(docs_drift.matches("docs/sketches/", "docs/sketches/a.yaml"))
        self.assertFalse(docs_drift.matches("docs/sketches/", "docs/sketches.md"))
        self.assertTrue(docs_drift.matches("src/**/*.py", "src/a/b/c.py"))
        self.assertTrue(docs_drift.matches("src/**/*.py", "src/c.py"))
        self.assertFalse(docs_drift.matches("src/**/*.py", "tests/c.py"))
        self.assertTrue(docs_drift.matches("README.md", "README.md"))
        self.assertFalse(docs_drift.matches("README.md", "docs/README.md"))

    def test_a_folder_without_its_trailing_slash_still_matches_below_it(self):
        self.assertTrue(docs_drift.matches("src/payments", "src/payments/api.py"))
        self.assertFalse(docs_drift.matches("src/payments", "src/payments-old/api.py"))
        found = docs_drift.pr_findings([{"id": "d", "path": "d.md", "sources": [{"path": "src/payments"}]}],
                                       ["src/payments/api.py"])
        self.assertEqual(found[0]["files"], ["src/payments/api.py"])

    def test_api_path_is_the_part_before_the_wildcard(self):
        self.assertEqual(docs_drift.api_path("apps/cdr/"), "apps/cdr")
        self.assertEqual(docs_drift.api_path("src/**/*.py"), "src")
        self.assertEqual(docs_drift.api_path("a/b.yaml"), "a/b.yaml")


class ScanLocal(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.commit({"src/app/main.py": "1", "docs/sketches/v.yaml": "1"}, T0)
        self.repo.commit({"docs/sad.md": "doc"}, T0 + DAY)

    def state(self, docs=DOCS, now=T0 + 2 * DAY, github=None):
        local = docs_drift.Local(self.repo.root)
        return docs_drift.scan(docs, local=local, github=github, now=now)[0]

    def test_up_to_date_document_is_ok(self):
        self.assertEqual(self.state()["state"], "ok")

    def test_a_newer_source_means_drift_and_names_it(self):
        self.repo.commit({"src/app/main.py": "2"}, T0 + 3 * DAY)
        result = self.state(now=T0 + 4 * DAY)
        self.assertEqual(result["state"], "drift")
        self.assertEqual([n["source"] for n in result["newer"]], ["src/**/*.py"])

    def test_untouched_for_too_long_is_overdue(self):
        self.assertEqual(self.state(now=T0 + 40 * DAY)["state"], "overdue")

    def test_a_missing_document_is_reported(self):
        docs = [{**DOCS[0], "path": "docs/nothing.md"}]
        self.assertEqual(self.state(docs)["state"], "missing")

    def test_another_repository_without_access_is_unknown_not_ok(self):
        docs = [{**DOCS[0], "sources": [{"repo": "org/gitops", "path": "apps/"}]}]
        self.assertEqual(self.state(docs)["state"], "unknown")
        github = FakeGitHub({}, readable=[])
        self.assertEqual(self.state(docs, github=github)["unknown"][0]["reason"], "cannot read org/gitops (404)")

    def test_another_repository_with_a_newer_change_is_drift(self):
        docs = [{**DOCS[0], "sources": [{"repo": "org/gitops", "path": "apps/cdr/"}]}]
        github = FakeGitHub({("org/gitops", "apps/cdr"): (T0 + 5 * DAY, "abc1234")}, readable=["org/gitops"])
        result = self.state(docs, github=github, now=T0 + 6 * DAY)
        self.assertEqual(result["state"], "drift")
        self.assertEqual(result["newer"][0]["source"], "org/gitops:apps/cdr/")


class ScanRegistry(unittest.TestCase):
    """Registry mode: no checkout, every date from the API."""

    def test_dates_of_the_repository_itself_come_from_the_api(self):
        github = FakeGitHub({("org/app", "docs/sad.md"): (T0 + DAY, "d0c"),
                             ("org/app", "docs/sketches"): (T0 + 2 * DAY, "5ce")}, readable=["org/app"])
        docs = [{"id": "sad", "path": "docs/sad.md", "sources": [{"path": "docs/sketches/"}]}]
        result = docs_drift.scan(docs, github=github, repo="org/app", now=T0 + 3 * DAY)[0]
        self.assertEqual(result["state"], "drift")


class PullRequest(unittest.TestCase):
    def test_a_changed_source_without_its_document_is_reported(self):
        found = docs_drift.pr_findings(DOCS, ["src/app/main.py", "README.md"])
        self.assertEqual(found[0]["files"], ["src/app/main.py"])

    def test_changing_the_document_too_is_fine(self):
        self.assertEqual(docs_drift.pr_findings(DOCS, ["src/app/main.py", "docs/sad.md"]), [])

    def test_sources_in_other_repositories_are_ignored(self):
        docs = [{**DOCS[0], "sources": [{"repo": "org/gitops", "path": "src/"}]}]
        self.assertEqual(docs_drift.pr_findings(docs, ["src/a.py"]), [])

    def test_markdown_lists_document_and_files(self):
        text = docs_drift.pr_markdown(docs_drift.pr_findings(DOCS, ["docs/sketches/v.yaml"]))
        self.assertIn("System SAD", text)
        self.assertIn("`docs/sketches/v.yaml`", text)


@needs_yaml
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        manifest = textwrap.dedent("""\
            version: 1
            docs:
              - id: sad
                title: System SAD
                path: docs/sad.md
                sources:
                  - path: src/
            """)
        self.repo.commit({".factory/docs.yml": manifest, "docs/sad.md": "1", "src/a.py": "1"}, T0)
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.commit({"src/a.py": "2"}, T0 + DAY)

    def run_cli(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "DOCS_DRIFT_TOKEN")}
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args, "--root", str(self.repo.root)],
                              capture_output=True, text=True, env=env, check=False)

    def test_validate(self):
        out = self.run_cli("validate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 document", out.stdout)

    def test_pr_reports_and_strict_fails(self):
        self.assertEqual(self.run_cli("pr", "--base", "main").returncode, 0)
        out = self.run_cli("pr", "--base", "main", "--strict")
        self.assertEqual(out.returncode, 1)
        self.assertIn("System SAD", out.stdout)

    def test_scan_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_cli("scan", "--json", f"{tmp}/r.json", "--markdown", f"{tmp}/r.md")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn('"state": "drift"', Path(tmp, "r.json").read_text(encoding="utf-8"))
            self.assertIn("1 drift", Path(tmp, "r.md").read_text(encoding="utf-8"))

    def test_a_broken_manifest_is_a_usage_error(self):
        (self.repo.root / ".factory/docs.yml").write_text("version: 2\n", encoding="utf-8")
        out = self.run_cli("validate")
        self.assertEqual(out.returncode, 2)
        self.assertIn("version: 1", out.stderr)


class Registry(unittest.TestCase):
    def test_tokens_are_picked_per_owner(self):
        tokens = docs_drift.owner_tokens({"DOCS_DRIFT_TOKEN_EGOV_TECH": "a", "DOCS_DRIFT_TOKEN_X": "", "PATH": "/"})
        self.assertEqual(tokens, {"EGOV_TECH": "a"})
        self.assertEqual(docs_drift.owner_key("egov-tech/app"), "EGOV_TECH")

    def test_the_registry_file_is_checked(self):
        self.assertEqual(docs_drift.check_registry({"version": 1, "repos": ["a/b"]}), ["a/b"])
        for bad in ({"repos": ["a/b"]}, {"version": 1, "repos": []}, {"version": 1, "repos": ["ab"]}):
            with self.subTest(bad), self.assertRaises(docs_drift.ManifestError):
                docs_drift.check_registry(bad)

    @needs_yaml
    def test_dashboard_scans_each_repository_and_flags_missing_manifests(self):
        class Fake(FakeGitHub):
            def read_file(self, repo, path, ref=None):
                if repo == "org/app":
                    return "version: 1\ndocs:\n  - id: sad\n    path: docs/sad.md\n    sources:\n      - path: src/\n"
                return None
        github = Fake({("org/app", "docs/sad.md"): (T0, "d0c"), ("org/app", "src"): (T0 + DAY, "5ce")},
                      readable=["org/app"])
        rows = docs_drift.dashboard(["org/app", "org/other"], github, now=T0 + 2 * DAY)
        self.assertEqual([(r["repo"], r["state"]) for r in rows], [("org/app", "drift"), ("org/other", "unknown")])
        text = docs_drift.scan_markdown(rows)
        self.assertIn("| Repository |", text)
        self.assertIn("org/other", text)


class Issue(unittest.TestCase):
    def test_the_issue_follows_the_report(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import docs_drift_issue
        self.assertEqual(docs_drift_issue.plan(["ok", "drift"], None), "open")
        self.assertEqual(docs_drift_issue.plan(["ok", "drift"], "7"), "update")
        self.assertEqual(docs_drift_issue.plan(["ok"], "7"), "close")
        self.assertEqual(docs_drift_issue.plan(["ok"], None), "nothing")


if __name__ == "__main__":
    unittest.main()
