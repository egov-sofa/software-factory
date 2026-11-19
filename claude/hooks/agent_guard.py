#!/usr/bin/env python3
"""Claude Code PreToolUse hook for the software factory's agents: refuse the tool calls an agent must not make.

Each factory agent that may edit files or run commands declares this hook in its frontmatter, so it runs only while
that agent runs (docs/plans/2026-11-19-enforce-agent-limits-with-hooks.md):

    python3 agent_guard.py <agent>      reads the tool call as JSON on stdin

- Edit, Write and NotebookEdit: the file must match the agent's paths (none for the implementer, which edits freely).
- Bash: git commands that change history or the branch are refused; the conductor does all git work.

A refused call prints a deny decision with a reason the agent can act on; an allowed one prints nothing. The reviewer
and security-auditor need no hook: they have no tool that writes.

Exit code 0 in both cases (the decision is in the JSON), 2 on a usage error.
"""
import fnmatch
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

# Paths each agent may edit, relative to the project root. A pattern without "/" matches at the root only; "**/" at
# the start also matches at the root. None: no path limit.
TEST_PATHS = ("tests/**", "test/**", "__tests__/**", "**/__tests__/**", "**/*.test.*", "**/*.spec.*",
              "**/test_*.py", "**/*_test.*", "**/testdata/**", "**/fixtures/**")
PATHS = {
    "planner": ("docs/plans/**",),
    "tester": TEST_PATHS,
    "docs-writer": ("**/README*", "**/CHANGELOG*", "*.md", ".env.example", "docs/**"),
    "implementer": None,
}
WHAT = {
    "planner": "plans in docs/plans/",
    "tester": "test files",
    "docs-writer": "documentation (READMEs, CHANGELOGs, docs/, root *.md, .env.example)",
}

# git subcommands that change history, the index or the branch. Read-only ones (status, diff, log, show, blame,
# ls-files, rev-parse) are not listed and stay allowed.
GIT_WRITES = {"push", "commit", "reset", "checkout", "switch", "rebase", "merge", "cherry-pick", "revert", "am",
              "stash", "tag", "clean", "pull", "apply", "rm", "mv", "add", "update-ref", "filter-branch", "worktree"}
GIT_BRANCH_WRITES = {"-d", "-D", "-m", "-M", "-c", "-C", "-f", "--delete", "--move", "--copy", "--force",
                     "--set-upstream-to", "-u", "--unset-upstream"}
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo", "nice", "xargs"}
SHELLS = {"bash", "sh", "zsh", "dash"}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def project_root(cwd):
    """The git work tree the agent is in, else its cwd."""
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             check=False, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def inside(path, folder):
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:   # another drive on Windows
        return False


def matches(rel, pattern):
    if "/" not in pattern:
        return "/" not in rel and fnmatch.fnmatchcase(rel, pattern)
    return fnmatch.fnmatchcase(rel, pattern) or (pattern.startswith("**/") and fnmatch.fnmatchcase(rel, pattern[3:]))


def check_path(agent, file_path, cwd):
    """None if the agent may edit file_path, else the reason it may not."""
    allowed = PATHS[agent]
    if allowed is None:
        return None
    full = os.path.realpath(os.path.join(cwd, file_path))   # resolves .., symlinks; keeps an absolute path as is
    if inside(full, os.path.realpath(tempfile.gettempdir())):
        return None
    root = os.path.realpath(project_root(cwd))
    if not inside(full, root):
        return f"{agent} may only edit {WHAT[agent]} inside the project; {file_path} is outside it."
    rel = Path(os.path.relpath(full, root)).as_posix()
    if any(matches(rel, p) for p in allowed):
        return None
    return (f"{agent} may only edit {WHAT[agent]} ({', '.join(allowed)}); {rel} is not one. "
            "Report what needs to change there instead of editing it.")


def segments(command):
    """The simple commands in a shell command line, as token lists (split on ; && || | & and newlines)."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    current = []
    for token in lexer:
        if token and set(token) <= set("();<>|&"):
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def git_write(tokens):
    """The git subcommand in tokens if it changes history or the branch, else None."""
    i = 0
    while i < len(tokens) and ("=" in tokens[i] and not tokens[i].startswith("-") or tokens[i] in WRAPPERS):
        i += 1   # VAR=value, env, command, sudo, ...
    if i >= len(tokens):
        return None
    name = Path(tokens[i]).name.lower()
    if name in SHELLS and "-c" in tokens[i + 1:]:
        script = tokens[tokens.index("-c", i + 1) + 1:tokens.index("-c", i + 1) + 2]
        return git_write_in(script[0]) if script else None
    if name not in ("git", "git.exe"):
        return None
    i += 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in GIT_OPTIONS_WITH_VALUE:
            i += 2
        elif tok.startswith("-"):
            i += 1   # --no-pager, -p, --git-dir=..., -c=... spellings
        else:
            break
    if i >= len(tokens):
        return None
    sub, args = tokens[i], tokens[i + 1:]
    if sub in GIT_WRITES:
        return sub
    if sub == "branch" and any(a in GIT_BRANCH_WRITES or a.split("=")[0] in GIT_BRANCH_WRITES for a in args):
        return "branch " + next(a for a in args if a in GIT_BRANCH_WRITES or a.split("=")[0] in GIT_BRANCH_WRITES)
    if sub == "restore" and any(a in ("--staged", "-S") for a in args):
        return "restore --staged"
    return None


def git_write_in(command):
    for tokens in segments(command):
        found = git_write(tokens)
        if found:
            return found
    return None


def check_bash(agent, command):
    """None if the command is allowed, else the reason it is not."""
    try:
        found = git_write_in(command)
    except ValueError:   # unbalanced quotes: cannot tell what runs
        if "git" in command:
            return f"{agent} ran a command the guard could not parse, and it mentions git; split it into simple commands."
        return None
    if found:
        return (f"{agent} may not run `git {found}`: the factory's conductor does all git work (commits, branches, "
                "pushes). Leave the change in the working tree and report it.")
    return None


def main(argv):
    if len(argv) != 1 or argv[0] not in PATHS:
        print(f"usage: agent_guard.py <{'|'.join(PATHS)}>", file=sys.stderr)
        return 2
    agent = argv[0]
    try:
        call = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        deny(f"the factory's guard for {agent} could not read this tool call, so it is refused.")
        return 0
    tool, args = call.get("tool_name", ""), call.get("tool_input") or {}
    cwd = call.get("cwd") or os.getcwd()
    reason = None
    if tool in ("Edit", "Write", "NotebookEdit"):
        path = args.get("file_path") or args.get("notebook_path") or ""
        reason = check_path(agent, path, cwd) if path else None
    elif tool == "Bash":
        reason = check_bash(agent, args.get("command", ""))
    if reason:
        deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
