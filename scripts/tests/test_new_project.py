"""Tests of scripts/new-project.sh, run with bash against a temporary copy of the factory with a fake git remote.

The copy sits at <tmp>/ws/test-org/software-factory, so the default workspace (two levels up) is <tmp>/ws, and the
factory repository read from the remote does not depend on the real checkout. Most cases use --no-git to stay fast.
Run: python3 -m unittest discover -s scripts/tests
"""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from support import FACTORY, needs_bash, posix, run
import support

# A factory placeholder; the $ lookbehind keeps GitHub expressions such as ${{ secrets.X }} out of it.
PLACEHOLDER_RE = re.compile(r"(?<!\$)\{\{\s*[A-Z_]+\s*\}\}")
GITHUB_EXPR_RE = re.compile(r"\$\{\{.*?\}\}")
TEMPLATES = ("typescript", "python", "generic")
NAME = "selftest-app"


def fake_factory(tmp, remote):
    """A copy of the factory's scripts and templates at <tmp>/ws/test-org/software-factory; remote None = no remote."""
    home = Path(tmp) / "ws" / "test-org" / "software-factory"
    for part in ("scripts", "templates"):
        shutil.copytree(FACTORY / part, home / part, ignore=shutil.ignore_patterns("__pycache__"))
    support.git(home, "init", "-q")
    if remote:
        support.git(home, "remote", "add", "origin", remote)
    return home


def text_files(root):
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            try:
                yield path, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue


@needs_bash
class Base(unittest.TestCase):
    remote = "https://github.com/test-org/test-factory.git"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = fake_factory(cls.tmp.name, cls.remote)
        cls.ws = cls.home.parent.parent

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "out"
        self.addCleanup(shutil.rmtree, self.ws / "acme", True)

    def new_project(self, *args):
        return run(self.home / "scripts" / "new-project.sh", *args)

    def created(self, *args):
        result = self.new_project(*args)
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        return result


class Options(Base):
    def test_owner_required_without_dir(self):
        result = self.new_project(NAME, "generic", "--no-git")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("--owner", result.stderr)
        self.assertEqual(["test-org"], [p.name for p in self.ws.iterdir()])

    def test_dir_without_owner(self):
        self.created(NAME, "generic", "--dir", posix(self.out), "--no-git")
        self.assertTrue((self.out / NAME / "CLAUDE.md").is_file())

    def test_default_dir_from_owner(self):
        self.created(NAME, "generic", "--owner", "acme", "--no-git")
        self.assertTrue((self.ws / "acme" / NAME / "CLAUDE.md").is_file())

    def test_no_git(self):
        self.created(NAME, "generic", "--dir", posix(self.out), "--no-git")
        self.assertFalse((self.out / NAME / ".git").exists())

    def test_git_repo_and_hooks(self):
        self.created(NAME, "generic", "--dir", posix(self.out))
        project = self.out / NAME
        self.assertTrue((project / ".git").is_dir())
        self.assertEqual("1", support.git(project, "rev-list", "--count", "main").strip())
        self.assertEqual("scripts/hooks", support.git(project, "config", "core.hooksPath").strip())
        self.assertTrue(support.git(project, "ls-files", "-s", "scripts/hooks/pre-commit").startswith("100755 "))

    def test_rejected_arguments(self):
        out = posix(self.out)
        cases = {
            "uppercase name": ["My_App", "generic", "--dir", out],
            "name starts with a digit": ["1app", "generic", "--dir", out],
            "underscore in name": ["app_x", "generic", "--dir", out],
            "unknown template": ["app", "cobol", "--dir", out],
            "shared layer as template": ["app", "_shared", "--dir", out],
            "bad owner": ["app", "generic", "--owner", "bad/owner", "--dir", out],
            "bad --github": ["app", "generic", "--owner", "acme", "--dir", out, "--github", "internal"],
            "--github with --no-git": ["app", "generic", "--owner", "acme", "--dir", out, "--github", "private",
                                       "--no-git"],
            "unknown option": ["app", "generic", "--dir", out, "--bogus"],
        }
        for label, args in cases.items():
            with self.subTest(label):
                result = self.new_project(*args)
                self.assertEqual(1, result.returncode, result.stdout)
                self.assertFalse(self.out.exists())

    def fake_gh(self, body):
        """A `gh` that runs body (sh), first on PATH, so the owner hint does not depend on the real gh or account."""
        bin_dir = Path(tempfile.mkdtemp(dir=self.tmp.name))
        gh = bin_dir / "gh"
        gh.write_bytes(f"#!/bin/sh\n{body}\n".encode("utf-8"))
        gh.chmod(0o755)
        return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

    def test_owner_hint_when_gh_fails(self):
        """gh logged out (it exits non-zero): the --owner error still shows, with exit 1 and no options."""
        env = self.fake_gh("exit 1")
        result = run(self.home / "scripts" / "new-project.sh", NAME, "generic", "--no-git", env=env)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("Choose who owns the project with --owner", result.stderr)
        self.assertNotIn("Options:", result.stderr)
        self.assertEqual(["test-org"], [p.name for p in self.ws.iterdir()])

    def test_owner_hint_lists_gh_accounts(self):
        env = self.fake_gh('case "$2" in user) echo alice ;; user/orgs) printf "acme\\nbeta\\n" ;; esac')
        result = run(self.home / "scripts" / "new-project.sh", NAME, "generic", "--no-git", env=env)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("Options: alice acme beta", result.stderr)

    def test_github_needs_owner_even_with_dir(self):
        result = self.new_project(NAME, "generic", "--dir", posix(self.out), "--github", "private")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("--owner", result.stderr)
        self.assertFalse(self.out.exists())

    def test_existing_target_rejected(self):
        target = self.out / NAME
        target.mkdir(parents=True)
        (target / "keep.txt").write_text("mine\n", encoding="utf-8")
        result = self.new_project(NAME, "generic", "--dir", posix(self.out), "--no-git")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(["keep.txt"], [p.name for p in target.iterdir()])
        self.assertEqual("mine\n", (target / "keep.txt").read_text(encoding="utf-8"))


