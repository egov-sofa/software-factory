# Plan: The review folder moves out of `.git`, to a self-ignoring `.factory/review/`

**Status:** Withdrawn (2026-11-22: its premise was disproved; see "Withdrawn" below. Approved and built on
2026-11-21 on `feat/review-folder-outside-git`, three review rounds, not merged)
**Stage:** done
**Round:** 2
**Base:** main
**Branch:** feat/review-folder-outside-git
**Request:** "Move the review folder to a place that is writable inside the sandbox, is never committed, and keeps
every guarantee the current design has." Found by a real eval run on 2026-11-21: `/factory-review` (step 3) and
`/factory-build` (Stage 5) write the review folder to `$(git rev-parse --absolute-git-dir)/factory-review/`; inside
Claude Code's Bash sandbox `.git` is read-only (and so was `$TMPDIR` in that run), so `mkdir` failed with "Read-only
file system", the model reviewed the diff itself, the reviewer and security-auditor agents never ran and the report
format was lost. Also, as a small related part: record that `plugin eval` runs inside bubblewrap, that Claude Code's
Bash sandbox cannot nest inside it on GitHub's Ubuntu runners ("apply-seccomp: write /proc/self/setgroups (nested
userns is capability-restricted …)") but can in WSL, and verify `factory-review-starts-from-request` locally.

## Withdrawn

Measured on 2026-11-22 in WSL (Ubuntu 26.04, Claude Code 2.1.310), after the plan was built and reviewed:

- **Claude Code's own sandbox does not make `.git` read-only.** `claude -p` with `sandbox.enabled` ran
  `mkdir -p .git/factory-review/reports` and `mkdir -p .factory/review/reports` in a scratch repository: both
  succeeded, while `touch ~/outside-sentinel` in the same run was refused ("Read-only file system"), so the sandbox
  was on. Projects using the factory with the sandbox on were never affected.
- **The failure that started this plan is `plugin eval`'s.** Each eval run is itself inside bubblewrap, and there the
  Bash sandbox refused every write: `.git/factory-review/`, `$TMPDIR`, and on the built branch `.factory/review/`
  too, even Claude Code's own working-directory file under the sandbox's `tmp/`. The plan read that as "`.git` is
  read-only"; it was "nothing is writable".
- **So moving the folder fixes nothing real**, and it costs: a folder in the work tree is controlled by the branch
  under review, which took the symlink, tracked-file, submodule and `find` checks of three review rounds to close.
  The folder stays inside `.git`, where a branch cannot put files.

