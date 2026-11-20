---
name: factory-build
description: Run the full software-factory pipeline for a feature - plan, user approval, implement, test, parallel code and security review, fix loop, docs. Started by typing /factory-build <feature>, or /factory-build --resume to continue an interrupted run.
argument-hint: "[--auto] [--resume [plan path]] <feature description>"
disable-model-invocation: true
---

# Factory Build Pipeline

You are the **conductor**. You coordinate specialist agents; you do not write the feature code yourself.
Request: **$ARGUMENTS**

If the arguments start with `--auto`, skip the plan approval in Stage 2 (still show the plan summary).
If they contain `--resume`, continue an interrupted run (see "Resume" below) instead of starting a new one.
Before each stage, tell the user in **one plain sentence** what is about to happen and why. The user is learning, so make the process visible.

## Pipeline state
The plan file records where the run is, so a crash, a compaction or a new session can continue it. Right under
`**Status:**` the plan holds four lines that you (not the agents) keep up to date:
```
**Stage:** implement
**Round:** 0
**Base:** main
**Branch:** feat/example
```
`Stage` is the **next** stage to run; `Round` the number of fix rounds completed (0 to 2). Every stage ends with a
commit that also writes the next state, so the state on disk always matches the last checkpoint:

| Stage done | Commit | Writes |
|---|---|---|
| 2 Approval | `docs: plan for <title>` | the four lines, `Stage: implement`, `Round: 0` |
| 3 Implement | `feat: …` | `Stage: test` |
| 4 Test | `test: …`, or `chore: factory pipeline at review` if no tests were added | `Stage: review` |
| 5 Review | `docs: review round <n>` | the round in `## Review rounds`; `Stage: fix`, or `Stage: docs` when nothing blocks |
| 6 Fix | `fix: address review findings` | the answers; `Round` + 1; `Stage: test` |
| 7 Docs | `docs: …` (alone if nothing else changed) | `Stage: done` |

**Trust the plan over your memory:** after an interruption, a compaction, or whenever unsure, read stage, round and
base from the plan with `$FS state <plan>`.

`$FS` is `python3 "{{FACTORY_HOME}}/scripts/factory_state.py"` (or `python` if there is no `python3`). If neither
exists, apply its rules by reading: the header lines below, and the consistency rules in its source.

## Checking reports
Every agent's report starts with fixed header lines (`Verdict:`, `Blocking:`, `Result:` …). Save each report to
`$R/reports/<agent>.md` (`$R` below) and run `$FS report <agent> <file>`, adding `--ids <IDs> --round <n>` for the
implementer in a fix round and for the reviewers from round 2 on. It prints the values (`verdict=APPROVE`,
`blocking=0` …): gate on those, not on your reading of the prose.
- **Exit 1:** send the parser's message back to the **same** agent once and ask for a corrected report (no new work).
- **Still wrong:** do not guess. Stop, show the user the report and the message, and offer: rerun the agent, decide by
  hand, or stop. A rejected report never counts as a pass and never uses up a fix round.

## Stage 0: Preflight
1. Confirm this is a git repo (`git rev-parse --is-inside-work-tree`). If not, offer to run `git init` and make an initial commit, then stop until the user answers.
2. Run `git status --porcelain`. If there are uncommitted changes, ask the user whether to commit them, stash them, or continue on top of them.
3. **Base branch**, detected once: `git symbolic-ref --quiet --short refs/remotes/origin/HEAD` without the `origin/`;
   else `main` if it exists; else `master`; else ask the user. Tell every agent `Base branch: <base>` in its prompt.
4. Create and switch to `feat/<kebab-slug-of-request>` (or `fix/…` for bug fixes). If already on a feature branch
   (not the base), ask whether to stay on it.
5. Read the project's `AGENTS.md` (`CLAUDE.md` in projects from before AGENTS.md) to learn the test and lint commands. If there is none, suggest `/factory-onboard` afterwards, and continue.

