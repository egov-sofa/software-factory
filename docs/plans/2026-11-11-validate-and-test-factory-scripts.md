# Plan: Validate and test the factory's own scripts (roadmap I6)

**Status:** Done
**Request:** Feature request — roadmap item I6 in docs/ROADMAP.md, "Validate and test the factory's own scripts":
1. A validator (suggested: scripts/validate.py, stdlib-only Python like scripts/check_content.py) that checks frontmatter of claude/agents/*.md and claude/skills/*/SKILL.md (and .claude/skills/*/SKILL.md, templates/_shared/.claude/skills/*/SKILL.md if sensible): required fields present, `name` matches the file name / folder name, `model` (if present) is a valid value, `tools` lists only real Claude Code tool names. Exit non-zero with clear messages.
2. Tests for scripts/install.sh run into a temporary CLAUDE_CONFIG_DIR: a pre-existing user CLAUDE.md content is kept, the factory block (between <!-- software-factory:start/end --> markers) is inserted once and replaced (not duplicated) on the second run, backups are written when files change, second run is idempotent ("unchanged"), {{FACTORY_HOME}} rendered. Also scripts/uninstall.sh if cheap.
3. Tests for scripts/new-project.sh options: --owner required unless --dir; --dir; --no-git; invalid name / template / owner / --github value rejected; target already exists rejected; {{FACTORY_REPO}} filled from the factory's git remote (tests can run against a temp copy of the factory with a fake remote to make it deterministic); no leftover template placeholders — note GitHub `${{ ... }}` expressions are legitimate and must NOT count as leftovers (the current selftest grep of "{{" may be wrong about this; check it).
4. Run all of it in .github/workflows/factory-selftest.yml (pinned actions by SHA as the existing workflow does).
5. Update docs/ROADMAP.md status for I6 (and the review log).

## Goal
A typo in an agent's or skill's frontmatter, or a regression in `install.sh`, `uninstall.sh` or `new-project.sh`,
turns the factory's self-test red instead of going unnoticed. Today CI only lints the shell scripts and scaffolds one
project per template; nothing checks the installer, the script options or the frontmatter.

## Assumptions
- **Validator scope:** `claude/agents/*.md`, `claude/skills/*/SKILL.md`, `.claude/skills/*/SKILL.md` and
  `templates/*/.claude/skills/*/SKILL.md` (today only `templates/_shared/`). The template copy holds
  `{{PROJECT_NAME}}` in its description; that is fine, since only `name` must match the folder.
- **Valid `model` values** are exactly `opus`, `sonnet`, `haiku`, `inherit`, as `.claude/skills/pr-review/SKILL.md`
  states. Full model IDs are rejected on purpose: the checklist is the source of truth, and an alias survives model
  releases.
- **Unknown frontmatter keys are errors** (catches `tool:` instead of `tools:`). The allowed keys are a constant at
  the top of the validator, easy to extend when Claude Code adds a field.
- **Read-only agents** (`reviewer`, `security-auditor`) must declare `tools` and must not list `Edit`, `Write`,
  `MultiEdit` or `NotebookEdit`. This is a rule from the review checklist and costs a few lines, so the validator
  enforces it.
- **install.sh fix (small, in scope):** the second run currently always backs up `CLAUDE.md` and reports
  "factory block updated" even when nothing changed, so the requested "second run is idempotent" test would fail.
  The fix: build the new `CLAUDE.md` in a temporary file, `cmp -s` it with the current one, and if equal print
  `= CLAUDE.md (unchanged)` with no backup. This is the only behavior change; it matches how `install_file` already
  treats agents and skills.
- **Selftest placeholder grep:** checked, and it is already correct. It matches `\{\{[A-Z_]+\}\}`, and every GitHub
  expression in the templates has spaces and lower-case names (`${{ secrets.X }}`, `${{ vars.Y }}`), so none is
  flagged. The workflow step stays as it is. The Python test uses a stricter pattern that also ignores a `$` before
  the braces, `(?<!\$)\{\{\s*[A-Z_]+\s*\}\}`, so a future `${{FOO}}` cannot cause a false alarm.