Kept from the build (in a separate change, folder unchanged): the conductor stops and reports when it cannot write
the review folder instead of reviewing the diff alone, and each round clears the last round's `round.diff`,
`checks.txt` and reports with fixed paths (no glob: zsh's `nomatch`, REV-1.1). The eval case
`factory-review-starts-from-request` is marked as not runnable under `plugin eval` for now.

The text below is the plan as approved, kept for the record with its review rounds.

## Goal

Anyone who runs the factory with Claude Code's sandbox on (not only the evals) gets the factory's review: the
conductor can write the reviewers' input, both read-only agents run, and their reports keep the checked format.
The folder stays out of every commit, one per worktree, and readable by both agents with only Read, Grep and Glob.

## Facts this plan relies on (read from the repository on 2026-11-21)

- **Why `.git` was chosen** (I26, `2026-11-19-enforce-agent-limits-with-hooks.md`, criterion 2): the reviewers lost
  Bash, so the conductor writes their input to files; `.git/` is "a folder git never commits, also in a worktree"
  (`--absolute-git-dir` is per worktree). No other reason is recorded. The evals plan already named the fallback
  `.factory-review/` in the working tree if agents could not read `.git` (probe (b)); they could, so it was not used.
- **What is in the folder:** `base.txt`, `changes.diff`, `files.txt`, `checks.txt`, `reports/<agent>.md`, and from
  round 2 `round.diff`. Today it is made with `mkdir -p` and never emptied, so `round.diff` and old reports from an
  earlier run stay in it.
- **Who reads it:** the reviewer and the security auditor (`tools: Read, Grep, Glob`) read "the review folder you were
  given"; the path comes from the conductor's prompt, the agents only describe the default in a parenthetical. The
  security auditor Greps `changes.diff` for secrets. The conductor saves reports to `$R/reports/<agent>.md` and passes
  that path to `factory_state.py report`.
- **`scripts/factory_state.py` does not know the folder:** it takes a report file as an argument and reads review
  rounds from the plan. **`/factory-ship` does not read reports either:** it ticks "Reviewed" from the plan's last
  `### Round` or from the conversation. So no script has to find the folder.
- **`claude/hooks/agent_guard.py`:** `check_path` makes the path relative to the work tree root and matches it against
  the agent's patterns. A path under `.factory/review/` matches none of the tester's, docs-writer's or planner's
  patterns (the docs-writer's `*.md` is root only), so they are already refused there; the implementer has no limit
  (as it has none for `.git/factory-review/` today, which is inside the root).
- **`.factory/` already exists** in projects made or onboarded by the factory (`answers.yml`, `standards/*.md`,
  optionally `docs.yml`). Nothing treats the folder itself as a marker: every check names a file in it.
- **`.gitignore` is a merged file** (`templates/file-kinds.txt`): `/factory-update` brings a factory change into
  existing projects with a 3-way merge (`git merge-file`); overlapping or adjacent edits become conflict markers. Each
  stack template (`templates/{generic,python,typescript}/.gitignore`) ends with the content guard block.
- **The content guard** (`check_content.py --all`) reads `git ls-files`, and the pre-commit hook reads what is staged:
  an ignored file is never scanned, a staged one is.
- **The evals:** `evals/_lib/make_repo.sh` `review_folder` copies factory-review step 3, and
  `scripts/tests/test_evals_suite.py` (`test_make_repo_writes_the_review_folder_as_factory_review_does`) checks the
  lines match, including the `R=` line. Four case prompts name `.git/factory-review/` (reviewer and security cases),
  and so do `evals/_probe/` (scaffold and prompt) and the scaffold tests (`.git/factory-review`). The
  `Scaffolds.test_every_scaffold` test already asserts `git status --porcelain` is empty after a scaffold.
- **The nested sandbox** is already handled in `scripts/run-evals.sh` and `evals/README.md` (#38, and made opt-in by the
  pull request that adds this plan):
  `factory-review-starts-from-request` is tagged `shell-commands` and runs on Linux only with
  `EVALS_NESTED_SANDBOX=yes`. `evals/README.md` carries a "Known failure (2026-11-21)" note pointing to this plan.
- **Other mentions of the old path:** `claude/agents/reviewer.md`, `claude/agents/security-auditor.md`,
  `claude/skills/factory-review/SKILL.md`, `claude/skills/factory-build/SKILL.md`, `docs/HOW-IT-WORKS.md:43`. The
  older plans and `scripts/tests/data/eval-result-probe.json` (a recorded result) mention it as history.

## Assumptions

- **Claude Code's sandbox lets a command write anywhere below its working directory** except its protected paths
  (`.git`, the Claude settings files); `.factory/review/` is not one of them. The WSL run of case 8 checks this.
- **The conductor runs from the work tree's root**, as the factory skills already assume. Run from a subfolder, the
  sandbox may not allow writes to the root's `.factory/` (see Risks).
- **No migration of the old folder:** nothing reads it after a round is recorded in the plan (below), so it is left
  where it is; it cannot be deleted from inside the sandbox anyway.

## Acceptance criteria

1. **New location.** `/factory-review` step 3 and `/factory-build` Stage 5 use
   `R="$(git rev-parse --show-toplevel)/.factory/review"` (one folder per worktree, because each worktree has its own
   top level). If the command fails, the conductor stops and says so instead of reviewing alone.
2. **The folder ignores itself.** Before writing, the conductor runs:
   ```bash
   if [ -L "${R%/review}" ] || [ -L "$R" ] || [ -L "$R/reports" ] || [ -n "$(git ls-files -- "$R")" ]; then
     echo "error: $R is a symlink or holds tracked files; nothing written" >&2; exit 1
   fi
   rm -rf "$R/round.diff" "$R/checks.txt" "$R/reports"                # nothing from an earlier run
   mkdir -p "$R/reports"
   printf '# software-factory review folder: scratch input for the reviewers, never committed\n*\n' > "$R/.gitignore"
   ```
   (Round 1 review: fixed paths instead of the `reports/*.md` glob, which zsh's `nomatch` fails on an empty folder;
   `checks.txt` cleared too; a symlink or tracked file there, which the branch under review controls, stops the
   conductor before any write.) Then the existing `base.txt`, `changes.diff`, `files.txt` and `checks.txt` lines unchanged. After that,
   `git status --porcelain` shows nothing for the folder, in any repository, with or without a project `.gitignore`
   line, and `git add -A` stages none of it.
3. **No stale input.** A new review round never sees `round.diff` or a report from an earlier run: both are removed
   before the round's files are written (`round.diff` is then written again in round 2 and later, as today).
4. **If the sandbox still refuses the write,** the skills tell the conductor to stop, show the error and suggest
   running from the project root or allowing writes to `.factory/review/`, never to review the diff itself. (This is
   the failure that hid the bug.)
5. **The agents** describe the default as "`.factory/review/` in the project (git-ignored)"; the security auditor
   Greps `changes.diff` by the file's full path, because a search over the folder may skip an ignored, hidden folder.
6. **New projects** get `.factory/review/` in their `.gitignore` (all three stack templates), placed before the
   content guard block, not at the end of the file, so `/factory-update` merges it into a project that appended its
   own lines without a conflict. Existing projects get it with their next `/factory-update`; until then the folder's
   own `.gitignore` covers them.
7. **Guard:** the tester, docs-writer and planner are refused an Edit or Write under `.factory/review/` (unit tests pin
   today's behaviour; no change to `PATHS`). The implementer stays unlimited.
8. **Evals:** `make_repo.sh` `review_folder` writes `.factory/review/` with the same lines as factory-review step 3,
   and `test_evals_suite.py` checks every line, the `R=` line included; the four reviewer and security case prompts and
   the probe name `.factory/review/`; no `evals/*/case.yaml` mentions `.git/factory-review`. Scaffolds still end with
   an empty `git status --porcelain`.
9. **Docs:** `docs/HOW-IT-WORKS.md` names the new folder and why it is not in `.git`; `evals/README.md` loses the
   "Known failure (2026-11-21)" note and records the WSL result of case 8.
10. **No old path left** outside `docs/plans/` and recorded test data: `grep -rn "absolute-git-dir)/factory-review\|\.git/factory-review"`
    finds nothing else.
11. **Verified in WSL (nested sandbox), by hand, about $1:** in the Ubuntu distro, from the factory clone,
    `EVALS_NESTED_SANDBOX=yes bash scripts/run-evals.sh --smoke --case factory-review-starts-from-request` passes:
    the trace shows the skill's `mkdir` succeeding, both agents launched, and `Verdict: CHANGES_REQUESTED`. This case
    cannot be verified in GitHub Actions (nested user namespaces are refused there, and `run-evals.sh` leaves it out
    with a note), nor on Windows (no shell can be granted).
12. **The portable cases still pass** after the prompt change: `bash scripts/run-evals.sh --smoke --case "reviewer-*"`
    and `--case "security-*"` (anywhere, about $2), and `--case _probe` (about $0.10), whose prompt also Greps the
    probe line in `.factory/review/probe.txt` to confirm the agents' Grep reaches an ignored folder.

## Design

**The folder** is `<work tree root>/.factory/review/`, holding the same files as today plus its own `.gitignore`
with `*`. That one file ignores the folder's contents and itself, the way `.ruff_cache/` and `.pytest_cache/` do, so
the guarantee "never committed" no longer depends on the project's `.gitignore`, on `/factory-update` having run, or on
the project being a factory project at all (`/factory-review` also runs in repositories the factory never touched).
The template line (criterion 6) is a second, visible layer for people reading `.gitignore`.

**Alternatives weighed:**

| Option | Writable in the sandbox | Never committed | Per worktree | Verdict |
|---|---|---|---|---|
| `.git/factory-review/` (today) | no | yes | yes | the bug |
| `$TMPDIR` or `mktemp -d` | no in the failing run; and outside the project, so Read may prompt | yes | only if the path is passed around, and nothing finds it after a compaction | rejected |
| Keep `.git`, ask users to allow it in sandbox settings | yes after a settings change | yes | yes | rejected: Claude Code protects `.git` on purpose, and every user would have to change a setting |
| `.factory-review/` at the root (the evals plan's fallback) | yes | only with a `.gitignore` | yes | close second: one more root folder, where `.factory/` already groups the factory's files |
| Try `.git`, fall back to `.factory/review/` | yes | yes | yes | rejected: two paths for the agents, the docs and the evals to keep in step |
| **`.factory/review/` with its own `.gitignore`** | **yes** | **yes, without help** | **yes** (`--show-toplevel`) | **chosen** |

**What happens when the project's `.gitignore` line is missing** (an old project, a non-factory repository): nothing
changes, the folder's own `.gitignore` hides it from `git status`, `git add -A`, `git stash -u` and the content guard.
**If both are gone** (someone deleted the inner file between rounds): the next round writes it again; until then
`git status` shows `.factory/review/` as untracked, and an accidental commit of `changes.diff` would go through the
pre-commit content guard, which flags a secret in it. That is the same last line of defence as for any file.

**Stale input.** Today nothing clears the folder. As built after review round 1, each round removes three fixed paths
before writing (`rm -rf "$R/round.diff" "$R/checks.txt" "$R/reports"`, then `mkdir -p "$R/reports"`): the files not
overwritten by command, and `checks.txt`, so a skipped write shows as a missing file. It uses no glob (zsh's `nomatch`
failed on an empty `reports/`) and never `rm -rf "$R"`: it cannot reach anything else, and a reader sees what it
deletes. Before that, the guard refuses a `.factory` holding any symlink (a submodule's included) or tracked files.

**Reports and `/factory-ship`.** Unchanged: reports are saved to `$R/reports/<agent>.md` and checked with
`$FS report <agent> <file>`; the round goes into the plan; `/factory-ship` reads the plan. No script learns the path.

**A run in progress during the upgrade.** The skills and agents are installed together (`install.sh`, or the built
plugin), and the folder is rebuilt at the start of every review round, so:
- a run between stages simply uses the new folder at its next Stage 5;
- a run interrupted inside Stage 5 (reports saved, round not yet committed) resumes at `Stage: review` and runs the
  reviewers again into the new folder: one extra review, no wrong result;
- a conversation that loaded the old skill text keeps the old path until it ends: without the sandbox it still
  works, with the sandbox it fails as today (and, with criterion 4 in the new text only, the next run says so).
The old `.git/factory-review/` stays behind, unused; `docs/HOW-IT-WORKS.md` says it can be deleted.

**Guard.** No change to `PATHS`: the tester, docs-writer and planner are already refused there, and the folder is
written by the conductor, which the guard does not limit. Tests pin it, so a later widening of a pattern (for example
`**/*.md` for the docs-writer) cannot silently let an agent edit the reviewers' input.

**The eval runner fact.** Nothing to build: #38 and the pull request that adds this plan already leave the
`shell-commands` case out on GitHub's runners and
opts in with `EVALS_NESTED_SANDBOX=yes`. This plan adds the verification (criterion 11) and replaces the "Known
failure" note with its result.

## Files

| File | Change |
|---|---|
| `claude/skills/factory-review/SKILL.md` | Step 3: new `R=`, the self-ignore and cleanup lines, stop if the folder cannot be written |
| `claude/skills/factory-build/SKILL.md` | Stage 5: the same |
| `claude/agents/reviewer.md`, `claude/agents/security-auditor.md` | Default folder description; the auditor Greps `changes.diff` by its full path |
| `templates/{generic,python,typescript}/.gitignore` | `.factory/review/` with a comment, before the content guard block |
| `evals/_lib/make_repo.sh` | `review_folder` writes `.factory/review/` with the skill's lines |
| `evals/{reviewer-finds-off-by-one,reviewer-approves-clean-change,security-finds-key-and-sqli,security-passes-clean-change}/case.yaml` | Prompt names `.factory/review/` |
| `evals/_probe/scaffold.sh`, `evals/_probe/case.yaml` | New path; the prompt also Greps the probe line |
| `scripts/tests/test_evals_suite.py` | In-step check with the new lines; scaffold tests read `.factory/review/`; no case mentions `.git/factory-review` |
| `scripts/tests/test_agent_guard.py` | Tester, docs-writer and planner refused under `.factory/review/` |
| `scripts/tests/test_factory_update.py` | The new template line merges into a project `.gitignore` with its own lines at the end, without a conflict |
| `docs/HOW-IT-WORKS.md` | New folder and why; the old one can be deleted |
| `evals/README.md` | Remove the known-failure note; record the WSL result and cost of case 8 |

Left unchanged on purpose: the older plans (history) and `scripts/tests/data/eval-result-probe.json` (a recorded run).

## Test plan

All free, in the self-test, except the last item:

- **`test_make_repo_writes_the_review_folder_as_factory_review_does`:** each folder line (the `R=` line, `mkdir`, the
  `.gitignore` line, the cleanup line and the four file lines) is in factory-review step 3, in factory-build Stage 5,
  and (with `main` for `<base>`) in `make_repo.sh`.
- **`test_every_scaffold`:** the review folder is `.factory/review/`, holds `.gitignore` with `*`, the planted line in
  `changes.diff`, and `git status --porcelain` stays empty; `git check-ignore .factory/review/changes.diff` succeeds
  in a repository with no `.gitignore` of its own.
- **`test_no_case_names_the_old_folder`:** no `evals/*/case.yaml` contains `.git/factory-review`.
- **`test_the_key_is_random_and_made_at_run_time`, `test_the_probe_scaffold`:** read the new path.
- **`test_agent_guard.Paths`:** `.factory/review/changes.diff` and `.factory/review/reports/reviewer.md` refused for
  tester, docs-writer and planner; allowed for the implementer (unchanged behaviour, pinned).
- **`test_factory_update`:** a project whose `.gitignore` gained a line at the end, updated to a factory whose
  template gained `.factory/review/` before the content guard block, merges cleanly and holds both lines.
- **Stale input, by hand:** run `/factory-review` twice on a scratch branch after putting a `round.diff` and an old
  `reports/reviewer.md` in the folder; both are gone before the reviewers start.
- **Evals (cost money, by hand):** criteria 11 and 12; record the scores and cost in `evals/README.md`.

## Risks / out of scope

- **The sandbox may refuse more than `.git`.** If a Claude Code version also protects `.factory/` or hidden folders,
  criterion 4 makes the failure visible instead of silent; the WSL run is the check. A conductor started in a
  subfolder may be refused the root's `.factory/` for the same reason.
- **Grep and Glob may skip the folder** (it is hidden and ignored, and ripgrep honours both when it walks a folder).
  Reading and Grepping by full file path works; the probe checks it. Today's `.git` folder had the same property.
- **Project tools that walk the tree** (a linter or formatter without `.gitignore` support) may now see
  `changes.diff`; the files are `.diff`, `.txt` and `.md`, which none of the three stacks' tools lint by default.
- **Two conversations reviewing the same worktree at once** overwrite each other's folder, as today. Out of scope.
- **The implementer can still write the folder** (as it can `.git/factory-review/` today); it runs before the folder is
  rebuilt each round, so this changes no review. Out of scope (open question 3).
- **Case 8 stays local-only:** it cannot run on GitHub's runners or Windows, so a regression in it shows only when
  someone runs it in WSL or on Linux or macOS.
- **Out of scope:** deleting the old `.git/factory-review/` automatically, the main conversation's sandbox settings,
  making case 8 run in CI.

## Open questions for the user

**Answered 2026-11-21:** the maintainer accepted the recommended answer to every question below; build to those.

1. **Template `.gitignore` line:** add `.factory/review/` to the three stack templates, as a visible second layer?
   *Recommended: yes*, placed before the content guard block so `/factory-update` merges without a conflict; the
   folder's own `.gitignore` remains the real guarantee.
2. **Clearing the folder:** remove only `round.diff` and `reports/*.md` (`rm -f`), or wipe it (`rm -rf "$R"`) each
   round? *Recommended: `rm -f` on fixed names*: the other files are overwritten anyway, and a targeted delete is
   easier to trust and less likely to trigger a permission prompt. *As built after review round 1:*
   `rm -rf "$R/round.diff" "$R/checks.txt" "$R/reports"`, still fixed names but no glob (zsh), and `checks.txt` too.
3. **Guard the folder for the implementer too** (refuse its Edit and Write under `.factory/review/`)? *Recommended:
   no, not now*: the folder is rebuilt after every implementer run, so it cannot change a review; revisit if a stage
   order ever changes.
4. **Old folder:** leave `.git/factory-review/` in existing clones, or have the skill remove it when it can?
   *Recommended: leave it*, and say in `docs/HOW-IT-WORKS.md` that it can be deleted; removing it would need a write
   to `.git`, the very thing that fails in the sandbox.
5. **Verifying case 8:** is a WSL smoke run (one run per arm, about $1) enough before merging, or a full three-run
   case? *Recommended: the smoke run before merging, the full case at the next manual evals run*.

## Review rounds

### Round 1 (reviewed 7977b46)
| ID | Severity | Location | Finding | Answer |
|---|---|---|---|---|
| REV-1.1 | MAJOR | claude/skills/factory-review/SKILL.md:27, factory-build/SKILL.md:110, evals/_lib/make_repo.sh:46 | `rm -f "$R"/reports/*.md` fails under zsh (macOS default, `nomatch`) when `reports/` is empty, so every first review stops | fixed: no glob; `rm -rf "$R/round.diff" "$R/checks.txt" "$R/reports"` before `mkdir -p "$R/reports"`, the same line in both skills and make_repo.sh; `test_a_new_round_leaves_no_stale_input` runs it on an empty `reports/` under bash, and under zsh where installed → resolved (round 2) |
| REV-1.2 | MINOR | evals/README.md | case 8's WSL result is not recorded yet (waits for criterion 11) | |
| SEC-1.1 | MEDIUM | claude/skills/factory-review/SKILL.md, factory-build/SKILL.md, evals/_lib/make_repo.sh | the branch under review controls `.factory/review`: a committed symlink redirects the writes and deletes (e.g. the root `.gitignore` becomes `*`), and tracked files there are not ignored, so a later commit picks up the diff | fixed: before any write or delete, the three places stop with "error: $R is a symlink or holds tracked files; nothing written" (`exit 1`) when `.factory`, `$R` or `$R/reports` is a symlink or `git ls-files -- "$R"` prints anything; both skills say to stop, show the error and ask the user to remove the link or untrack the files; tests `test_a_symlinked_folder_is_refused` (target untouched; skipped where symlinks cannot be made) and `test_tracked_files_in_the_folder_are_refused` → resolved (round 2) |
| SEC-1.2 | LOW | claude/skills/factory-review/SKILL.md, factory-build/SKILL.md | `checks.txt` is not cleared, so a skipped write leaves the last round's results looking current | fixed: `"$R/checks.txt"` is in the cleanup line, so a skipped write shows as a missing file; `test_a_new_round_leaves_no_stale_input` checks it is gone → resolved (round 2) |
Result: reviewer CHANGES_REQUESTED, security ISSUES_FOUND, tests PASS; blocking 1
Not blocking: REV-1.2 (MINOR), SEC-1.1 (MEDIUM), SEC-1.2 (LOW); the conductor fixes SEC-1.1 and SEC-1.2 in the same round

### Round 2 (reviewed 91418d9)
| ID | Severity | Location | Finding | Answer |
|---|---|---|---|---|
| REV-2.1 | MINOR | docs/plans/2026-11-21-review-folder-outside-git.md (Design, "Stale input") | still describes `rm -f` on two names, not the `rm -rf` of three fixed paths built after round 1 | fixed: the Design paragraph now describes the cleanup and guard as built |
| SEC-2.1 | MEDIUM | claude/skills/factory-review/SKILL.md, factory-build/SKILL.md, evals/_lib/make_repo.sh | a `.factory` submodule escapes `git ls-files`, so a symlink committed inside it (e.g. `review/changes.diff`) gets past the check and the write follows it | fixed: the guard refuses any symlink under `.factory` (`find "${R%/review}" -type l`, after the `-L .factory` test), so a link git cannot see is refused; test_an_untracked_link_inside_the_folder_is_refused, run in WSL |
Result: reviewer APPROVE, security PASS, tests PASS; blocking 0
Not blocking: REV-2.1 (MINOR), SEC-2.1 (MEDIUM); the conductor fixes both in the last fix round

### Round 3 (reviewed 3335e81)
| ID | Severity | Location | Finding | Answer |
|---|---|---|---|---|
| REV-3.1 | MINOR | claude/skills/factory-review/SKILL.md, factory-build/SKILL.md, evals/_lib/make_repo.sh | before `.factory` exists, `find` prints "No such file or directory", which a conductor told to stop on errors may read as a failure | fixed: `find` runs only when `.factory` exists; test_a_first_review_writes_no_error |
| SEC-3.1 | LOW | same | the check read only `find`'s output, so a failing `find` (Windows' `find.exe` first on PATH) passed it | fixed: a failed `find` refuses ("could not check"); test_a_failing_find_refuses |
Result: reviewer APPROVE, security PASS, tests PASS; blocking 0
Not blocking: REV-3.1 (MINOR), SEC-3.1 (LOW), both fixed by the conductor after the round (no fix round counted)
