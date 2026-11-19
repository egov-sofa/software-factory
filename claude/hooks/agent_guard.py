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
import json
import os
import re
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

# The git an agent may run is an allowlist: subcommands that only read. Anything else is refused, so an alias
# (git -c alias.x=push x, or one in the user's own config), a plumbing command or a new git command cannot get past.
GIT_READS = {"status", "diff", "log", "show", "blame", "ls-files", "ls-tree", "rev-parse", "rev-list", "grep",
             "describe", "shortlog", "cat-file", "merge-base", "name-rev", "for-each-ref", "check-ignore",
             "check-attr", "diff-tree", "diff-files", "diff-index", "whatchanged", "show-ref", "count-objects",
             "range-diff", "version", "help", "var"}
# Subcommands that read in some forms only: the forms (first argument) that read. None: see git_refusal.
GIT_READ_FORMS = {"tag": {"-l", "--list"}, "stash": {"list", "show"}, "reflog": {"show"}, "notes": {"list", "show"},
                  "worktree": {"list"}, "remote": {"-v", "--verbose", "show", "get-url"}, "branch": None,
                  "restore": None, "config": None}
GIT_BRANCH_WRITES = {"-d", "-D", "-m", "-M", "-c", "-C", "-f", "--delete", "--move", "--copy", "--force",
                     "--set-upstream-to", "-u", "--unset-upstream", "--edit-description", "-t", "--track"}
GIT_BRANCH_VALUE_OPTIONS = {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort",
                            "--format", "--color", "--column", "--abbrev"}
GIT_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "-l", "get", "list"}
# `git -c key=value` keys that make git run a command; allowed only with a harmless value (cat, false, true, empty)
GIT_COMMAND_KEYS = re.compile(r"^(?:alias\..*|.*\.pager|pager\..*|core\.(?:editor|fsmonitor|sshcommand|hookspath|"
                              r"askpass|gitproxy)|sequence\.editor|diff\..*\.(?:command|textconv)|"
                              r"credential\..*|gpg\..*program|.*\.cmd)$", re.I)
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo", "nice", "xargs", "stdbuf", "timeout", "doas"}
# options of those wrappers that take a value: env -u NAME, nice -n 5, sudo -u me, xargs -I {}, timeout -s KILL
WRAPPER_OPTIONS_WITH_VALUE = {"-u", "-g", "-n", "-C", "-I", "-P", "-L", "-s", "-k", "-S",
                              "--user", "--group", "--chdir", "--unset", "--adjustment", "--signal", "--split-string"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}

# Second layer, over the whole command text (inside quotes, backticks, $( ) and eval too): every `git <options>
# <subcommand> <arguments>` in it must pass the same check. Stricter than the parser on purpose: an echo that quotes a
# writing git command is refused as well.
GIT_TEXT_RE = re.compile(
    r"(?<![\w.-])git(?:\.exe)?"
    r"((?:\s+(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace|exec-path|config-env)(?:=\S+|\s+\S+)|-\S+))*)"
    r"\s+([\w][\w.-]*)([^;&|\n`)]*)")


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


