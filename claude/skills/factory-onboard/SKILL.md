---
name: factory-onboard
description: Add software-factory standards and shared services to an existing project - a project CLAUDE.md, CI using the factory's reusable workflows, the Claude PR review and @claude mentions, the content guard with its git hooks, a PR template, Dependabot, and .editorconfig. Use on projects not created with /factory-new.
---

# Factory Onboard

Bring an existing project up to factory standards **without breaking anything**.
Factory location: `{{FACTORY_HOME}}`

## 1. Detect
- Stack: `package.json` → typescript/node; `pyproject.toml` / `requirements.txt` → python; anything else → generic.
- The real commands: read `package.json` scripts, `pyproject.toml`, `Makefile`, and existing CI files. **Use the commands the project actually has**; don't invent them.
- Existing files: `CLAUDE.md`, `.github/workflows/*`, `.github/pull_request_template.md`, `.editorconfig`, `.github/dependabot.yml`, `.claude/skills/pr-review/SKILL.md`, `scripts/hooks/`, and `git config core.hooksPath` (another hook manager such as husky or pre-commit may already own the hooks).
- GitHub owner: `gh api user -q .login`.

## 2. Propose
Show the user a table of files to **add** and files that **already exist** (to be skipped or merged), then ask for confirmation. Never overwrite an existing file without explicit approval.

The shared services are opt-in, one by one (see `{{FACTORY_HOME}}/docs/SHARED-SERVICES.md`). Ask which ones the project wants, and explain each in one plain sentence:
- **CI pipeline:** lint, build and test on every push.
- **Content guard:** blocks secrets, public IPs, internal host names and a private denylist in pull requests and, through git hooks, before each commit. Free, no setup.
- **Claude review and @claude mentions:** Claude reviews each pull request against a checklist. Costs API credit per review and needs a one-time setup, so it stays off until the variable `CLAUDE_REVIEW_ENABLED` is `true`.
If the project would need project-specific changes to a shared workflow to fit, say so and suggest keeping its own workflow instead: forcing it into the shared one is worse for both.

## 3. Apply (on a branch `chore/factory-onboard`)
- **CLAUDE.md:** base it on `{{FACTORY_HOME}}/templates/<stack>/CLAUDE.md`, rewritten with this project's real commands, folder structure (from `ls` and a quick look around) and conventions you observed in the code.
- **CI:** copy `{{FACTORY_HOME}}/templates/<stack>/.github/workflows/ci.yml` and replace `{{GITHUB_OWNER}}`. If the project already has CI, show both and ask which to keep.
- **From `{{FACTORY_HOME}}/templates/_shared/`:** `.editorconfig`, `.github/pull_request_template.md`, `.github/dependabot.yml` (keep only the ecosystems this project uses).
- **Shared services the user chose**, from `{{FACTORY_HOME}}/templates/_shared/`, replacing `{{GITHUB_OWNER}}` (and `{{PROJECT_NAME}}` in the checklist):
  - Claude review: `.github/workflows/claude-review.yml`, `.github/workflows/claude-mention.yml`, and `.claude/skills/pr-review/SKILL.md`. Fill its "Project rules" section with rules you observed in this codebase, and tell the user the setup steps in `SHARED-SERVICES.md` ("Turning on the Claude services").
  - Content guard: `.github/workflows/content-guard.yml`; copy `{{FACTORY_HOME}}/scripts/check_content.py` to `scripts/` and `{{FACTORY_HOME}}/scripts/hooks/*` to `scripts/hooks/`, add `.content-denylist` to `.gitignore`, then run `python3 scripts/check_content.py --all`. Fix or mark (`content-ok`) what it finds **before** enabling the hooks with `git config core.hooksPath scripts/hooks`; if another hook manager owns the hooks, don't change `core.hooksPath`; show the user how to call the guard from their existing hook instead.
  - All callers use `@v1`, never `@main`.
- **docs/plans/.gitkeep**, so the factory pipeline has somewhere to put plans.
- Make sure `.gitignore` covers `.env`, plus dependency and build folders for the stack.

## 4. Verify and commit
Run lint and test commands to confirm nothing broke. Commit with `chore: adopt software-factory standards`. Suggest `/factory-ship` to open a PR.
