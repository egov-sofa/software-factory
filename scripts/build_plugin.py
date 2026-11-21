#!/usr/bin/env python3
"""Build the factory's agents and skills as a Claude Code plugin, for `claude plugin eval` (roadmap I1).

    python3 scripts/build_plugin.py --out DIR

writes DIR/software-factory/ with .claude-plugin/plugin.json, hooks/hooks.json, agents/, skills/, claude/hooks/,
standards/ and evals/ (without evals/results/). Every {{FACTORY_HOME}} is replaced by the built folder's absolute
path, as install.sh does, so the agents find the standards; a placeholder left anywhere is an error.

A built copy, not a manifest at the repository root: an eval run sees only the plugin folder, and the placeholders must
be filled in. The smallest form of I7's build step; I7 decides how the distributed plugin fills the paths.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "software-factory"
PLACEHOLDER = "{{FACTORY_HOME}}"
# Claude Code does not run the hooks: of a plugin's agents (evals plan, Probe results), so the plugin declares the guard
# once for every tool call; agent_guard.py takes the agent from the input. Same matcher and python fallback as the
# agents' frontmatter.
GUARD_MATCHER = "Edit|Write|NotebookEdit|Bash"
GUARD_COMMAND = ('PY=python3; "$PY" -c "" 2>/dev/null || PY=python; '
                 '"$PY" "${CLAUDE_PLUGIN_ROOT}/claude/hooks/agent_guard.py" --agent-from-input')
TEXT = {".md", ".py", ".sh", ".yaml", ".yml", ".txt", ".json", ".toml", ".cfg", ".ini", ""}


class BuildError(Exception):
    pass


def version(root):
    # releases only: the moving v1 tag would win otherwise
    done = subprocess.run(["git", "-C", str(root), "describe", "--tags", "--always", "--match", "v[0-9]*.[0-9]*.[0-9]*"],
                          capture_output=True, text=True, check=False)
    return done.stdout.strip() or "unknown"


def copy_tree(src, dst, ignore=None):
    if src.is_dir():
        shutil.copytree(src, dst, ignore=ignore)


def render(folder, home):
    """Fill {{FACTORY_HOME}} in every text file; return the files where it was used."""
    used = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PLACEHOLDER in text:
            path.write_bytes(text.replace(PLACEHOLDER, home).encode("utf-8"))
            used.append(path)
    return used


def leftovers(folder):
    found = []
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            try:
                if PLACEHOLDER in path.read_text(encoding="utf-8"):
                    found.append(path)
            except UnicodeDecodeError:
                pass
    return found


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))   # LF on Windows too


def build(out, root=ROOT):
    out = Path(out).resolve()
    plugin = out / NAME
    if plugin.exists():
        shutil.rmtree(plugin)
    plugin.mkdir(parents=True)
    copy_tree(root / "claude" / "agents", plugin / "agents")
    copy_tree(root / "claude" / "skills", plugin / "skills")
    copy_tree(root / "claude" / "hooks", plugin / "claude" / "hooks",
              ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    copy_tree(root / "standards", plugin / "standards")
    # the pipeline skills (factory-build, -review, -ship) record their state with it; standard library only
    state = root / "scripts" / "factory_state.py"
    if state.is_file():
        (plugin / "scripts").mkdir()
        shutil.copy2(state, plugin / "scripts" / "factory_state.py")
    copy_tree(root / "evals", plugin / "evals", ignore=shutil.ignore_patterns("results", "__pycache__"))
    # forward slashes: the path goes into bash commands and Markdown, on Windows too
    render(plugin, plugin.as_posix())
    manifest = {"name": NAME, "version": version(root),
                "description": "Software factory agents and skills (built for evals)",
                "author": {"name": "software-factory"},   # validate --strict warns without one
                "experimental": {"evals": "evals"}}
    write_json(plugin / ".claude-plugin" / "plugin.json", manifest)
    write_json(plugin / "hooks" / "hooks.json", {"hooks": {"PreToolUse": [
        {"matcher": GUARD_MATCHER, "hooks": [{"type": "command", "command": GUARD_COMMAND}]}]}})
    left = leftovers(plugin)
    if left:
        raise BuildError(f"{PLACEHOLDER} left in: " + ", ".join(p.relative_to(plugin).as_posix() for p in left))
    return plugin


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", required=True, help="folder to build into (DIR/software-factory/ is replaced)")
    a = p.parse_args(argv)
    try:
        print(build(a.out).as_posix())
    except BuildError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
