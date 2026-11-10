---
name: factory-ship
description: Commit remaining work, push the current feature branch, and open a GitHub pull request with a generated description. Use when a feature is finished and ready for review/CI.
argument-hint: "[--draft]"
---

# Factory Ship

Get the current branch onto GitHub as a pull request. Explain each step in one plain sentence as you go.

## 1. Safety checks
- Current branch must **not** be `main`/`master`. If it is, stop and offer to create a feature branch.
- Run `gh auth status`. If not logged in, tell the user to run `! gh auth login` and stop.
- Run `git remote -v`. If there's no `origin`, ask whether to create a GitHub repo (`gh repo create <name> --private --source . --push`, or `--public`). This is a visible, outward-facing action, so **always ask** first.
- Scan the changes for secrets: `git diff origin/main...HEAD 2>/dev/null || git diff main...HEAD`, grepping for keys, tokens and passwords, and check that no `.env` file is staged. If you find anything, **stop** and warn the user.

## 2. Final checks
Run the project's lint and test commands from `CLAUDE.md`. If they fail, stop, show the failures, and suggest fixing first. Don't open a PR with known-failing tests.

## 3. Commit leftovers
If `git status` shows changes, show them to the user and commit with a Conventional Commit message.

## 4. Push
`git push -u origin <branch>`

## 5. Open the PR
Build the description from the plan in `docs/plans/` (if any) and `git log main..HEAD`:
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
- [x] Tests pass locally
- [x] Reviewed by factory reviewer + security-auditor
- [ ] CI green
Plan: docs/plans/<file>.md
```
Then run `gh pr create --base main --title "<conventional title>" --body "<body>"`, adding `--draft` if `$ARGUMENTS` contains `--draft`.

## 6. Report
Give the PR URL. Explain: "GitHub Actions is now running CI on this PR. When it shows a green check, you can merge it (Squash and merge is recommended)." Offer to check CI status with `gh pr checks --watch`.
**Never merge the PR yourself** unless the user explicitly asks.
