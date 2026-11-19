---
name: factory-build
description: Run the full software-factory pipeline for a feature - plan, user approval, implement, test, parallel code and security review, fix loop, docs. Started by typing /factory-build <feature>.
argument-hint: "[--auto] <feature description>"
disable-model-invocation: true
---

# Factory Build Pipeline

You are the **conductor**. You coordinate specialist agents; you do not write the feature code yourself.
Request: **$ARGUMENTS**

If the arguments start with `--auto`, skip the plan approval in Stage 2 (still show the plan summary).
Before each stage, tell the user in **one plain sentence** what is about to happen and why. The user is learning, so make the process visible.

## Stage 0: Preflight
1. Confirm this is a git repo (`git rev-parse --is-inside-work-tree`). If not, offer to run `git init` and make an initial commit, then stop until the user answers.
2. Run `git status --porcelain`. If there are uncommitted changes, ask the user whether to commit them, stash them, or continue on top of them.
3. Find the base branch (`main`, or `master`). Create and switch to `feat/<kebab-slug-of-request>` (or `fix/…` for bug fixes). If already on a non-main feature branch, ask whether to stay on it.
4. Read the project's `AGENTS.md` (`CLAUDE.md` in projects from before AGENTS.md) to learn the test and lint commands. If there is none, suggest `/factory-onboard` afterwards, and continue.

## Stage 1: Plan 🧭
Launch the `planner` agent with the full request and the current date. Wait for the plan path.

## Stage 2: Approval gate ✋
Show the user the plan summary and the plan file path. Ask them to **approve**, **request changes**, or **cancel**.
- Changes → send their feedback to the `planner` agent to revise the same file, then ask again.
- Cancel → stop and leave the branch for them.
Explain briefly: "Approving the plan is the cheapest point to catch a misunderstanding; fixing it after the code is written costs much more."
Once approved (with `--auto`, straight away), commit the plan on its own: `git add -- <plan path> && git commit -m "docs: plan for <title>"`. Any later change to the approved plan then shows up in the diff.

## Stage 3: Implement 🔨
Launch the `implementer` agent with the plan path. When it reports back, **check the report before committing**:
- If it says it stopped (the plan was wrong or impossible), or any line under **Commands run** failed, do not commit. Show the user the report and offer: send it back to the `planner` to revise the plan (then Stage 2 again), let the implementer try again, or stop.
- Otherwise stage only the files under **Files changed**: `git add -- <file> <file> …`. Then run `git status --porcelain`; if anything else changed, show it to the user and ask whether it belongs in the commit.
- Commit: `git commit -m "feat: <summary>"` (use the right Conventional Commit type).

Committing between stages gives a checkpoint to return to if a later stage goes wrong; checking the report first keeps a half-done change out of that checkpoint.

## Stage 4: Test 🧪
Launch the `tester` agent with the plan path. If it added tests, commit them (`test: …`).
If the result is FAIL, treat the failures as BLOCKER findings and go to Stage 6.

## Stage 5: Review 🔍🛡️
Prepare the reviewers' input first: they have no shell, so they read it from files. With `<base>` the base branch
(Stage 0) and `R="$(git rev-parse --absolute-git-dir)/factory-review"` (a folder git never commits, also in a worktree):
```bash
mkdir -p "$R"
{ git diff <base>...HEAD; git diff HEAD; } > "$R/changes.diff"     # committed since <base>, then uncommitted
{ git diff --name-only <base>...HEAD; git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u > "$R/files.txt"
```
Write `$R/checks.txt` with the latest test and lint results (the tester's report, or run the commands from
`AGENTS.md`), followed by the dependency audit when the project has one (`npm audit --omit=dev`, or `pip-audit` /
`uvx pip-audit`). Then pass the folder's full path to both reviewers.
Launch the `reviewer` and `security-auditor` agents **in parallel, in one message**, both with the plan path and
the review folder.
Combine their findings into one list. Blocking = reviewer BLOCKER/MAJOR + security CRITICAL/HIGH + any test failures.

## Stage 6: Fix loop 🔁 (max 2 rounds)
If there are blocking findings:
1. Send the blocking findings to the `implementer` agent.
2. Stage the files under **Files changed** (as in Stage 3) and commit (`fix: address review findings`), even when a
   command under **Commands run** still fails: the tester and reviewers see that failure in step 3 as a blocker, and
   it counts toward the 2 rounds. Stop and ask the user only if the implementer reports that it stopped or cannot
   fix a finding.
3. Re-run the `tester` agent, prepare the review folder again (Stage 5), then run the reviewers in parallel again.
After 2 rounds, if blockers remain, **stop** and present them to the user with your recommendation. Never loop forever.
List MINOR/LOW findings in the summary without fixing them automatically.

## Stage 7: Docs 📝
Launch the `docs-writer` agent with the plan path. Commit (`docs: …`).

## Stage 8: Summary
Present:
```
✅ Feature: <title>    🌿 Branch: <branch>
📋 Plan: <path>
Acceptance criteria: X/Y met
Tests: PASS (N tests)    Review: APPROVED    Security: PASS
Commits: <git log --oneline base..HEAD>
Not fixed (minor): <list or "none">
Try it: <how to manually check the feature>
Next: run /factory-ship to push and open a pull request.
```
Never push or open a PR from this skill; that's `/factory-ship`.