def glob_re(pattern):
    """A glob as a regular expression: * and ? stay within one folder, **/ is any number of folders (none too), a
    trailing /** is everything below. fnmatch would let * cross folders: src/test_runner/app.py would match
    **/test_*.py."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:[^/]+/)*", i + 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out, i = out + "/.+", i + 3
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def matches(rel, pattern):
    return bool(glob_re(pattern).match(rel))


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
    while i < len(tokens):
        if "=" in tokens[i] and not tokens[i].startswith("-"):
            i += 1   # VAR=value
        elif Path(tokens[i]).name in WRAPPERS:
            i += 1   # env, sudo, nice, ... and their options: env -i, nice -n 5, sudo -u me
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in WRAPPER_OPTIONS_WITH_VALUE else 1
            if i < len(tokens) and tokens[i].isdigit():
                i += 1   # timeout 10 git push
        else:
            break
    if i >= len(tokens):
        return None
    name = Path(tokens[i]).name.lower()
    if name == "eval":
        return git_write_in(" ".join(tokens[i + 1:]))
    if name in SHELLS:
        # bash -c "...", also with other flags in the same word: bash -lc "...", sh -ec "..."
        for j in range(i + 1, len(tokens) - 1):
            if tokens[j].startswith("-") and not tokens[j].startswith("--") and "c" in tokens[j]:
                return git_write_in(tokens[j + 1])
        return None
    if name not in ("git", "git.exe"):
        return None
    i += 1
    options = []
    while i < len(tokens):
        tok = tokens[i]
        if tok in GIT_OPTIONS_WITH_VALUE:
            options += tokens[i:i + 2]
            i += 2
        elif tok.startswith("-"):
            options.append(tok)   # --no-pager, -p, --git-dir=..., -c=... spellings
            i += 1
        else:
            break
    if i >= len(tokens):
        return None   # git alone, or only options: prints help or a version
    return git_refusal(tokens[i], tokens[i + 1:], options)


def git_refusal(sub, args, options):
    """None if `git <options> <sub> <args>` only reads, else the command to name in the refusal."""
    for j, opt in enumerate(options):
        setting = options[j + 1] if opt == "-c" and j + 1 < len(options) else opt[3:] if opt.startswith("-c=") else ""
        key, _, value = setting.partition("=")
        if key and GIT_COMMAND_KEYS.match(key) and value.strip("'\"").lower() not in ("", "cat", "false", "true"):
            return f"-c {key}=…"
    if sub in GIT_READS:
        return None
    if sub not in GIT_READ_FORMS:
        return sub   # writes, or an alias or command the guard does not know
    forms = GIT_READ_FORMS[sub]
    if forms is not None:
        # with no arguments these list, except stash (git stash = git stash push)
        return None if (not args and sub in ("tag", "reflog", "remote", "worktree")) or \
            (args and args[0] in forms) else f"{sub} {args[0] if args else ''}".strip()
    if sub == "branch":
        names, k = [], 0
        while k < len(args):
            a = args[k]
            if a in GIT_BRANCH_WRITES or a.split("=")[0] in GIT_BRANCH_WRITES:
                return f"branch {a}"
            if a in GIT_BRANCH_VALUE_OPTIONS:
                k += 2
                continue
            if not a.startswith("-"):
                names.append(a)
            k += 1
        listing = not names or any(a in ("-l", "--list", "-a", "--all", "-r", "--remotes") for a in args)
        return None if listing else "branch " + names[0]   # git branch <name> creates a branch
    if sub == "restore":
        return "restore --staged" if any(a in ("--staged", "-S") for a in args) else None
    if sub == "config":
        return None if any(a in GIT_CONFIG_READS for a in args) else "config " + " ".join(args[:2])
    return sub


def git_write_in(command):
    for tokens in segments(command):
        found = git_write(tokens)
        if found:
            return found
    return None


def git_write_text(command):
    """A writing git command that appears anywhere in the command text, else None (the second layer)."""
    for m in GIT_TEXT_RE.finditer(command):
        found = git_refusal(m.group(2), m.group(3).split(), m.group(1).split())
        if found:
            return found
    return None


def check_bash(agent, command):
    """None if the command is allowed, else the reason it is not."""
    try:
        found = git_write_in(command) or git_write_text(command)
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
        reason = decide(agent, json.loads(sys.stdin.read() or "{}"))
    except Exception as ex:   # noqa: BLE001 - a crash would let the call through (Claude Code ignores exit 1)
        reason = f"the factory's guard for {agent} could not check this tool call ({type(ex).__name__}), so it is refused."
    if reason:
        deny(reason)
    return 0


def decide(agent, call):
    """The reason the call is refused, or None."""
    if not isinstance(call, dict) or not isinstance(call.get("tool_input") or {}, dict):
        raise ValueError("the tool call is not a JSON object")
    tool, args = call.get("tool_name", ""), call.get("tool_input") or {}
    cwd = call.get("cwd") or os.getcwd()
    if tool in ("Edit", "Write", "NotebookEdit"):
        path = args.get("file_path") or args.get("notebook_path") or ""
        return check_path(agent, path, cwd) if path else None
    if tool == "Bash":
        return check_bash(agent, args.get("command", ""))
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