## Resume
With `--resume [plan path]`:
1. Without a path, run `$FS find --branch "$(git branch --show-current)"`. No plan → say so and offer a fresh run;
   several → list them and ask which. A path whose `Branch` is not the current branch → offer to switch to it (only
   on a clean tree).
2. `$FS state <plan>`: `legacy` → stop: "this plan was written before pipeline state; continue by hand or with
   /factory-review". `Stage: done` → say so and suggest `/factory-ship`. Otherwise use its `Base` and announce the
   stage and round.
3. If `git status --porcelain` is not empty, show the changes and ask: **stash** (recommended:
   `git stash push -u -m "factory-resume <stage>"`, then rerun the stage from its checkpoint), **keep** (rerun the
   stage on top; tell the implementer uncommitted changes are present), or **stop**. Never discard changes.
4. Continue at the stage named. `fix` with `Round: 2` means the cap was reached: present the open blockers (Stage 6).
`--resume` combines with `--auto`, which then only skips approving plan revisions.

## Stage 1: Plan 🧭
Launch the `planner` agent with the full request, the current date and the base branch. Check its report (`Plan:`,
`Criteria:`) and wait for the plan path.

## Stage 2: Approval gate ✋
Show the user the plan summary and the plan file path. Ask them to **approve**, **request changes**, or **cancel**.
- Changes → send their feedback to the `planner` agent to revise the same file, then ask again.
- Cancel → stop and leave the branch for them.
Explain briefly: "Approving the plan is the cheapest point to catch a misunderstanding; fixing it after the code is written costs much more."
Once approved (with `--auto`, straight away), add the four pipeline lines under `**Status:**` (`Stage: implement`,
`Round: 0`, the base, the branch) and commit the plan on its own: `git add -- <plan path> && git commit -m "docs: plan for <title>"`.
Any later change to the approved plan then shows up in the diff.

## Stage 3: Implement 🔨
Launch the `implementer` agent with the plan path and the base branch. When it reports back, **check the report before committing**:
- `Result: STOPPED` (the plan was wrong or impossible) or `Commands: FAIL`: do not commit. Show the user the report and offer: send it back to the `planner` to revise the plan (then Stage 2 again), let the implementer try again, or stop.
- Otherwise stage only the files under **Files changed**: `git add -- <file> <file> …`. Then run `git status --porcelain`; if anything else changed, show it to the user and ask whether it belongs in the commit.
- Set `Stage: test` in the plan, stage it too, and commit: `git commit -m "feat: <summary>"` (use the right Conventional Commit type).

Committing between stages gives a checkpoint to return to if a later stage goes wrong; checking the report first keeps a half-done change out of that checkpoint.

## Stage 4: Test 🧪
Launch the `tester` agent with the plan path and the base branch. Set `Stage: review` and commit: with the tests it
added (`test: …`), or only the plan (`git commit -m "chore: factory pipeline at review" -- <plan>`).
If the result is `FAIL`, its failures are blocking findings `TEST-<n>.<k>` for the next round, with `<n>` that round's number (Stage 5): record them when
you log that round in Stage 5 (still run the review, so one round covers both).

## Stage 5: Review 🔍🛡️
Prepare the reviewers' input first: they have no shell, so they read it from files. With `<base>` from the plan and
`R="$(git rev-parse --absolute-git-dir)/factory-review"` (a folder git never commits, also in a worktree):
```bash
mkdir -p "$R/reports"
echo "<base>" > "$R/base.txt"
{ git diff <base>...HEAD; git diff HEAD; } > "$R/changes.diff"     # committed since <base>, then uncommitted
{ git diff --name-only <base>...HEAD; git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u > "$R/files.txt"
```
Write `$R/checks.txt` with the latest test and lint results (the tester's report, or run the commands from
`AGENTS.md`), followed by the dependency audit when the project has one (`npm audit --omit=dev`, or `pip-audit` /
`uvx pip-audit`).
**The round number** `<n>` is one more than the highest `### Round <number>` already in the plan (1 if there is
none), the same rule `/factory-review` uses, so IDs never repeat; the fix-round cap reads `Round`, not `<n>`.
**Round 2 and later** (the plan already has a round): also write `$R/round.diff` with
`{ git diff "$($FS last-reviewed <plan>)"..HEAD; git diff HEAD; }`, and tell the reviewers the round number.

