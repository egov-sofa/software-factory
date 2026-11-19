# Plan: Enforce the agents' limits with Claude Code hooks (roadmap I26)

**Status:** Proposed
**Request:** "draft the I26 plan" — roadmap I26: "Enforce with Claude Code hooks, not prompts. Ship a `settings.json`
with a PreToolUse path check per agent (tester edits tests, docs-writer edits docs, planner edits `docs/plans/`), a
block on pushing to `main` and on `--force`, and an explicit `tools` list for the implementer."

## Goal

Make the factory's promises true whatever the model does. Today "the tester only edits tests", "the reviewer can't
change code" and "never push to main" are sentences in prompts: a confused or prompt-injected agent can break them,
and `docs/HOW-IT-WORKS.md` says reviewers "can't accidentally change code" although they have Bash. After this change a
hook refuses the forbidden tool call and tells the agent why.

## Facts this plan relies on (checked 2026-11-19 in the Claude Code docs)

- **Hooks can live in an agent's frontmatter** (`hooks:` in `.claude/agents/*.md` or `~/.claude/agents/*.md`) and run
  only while that agent runs. User-level agents (where `install.sh` puts ours) run them without a trust prompt.
  Source: https://code.claude.com/docs/en/sub-agents.md
- **PreToolUse input** holds `tool_name`, `tool_input` (`file_path` for Edit and Write, `command` for Bash), `cwd`,
  and `agent_type` (the agent's `name`) when the call comes from a subagent. No branch field: a hook runs
  `git branch --show-current` itself. Source: https://code.claude.com/docs/en/hooks.md
- **Blocking:** a PreToolUse hook that prints `hookSpecificOutput.permissionDecision: "deny"` with a
  `permissionDecisionReason` stops the call, and the reason is shown to the model. Exit code 2 also blocks.
- **Hook commands run in Git Bash on Windows** (PowerShell only without Git Bash).
- **`disallowedTools` takes tool names only**: `Bash(git push *)` there would remove Bash entirely. Command patterns
  belong in `permissions.deny`, which the docs call best-effort for shell commands (`git -C . push` slips past). So the
  push rules need a hook that parses the command, not only a deny rule.
- `install.sh` already replaces `{{FACTORY_HOME}}` in agent files, so a hook command can point at a script in the
  factory clone.

## Assumptions

- The hooks live in the **agents' frontmatter**, plus one small **guard script** in the factory
  (`scripts/hooks/agent_guard.py`). No change to the user's `~/.claude/settings.json` in this item (see Open questions).
- Python is the factory's script language. The hook command finds `python3` or `python` the way
  `scripts/hooks/pre-commit` already does.
- "Test file" and "docs file" are decided by path patterns (below). The guard cannot read prose, so a project with an
  unusual layout would widen them in a small file such as `.factory/agent-paths.yml`, not in `AGENTS.md`
  (Open question 3).

## Acceptance criteria

1. **Tester** (`agent_type: tester`): Edit or Write outside test paths is denied with a reason naming the allowed
   patterns. Test paths: `tests/**`, `test/**`, `__tests__/**`, `**/*.test.*`, `**/*.spec.*`, `**/test_*.py`,
   `**/*_test.*`, `**/testdata/**`, `**/fixtures/**`.
2. **Docs-writer:** Edit or Write is allowed only on `README*`, `CHANGELOG*`, `docs/**`, `*.md` at the project root,
   `.env.example`, and the plan file's `Status` line through `docs/plans/**`. Anything else is denied.
3. **Planner:** Write only under `docs/plans/`. Anything else is denied.
4. **Reviewer and security-auditor:** no Edit or Write (already absent from their `tools`). Bash commands that change
   the repository are denied: `git` `commit`, `push`, `reset`, `checkout`, `switch`, `restore`, `rebase`, `merge`,
   `stash`, `add`, `rm`, `mv`, `clean`, `tag`, `branch -d/-D`, `apply`, `am`, `cherry-pick`, `revert`, plus
   `rm`, `mv`, `cp` outside the system temp folder, `sed -i`, and output redirection (`>`, `>>`, `tee`) to a path
   inside the project. Running tests and read-only git commands still works.
5. **Every factory agent:** `git push` in any form (including `git -C <dir> push` and `git -c … push`) is denied:
   only `/factory-ship`, in the main conversation, pushes.
6. **Implementer:** has an explicit `tools` list: `Read, Grep, Glob, Bash, Write, Edit`. It no longer inherits web or
   MCP tools.
7. A denied call returns a reason the agent can act on, for example: "tester may only edit test files (tests/**,
   **/*.test.*, …); src/app.ts is production code. Report what needs to change instead."
8. The guard **fails closed** for the read-only agents (an unreadable input is denied) and **fails open with a
   warning** for path checks when it cannot run (no Python), so a broken install never silently loosens a
   read-only agent, but also never blocks the whole pipeline.
9. `validate.py` accepts `hooks` in agent frontmatter, and checks that every factory agent that may not edit freely
   (planner, tester, docs-writer, reviewer, security-auditor) declares the guard hook.
10. `docs/HOW-IT-WORKS.md` describes what is enforced and what is still only asked of the agents.

## Design

**`scripts/hooks/agent_guard.py <agent>`** reads the PreToolUse JSON on stdin and prints a deny decision or nothing.
- Edit/Write: normalize `tool_input.file_path` against `cwd` (Windows paths, `..`, symlinks resolved with
  `os.path.realpath`), then match the agent's patterns with `fnmatch` on the POSIX-style relative path. A path
  outside the project is denied for every agent except through the system temp folder.
- Bash: split the command with `shlex` (posix mode) into subcommands on `&&`, `||`, `;`, `|` and newlines; for each,
  skip leading `VAR=value` and `env`, find `git` and its subcommand after global options (`-C`, `-c`, `--git-dir`,
  `--work-tree`, `--no-pager`). A command `shlex` cannot split is denied for read-only agents (fail closed).
- One table of rules per agent, at the top of the script, so a reviewer of the factory sees all limits in one place.

**Agent frontmatter** (example for the tester):
```yaml
hooks:
  PreToolUse:
    - matcher: "Edit|Write|Bash"
      hooks:
        - type: command
          command: 'PY=python3; "$PY" -c "" 2>/dev/null || PY=python; "$PY" "{{FACTORY_HOME}}/scripts/hooks/agent_guard.py" tester'
```

**Why frontmatter and not `~/.claude/settings.json`:** the hooks then exist exactly while the agent runs, need no
merge into the user's own settings file, are installed and removed with the agents by `install.sh` and
`uninstall.sh`, and move unchanged into the plugin when I7 lands.

## Files

| File | Change |
|---|---|
| `scripts/hooks/agent_guard.py` | New: the guard |
| `claude/agents/{planner,tester,docs-writer,reviewer,security-auditor,implementer}.md` | `hooks:` block; implementer gets `tools:` |
| `scripts/validate.py` | Accept `hooks`; check the guard is declared |
| `scripts/tests/test_agent_guard.py` | New: unit tests (stdin JSON in, decision out) |
| `scripts/tests/test_validate.py` | The new checks |
| `docs/HOW-IT-WORKS.md`, `docs/CUSTOMIZING.md` | What is enforced; how to widen paths |
| `docs/ROADMAP.md` | I26 status |

## Test plan

- **Unit, per agent and rule:** allowed and denied Edit/Write paths (including `..`, absolute Windows paths, a
  symlink into `src/`); git subcommands with `-C` and `-c` before them; chained commands (`npm test && git push`);
  redirection; an unsplittable command (denied for reviewer, path-check fallback for tester).
- **validate.py:** an agent without its guard is reported.
- **End to end (manual, then an eval under I1):** run `/factory-build` on a scratch project, ask the tester to "also fix
  the bug in src/", and check the edit is refused with the reason and the run continues.
- The self-test runs the unit tests on Linux; Windows is covered by running them locally (Git Bash).

## Risks / out of scope

- **Best effort for Bash.** No parser catches every shell trick (`eval`, `python -c "open(...).write"`). The goal is to
  stop mistakes and casual injection, not a determined attacker with Bash; the real boundary stays the
  `protect-main` ruleset on GitHub and code review.
- **Main conversation not covered.** Frontmatter hooks guard the factory's agents only. "Never push to main" for the
  main conversation needs a hook in settings or the plugin (Open question 1).
- **Project path conventions** that the default patterns miss would block a legitimate tester edit (Open question 3).

## Open questions (for the user, before building)

1. **Global push guard.** Also block `git push` to `main` and `--force` in the **main conversation**? That needs a
   hook in `~/.claude/settings.json` (install.sh would merge one entry, with a backup) or waiting for the plugin (I7)
   whose `hooks/hooks.json` carries it. Recommendation: wait for I7; the `protect-main` ruleset already refuses those
   pushes on GitHub for repositories that have it, and new projects can get the same ruleset from `/factory-new`.
2. **Reviewer Bash:** a blocklist (this plan) keeps "run the tests" working. The stricter alternative removes Bash
   from the reviewer and security-auditor and hands them the diff from the conductor instead.
3. **Path overrides:** allow `.factory/agent-paths.yml` in a project to add test or docs paths, or keep the fixed
   list and change the factory when a stack needs more?
