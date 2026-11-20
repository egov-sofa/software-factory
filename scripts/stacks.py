#!/usr/bin/env python3
"""The factory's stacks, from templates/stacks.toml: one place that says what each template is, how it is built and
which shared workflow its CI calls (docs/plans/2026-11-19-stack-manifest-and-real-selftest.md).

Usage:
  python3 scripts/stacks.py list                       the stacks, one per line
  python3 scripts/stacks.py get <stack> <field>        one field, e.g. lockfile.file or ci.workflow
  python3 scripts/stacks.py commands <stack>           the stack's commands, one per line (what the self-test runs)
  python3 scripts/stacks.py check                      validate the manifest against the templates and workflows
  python3 scripts/stacks.py fixtures [--check] [stack ...]
      Scaffold tests/fixtures/<stack>/ with new-project.sh (the self-test runs the real shared workflows on them);
      --check compares them with a fresh scaffold instead (the lockfile is not compared: it is resolved anew).

Exit code 0 if all is well, 1 if a problem is found, 2 on a usage error. Standard library only, Python 3.11 or later.
"""
import argparse
import filecmp
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("stacks.py needs Python 3.11 or later (tomllib)")
import tomllib  # noqa: E402  (after the version check)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "templates/stacks.toml"
FIXTURES = "tests/fixtures"
REQUIRED = {"description", "tools", "recommend_for", "next_steps", "commands", "ci"}
OPTIONAL = {"lockfile"}
FIXTURE_NAME, FIXTURE_OWNER, FIXTURE_FACTORY = "selftest-app", "example", "example/software-factory"


class Problem(Exception):
    """Something the caller must fix; printed on stderr, exit 1."""


def load(root=ROOT):
    """The stacks as a dict, in manifest order."""
    try:
        with open(Path(root) / MANIFEST, "rb") as f:
            return tomllib.load(f).get("stacks", {})
    except FileNotFoundError:
        raise Problem(f"{MANIFEST} not found") from None
    except tomllib.TOMLDecodeError as ex:
        raise Problem(f"{MANIFEST}: {ex}") from None


def workflow_inputs(path):
    """The input names a reusable workflow declares under on.workflow_call.inputs."""
    names, inside = set(), False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if re.match(r"^    inputs:\s*$", line):
            inside = True
        elif inside and re.match(r"^      ([\w-]+):\s*$", line):
            names.add(re.match(r"^      ([\w-]+):", line).group(1))
        elif inside and line.strip() and not line.startswith("      "):
            inside = False
    return names


def problems(root=ROOT, stacks=None):
    """What is wrong with the manifest, as messages naming the stack and the field."""
    root = Path(root)
    stacks = load(root) if stacks is None else stacks
    found = []
    folders = {p.name for p in (root / "templates").iterdir() if p.is_dir() and not p.name.startswith("_")}
    for name in sorted(folders - set(stacks)):
        found.append(f"templates/{name}/ has no [stacks.{name}] entry in {MANIFEST}")
    for name, stack in stacks.items():
        where = f"[stacks.{name}]"
        if name not in folders:
            found.append(f"{where}: no templates/{name}/ folder")
        for field in sorted(REQUIRED - set(stack)):
            found.append(f"{where}: missing '{field}'")
        for field in sorted(set(stack) - REQUIRED - OPTIONAL):
            found.append(f"{where}: unknown field '{field}'")
        if "commands" in stack and (not isinstance(stack["commands"], list) or not stack["commands"]):
            found.append(f"{where}: 'commands' must be a non-empty list")
        lock = stack.get("lockfile")
        if lock is not None and set(lock) != {"tool", "file", "command"}:
            found.append(f"{where}: 'lockfile' needs exactly tool, file and command")
        ci = stack.get("ci", {})
        workflow = root / ".github" / "workflows" / str(ci.get("workflow", ""))
        if "ci" in stack and not workflow.is_file():
            found.append(f"{where}: ci.workflow '{ci.get('workflow')}' is not a file in .github/workflows/")
        elif "ci" in stack:
            declared = workflow_inputs(workflow)
            for key in sorted(set(ci.get("with", {})) - declared):
                found.append(f"{where}: ci.with '{key}' is not an input of {ci['workflow']}")
    return found


def field(stack, dotted):
    value = stack
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise Problem(f"no field '{dotted}'")
        value = value[part]
    return value


def find_bash():
    """Git Bash on Windows (never WSL's bash in System32), bash elsewhere."""
    bash = os.environ.get("FACTORY_TEST_BASH") or shutil.which("bash")
    if not bash or (os.name == "nt" and Path(bash).resolve().parent.name.lower() == "system32"):
        raise Problem("bash not found (on Windows, Git Bash must be on PATH or set FACTORY_TEST_BASH)")
    return str(Path(bash).resolve())