- The roadmap item also says "test the content guard's rules": `scripts/tests/test_check_content.py` already does
  that, so nothing is added for it.
- `--github private|public` is tested only for argument validation (bad value, combined with `--no-git`). Creating a
  real GitHub repository is out of scope.

## Acceptance criteria

Validator (`python scripts/validate.py`):
- [x] Exits 0 and prints `No problems in N file(s).` on the current repository.
- [x] Exits 1 and prints `path:line: problem` for each of: no frontmatter (file does not start with `---`, or no
      closing `---`); missing `name` or `description`; empty `description`; `name` different from the file stem
      (agents) or folder name (skills); `model` not in the allowed set; an unknown tool in `tools` (agents) or
      `allowed-tools` (skills); an unknown frontmatter key; a read-only agent with a write tool or without `tools`.
- [x] `tools` accepts a comma-separated string, an inline list `[A, B]` or a block list (`- A`); `mcp__<server>__<tool>`
      names and permission-rule forms such as `Bash(git status:*)` (known tool name before the parenthesis) are valid.
- [x] Exits 2 with the usage text on an unknown argument; `--root DIR` checks another tree (used by the tests).
- [x] Stdlib only; no secret or file content beyond the offending key/value is printed.

install.sh / uninstall.sh (run with `bash`, `CLAUDE_CONFIG_DIR` set to a temporary folder):
- [x] Fresh install into an empty folder creates every agent and skill file and a `CLAUDE.md` with exactly one
      start and one end marker; no backup folder is created.
- [x] No installed file contains `{{FACTORY_HOME}}`; `agents/reviewer.md` contains the factory path followed by
      `/standards/`.
- [x] A pre-existing `CLAUDE.md` with user text keeps that text byte-for-byte before the factory block, and a backup
      of the original is written under `backups/software-factory-*/CLAUDE.md`.
- [x] Second run with nothing changed: every line reports `(unchanged)`, `CLAUDE.md` is byte-identical, and no new
      backup is written (requires the install.sh fix above).
- [x] When the block holds old content (the test edits a line between the markers) and user text sits both before
      and after the block, the next run replaces the block in place: still one start marker, old line gone, user text
      before and after kept, and a backup holding the old content exists.
- [x] When an installed agent was edited by hand, the next run restores it and backs up the edited copy.
- [x] `--dry-run` writes nothing (the target folder stays empty or absent).
- [x] uninstall.sh removes the factory's agents, skills and block, keeps a user-created `agents/mine.md` and the
      user's `CLAUDE.md` text, and deletes `CLAUDE.md` when only the factory block was in it.

new-project.sh (run against a temporary copy of the factory with a fake remote):
- [x] Without `--owner` and without `--dir`: exit 1, message mentions `--owner`, nothing is created.
- [x] `--dir <parent>` without `--owner` succeeds and creates `<parent>/<name>`.
- [x] `--owner acme` without `--dir` creates `<workspace>/acme/<name>`, where the workspace is two levels above the
      factory copy (`FACTORY_WORKSPACE` unset in the test environment).
- [x] Default (git on): `.git` exists with one commit on `main`, `core.hooksPath` is `scripts/hooks`, and
      `scripts/hooks/pre-commit` is mode `100755` in the index. With `--no-git`: no `.git` folder.
- [x] Rejected with exit 1 and nothing created: names `My_App`, `1app`, `app_x`; templates `cobol`, `_shared`;
      owner `bad/owner`; `--github internal`; `--github private --no-git`; an unknown option; a target that already
      exists (whose existing content stays untouched).
- [x] `{{FACTORY_REPO}}` is filled from the remote: `https://github.com/test-org/test-factory.git` gives
      `test-org/test-factory` and `git@github.com:other-org/fork.git` gives `other-org/fork` in
      `.github/workflows/ci.yml`; with no remote, it falls back to `YOUR_ORG/software-factory` and prints the warning.
