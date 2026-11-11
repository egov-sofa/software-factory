"""Tests of scripts/check_content.py, the content guard shared with every project.

Fake secrets are assembled at runtime from two halves, so this file never holds one and the guard's --all run on the
factory stays clean. Run: python3 -m unittest discover -s scripts/tests
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_content.py"
sys.path.insert(0, str(SCRIPT.parent))
import check_content  # noqa: E402  (after the sys.path line above)


def joined(*parts):
    return "".join(parts)


class Findings(unittest.TestCase):
    def check(self, line, deny=()):
        return check_content.findings(line, list(deny))

    def test_secrets_are_found_by_kind_without_their_value(self):
        cases = {
            "private key": joined("-----BEGIN RSA ", "PRIVATE KEY-----"),
            "AWS access key ID": joined("key = AKIA", "ABCDEFGHIJKLMNOP"),
            "GitHub token": joined("ghp", "_", "a" * 36),
            "Anthropic API key": joined("sk-", "ant-", "api03-", "x" * 30),
            "Slack token": joined("xox", "b-1234567890-abcdef"),
            "Google API key": joined("AIza", "B" * 35),
            "Stripe live key": joined("sk", "_live_", "c" * 24),
        }
        for kind, line in cases.items():
            with self.subTest(kind=kind):
                found = self.check(line)
                self.assertEqual([f"possible secret ({kind})"], found)
                self.assertNotIn(line, " ".join(found))

    def test_ordinary_code_is_not_a_secret(self):
        for line in ("api_key = os.environ['API_KEY']", "BEGIN TRANSACTION;", "const sk = 'sk-learn';",
                     "AKIA is the AWS key prefix", "the -----BEGIN PUBLIC KEY----- block"):
            with self.subTest(line=line):
                self.assertEqual([], self.check(line))

    def test_public_ip_and_internal_host(self):
        self.assertEqual(["public IP address 8.8.8.8"], self.check("dns = 8.8.8.8"))  # content-ok
        self.assertEqual([], self.check("bind 10.0.0.1 and 192.168.1.1"))
        self.assertEqual(["internal host name db01.corp"], self.check("connect to db01.corp"))  # content-ok
        self.assertEqual([], self.check("see settings.local.json and db.example.local"))

    def test_marker_skips_built_in_rules_but_never_the_denylist(self):
        deny = re.compile(r"(?<!\w)acme(?!\w)", re.I)
        self.assertEqual([], self.check("dns = 8.8.8.8  content-ok"))  # content-ok
        self.assertEqual(["denylist term 1"], self.check("Acme example  content-ok", [deny]))


class CommandLine(unittest.TestCase):
    """The guard run as a command on a throwaway repository, as the hooks and CI run it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("hello\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore: start")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        subprocess.run(["git", *args], cwd=self.repo, check=True, env=env)

    def guard(self, *args, env=None):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(self.repo), *args],
                              check=False, capture_output=True, text=True, env={**os.environ, **(env or {})})

    def test_staged_secret_is_refused(self):
        (self.repo / "config.py").write_text(joined("TOKEN = 'ghp", "_", "z" * 36, "'\n"))
        self.git("add", "config.py")
        result = self.guard("--staged")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("config.py:1: possible secret (GitHub token)", result.stdout)
        self.assertNotIn("z" * 36, result.stdout)

    def test_diff_checks_lines_and_commit_messages(self):
        self.git("checkout", "-q", "-b", "feature")
        (self.repo / "notes.md").write_text("server is at 8.8.4.4\n")  # content-ok
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "docs: Acme notes")
        result = self.guard("--diff", "main", env={"CONTENT_DENYLIST": "acme"})
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("notes.md:1: public IP address 8.8.4.4", result.stdout)  # content-ok
        self.assertIn("denylist term 1", result.stdout)
        self.assertNotIn("Acme", result.stdout)

    def test_clean_change_passes(self):
        (self.repo / "app.py").write_text("print('hi')\n")
        self.git("add", "-A")
        result = self.guard("--staged")
        self.assertEqual(0, result.returncode, result.stdout)


if __name__ == "__main__":
    unittest.main()
