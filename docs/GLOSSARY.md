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
| **Diagram sketch** | A short YAML file describing what a diagram shows (boxes, containers, flows). The architecture-diagram engine of claude-skills lays it out; the sketch is the source, never the picture. See [diagrams/README.md](diagrams/README.md). |
| **draw.io** | A free diagram editor. Its `.drawio` files are what the engine generates; its command-line tool exports them to PNG. |
| **C4** | A way of drawing software at zoom levels (context, containers, components) with plain boxes and labelled arrows. |
| **BPMN** | Business Process Model and Notation: a process drawn as tasks, decisions (diamonds) and events (circles), in one lane per role. |
| **ArchiMate** | An enterprise architecture language with standard shapes for business, application and technology elements. |
| **Capability map** | A picture of what an organization (or the factory) can do, with "heat" marking where attention is needed. |
| **Trust boundary** | A dashed line around something you do not trust, such as a pull request from someone else: nothing inside it may run with your secrets. |
| **Change diagram** | A diagram that compares two versions and marks elements as new, changed, removed or planned. |
| **Workload identity federation (WIF)** | A way for a CI job to use the Claude API without a stored key: the job proves who it is with a token GitHub signs, and Anthropic swaps it for a short-lived Claude token. See [CLAUDE-SERVICES-AUTH.md](CLAUDE-SERVICES-AUTH.md). |
| **OIDC token** | The signed identity token (a JWT) GitHub gives a workflow run that has `id-token: write`. Its subject says which repository and event started the run. |
| **Federation rule** | An Anthropic setting that says which GitHub tokens (repository, event, claims) may get a Claude token, for which service account and workspace. One per repository and workflow. |
| **Service account** | A non-human identity in the Anthropic organization, with no login; federation rules mint tokens that act as it. |
| **Admin API** | Anthropic's API for managing the organization itself (workspaces, service accounts, federation rules). `scripts/claude_federation.py` uses it. |
