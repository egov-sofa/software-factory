---
name: factory-build
description: Run the full software-factory pipeline for a feature - plan, user approval, implement, test, parallel code and security review, fix loop, docs. Use when the user wants to build a feature end to end.
argument-hint: "[--auto] <feature description>"
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
4. Read the project's `CLAUDE.md` to learn the test and lint commands. If there is none, suggest `/factory-onboard` afterwards, and continue.

## Stage 1: Plan 🧭
Launch the `planner` agent with the full request and the current date. Wait for the plan path.

## Stage 2: Approval gate ✋
Show the user the plan summary and the plan file path. Ask them to **approve**, **request changes**, or **cancel**.
- Changes → send their feedback to the `planner` agent to revise the same file, then ask again.
- Cancel → stop and leave the branch for them.
Explain briefly: "Approving the plan is the cheapest point to catch a misunderstanding; fixing it after the code is written costs much more."

## Stage 3: Implement 🔨
Launch the `implementer` agent with the plan path. When it reports back, commit:
`git add -A && git commit -m "feat: <summary>"` (use the right Conventional Commit type).
Committing between stages gives a checkpoint to return to if a later stage goes wrong.

## Stage 4: Test 🧪
Launch the `tester` agent with the plan path. If it added tests, commit them (`test: …`).
If the result is FAIL, treat the failures as BLOCKER findings and go to Stage 6.

## Stage 5: Review 🔍🛡️
Launch the `reviewer` and `security-auditor` agents **in parallel, in one message**, both with the plan path.
Combine their findings into one list. Blocking = reviewer BLOCKER/MAJOR + security CRITICAL/HIGH + any test failures.

## Stage 6: Fix loop 🔁 (max 2 rounds)
If there are blocking findings:
1. Send the blocking findings to the `implementer` agent.
2. Commit (`fix: address review findings`).
3. Re-run the `tester` agent, then the reviewers in parallel again.
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