class FactoryRepo(Base):
    def factory_repo(self, remote):
        if remote:
            support.git(self.home, "remote", "set-url", "origin", remote)
        else:
            support.git(self.home, "remote", "remove", "origin")
            self.addCleanup(support.git, self.home, "remote", "add", "origin", self.remote)
        result = self.created(NAME, "generic", "--dir", posix(self.out), "--no-git")
        return result, (self.out / NAME / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_https_remote(self):
        _, ci = self.factory_repo("https://github.com/test-org/test-factory.git")
        self.assertIn("test-org/test-factory/.github/workflows/", ci)

    def test_ssh_remote(self):
        _, ci = self.factory_repo("git@github.com:other-org/fork.git")
        self.assertIn("other-org/fork/.github/workflows/", ci)
        self.assertNotIn("test-org", ci)

    def test_no_remote_fallback(self):
        result, ci = self.factory_repo(None)
        self.assertIn("YOUR_ORG/software-factory/.github/workflows/", ci)
        self.assertIn("has no git remote", result.stdout)


class Placeholders(Base):
    def test_no_leftovers_per_template(self):
        for template in TEMPLATES:
            with self.subTest(template):
                out = self.out / template
                self.created(NAME, template, "--owner", "acme", "--dir", posix(out), "--no-git")
                project = out / NAME
                for path in project.rglob("*"):
                    self.assertIsNone(PLACEHOLDER_RE.search(path.relative_to(project).as_posix()), path)
                for path, text in text_files(project):
                    match = PLACEHOLDER_RE.search(text)
                    self.assertIsNone(match, f"{path}: {match and match.group(0)}")
                if template == "python":
                    self.assertTrue((project / "src" / NAME.replace("-", "_")).is_dir())
                self.assert_github_expressions_kept(template, project)

    def assert_github_expressions_kept(self, template, project):
        """Every ${{ ... }} expression of the template's workflows is in the project's copy, unchanged."""
        sources = {}
        for layer in ("_shared", template):   # a language template overrides a shared file of the same path
            base = self.home / "templates" / layer
            for path in (base / ".github" / "workflows").glob("*.yml"):
                sources[path.relative_to(base)] = path
        self.assertTrue(sources)
        found = 0
        for rel, source in sources.items():
            expected = GITHUB_EXPR_RE.findall(source.read_text(encoding="utf-8"))
            self.assertEqual(expected, GITHUB_EXPR_RE.findall((project / rel).read_text(encoding="utf-8")), rel)
            found += len(expected)
        self.assertGreater(found, 0)

    def test_documented_placeholders_match_script(self):
        """The placeholders allowed by the pr-review checklist, those new-project.sh fills and those the templates use
        agree: every used one is filled and listed, and every listed one is filled."""
        checklist = (FACTORY / ".claude" / "skills" / "pr-review" / "SKILL.md").read_text(encoding="utf-8")
        allowed = re.search(r"Placeholders are only(.*?);", checklist, re.S)
        self.assertIsNotNone(allowed, "the placeholder rule moved in .claude/skills/pr-review/SKILL.md")
        listed = set(PLACEHOLDER_RE.findall(allowed.group(1)))
        script = (FACTORY / "scripts" / "new-project.sh").read_text(encoding="utf-8")
        filled = set(re.findall(r"s\|(\{\{[A-Z_]+\}\})\|", script))
        used = set()
        for path in (FACTORY / "templates").rglob("*"):
            used |= set(PLACEHOLDER_RE.findall(path.relative_to(FACTORY).as_posix()))
        for _, text in text_files(FACTORY / "templates"):
            used |= set(PLACEHOLDER_RE.findall(text))
        self.assertIn("{{FACTORY_REPO}}", listed)
        self.assertEqual(listed, filled)
        self.assertLessEqual(used, filled)

    def test_no_in_place_sed(self):
        """sed -i without a suffix is GNU-only; BSD sed on macOS reads the next argument as the suffix."""
        script = (FACTORY / "scripts" / "new-project.sh").read_text(encoding="utf-8")
        code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
        self.assertEqual([], [line for line in code if re.search(r"\bsed\b(\s+-\w+)*\s+-i", line)])


if __name__ == "__main__":
    unittest.main()
