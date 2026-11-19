# Plan: Enforce the agents' limits with Claude Code hooks (roadmap I26)

**Status:** Implemented (2026-11-19, with the decisions below)
**Request:** "draft the I26 plan" — roadmap I26: "Enforce with Claude Code hooks, not prompts. Ship a `settings.json`
with a PreToolUse path check per agent (tester edits tests, docs-writer edits docs, planner edits `docs/plans/`), a
block on pushing to `main` and on `--force`, and an explicit `tools` list for the implementer."

## Decisions (2026-11-19)

1. **Main conversation:** no change to `~/.claude/settings.json` now. The push guard for the main conversation comes
   with the plugin (I7); until then the `protect-main` ruleset refuses those pushes on GitHub.
2. **Reviewer and security-auditor lose Bash.** The conductor prepares what they ran Bash for (the diff, test and
   audit results) in files they read.
3. **Fixed path lists in the factory.** No per-project override file; a stack that needs more paths changes the factory.

## Goal

Make the factory's promises true whatever the model does. Today "the tester only edits tests", "the reviewer can't
change code" and "never push" are sentences in prompts: a confused or prompt-injected agent can break them, and
`docs/HOW-IT-WORKS.md` says reviewers "can't accidentally change code" although they have Bash. After this change the
reviewers have no tool that writes, and a hook refuses the other agents' forbidden calls and tells them why.

## Facts this plan relies on (checked 2026-11-19 in the Claude Code docs)

- **Hooks can live in an agent's frontmatter** (`hooks:` in `~/.claude/agents/*.md`) and run only while that agent
  runs; user-level agents run them without a trust prompt. https://code.claude.com/docs/en/sub-agents.md
- **PreToolUse input** holds `tool_name`, `tool_input` (`file_path` for Edit and Write, `command` for Bash) and `cwd`.
  https://code.claude.com/docs/en/hooks.md
- **Blocking:** `hookSpecificOutput.permissionDecision: "deny"` with a `permissionDecisionReason` stops the call and
  shows the reason to the model.
- **Hook commands run in Git Bash on Windows.**
- **`disallowedTools` takes tool names only**, and `permissions.deny` rules for shell commands are best-effort
  (`git -C . push` slips past), so the git rules need a script that parses the command.
- `install.sh` already replaces `{{FACTORY_HOME}}` in agent files, so a hook command can point at a script in the
  factory clone.

## Acceptance criteria

1. **Reviewer and security-auditor** have `tools: Read, Grep, Glob`: no Bash, Edit or Write.
2. **`/factory-build` (Stage 5) and `/factory-review`** write the reviewers' input to `.git/factory-review/` before
   launching them, and pass the folder's path:
   - `changes.diff`: `git diff <base>...HEAD` followed by `git diff` (uncommitted work);
   - `files.txt`: the changed files (`git diff --name-only <base>...HEAD` and uncommitted);
   - `checks.txt`: the latest test and lint results (from the tester's report, or by running the project's commands),
     and the output of `npm audit --omit=dev` or `pip-audit` when the project has one.
   The reviewers read those files instead of running commands; the security auditor's secret search becomes a Grep on
   `changes.diff`.
3. **Tester:** Edit or Write outside the test paths is denied, with a reason naming them: `tests/**`, `test/**`,
   `__tests__/**`, `**/*.test.*`, `**/*.spec.*`, `**/test_*.py`, `**/*_test.*`, `**/testdata/**`, `**/fixtures/**`.
4. **Docs-writer:** Edit or Write only on `README*` and `CHANGELOG*` (in any folder), `docs/**`, `*.md` at the project
   root and `.env.example`.
5. **Planner:** Write only under `docs/plans/`.
6. **Implementer:** `tools: Read, Grep, Glob, Bash, Write, Edit`, so it no longer inherits web or MCP tools. Its edits
   are not path-limited.