- [x] For each template (`typescript`, `python`, `generic`): no file or path contains a factory placeholder
      (`(?<!\$)\{\{\s*[A-Z_]+\s*\}\}`), the python package folder is renamed, and the GitHub `${{ ... }}`
      expressions in the workflows are still present and unchanged.

Extra fixes (approved with the plan; previously listed as out of scope):
- [x] A. `.claude/skills/pr-review/SKILL.md` lists `{{FACTORY_REPO}}` among the allowed template placeholders. A test
      checks that the placeholders listed there, the placeholders `new-project.sh` replaces, and the placeholders the
      templates use agree (every used one is replaced and listed; every listed one is replaced).
- [x] B. `new-project.sh` fills placeholders without `sed -i` (GNU-only without a suffix; BSD sed on macOS needs one):
      it writes `sed` output to a temporary file made with `mktemp` (outside the project, so the running `grep -rl`
      never lists it) and copies it back with `cat`, which keeps the file mode. Shellcheck stays clean; a test
      asserts the script no longer calls `sed -i`, and the placeholder tests cover the behavior.
- [x] C. `install.sh` and `uninstall.sh` never drop user content when the markers in `CLAUDE.md` are broken: a start
      marker without an end marker, an end marker without a start marker, two start markers or two blocks, the end
      before the start, or a marker sharing its line with other text. Both scripts then print a clear error naming
      `CLAUDE.md` and the markers, exit 1, and leave `CLAUDE.md` byte-identical (no `.tmp` left behind). Both make
      the check before touching anything (install.sh also in `--dry-run`; uninstall.sh removes no agent or skill).

Found while testing (fixed, since the acceptance criteria above require it):
- [x] `new-project.sh` without `--owner` and `--dir` exited with status 4 and no message when `gh` was installed but
      logged out (and would have when `gh` was missing): the `choices=$(...)` substitution failed under
      `set -e`/`pipefail`. It now ends in `|| true`, so the "Choose who owns the project with --owner" error shows.

CI and docs:
- [x] `factory-selftest.yml` runs the validator and the whole `scripts/tests` suite on ubuntu; existing pinned SHAs
      are reused, no new action is added.
- [x] `python scripts/check_content.py --all` and `shellcheck scripts/*.sh scripts/hooks/* templates/generic/scripts/*.sh` (both pass; shellcheck 0.11.0 run locally)
      still pass.
- [x] `docs/ROADMAP.md`: I6 status `done (this branch)`, review log has a dated entry.

## Design

**`scripts/validate.py`** follows `check_content.py`: module docstring as usage text, `ROOT` from the script path,
`--root` override, `path:line: problem` output, a summary line, exit codes 0/1/2. A small frontmatter reader (no
PyYAML, since stdlib only) handles what the repo uses: `key: value`, quoted values, inline `[a, b]` lists and `- item`
block lists; anything else (for example `key: >`) is reported as "unsupported frontmatter syntax" rather than guessed.
Constants at the top: `MODELS`, `KNOWN_TOOLS` (`Agent`, `Task`, `Bash`, `BashOutput`, `KillShell`, `Edit`,
`MultiEdit`, `Write`, `Read`, `Glob`, `Grep`, `LS`, `NotebookEdit`, `NotebookRead`, `TodoWrite`, `WebFetch`,
`WebSearch`, `Skill`, `SlashCommand`, `AskUserQuestion`, `ExitPlanMode`), `AGENT_KEYS`, `SKILL_KEYS`,
`READ_ONLY_AGENTS`. The functions return lists of problem strings, so tests can call them directly (as
`test_check_content.py` calls `findings`).

**Test support (`scripts/tests/support.py`)**: one shared helper, imported by the test files (discovery puts
`scripts/tests` on `sys.path`).
- `BASH`: `os.environ.get("FACTORY_TEST_BASH") or shutil.which("bash")`, as an absolute path. If it is missing, or on
  Windows resolves to `System32\bash.exe` (that is WSL, not Git Bash, and cannot read Windows paths the same way), the
  shell tests are skipped with a message saying so. Calling `["bash", ...]` directly is avoided on purpose: Windows
  searches System32 before `PATH`, so it would pick WSL.
