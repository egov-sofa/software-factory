"""Tests of scripts/factory_update.py: the answers file, the file kinds and marker blocks, render (and its parity with
new-project.sh), update, check and adopt.

Most cases build a throwaway factory, a git repository with a small template tagged v1.0.0 and v1.1.0, render a
project from v1.0.0, change it, and update it. The script runs as a subprocess with the isolated git config of
support.py, so the developer's own git settings (autocrlf, hooks) cannot change the results.
Run: python3 -m unittest discover -s scripts/tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import support
from support import FACTORY, needs_bash, posix

SCRIPT = support.SCRIPTS / "factory_update.py"
sys.path.insert(0, str(support.SCRIPTS))
import factory_update as fu  # noqa: E402  (after the sys.path line above)

KINDS = """# test kinds
managed scripts/check_content.py
managed scripts/hooks/*
managed .factory/standards/*.md
merged .github/workflows/*.yml
merged CLAUDE.md
merged .gitignore
"""


def block(text):
    return f"{fu.MARK_START}\n{text}\n{fu.MARK_END}\n"


CLAUDE = "# Claude\n\nline a\nline b\nline c\nline d\nline e\n"
V1 = {
    ".gitattributes": "* text=auto eol=lf\n",   # as the factory has: git archive gives LF whatever core.autocrlf says
    "templates/file-kinds.txt": KINDS,
    "templates/_shared/CLAUDE.md": CLAUDE,
    "templates/_shared/.gitignore": "node_modules/\n",
    "templates/_shared/.github/workflows/ci.yml": "jobs:\n  ci:\n    uses: {{FACTORY_REPO}}/.github/workflows/ci.yml@v1\n",
    "templates/generic/AGENTS.md": "# {{PROJECT_NAME}}\n\nOwn words.\n\n" + block("Standards v1."),
    "templates/generic/README.md": "# {{PROJECT_NAME}}\n\nv1 readme\n",
    "templates/stacks.toml": "",
    "scripts/check_content.py": "#!/usr/bin/env python3\nprint('guard v1')\n",
    "scripts/hooks/pre-commit": "#!/usr/bin/env bash\necho pre v1\n",
    "standards/RULES.md": "# Rules\n\nv1\n",
}
ANSWERS = {"_src_path": "test-org/test-factory", "_commit": "unknown", "version": "unknown", "template": "generic",
           "project_name": "my-app", "package_name": "my_app", "github_owner": "acme", "year": "2026",
           "onboarded": False, "skip": []}
DAY = 86400
T0 = 1767225600   # 2026-01-01


def git(repo, *args, when=None):
    """git with the isolated config; when (a unix time) sets the author and committer dates."""
    env = support.environment(**({"GIT_AUTHOR_DATE": f"@{when} +0000", "GIT_COMMITTER_DATE": f"@{when} +0000"}
                                 if when else {}))
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, check=False)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout


def write(root, files):
    for rel, text in files.items():
        path = Path(root) / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)


def commit(repo, message, when=None):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message, when=when)


class Base(unittest.TestCase):
    """A factory with v1.0.0 and v1.1.0 (V1 plus the class's CHANGES), and a project rendered from v1.0.0."""
    CHANGES = {}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.factory = self.tmp / "factory"
        self.factory.mkdir()
        git(self.factory, "init", "-q", "-b", "main")
        write(self.factory, V1)
        commit(self.factory, "v1.0.0", when=T0)
        git(self.factory, "tag", "v1.0.0")
        write(self.factory, self.CHANGES)
        commit(self.factory, "v1.1.0", when=T0 + 60 * DAY)
        git(self.factory, "tag", "v1.1.0")
        self.project = self.tmp / "my-app"

    def scaffold(self, ref="v1.0.0", answers=None, when=T0 + 30 * DAY):
        files, _, _ = fu.render(self.factory, ref, {**ANSWERS, **(answers or {})})
        self.project.mkdir()
        write(self.project, files)
        git(self.project, "init", "-q", "-b", "main")
        commit(self.project, "chore: scaffold from software-factory (generic template)", when=when)
        for rel in files:
            if fu.executable(rel):
                git(self.project, "update-index", "--chmod=+x", "--", rel)
        git(self.project, "commit", "-q", "--allow-empty", "-m", "chore: modes")

    def change(self, files, message="project change"):
        write(self.project, files)
        commit(self.project, message)

    def run_script(self, *args, project=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--factory", str(self.factory),
                               *([] if args[0] == "render" else ["--project", str(project or self.project)])],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=support.environment(), cwd=self.tmp, check=False)

    def update(self, *args, code=0):
        done = self.run_script("update", *args)
        self.assertEqual(code, done.returncode, done.stdout + done.stderr)
        return done

    def text(self, rel):
        return (self.project / rel).read_bytes().decode("utf-8")

    def answers(self):
        return fu.parse_answers(self.text(fu.ANSWERS))


class AnswersFile(unittest.TestCase):
    def test_round_trip(self):
        answers = {**ANSWERS, "github_owner": "", "year": "2026", "project_name": "no", "skip": ["a b.txt", "c"],
                   "_commit": "0123abc"}
        text = fu.dump_answers(answers)
        self.assertIn('github_owner: ""\n', text)
        self.assertIn('year: "2026"\n', text)
        self.assertIn('project_name: "no"\n', text)   # YAML would read a plain no as false
        self.assertEqual(answers, fu.parse_answers(text))
        self.assertEqual(ANSWERS, fu.parse_answers(fu.dump_answers(ANSWERS)))

    def test_yaml_subset(self):
        text = ("# c\n_src_path: 'o/r'   # comment\nskip: [x, \"y, z\"]\nyear: \"2026\"\nonboarded: true\n"
                "list:\n  - one\n  - 'two'\n")
        self.assertEqual({"_src_path": "o/r", "skip": ["x", "y, z"], "year": "2026", "onboarded": True,
                          "list": ["one", "two"]}, fu.parse_answers(text))

    def test_values_outside_the_subset_are_refused(self):
        cases = {"nested map": "template: generic\nnested:\n  key: value\n",
                 "flow map": "template: {a: 1}\n", "no colon": "template generic\n",
                 "duplicate": "a: x\na: y\n", "unterminated": 'a: "x\n'}
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaises(fu.Usage) as ctx:
                    fu.parse_answers(text)
                self.assertIn(fu.ANSWERS, str(ctx.exception))
        with self.assertRaises(fu.Usage):
            fu.check_answers({**ANSWERS, "year": True})

    def test_new_project_quoting_rule_matches(self):
        """new-project.sh writes the same scalars; its yaml_value is tested through the parity test, this pins the
        rule both follow."""
        self.assertEqual("acme", fu.yaml_value("acme"))
        self.assertEqual('"0abc"', fu.yaml_value("0abc"))
        self.assertEqual('"True"', fu.yaml_value("True"))
        self.assertEqual('"a\\"b"', fu.yaml_value('a"b'))


class KindsAndBlocks(unittest.TestCase):
    def test_first_rule_wins_and_seeded_is_the_default(self):
        rules = fu.parse_kinds("merged a/*\nmanaged a/b.txt\n# x\n")
        self.assertEqual("merged", fu.kind_of("a/b.txt", rules))
        self.assertEqual("merged", fu.kind_of("a/c/d.txt", rules))   # * matches / too, as bash [[ == ]] does
        self.assertEqual("seeded", fu.kind_of("b.txt", rules))
        with self.assertRaises(fu.Usage):
            fu.parse_kinds("owned x\n")

    def test_the_repository_rules(self):
        rules = fu.parse_kinds((FACTORY / fu.KINDS_FILE).read_text(encoding="utf-8"))
        expected = {"scripts/check_content.py": "managed", "scripts/hooks/pre-commit": "managed",
                    ".factory/standards/SECURITY.md": "managed", ".github/workflows/ci.yml": "merged",
                    ".gitignore": "merged", "tsconfig.build.json": "merged", "AGENTS.md": "seeded",
                    ".claude/skills/pr-review/SKILL.md": "seeded", "package.json": "seeded",
                    "scripts/check.sh": "seeded", "src/index.ts": "seeded"}
        self.assertEqual(expected, {rel: fu.kind_of(rel, rules) for rel in expected})

    def test_block_replaced_appended_or_refused(self):
        new = block("new").splitlines()
        self.assertEqual("a\n" + block("new") + "b\n", fu.with_block("a\n" + block("old") + "b\n", new, "F.md"))
        self.assertEqual("a\n\n" + block("new"), fu.with_block("a\n", new, "F.md"))
        broken = {"lone start": f"a\n{fu.MARK_START}\nb\n", "lone end": f"a\n{fu.MARK_END}\n",
                  "reversed": f"{fu.MARK_END}\nx\n{fu.MARK_START}\n", "doubled": block("x") + block("y"),
                  "shared line": f"text {fu.MARK_START}\nx\n{fu.MARK_END}\n"}
        for label, text in broken.items():
            with self.subTest(label):
                with self.assertRaises(fu.Usage) as ctx:
                    fu.with_block(text, new, "docs/F.md")
                self.assertIn("docs/F.md", str(ctx.exception))

    def test_header(self):
        self.assertEqual(f"#!/bin/sh\n# {fu.MANAGED_HEADER}\nx\n".encode(), fu.with_header("a", b"#!/bin/sh\nx\n"))
        self.assertEqual(f"#!/bin/sh\n# {fu.MANAGED_HEADER}\n".encode(), fu.with_header("a", b"#!/bin/sh"))
        self.assertEqual(f"# {fu.MANAGED_HEADER}\nx\n".encode(), fu.with_header("a.py", b"x\n"))
        self.assertEqual(f"<!-- {fu.MANAGED_HEADER} -->\n# T\n".encode(), fu.with_header("a.md", b"# T\n"))


class Render(Base):
    def test_render_writes_the_project(self):
        answers = self.tmp / "answers.yml"
        answers.write_text(fu.dump_answers({**ANSWERS, "skip": ["README.md"]}), encoding="utf-8")
        out = self.tmp / "out"
        done = self.run_script("render", "--ref", "v1.0.0", "--answers", str(answers), "--out", str(out))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((out / "README.md").exists())   # skipped
        self.assertTrue((out / "AGENTS.md").read_text(encoding="utf-8").startswith("# my-app\n"))
        self.assertIn("test-org/test-factory/.github", (out / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        self.assertEqual(f"<!-- {fu.MANAGED_HEADER} -->\n# Rules\n\nv1\n",
                         (out / ".factory/standards/RULES.md").read_text(encoding="utf-8"))
        written = fu.parse_answers((out / fu.ANSWERS).read_text(encoding="utf-8"))
        self.assertEqual(("v1.0.0", git(self.factory, "rev-parse", "v1.0.0").strip()),
                         (written["version"], written["_commit"]))

    def test_version_without_file_kinds_has_no_standards_or_headers(self):
        write(self.factory, {"templates/file-kinds.txt": None})
        commit(self.factory, "old layout")
        files, _, _ = fu.render(self.factory, "HEAD", ANSWERS)
        self.assertNotIn(fu.ANSWERS, files)
        self.assertFalse(any(rel.startswith(".factory/") for rel in files))
        self.assertEqual(b"#!/usr/bin/env python3\nprint('guard v1')\n", files["scripts/check_content.py"])


class Managed(Base):
    CHANGES = {"scripts/check_content.py": "#!/usr/bin/env python3\nprint('guard v2')\n",
               "scripts/hooks/commit-msg": "#!/usr/bin/env bash\necho msg v2\n",
               "standards/RULES.md": "# Rules\n\nv2\n"}

    def test_replaced_added_and_local_changes_reported(self):
        self.scaffold()
        self.change({"scripts/hooks/pre-commit": "#!/usr/bin/env bash\necho my own hook\n"})
        done = self.update()
        guard = self.text("scripts/check_content.py")
        self.assertEqual(f"#!/usr/bin/env python3\n# {fu.MANAGED_HEADER}\nprint('guard v2')\n", guard)
        self.assertIn("v2", self.text(".factory/standards/RULES.md"))
        self.assertEqual(f"#!/usr/bin/env bash\n# {fu.MANAGED_HEADER}\necho pre v1\n",
                         self.text("scripts/hooks/pre-commit"))   # the local edit is gone
        self.assertIn("Local changes replaced (managed):\n  scripts/hooks/pre-commit", done.stdout)
        self.assertIn("Replaced (managed):\n  .factory/standards/RULES.md\n  scripts/check_content.py", done.stdout)
        self.assertIn("Added:\n  scripts/hooks/commit-msg", done.stdout)
        for rel in ("scripts/check_content.py", "scripts/hooks/commit-msg"):
            with self.subTest(rel):
                self.assertTrue(git(self.project, "ls-files", "-s", rel).startswith("100755 "))
        answers = self.answers()
        self.assertEqual(("v1.1.0", git(self.factory, "rev-parse", "v1.1.0").strip()),
                         (answers["version"], answers["_commit"]))

    def test_check(self):
        self.scaffold()
        done = self.run_script("check")
        self.assertEqual(3, done.returncode, done.stdout + done.stderr)   # v1.1.0 is newer
        self.assertIn("v1.1.0 is available", done.stdout)
        self.change({"scripts/check_content.py": "#!/usr/bin/env python3\nprint('weakened')\n"})
        done = self.run_script("check")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("scripts/check_content.py", done.stderr)
        git(self.project, "checkout", "-q", "HEAD~1", "--", "scripts/check_content.py")
        commit(self.project, "restore")
        self.update()
        commit(self.project, "chore: update from software-factory v1.1.0")
        done = self.run_script("check")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)


class Merged(Base):
    CHANGES = {"templates/_shared/CLAUDE.md": CLAUDE.replace("line e", "line e (factory)").replace("line c", "C!"),
               "templates/_shared/.gitignore": "node_modules/\ndist/\n",
               "templates/_shared/.github/workflows/new.yml": "on: push\n"}

    def test_clean_merge(self):
        self.scaffold()
        self.change({"CLAUDE.md": CLAUDE.replace("line a", "line a (project)")})
        done = self.update()
        self.assertEqual(CLAUDE.replace("line a", "line a (project)").replace("line e", "line e (factory)")
                         .replace("line c", "C!"), self.text("CLAUDE.md"))
        self.assertIn("Merged:\n  .gitignore\n  CLAUDE.md", done.stdout)
        self.assertEqual("on: push\n", self.text(".github/workflows/new.yml"))

    def test_conflict_leaves_markers_and_exits_1(self):
        self.scaffold()
        self.change({"CLAUDE.md": CLAUDE.replace("line c", "line c (project)")})
        done = self.update(code=1)
        text = self.text("CLAUDE.md")
        self.assertIn("<<<<<<< project\nline c (project)\n=======\nC!\n>>>>>>> factory v1.1.0\n", text)
        self.assertIn("line e (factory)", text)   # the rest merged
        self.assertIn("Conflicts (markers left in the file):\n  CLAUDE.md (1 conflict(s))", done.stdout)

    def test_deleted_here_changed_in_the_factory_is_not_re_added(self):
        self.scaffold()
        self.change({".gitignore": None})
        done = self.update()
        self.assertFalse((self.project / ".gitignore").exists())
        self.assertIn(".gitignore: deleted here, changed in the factory (not re-added)", done.stdout)

    def test_skip_is_never_added(self):
        self.scaffold(answers={"skip": [".github/workflows/new.yml"]})
        self.update()
        self.assertFalse((self.project / ".github/workflows/new.yml").exists())
        self.assertEqual([".github/workflows/new.yml"], self.answers()["skip"])

    def test_crlf_input_comes_out_lf(self):
        self.scaffold()
        self.change({"CLAUDE.md": CLAUDE.replace("\n", "\r\n").replace("line a", "line a (project)").encode()})
        self.update()
        data = (self.project / "CLAUDE.md").read_bytes()
        self.assertNotIn(b"\r", data)
        self.assertIn(b"line a (project)\n", data)

    def test_dirty_tree_is_refused_and_nothing_changes(self):
        self.scaffold()
        write(self.project, {"CLAUDE.md": "uncommitted\n"})
        done = self.update(code=2)
        self.assertIn("working tree has changes", done.stderr)
        self.assertEqual("node_modules/\n", self.text(".gitignore"))

    def test_nothing_is_written_outside_the_project(self):
        self.scaffold()
        before = sorted(p.relative_to(self.tmp).as_posix() for p in self.tmp.rglob("*")
                        if self.project not in p.parents and ".git" not in p.parts)
        self.update()
        after = sorted(p.relative_to(self.tmp).as_posix() for p in self.tmp.rglob("*")
                       if self.project not in p.parents and ".git" not in p.parts)
        self.assertEqual(before, after)
        self.assertEqual("", git(self.factory, "status", "--porcelain"))
        with self.assertRaises(fu.Usage):
            fu.inside(self.project, "../escape.txt")
        with self.assertRaises(fu.Usage):
            fu.inside(self.project, ".git/config")


class Seeded(Base):
    CHANGES = {"templates/generic/README.md": "# {{PROJECT_NAME}}\n\nv2 readme\n",
               "templates/generic/AGENTS.md": "# {{PROJECT_NAME}}\n\nNew words.\n\n" + block("Standards v2.")}

    def test_untouched_except_the_block(self):
        self.scaffold()
        agents = "# my-app\n\nThe project's own words.\n\n" + block("Standards v1.") + "\nAfter the block.\n"
        self.change({"README.md": "mine\r\n", "AGENTS.md": agents})
        done = self.update()
        self.assertEqual(b"mine\r\n", (self.project / "README.md").read_bytes())   # byte-identical
        self.assertEqual(agents.replace("Standards v1.", "Standards v2."), self.text("AGENTS.md"))
        self.assertIn("Standards block updated:\n  AGENTS.md", done.stdout)

    def test_missing_block_is_appended(self):
        self.scaffold()
        self.change({"AGENTS.md": "# Mine\n"})
        self.update()
        self.assertEqual("# Mine\n\n" + block("Standards v2."), self.text("AGENTS.md"))

    def test_broken_marker_refuses_naming_the_file(self):
        self.scaffold()
        self.change({"AGENTS.md": f"# Mine\n{fu.MARK_START}\n"})
        done = self.update(code=2)
        self.assertIn("AGENTS.md has broken software-factory standards markers", done.stderr)
        self.assertEqual("v1.0.0", self.answers()["version"])   # nothing written
        self.assertEqual("", git(self.project, "status", "--porcelain"))


class Removed(Base):
    CHANGES = {"scripts/hooks/pre-commit": None, "templates/_shared/.gitignore": None}

    def test_unchanged_files_are_deleted_changed_ones_kept(self):
        self.scaffold()
        self.change({".gitignore": "node_modules/\nmine/\n"})
        done = self.update()
        self.assertFalse((self.project / "scripts/hooks/pre-commit").exists())
        self.assertTrue((self.project / ".gitignore").exists())
        self.assertIn("Removed:\n  scripts/hooks/pre-commit", done.stdout)
        self.assertIn(".gitignore: changed here, removed from the factory (kept)", done.stdout)


class BaseSelection(Base):
    CHANGES = {"templates/_shared/.gitignore": "node_modules/\ndist/\n"}

    def setUp(self):
        super().setUp()
        write(self.factory, {"templates/_shared/.gitignore": "v2\n"})
        commit(self.factory, "v2.0.0", when=T0 + 90 * DAY)
        git(self.factory, "tag", "v2.0.0")

    def test_default_target_stays_on_the_major(self):
        self.scaffold()
        self.update()
        self.assertEqual("v1.1.0", self.answers()["version"])
        self.assertEqual("node_modules/\ndist/\n", self.text(".gitignore"))

    def test_explicit_to_crosses_the_major(self):
        self.scaffold()
        self.update("--to", "v2.0.0")
        self.assertEqual("v2.0.0", self.answers()["version"])

    def test_unknown_commit_falls_back_to_the_version_tag(self):
        self.scaffold()
        answers = {**self.answers(), "_commit": "f" * 40}
        self.change({fu.ANSWERS: fu.dump_answers(answers)})
        done = self.update()
        self.assertIn("is not in the factory's history; using the tag v1.0.0", done.stderr)
        self.assertEqual("node_modules/\ndist/\n", self.text(".gitignore"))

    def test_unknown_version_needs_to(self):
        self.scaffold()
        self.change({fu.ANSWERS: fu.dump_answers({**self.answers(), "_commit": "unknown", "version": "unknown"})})
        done = self.update(code=2)
        self.assertIn("cannot find the project's factory version", done.stderr)


class Adopt(Base):
    CHANGES = {"templates/_shared/.gitignore": "node_modules/\ndist/\n"}

    def old_project(self, when):
        """A project made before the answers file existed: no .factory/ at all."""
        self.scaffold(when=when)
        shutil.rmtree(self.project / ".factory")
        commit(self.project, "as before")
        git(self.project, "remote", "add", "origin", "git@github.com:acme/my-app.git")

    def test_base_is_the_newest_release_at_or_before_the_scaffold(self):
        for n, (when, expected) in enumerate(((T0 + 30 * DAY, "v1.0.0"), (T0 + 61 * DAY, "v1.1.0"),
                                              (T0, "v1.0.0"))):
            with self.subTest(expected=expected, day=(when - T0) // DAY):
                self.project = self.tmp / f"my-app-{n}"   # a new folder: git's read-only objects resist rmtree
                self.old_project(when)
                done = self.run_script("adopt")
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertIn(f"version: {expected}\n", done.stdout)
                self.assertFalse((self.project / fu.ANSWERS).exists())   # shown, not written
        self.assertIn("github_owner: acme\n", done.stdout)
        self.assertIn("year: \"2026\"\n", done.stdout)
        self.assertIn("template: generic\n", done.stdout)

    def test_yes_writes_then_update_runs_and_a_second_adopt_is_refused(self):
        self.old_project(T0 + 30 * DAY)
        done = self.run_script("adopt", "--set", "github_owner=other", "--yes")
        self.assertEqual(0, done.returncode, done.stderr)
        answers = self.answers()
        self.assertEqual(("other", "v1.0.0", False), (answers["github_owner"], answers["version"],
                                                      answers["onboarded"]))
        self.update()   # the new answers file does not count as a dirty tree
        self.assertEqual("node_modules/\ndist/\n", self.text(".gitignore"))
        self.assertTrue((self.project / ".factory/standards/RULES.md").is_file())
        done = self.run_script("adopt")
        self.assertEqual(2, done.returncode)
        self.assertIn("already exists", done.stderr)

    def test_onboarded(self):
        self.project.mkdir()
        write(self.project, {"AGENTS.md": "# Theirs\n", "CLAUDE.md": "their own\n", "README.md": "theirs\n",
                             "scripts/check_content.py": "print('old copy')\n"})
        git(self.project, "init", "-q", "-b", "main")
        commit(self.project, "their history")
        done = self.run_script("adopt", "--onboarded", "--yes")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        answers = self.answers()
        self.assertEqual(("v1.1.0", True), (answers["version"], answers["onboarded"]))
        self.assertEqual([".github/workflows/ci.yml", ".gitignore"], answers["skip"])
        self.assertIn(fu.MANAGED_HEADER, self.text("scripts/check_content.py"))
        self.assertIn("-print('old copy')", done.stdout)   # the guard's diff is shown
        self.assertTrue((self.project / "scripts/hooks/pre-commit").is_file())
        self.assertEqual("# Theirs\n\n" + block("Standards v1."), self.text("AGENTS.md"))
        self.assertEqual("their own\n", self.text("CLAUDE.md"))
        self.assertEqual("theirs\n", self.text("README.md"))
        self.assertIn("compare them by hand): CLAUDE.md", done.stdout)


def fake_tools(bin_dir):
    """npm and uv that write an empty lockfile: no network, and the lockfile is not compared."""
    bin_dir.mkdir(parents=True)
    for tool, lockfile in (("npm", "package-lock.json"), ("uv", "uv.lock")):
        (bin_dir / tool).write_bytes(f"#!/bin/sh\necho '{{}}' > {lockfile}\n".encode("utf-8"))
        (bin_dir / tool).chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def tree(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in Path(folder).rglob("*")
            if p.is_file() and ".git" not in p.relative_to(folder).parts}


def without_volatile(data):
    return b"\n".join(line for line in data.split(b"\n") if not line.startswith((b"_commit:", b"version:")))


@needs_bash
class Parity(unittest.TestCase):
    """new-project.sh (bash) and render (Python) produce the same project, so an update's base and target are what
    the project was really made from."""
    LOCKFILES = {"package-lock.json", "uv.lock"}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.env = fake_tools(self.tmp / "bin")

    def factory_copy(self, files):
        """A factory at <tmp>/ws/test-org/software-factory with the given files, committed, with a remote."""
        home = self.tmp / "ws" / "test-org" / "software-factory"
        write(home, files)
        git(home, "init", "-q", "-b", "main")
        git(home, "remote", "add", "origin", "https://github.com/test-org/test-factory.git")
        commit(home, "factory")
        return home

    def scaffold(self, home, template):
        out = self.tmp / "out" / template
        done = support.run(home / "scripts" / "new-project.sh", "selftest-app", template, "--owner", "acme",
                           "--dir", posix(out), "--no-git", env=self.env)
        self.assertEqual(0, done.returncode, done.stderr + done.stdout)
        return out / "selftest-app"

    def render(self, factory, ref, answers):
        path = self.tmp / f"answers-{answers['template']}-{ref}.yml"
        path.write_text(fu.dump_answers(answers), encoding="utf-8")
        out = self.tmp / "rendered" / ref / answers["template"]
        done = subprocess.run([sys.executable, str(SCRIPT), "render", "--factory", str(factory), "--ref", ref,
                               "--answers", str(path), "--out", str(out)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=support.environment(), check=False)
        self.assertEqual(0, done.returncode, done.stderr)
        return tree(out)

    def assert_same(self, scaffolded, rendered):
        bash = {rel: data for rel, data in tree(scaffolded).items() if rel not in self.LOCKFILES}
        self.assertEqual(sorted(bash), sorted(rendered))
        for rel in bash:
            with self.subTest(rel):
                a, b = bash[rel], rendered[rel]
                if rel == fu.ANSWERS:
                    a, b = without_volatile(a), without_volatile(b)
                self.assertEqual(a, b)

    def test_head(self):
        """The working tree's scripts, templates and standards, committed in a copy (so uncommitted work counts)."""
        files = {}
        for part in ("scripts", "templates", "standards"):
            for path in (FACTORY / part).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    files[path.relative_to(FACTORY).as_posix()] = path.read_bytes()
        files[".gitattributes"] = (FACTORY / ".gitattributes").read_bytes()
        home = self.factory_copy(files)
        for template in ("typescript", "python", "generic"):
            with self.subTest(template):
                project = self.scaffold(home, template)
                answers = fu.parse_answers((project / fu.ANSWERS).read_text(encoding="utf-8"))
                self.assertEqual(git(home, "rev-parse", "HEAD").strip(), answers["_commit"])
                self.assert_same(project, self.render(home, "HEAD", answers))

    @unittest.skipUnless(fu.commit_of(FACTORY, "v1.2.0"), "the v1.2.0 tag is not in this clone (git fetch --tags)")
    def test_v1_2_0(self):
        """The real v1.2.0 release: its own new-project.sh and render agree, with no standards and no headers."""
        with tempfile.TemporaryDirectory() as tmp:
            fu.export(FACTORY, "v1.2.0", tmp)
            files = tree(tmp)
        files[".gitattributes"] = b"* text=auto eol=lf\n"
        home = self.factory_copy(files)
        year = str(time.localtime().tm_year)
        for template in ("typescript", "python", "generic"):
            with self.subTest(template):
                project = self.scaffold(home, template)
                answers = {**ANSWERS, "template": template, "project_name": "selftest-app",
                           "package_name": "selftest_app", "year": year}
                rendered = self.render(FACTORY, "v1.2.0", answers)
                self.assertFalse(any(rel.startswith(".factory/") for rel in rendered))
                self.assertNotIn(fu.MANAGED_HEADER.encode(), rendered["scripts/check_content.py"])
                self.assert_same(project, rendered)


if __name__ == "__main__":
    unittest.main()