7. **Planner, tester, docs-writer and implementer:** only git commands that read are allowed, an allowlist: `status`,
   `diff`, `log`, `show`, `blame`, `grep`, `ls-files`, `rev-parse` and similar, and the read forms of `branch`, `tag`,
   `stash`, `config`, `remote`, `reflog`, `notes` and `worktree` (listing, never creating or deleting). Everything
   else is refused, so an alias (`git -c alias.x=push x`, or one in the user's config) or a command the guard does
   not know cannot get past; so are `git -c` settings that run a command (an alias, a pager, an editor,
   `core.fsmonitor`) unless their value is harmless. This holds behind `-C <dir>`, `env` and other wrappers with
   their options, `VAR=value`, `bash -c` in any flag combination, `eval`, backticks and `$( )`. The conductor does
   all git work; the project's own commands still work. (A blocklist first; changed to an allowlist after the
   review of #24 showed aliases past it.)
8. A denied call returns a reason the agent can act on, for example: "tester may only edit test files (tests/**,
   **/*.test.*, …); src/app.ts is production code. Report what needs to change instead."
9. If Python cannot be found, the hook warns and allows the call (fail open), so a broken setup never blocks the
   whole pipeline; a command the guard cannot parse is denied for the git rule (fail closed).
10. `validate.py` accepts `hooks` in agent frontmatter, checks that the planner, tester, docs-writer and implementer
    declare the guard, and that the reviewer and security-auditor have none of Bash, Edit, Write.
11. `docs/HOW-IT-WORKS.md` and `docs/CUSTOMIZING.md` say what is enforced, and what is still only asked of the agents.

## Design

**`claude/hooks/agent_guard.py <agent>`** reads the PreToolUse JSON on stdin and prints a deny decision, or nothing.
- Edit/Write: make `tool_input.file_path` relative to `cwd` (Windows paths, `..`, symlinks resolved with
  `os.path.realpath`) and match it with `fnmatch` against the agent's patterns, on a POSIX-style path. A path outside
  the project is denied, except in the system temp folder.
- Bash: split the command with `shlex` (POSIX mode) into subcommands on `&&`, `||`, `;`, `|` and newlines. For each,
  skip leading `VAR=value` and `env`, then find `git` and its subcommand after global options (`-C`, `-c`,
  `--git-dir`, `--work-tree`, `--no-pager`). An unsplittable command that mentions `git` is denied.
- A second layer reads the whole command text, inside quotes, backticks, `$( )` and `eval` too: `git`, any options,
  then a writing subcommand anywhere is refused. It is stricter than the parser on purpose, so `echo "git push"` is
  refused as well (added after the review of #24, which got `env -i git push`, `bash -lc "git push"` and backticks
  past the parser alone).
- Any error inside the guard, including input that is not a JSON object, refuses the call: Claude Code treats a
  crashing hook (exit 1) as non-blocking, so a crash must not become an allowed call.
- One table of rules per agent at the top of the script, so a reviewer of the factory sees every limit in one place.

**Agent frontmatter** (tester):
```yaml
hooks:
  PreToolUse:
    - matcher: "Edit|Write|Bash"
      hooks:
        - type: command
          command: 'PY=python3; "$PY" -c "" 2>/dev/null || PY=python; "$PY" "{{FACTORY_HOME}}/claude/hooks/agent_guard.py" tester'
```

**Why frontmatter and not `~/.claude/settings.json`:** the hooks exist exactly while the agent runs, need no merge
into the user's own settings, are installed and removed with the agents, and move unchanged into the plugin (I7).

## Files

| File | Change |
|---|---|
| `claude/hooks/agent_guard.py` | New: the guard |
| `claude/agents/{planner,tester,docs-writer,implementer}.md` | `hooks:` block; implementer gets `tools:`; no `git` writes in the prompts |
| `claude/agents/{reviewer,security-auditor}.md` | `tools: Read, Grep, Glob`; read `.git/factory-review/` |
| `claude/skills/factory-build/SKILL.md`, `claude/skills/factory-review/SKILL.md` | Prepare `.git/factory-review/` |
| `scripts/validate.py`, `scripts/tests/test_validate.py` | Accept `hooks`; the new checks |
| `scripts/tests/test_agent_guard.py` | New: unit tests (JSON in, decision out) |
| `docs/HOW-IT-WORKS.md`, `docs/CUSTOMIZING.md`, `docs/ROADMAP.md` | What is enforced; I26 status |

## Test plan

- **Guard, per agent and rule:** allowed and denied paths (`..`, absolute Windows paths, a symlink into `src/`, the
  temp folder); each git subcommand, with `-C` and `-c` before it; chained commands (`npm test && git push`); an
  unsplittable command; a read-only git command and a project command allowed.
- **validate.py:** an agent without its guard, and a reviewer with Bash, are both reported.
- **End to end (by hand, then an eval under I1):** run `/factory-build` on a scratch project, ask the tester to "also
  fix the bug in src/", and check the edit is refused with the reason and the run continues; run `/factory-review` and
  check both reviewers report from `.git/factory-review/`.

## Risks / out of scope

- **Bash stays best effort** for the four agents that keep it: `eval`, `python -c` and similar can still write files.
  The goal is to stop mistakes and casual injection; the real boundary stays the `protect-main` ruleset and review.
- **The main conversation is not covered** until I7 (decision 1).
- **Larger reviewer input:** a very large diff in `changes.diff` costs the reviewers context; they already read the
  changed files in full, so this adds little.
