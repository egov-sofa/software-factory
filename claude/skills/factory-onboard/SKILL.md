---
name: factory-onboard
description: Add software-factory standards and shared services to an existing project - project instructions (AGENTS.md, imported by CLAUDE.md), CI using the factory's reusable workflows, the Claude PR review and @claude mentions, the content guard with its git hooks, a PR template, Dependabot, and .editorconfig. Use on projects not created with /factory-new.
disable-model-invocation: true
---

# Factory Onboard

Bring an existing project up to factory standards **without breaking anything**.
Factory location: `{{FACTORY_HOME}}`

## 1. Detect
- Stack: `package.json` → typescript/node; `pyproject.toml` / `requirements.txt` → python; anything else → generic.
- The real commands: read `package.json` scripts, `pyproject.toml`, `Makefile`, and existing CI files. **Use the commands the project actually has**; don't invent them.
- Existing files: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/*`, `.github/pull_request_template.md`, `.editorconfig`, `.github/dependabot.yml`, `.claude/skills/pr-review/SKILL.md`, `scripts/hooks/`, and `git config core.hooksPath` (another hook manager such as husky or pre-commit may already own the hooks).
- GitHub owner: `gh api user -q .login`.

## 2. Propose
Show the user a table of files to **add** and files that **already exist** (to be skipped or merged), then ask for confirmation. Never overwrite an existing file without explicit approval.

The shared services are opt-in, one by one (see `{{FACTORY_HOME}}/docs/SHARED-SERVICES.md`). Ask which ones the project wants, and explain each in one plain sentence:
- **CI pipeline:** lint, build and test on every push.
- **Content guard:** blocks secrets, public IPs, internal host names and a private denylist in pull requests and, through git hooks, before each commit. Free, no setup.
- **Claude review and @claude mentions:** Claude reviews each pull request against a checklist. Costs API credit per review and needs a one-time setup, so it stays off until the variable `CLAUDE_REVIEW_ENABLED` is `true`.
If the project would need project-specific changes to a shared workflow to fit, say so and suggest keeping its own workflow instead: forcing it into the shared one is worse for both.

## 3. Apply (on a branch `chore/factory-onboard`)
- **AGENTS.md and CLAUDE.md:** `AGENTS.md` holds the project's instructions, so every AI coding agent (Claude Code, GitHub Copilot, Codex, Cursor) and every person reads the same ones. Base it on `{{FACTORY_HOME}}/templates/<stack>/AGENTS.md`, rewritten with this project's real commands, folder structure (from `ls` and a quick look around) and conventions you observed in the code. `CLAUDE.md` is `{{FACTORY_HOME}}/templates/_shared/CLAUDE.md`, which imports it with `@AGENTS.md`. If the project already has a `CLAUDE.md` with its own instructions, propose moving them into `AGENTS.md` (keeping anything Claude-specific in `CLAUDE.md` below the import) and ask before changing it; if it already has an `AGENTS.md`, extend that one.
- **CI:** copy `{{FACTORY_HOME}}/templates/<stack>/.github/workflows/ci.yml` and replace the factory-repo placeholder (the text between double curly braces) with the factory's `owner/repo`, taken from `git -C "{{FACTORY_HOME}}" remote get-url origin`. If the project already has CI, show both and ask which to keep.
- **From `{{FACTORY_HOME}}/templates/_shared/`:** `.editorconfig`, `.github/pull_request_template.md`, `.github/dependabot.yml` (keep only the ecosystems this project uses).
- **Shared services the user chose**, from `{{FACTORY_HOME}}/templates/_shared/`, replacing the factory-repo placeholder as for CI (and `{{PROJECT_NAME}}` in the checklist):
  - Claude review: `.github/workflows/claude-review.yml`, `.github/workflows/claude-mention.yml`, and `.claude/skills/pr-review/SKILL.md`. Fill its "Project rules" section with rules you observed in this codebase. Then set up its access to the Claude API, if the repository is on GitHub: follow "Set up a repository from Claude Code" in `{{FACTORY_HOME}}/docs/CLAUDE-SERVICES-AUTH.md`. In short: make sure the Claude GitHub app is installed on the repository (ask; nothing can check it for you), run the preview yourself and show it, then give the user the one `--apply --set-variables` command to run with `!`; it needs their `org:admin` login, so never run it yourself. Never set `CLAUDE_REVIEW_ENABLED` by hand: the script sets it last, once the rules and the other variables exist.
  - Content guard: `.github/workflows/content-guard.yml` and `.content-denylist` in `.gitignore`. The guard itself (`scripts/check_content.py`) and its hooks (`scripts/hooks/*`) are written in step 5, by the factory's own script, with the header that marks them as the factory's. They belong to the factory, so exclude the guard from the project's own linters and formatters (for Ruff: `extend-exclude = ["scripts/check_content.py"]` under `[tool.ruff]`).
  - All callers use `@v1`, never `@main`.
- **docs/plans/.gitkeep**, so the factory pipeline has somewhere to put plans.
- Make sure `.gitignore` covers `.env`, plus dependency and build folders for the stack.

## 4. Verify and commit
Run lint and test commands to confirm nothing broke. Commit with `chore: adopt software-factory standards`.

## 5. Record the factory version
Every onboarded project gets `.factory/answers.yml`, so `/factory-update` can bring it later factory releases. `$FU`
is `python3 "{{FACTORY_HOME}}/scripts/factory_update.py"` (or `python`), run from the project's root.
- `git -C "{{FACTORY_HOME}}" fetch --tags --quiet origin`, then `$FU adopt --onboarded`: it prints the answers it
  inferred (the newest factory release is the base, since no template made this project). Show them and let the user
  confirm or correct each one (`--set key=value`). If the user did not want the content guard, add
  `--set skip=scripts/check_content.py,scripts/hooks/commit-msg,scripts/hooks/pre-commit`.
- Run it again with `--yes`. It writes the content guard, its hooks and `.factory/standards/` (showing the diff of
  any guard file the project already had), adds the standards block to `AGENTS.md` and the review checklist, lists the
  template files the project does not have under `skip:` (updates leave them out), and lists the factory files that
  differ from the project's for a look by hand (it changes none of them).
- Content guard chosen: run `python3 scripts/check_content.py --all`, fix or mark (`content-ok`) what it finds
  **before** enabling the hooks with `git config core.hooksPath scripts/hooks`. If another hook manager owns the
  hooks, don't change `core.hooksPath`; show the user how to call the guard from their existing hook instead.
- Commit with `chore: record the software-factory version`. Suggest `/factory-ship` to open a PR.
