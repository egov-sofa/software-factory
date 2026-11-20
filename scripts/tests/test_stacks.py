"""Tests of templates/stacks.toml and scripts/stacks.py: the manifest is valid, and every other place that names a
stack agrees with it (each failure says which file and line to add or fix).

Run: python3 -m unittest discover -s scripts/tests
"""
import copy
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import support

sys.path.insert(0, str(support.SCRIPTS))
import stacks  # noqa: E402  (after the sys.path line above)

FACTORY = support.FACTORY
STACKS = stacks.load()


def read(*parts):
    return (FACTORY.joinpath(*parts)).read_text(encoding="utf-8")


def with_block(text, uses_line_re):
    """The `with:` inputs right after the `uses:` line matching the regex, as a dict (quotes and comments stripped)."""
    lines = text.splitlines()
    start = next((n for n, line in enumerate(lines) if re.search(uses_line_re, line)), None)
    if start is None:
        return None
    found, n = {}, start + 1
    if n < len(lines) and lines[n].strip() == "with:":
        indent = len(lines[n]) - len(lines[n].lstrip()) + 2
        n += 1
        while n < len(lines) and lines[n].startswith(" " * indent) and ":" in lines[n]:
            key, _, value = lines[n].strip().partition(":")
            found[key] = value.split(" #")[0].strip().strip('"')
            n += 1
    return found


class Manifest(unittest.TestCase):
    def test_the_manifest_is_valid(self):
        self.assertEqual([], stacks.problems())
        self.assertEqual(["typescript", "python", "generic"], list(STACKS))

    def test_each_problem_is_named(self):
        def found(change):
            data = copy.deepcopy(STACKS)
            change(data)
            return stacks.problems(stacks=data)
        cases = {
            "missing 'tools'": lambda d: d["python"].pop("tools"),
            "unknown field 'colour'": lambda d: d["python"].update(colour="blue"),
            "no templates/rust/ folder": lambda d: d.update(rust=copy.deepcopy(d["generic"])),
            "templates/generic/ has no [stacks.generic]": lambda d: d.pop("generic"),
            "ci.workflow 'reusable-rust.yml' is not a file": lambda d: d["generic"]["ci"].update(workflow="reusable-rust.yml"),
            "ci.with 'java-version' is not an input of reusable-node.yml":
                lambda d: d["typescript"]["ci"]["with"].update({"java-version": "21"}),
            "'lockfile' needs exactly tool, file and command": lambda d: d["python"]["lockfile"].pop("command"),
            "'commands' must be a non-empty list": lambda d: d["python"].update(commands=[]),
        }
        for message, change in cases.items():
            with self.subTest(message):
                self.assertTrue(any(message in p for p in found(change)), found(change))


