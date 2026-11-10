---
name: factory-onboard
description: Add software-factory standards to an existing project - a project CLAUDE.md, a CI workflow using the factory's reusable workflows, a PR template, Dependabot, and .editorconfig. Use on projects not created with /factory-new.
---

# Factory Onboard

Bring an existing project up to factory standards **without breaking anything**.
Factory location: `{{FACTORY_HOME}}`

## 1. Detect
- Stack: `package.json` → typescript/node; `pyproject.toml` / `requirements.txt` → python; anything else → generic.
- The real commands: read `package.json` scripts, `pyproject.toml`, `Makefile`, and existing CI files. **Use the commands the project actually has**; don't invent them.
- Existing files: `CLAUDE.md`, `.github/workflows/*`, `.github/pull_request_template.md`, `.editorconfig`, `.github/dependabot.yml`.
- GitHub owner: `gh api user -q .login`.

## 2. Propose
Show the user a table of files to **add** and files that **already exist** (to be skipped or merged), then ask for confirmation. Never overwrite an existing file without explicit approval.

## 3. Apply (on a branch `chore/factory-onboard`)
- **CLAUDE.md:** base it on `{{FACTORY_HOME}}/templates/<stack>/CLAUDE.md`, rewritten with this project's real commands, folder structure (from `ls` and a quick look around) and conventions you observed in the code.
- **CI:** copy `{{FACTORY_HOME}}/templates/<stack>/.github/workflows/ci.yml` and replace the factory-repo placeholder (the text between double curly braces) with the factory's `owner/repo`, taken from `git -C "{{FACTORY_HOME}}" remote get-url origin`. If the project already has CI, show both and ask which to keep.
- **From `{{FACTORY_HOME}}/templates/_shared/`:** `.editorconfig`, `.github/pull_request_template.md`, `.github/dependabot.yml` (keep only the ecosystems this project uses).
- **docs/plans/.gitkeep**, so the factory pipeline has somewhere to put plans.
- Make sure `.gitignore` covers `.env`, plus dependency and build folders for the stack.

## 4. Verify and commit
Run lint and test commands to confirm nothing broke. Commit with `chore: adopt software-factory standards`. Suggest `/factory-ship` to open a PR.
