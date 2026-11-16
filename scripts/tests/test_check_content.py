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
            "OpenAI API key": joined("sk-", "proj-", "d" * 40),
            "GitLab token": joined("gl", "pat-", "e" * 20),
            "npm token": joined("np", "m_", "f1" * 18),
            "PyPI token": joined("pypi-", "AgEIcHlwaS5vcmc", "g" * 60),
            "Google OAuth client secret": joined("GOC", "SPX-", "h" * 28),
            "Slack webhook": joined("https://hooks.slack", ".com/services/", "T0123ABCD/B0123ABCD/", "i" * 24),
            "Discord webhook": joined("https://discord", ".com/api/webhooks/", "123456/", "j" * 60),
            "Azure storage key": joined("DefaultEndpointsProtocol=https;Account", "Key=", "k" * 86, "=="),
            "JSON Web Token": joined("Authorization: Bearer ey", "JhbGciOiJIUzI1NiJ9", ".eyJ", "zdWIiOiIxMjM0In0",
                                     ".", "l" * 20),
            "AWS secret access key": joined("aws_secret_", "access_key = ", "Ab1/" * 10),
            "password in a URL": joined("DATABASE_URL=postgres://app:", "S3cr3t-Pw", "@db.example.org/app"),
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

    def test_url_placeholders_are_not_a_password(self):
        for line in ("git clone https://x-access-token:${GITHUB_TOKEN}@github.com/o/r",
                     "postgres://user:$DB_PASSWORD@db.example.org/app", "https://user:<password>@host.example.org",
                     "amqp://guest:password@rabbit.example.org", "https://u:***@example.org",
                     "https://example.org/path?a=b:c@d"):
            with self.subTest(line=line):
                self.assertEqual([], self.check(line))

    def test_utf16_text_is_decoded(self):
        secret = joined("AKIA", "ABCDEFGHIJKLMNOP")
        for data in (("﻿" + secret).encode("utf-16-le"), secret.encode("utf-16-le"),
                     secret.encode("utf-16")):
            with self.subTest(data=data[:4]):
                self.assertEqual(secret, check_content.utf16_text(data).lstrip("﻿"))
        self.assertIsNone(check_content.utf16_text(b"plain ascii text"))
        self.assertIsNone(check_content.utf16_text(bytes(range(256))))

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

    def test_utf16_file_cannot_hide_a_secret(self):
        """Windows tools (PowerShell, regedit) write UTF-16, which puts a NUL between every letter."""
        text = joined("$key = 'AKIA", "ABCDEFGHIJKLMNOP'\r\n")
        (self.repo / "setup.ps1").write_bytes(b"\xff\xfe" + ("# setup\r\n" + text).encode("utf-16-le"))
        self.git("add", "setup.ps1")
        staged = self.guard("--staged")
        self.assertEqual(1, staged.returncode, staged.stdout)
        self.assertIn("setup.ps1:2: possible secret (AWS access key ID)", staged.stdout)
        self.git("commit", "-q", "-m", "chore: setup")
        tracked = self.guard("--all")
        self.assertEqual(1, tracked.returncode, tracked.stdout)
        self.assertIn("possible secret (AWS access key ID)", tracked.stdout)

    def test_clean_change_passes(self):
        (self.repo / "app.py").write_text("print('hi')\n")
        self.git("add", "-A")
        result = self.guard("--staged")
        self.assertEqual(0, result.returncode, result.stdout)


if __name__ == "__main__":
    unittest.main()