class AgreesWithManifest(unittest.TestCase):
    """Every place that names a stack, checked against the manifest instead of generated from it."""

    def test_each_template_ci_calls_its_workflow_with_its_inputs(self):
        for name, stack in STACKS.items():
            with self.subTest(name):
                text = read("templates", name, ".github", "workflows", "ci.yml")
                workflow = re.escape(stack["ci"]["workflow"])
                inputs = with_block(text, rf"uses: \{{\{{FACTORY_REPO\}}\}}/\.github/workflows/{workflow}@v1\s*$")
                self.assertIsNotNone(inputs, f"templates/{name}/.github/workflows/ci.yml must call "
                                             f"{{{{FACTORY_REPO}}}}/.github/workflows/{stack['ci']['workflow']}@v1")
                self.assertEqual(stack["ci"]["with"], inputs, f"templates/{name}/.github/workflows/ci.yml `with:`")

    def test_new_project_locks_and_prints_next_steps_per_stack(self):
        script = read("scripts", "new-project.sh")
        lock_lines = re.findall(r"^  (\w+)\)\s+lock (.+?) ;;$", script, re.M)
        expected = [(name, f"{s['lockfile']['tool']} {s['lockfile']['file']} {s['lockfile']['command']}")
                    for name, s in STACKS.items() if "lockfile" in s]
        self.assertEqual(expected, [(n, " ".join(rest.split())) for n, rest in lock_lines],
                         "scripts/new-project.sh: the lockfile `case` must have `<stack>) lock <tool> <file> <command> ;;`")
        for name, stack in STACKS.items():
            with self.subTest(name):
                self.assertRegex(script, rf'(?m)^  {name}\)\s+echo "  {re.escape(stack["next_steps"])}" ;;$',
                                 f"scripts/new-project.sh: the next-steps `case` must print `{stack['next_steps']}`")

    def test_selftest_scaffolds_every_stack_and_runs_its_shared_ci(self):
        text = read(".github", "workflows", "factory-selftest.yml")
        matrix = re.search(r"^\s+stack: \[(.*)\]$", text, re.M)
        self.assertIsNotNone(matrix, "factory-selftest.yml: the scaffold job needs `stack: [...]`")
        self.assertEqual(list(STACKS), [s.strip() for s in matrix.group(1).split(",")],
                         "factory-selftest.yml: the scaffold matrix must list the manifest's stacks, in order")
        for name, stack in STACKS.items():
            with self.subTest(name):
                self.assertRegex(text, rf"(?m)^  ci-{name}:$", f"factory-selftest.yml: add a `ci-{name}` job")
                job = text[text.index(f"  ci-{name}:"):]
                inputs = with_block(job, rf"uses: \./\.github/workflows/{re.escape(stack['ci']['workflow'])}\s*$")
                self.assertIsNotNone(inputs, f"factory-selftest.yml: ci-{name} must use ./.github/workflows/"
                                             f"{stack['ci']['workflow']}")
                self.assertEqual({**stack["ci"]["with"], "working-directory": f"tests/fixtures/{name}"}, inputs)

    def test_readme_has_a_row_per_stack(self):
        rows = re.findall(r"^\| `(\w+)` \| (.+?) \| (.+?) \|$", read("README.md"), re.M)
        expected = [(name, s["description"], s["tools"]) for name, s in STACKS.items()]
        self.assertEqual(expected, rows, "README.md Templates table: one row per stack, `| `<stack>` | <description> | "
                                         "<tools> |`, in manifest order")

    def test_factory_new_offers_every_stack(self):
        text = read("claude", "skills", "factory-new", "SKILL.md")
        names = list(STACKS)
        self.assertIn(f"({', '.join(names)})", text, "factory-new SKILL.md description")
        self.assertIn(f"[{'|'.join(names)}]", text, "factory-new SKILL.md argument-hint")
        for name, stack in STACKS.items():
            with self.subTest(name):
                self.assertRegex(text, rf"{re.escape(stack['recommend_for'])} → `{name}`",
                                 f"factory-new SKILL.md: the recommendation must say `{stack['recommend_for']} → {name}`")

    def test_agents_md_lists_every_command(self):
        for name, stack in STACKS.items():
            text = read("templates", name, "AGENTS.md")
            for command in stack["commands"]:
                with self.subTest(stack=name, command=command):
                    self.assertIn(f"`{command}`", text, f"templates/{name}/AGENTS.md must show `{command}`")


@support.needs_bash
class Fixtures(unittest.TestCase):
    def test_committed_fixtures_match_a_fresh_scaffold(self):
        """With fake npm and uv (no network): the lockfile is not compared, every other file is."""
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            for tool, lockfile in (("npm", "package-lock.json"), ("uv", "uv.lock")):
                (bin_dir / tool).write_bytes(f"#!/bin/sh\necho '{{}}' > {lockfile}\n".encode("utf-8"))
                (bin_dir / tool).chmod(0o755)
            env = support.environment(PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
            self.assertEqual([], stacks.fixtures([], check=True, env=env),
                             "run `python scripts/stacks.py fixtures` and commit tests/fixtures/")

    def test_a_changed_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh, fixture = Path(tmp) / "fresh", Path(tmp) / "fixture"
            for folder in (fresh, fixture):
                (folder / "src").mkdir(parents=True)
                (folder / "src" / "a.txt").write_text("same\n")
            (fresh / "README.md").write_text("new\n")
            (fixture / "src" / "a.txt").write_text("changed\n")
            (fixture / "old.txt").write_text("x\n")
            self.assertEqual(["missing README.md", "extra old.txt", "differs src/a.txt"],
                             stacks.compare(fresh, fixture, None))
            self.assertEqual(["missing uv.lock (run: python scripts/stacks.py fixtures)"],
                             stacks.compare(fixture, fixture, "uv.lock"))


if __name__ == "__main__":
    unittest.main()
