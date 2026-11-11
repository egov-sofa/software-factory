# 🏭 Software Factory

A personal "factory" that turns ideas into working, tested, reviewed software, the same way every time, for any tech stack.

> **New here?** Read [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) first. It assumes no prior knowledge.

## What's inside (the 4 parts)

| Part | What it does for you | Where it lives |
|---|---|---|
| **1. AI agent pipeline** | A team of AI specialists (planner, builder, tester, reviewer, security auditor, docs writer) that build a feature end to end when you type `/factory-build add a login page` | [`claude/`](claude/) → installed to `~/.claude` |
| **2. Project scaffolding** | Creates a new project with folders, tests, linting, CI and docs already set up, in one command | [`templates/`](templates/) + [`scripts/new-project.sh`](scripts/new-project.sh) |
| **3. CI/CD and shared services** | Versioned services every project calls at `@v1`: CI pipelines, Claude PR review, `@claude` mentions, and a content guard that blocks secrets. A fix here reaches all your projects at the next release | [`.github/workflows/`](.github/workflows/), [`.github/actions/`](.github/actions/), [docs/SHARED-SERVICES.md](docs/SHARED-SERVICES.md) |
| **4. Shared standards** | Coding rules, git workflow, definition of done and security rules that both you and the AI follow | [`standards/`](standards/) |

## Quick start

```bash
# 1. Install the AI team and standards into Claude Code (safe to re-run)
bash ~/software-factory/scripts/install.sh

# 2. Create a new project
bash ~/software-factory/scripts/new-project.sh my-app typescript

# 3. Open it in Claude Code and build something
cd ~/projects/my-app && claude
> /factory-build add a function that converts Celsius to Fahrenheit
```

## Slash commands you get in Claude Code

| Command | What happens |
|---|---|
| `/factory-new <name> <template>` | Scaffolds a new project (same as the script, but Claude helps you pick) |
| `/factory-build <feature>` | Full pipeline: plan → **you approve** → build → test → review + security → fix → docs |
| `/factory-review` | Runs only the reviewer and security auditor on your current changes |
| `/factory-ship` | Commits, pushes, and opens a pull request with a good description |
| `/factory-onboard` | Adds factory standards (CLAUDE.md, CI, PR template) to an **existing** project |

## Templates

| Template | Use it for | Tools included |
|---|---|---|
| `typescript` | Web apps, APIs, CLIs in Node/TypeScript | TypeScript, Vitest (tests), ESLint (lint) |
| `python` | APIs, scripts, data and AI work | pytest (tests), Ruff (lint + format) |
| `generic` | Any other language (Go, Rust, C#, Java…) | A `scripts/check.sh` you fill in; CI runs it |

## Learn more

- [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md): step-by-step first use
- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md): how the parts fit together, with diagrams
- [docs/CUSTOMIZING.md](docs/CUSTOMIZING.md): add templates, change agents, tune the pipeline
- [docs/GLOSSARY.md](docs/GLOSSARY.md): plain-English definitions of every term
- [docs/SHARED-SERVICES.md](docs/SHARED-SERVICES.md): why and how other repositories use the factory's services
- [docs/ROADMAP.md](docs/ROADMAP.md): planned improvements, ranked by value, with their status