- `run(script, *args, env)`: `subprocess.run([BASH, script, ...], capture_output=True, text=True, encoding="utf-8")`
  with an isolated environment: `GIT_CONFIG_GLOBAL` pointing to an empty temp file, `GIT_CONFIG_NOSYSTEM=1`, git
  author/committer variables (as in `test_check_content.py`), `GH_PROMPT_DISABLED=1`, and `FACTORY_WORKSPACE`
  removed. Isolating git config stops the developer's own hooks, signing or `hooksPath` from changing results.
- Paths passed to bash use `Path.as_posix()` (`C:/...` works in Git Bash).

**`scripts/tests/test_install.py`** runs the real `scripts/install.sh` and `uninstall.sh` (they only read the factory)
with `CLAUDE_CONFIG_DIR` set to a `tempfile.TemporaryDirectory()`. **`scripts/tests/test_new_project.py`** builds a
fake workspace per test class: `tmp/ws/test-org/software-factory/` holding copies of `scripts/` and `templates/`
(`shutil.copytree`, ignoring `__pycache__`), then `git init` there and `git remote add origin <fake url>`. This makes
`{{FACTORY_REPO}}` and the default `--dir` deterministic and independent of the real checkout's remote. Most cases use
`--no-git` to stay fast; one case covers the git path.

**`scripts/install.sh` fix**: in the "markers present" branch, run awk into `$target.tmp`, then
`if cmp -s "$target.tmp" "$target"; then rm; say "  = CLAUDE.md (unchanged)"; else backup; mv; say "  ~ ..."; fi`.
Same pattern as `install_file`, shellcheck-clean, no GNU-only flags.

**Workflow**: rename the `guard` job to `tests` / "Factory script tests" (it now covers more than the guard), add a
step `python scripts/validate.py` before the unittest step, and rename that step to "Unit tests of the factory
scripts". The unittest step already runs `discover`, so new test files are picked up. Git is preinstalled on ubuntu
runners; the tests set their own git identity.

Alternative considered: pytest with fixtures would be shorter, but it is a new dependency and the existing tests use
unittest; `subprocess` against real scripts was chosen over mocking because the point is to catch real shell
regressions.

## Files
| File | Change |
|---|---|
| `scripts/validate.py` | create: frontmatter validator (stdlib only), `--root`, exit 0/1/2 |
| `scripts/install.sh` | modify: report `CLAUDE.md (unchanged)` and skip the backup when the block did not change; (C) refuse a `CLAUDE.md` with broken markers |
| `scripts/tests/support.py` | create: bash discovery (skip on missing bash or WSL), isolated env, run helper |
| `scripts/tests/test_validate.py` | create: validator unit and command-line tests on fake trees |
| `scripts/tests/test_install.py` | create: install/uninstall tests into a temp `CLAUDE_CONFIG_DIR` |
| `scripts/tests/test_new_project.py` | create: option, layout, remote and placeholder tests on a temp factory copy |
| `.github/workflows/factory-selftest.yml` | modify: rename the test job, add the validator step |
| `docs/ROADMAP.md` | modify: I6 `done (this branch)`, review log entry dated 2026-11-11 |
| `docs/HOW-IT-WORKS.md` | modify: one sentence in the self-test paragraph about the validator and script tests |
| `.claude/skills/pr-review/SKILL.md` | modify (A): add `{{FACTORY_REPO}}` to the allowed placeholders |
| `scripts/new-project.sh` | modify (B): portable in-place replacement through a temporary file; the `gh` owner hint can no longer abort the script |
| `scripts/uninstall.sh` | modify (C): refuse to touch a `CLAUDE.md` with broken markers |
| `docs/CUSTOMIZING.md` | modify: under "Change how an agent behaves", run `python scripts/validate.py` after editing frontmatter |

