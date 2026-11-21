---
name: factory-ship
description: Commit remaining work, push the current feature branch, and open a GitHub pull request with a generated description. Started by typing /factory-ship when a feature is finished.
argument-hint: "[--draft]"
disable-model-invocation: true
---

# Factory Ship

Get the current branch onto GitHub as a pull request. Explain each step in one plain sentence as you go.

**Base branch:** the plan's `**Base:**` if a plan with pipeline state belongs to this branch (`$FS find --branch
"$(git branch --show-current)"`, then `$FS state <plan>`); else `git symbolic-ref --quiet --short
refs/remotes/origin/HEAD` without `origin/`; else `main` if it exists; else `master`; else ask the user. `$FS` is
`python3 "{{FACTORY_HOME}}/scripts/factory_state.py"` (or `python`).


## 1. Safety checks
- Current branch must **not** be `main`/`master` or the base branch. If it is, stop and offer to create a feature branch.
- Run `gh auth status`. If not logged in, tell the user to run `! gh auth login` and stop.
- Run `git remote -v`. If there's no `origin`, ask whether to create a GitHub repo (`gh repo create <name> --private --source . --push`, or `--public`). This is a visible, outward-facing action, so **always ask** first.
- Scan the changes for secrets: `git diff origin/<base>...HEAD 2>/dev/null || git diff <base>...HEAD`, grepping for keys, tokens and passwords, and check that no `.env` file is staged. If you find anything, **stop** and warn the user.

## 2. Final checks
Run the project's lint and test commands from `AGENTS.md` (`CLAUDE.md` in projects from before AGENTS.md). If they fail, stop, show the failures, and suggest fixing first. Don't open a PR with known-failing tests.

## 3. Commit leftovers
If `git status` shows changes, show them to the user and commit with a Conventional Commit message.

## 4. Push
`git push -u origin <branch>`

## 5. Open the PR
Build the description from the plan in `docs/plans/` (if any) and `git log <base>..HEAD`:
```markdown
## What
<1–3 sentences>
## Why
<the user need>
## How
- <key changes>
## Testing
- <tests added and run; result>
## Checklist
- [ ] Tests pass locally
- [ ] Reviewed by factory reviewer + security-auditor
- [ ] CI green
Plan: docs/plans/<file>.md
```
Tick a box only for something that actually happened: "Tests pass locally" when you ran the test suite in this session and it passed (run it now if needed), "Reviewed" only when `/factory-build` or `/factory-review` ran on this branch and its result is in this conversation, or the plan's last `### Round` under `## Review rounds` reads `blocking 0` (findings marked `user: drop` do not count) and nothing was committed after the commit it reviewed except the plan and docs. Leave the others unticked; a ticked box that nobody checked misleads the reviewer.
Then run `gh pr create --base <base> --title "<conventional title>" --body "<body>"`, adding `--draft` if `$ARGUMENTS` contains `--draft`.

## 6. Report
Give the PR URL. Explain: "GitHub Actions is now running CI on this PR. When it shows a green check, you can merge it (Squash and merge is recommended)." Offer to check CI status with `gh pr checks --watch`.
**Never merge the PR yourself** unless the user explicitly asks.