def scaffold(stack, out, root=ROOT, env=None):
    """Scaffold the fixture project of a stack into out/<FIXTURE_NAME>, from a copy of the factory whose remote is
    FIXTURE_FACTORY, so the files do not depend on whose clone ran it."""
    with tempfile.TemporaryDirectory(prefix="factory-fixture-") as tmp:
        home = Path(tmp) / FIXTURE_OWNER / "software-factory"
        for part in ("scripts", "templates"):
            shutil.copytree(Path(root) / part, home / part, ignore=shutil.ignore_patterns("__pycache__"))
        git = ["git", "-c", "init.defaultBranch=main", "-C", str(home)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "remote", "add", "origin", f"https://github.com/{FIXTURE_FACTORY}.git"], check=True)
        done = subprocess.run([find_bash(), (home / "scripts" / "new-project.sh").as_posix(), FIXTURE_NAME, stack,
                               "--dir", Path(out).as_posix(), "--owner", FIXTURE_OWNER, "--no-git"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, **(env or {})}, check=False)
        if done.returncode != 0:
            raise Problem(f"new-project.sh failed for {stack}: {done.stderr.strip() or done.stdout.strip()}")
    return Path(out) / FIXTURE_NAME


def files(folder):
    return {p.relative_to(folder).as_posix() for p in Path(folder).rglob("*") if p.is_file()}


def same(a, b):
    if filecmp.cmp(a, b, shallow=False):
        return True
    return Path(a).read_bytes().replace(b"\r\n", b"\n") == Path(b).read_bytes().replace(b"\r\n", b"\n")


def compare(fresh, fixture, lockfile):
    """How a committed fixture differs from a fresh scaffold (the lockfile only has to exist)."""
    want, have = files(fresh), files(fixture)
    found = [f"missing {name}" for name in sorted(want - have)]
    found += [f"extra {name}" for name in sorted(have - want) if name != lockfile]
    found += [f"differs {name}" for name in sorted(want & have) if name != lockfile and not same(fresh / name, fixture / name)]
    if lockfile and lockfile not in have:
        found.append(f"missing {lockfile} (run: python scripts/stacks.py fixtures)")
    return found


def fixtures(names, check, root=ROOT, env=None):
    """Write tests/fixtures/<stack>/ for each stack, or (check) the differences from a fresh scaffold."""
    stacks = load(root)
    found = []
    for name in names or list(stacks):
        if name not in stacks:
            raise Problem(f"unknown stack '{name}' (stacks: {', '.join(stacks)})")
        lockfile = (stacks[name].get("lockfile") or {}).get("file")
        target = Path(root) / FIXTURES / name
        with tempfile.TemporaryDirectory(prefix="factory-fresh-") as tmp:
            fresh = scaffold(name, tmp, root, env)
            if check:
                found += [f"{FIXTURES}/{name}: {d}" for d in compare(fresh, target, lockfile)]
            else:
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(fresh, target)
                if lockfile and not (target / lockfile).is_file():
                    found.append(f"{FIXTURES}/{name}: no {lockfile} (is {stacks[name]['lockfile']['tool']} installed and online?)")
    return found


def write_lines(lines):
    """LF line endings on Windows too, so a bash loop reading the output sees no stray carriage return."""
    sys.stdout.buffer.write("".join(f"{line}\n" for line in lines).encode("utf-8"))


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("check")
    g = sub.add_parser("get")
    g.add_argument("stack")
    g.add_argument("field")
    c = sub.add_parser("commands")
    c.add_argument("stack")
    f = sub.add_parser("fixtures")
    f.add_argument("--check", action="store_true")
    f.add_argument("stacks", nargs="*")
    a = p.parse_args(argv)
    try:
        stacks = load()
        if a.command == "list":
            write_lines(stacks)
        elif a.command == "check":
            found = problems(ROOT, stacks)
            if found:
                raise Problem("\n".join(found))
            print(f"{MANIFEST}: {len(stacks)} stack(s), no problems")
        elif a.command in ("get", "commands"):
            if a.stack not in stacks:
                raise Problem(f"unknown stack '{a.stack}' (stacks: {', '.join(stacks)})")
            value = stacks[a.stack]["commands"] if a.command == "commands" else field(stacks[a.stack], a.field)
            write_lines(value if isinstance(value, list) else [value])
        else:
            found = fixtures(a.stacks, a.check)
            if found:
                raise Problem("\n".join(found))
            print("fixtures match a fresh scaffold" if a.check else "fixtures written")
    except Problem as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