## Test plan
- `test_validate.Frontmatter.test_repository_is_valid`: the real repo has no problems.
- `test_validate.Frontmatter.test_each_problem_is_reported`: subTests for every rejected case in the criteria.
- `test_validate.Frontmatter.test_tools_formats`: string, inline list, block list, `mcp__x__y`, `Bash(git:*)` accepted.
- `test_validate.CommandLine`: exit 0 on a clean fake tree, exit 1 with `path:line:` output, exit 2 on a bad argument.
- `test_install.Install.test_fresh_install`: files created, one marker pair, no backups, no `{{FACTORY_HOME}}`.
- `test_install.Install.test_user_content_kept_and_backed_up`.
- `test_install.Install.test_second_run_is_idempotent`: all `(unchanged)`, identical bytes, no new backup.
- `test_install.Install.test_old_block_is_replaced_not_duplicated`: text before and after the block kept.
- `test_install.Install.test_edited_agent_is_restored_and_backed_up`.
- `test_install.Install.test_dry_run_writes_nothing`.
- `test_install.Uninstall.test_removes_factory_files_keeps_user_files` and `test_deletes_claude_md_when_only_block`.
- `test_new_project.Options.test_owner_required_without_dir`, `test_dir_without_owner`, `test_default_dir_from_owner`,
  `test_no_git`, `test_git_repo_and_hooks`, `test_rejected_arguments` (subTests), `test_existing_target_rejected`.
- `test_new_project.FactoryRepo.test_https_remote`, `test_ssh_remote`, `test_no_remote_fallback`.
- `test_new_project.Placeholders.test_no_leftovers_per_template` (subTest per template, also checks `${{` kept).
- `test_new_project.Placeholders.test_documented_placeholders_match_script` (A) and `test_no_in_place_sed` (B).
- `test_install.Install.test_broken_markers_are_refused` and `test_install.Uninstall.test_broken_markers_are_refused`
  (C, subTest per broken layout).
- Manual: `python -m unittest discover -s scripts/tests -v` in Git Bash on Windows and in CI; `python scripts/validate.py`;
  `python scripts/check_content.py --all`; `shellcheck` on the scripts.

## Risks / out of scope
- **Required status check name:** renaming the job "Content guard tests" breaks merges if branch protection
  requires that exact check name. Check the repository settings before merging, or keep the old job name.
- **WSL bash on Windows:** handled by resolving bash explicitly and skipping when only WSL's is found; a developer
  running from PowerShell without Git Bash on `PATH` sees skips, not failures. CI is unaffected.
- **Tool list drift:** Claude Code may add or rename tools; `KNOWN_TOOLS` and the key allowlists must then be
  updated, otherwise the validator gives a false error (visible and easy to fix, which is the intended trade-off).
- **Timing:** backup folders are named to the second, so two runs in the same second share one folder. Tests assert
  on content, not on the number of folders.
- **Speed:** each `new-project.sh` run copies a template; keep git-enabled runs to one or two cases.
- The three items first listed here as out of scope (the pr-review placeholder list, `sed -i` on macOS, broken
  markers in `CLAUDE.md`) were approved with the plan and moved to the acceptance criteria as A, B and C.

## Follow-ups (not fixed)
LOW/MINOR review findings, left for a later change:
1. A `CLAUDE.md` with CRLF line endings is refused with an unhelpful message on Linux/macOS: strip `\r` in the awk
   marker check, or mention CRLF in the error.
2. The read-only agent rule uses a denylist of write tools. Switch to an allowlist so `Agent`/`Task` and MCP write
   tools are caught too.
3. `scripts/tests/support.py` should also unset `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`,
   `GIT_OBJECT_DIRECTORY`, `GIT_CONFIG_PARAMETERS` and `GIT_CONFIG_COUNT`.
4. `sed` replacement values (`FACTORY_REPO`, `FACTORY_HOME`) are not escaped for `&`, `|` and `\` (pre-existing).
5. The marker-check awk is duplicated in `install.sh` and `uninstall.sh`.
6. Add an explicit `trap - EXIT` after the `rm` in `new-project.sh`.
7. `test_no_in_place_sed` misses backslash-continued lines.
8. The validator prints `[]` for an empty `name` or `model`.
9. `test_rejected_arguments` does not assert the reason for the rejection.
