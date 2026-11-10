# Glossary

Plain-English definitions of every term used in the factory.

| Term | Meaning |
|---|---|
| **Agent / subagent** | A Claude instance with one focused job, its own instructions and limited tools. Defined in a `.md` file in `~/.claude/agents/`. |
| **Skill / slash command** | A reusable set of instructions you trigger by typing `/name`. Defined in `~/.claude/skills/<name>/SKILL.md`. |
| **CLAUDE.md** | A file Claude reads automatically at the start of every session. The global one (`~/.claude/CLAUDE.md`) applies everywhere; a project one applies to that project. |
| **Scaffolding** | Generating the starting files and folders of a project, so you don't begin from an empty folder. |
| **Template** | A ready-made project skeleton that scaffolding copies. |
| **Repository (repo)** | A folder tracked by git, holding the full history of every change. |
| **Branch** | A parallel copy of the code where you can work safely. `main` is the official version. |
| **Commit** | A saved snapshot of changes, with a message describing them. |
| **Pull Request (PR)** | A request on GitHub to merge a branch into `main`. This is where review and CI happen. |
| **CI (Continuous Integration)** | Automatic checks (lint, build, test) that run in the cloud on every push. |
| **CD (Continuous Deployment)** | Automatically releasing code to users (a website, server or store) after CI passes. |
| **GitHub Actions** | GitHub's built-in CI/CD system. Pipelines are YAML files in `.github/workflows/`. |
| **Reusable workflow** | A GitHub Actions pipeline that other repos can call with `uses:` instead of copying it. |
| **Lint / linter** | A tool that finds style problems and likely bugs without running the code (ESLint, Ruff). |
| **Test** | Code that checks other code works. **Unit** tests check one small piece; **integration** tests check pieces working together. |
| **Acceptance criteria** | A checklist that defines "this feature is done". The planner writes it; the reviewer checks it. |
| **Definition of Done** | The checklist *every* change must satisfy (tests pass, no secrets, docs updated…). |
| **Dependabot** | A GitHub bot that opens PRs to update outdated or vulnerable dependencies. |
| **Dependency** | Someone else's code your project uses (an npm or pip package). |
| **Secret** | A password, API key or token. **Never** commit these; use `.env` files (git-ignored) or GitHub Secrets. |
| **Model (opus / sonnet / haiku)** | Different Claude models. Opus is the most capable (used for planning and review); Sonnet is fast and strong; Haiku is fastest and cheapest. |