Launch the `reviewer` and `security-auditor` agents **in parallel, in one message**, with the plan path, the review
folder's full path, the base branch and the round number. Check both reports; from round 2 pass each its own earlier
blocking IDs that are not settled yet (`--ids REV-… --round <n>`, `--ids SEC-… --round <n>`). Settled means its
Answer reads `resolved in round …` or `user: drop`: a dropped finding is never passed again, so it cannot block.

Then append the round to `## Review rounds` at the end of the plan (create the section on the first round), with
the round number `<n>` and the commit the folder was built from:
```
### Round <n> (reviewed <short HEAD>)
| ID | Severity | Location | Finding | Answer |
|---|---|---|---|---|
| REV-<n>.1 | BLOCKER | src/page.ts:42 | off-by-one on the last page | |
Result: reviewer CHANGES_REQUESTED, security PASS, tests PASS; blocking 1
Not blocking: REV-<n>.2 (MINOR) naming in src/page.ts
```
IDs are `REV-<round>.<number of the finding in the report>`, `SEC-…` and `TEST-…`. From round 2, also write each
earlier finding's outcome from the reviewers' `## Earlier findings` into its Answer cell (`resolved in round <n>`,
`kept`). Blocking = the reviewer's and the security auditor's parsed `blocking` values (their new blocking findings
plus earlier ones they report still open; write still-open ones in the round's table too) + test failures. Set
`Stage: fix` (blocking > 0) or `Stage: docs`, and commit only the plan, even if other changes are staged:
`git commit -m "docs: review round <n>" -- <plan>`.

## Stage 6: Fix loop 🔁 (max 2 rounds)
If there are blocking findings:
1. **Disputed findings first.** A finding the implementer answered `disagree` and the reviewer reports `still open`
   is disputed: do not send it to the implementer again. Show the user the finding, the answer and the reviewer's
   reply, ask **fix** or **drop**, and write `user: fix` or `user: drop` in its Answer cell. `user: fix` goes to the
   implementer with the others; `user: drop` no longer blocks.
2. **Cap:** if `Round` is already 2 and blockers remain, **stop** and present them to the user with your
   recommendation. Never loop forever.
3. Send the remaining blocking findings, with their IDs, to the `implementer` agent. Check its report with
   `--ids <those IDs>`: every ID needs `fixed:` or `disagree:` under `## Answers`.
4. Write each answer into its Answer cell, add 1 to `Round`, set `Stage: test`, stage the files under **Files
   changed** (as in Stage 3) and the plan, and commit (`fix: address review findings`), even when `Commands: FAIL`:
   the tester and reviewers see that failure as a blocker, and it counts toward the 2 rounds. Stop and ask the user
   only if the implementer reports `Result: STOPPED`.
5. Continue at Stage 4.
List MINOR/LOW findings in the summary without fixing them automatically.

## Stage 7: Docs 📝
Launch the `docs-writer` agent with the plan path and the base branch. Check that the four pipeline lines are still
as you left them (`$FS state <plan>`) and restore them if not. Set `Stage: done` and commit (`docs: …`).

## Stage 8: Summary
Present:
```
✅ Feature: <title>    🌿 Branch: <branch>
📋 Plan: <path>
Acceptance criteria: X/Y met
Tests: PASS (N tests)    Review: APPROVED    Security: PASS    Fix rounds: <Round>
Commits: <git log --oneline base..HEAD>
Not fixed (minor): <list or "none">
Try it: <how to manually check the feature>
Next: run /factory-ship to push and open a pull request.
```
Never push or open a PR from this skill; that's `/factory-ship`.
