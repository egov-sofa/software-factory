# selftest-app

Instructions for anyone changing this project: people and AI coding agents alike (Claude Code reads them through
`CLAUDE.md`; GitHub Copilot, Codex and Cursor read this file directly). Keep them current when commands change.

Project scaffolded by software-factory (generic template).

> ⚠️ **Fill this in once the language is chosen.** The factory agents rely on this file to know how to build and test.

## Commands
| Task | Command |
|---|---|
| All checks (what CI runs) | `bash scripts/check.sh` |
| Install | _TODO_ |
| Test | _TODO_ |
| Lint | _TODO_ |
| Build | _TODO_ |

Run `bash scripts/check.sh` before declaring any change done.

## Structure
- `src/`: application code
- `scripts/check.sh`: the single quality gate (lint + build + test), used by CI
- `docs/plans/`: feature plans written by the factory planner

## Conventions
- _TODO: language-specific conventions (naming, error handling, test layout)_

<!-- software-factory:standards:start -->
## Standards

This project follows the software factory's standards, shipped in `.factory/standards/`:
- `.factory/standards/CODING-STANDARDS.md`: how code is written here (simplicity, naming, errors, tests, dependencies).
- `.factory/standards/DEFINITION-OF-DONE.md`: what every change needs before it is done (the reviewer checks it).
- `.factory/standards/GIT-WORKFLOW.md`: branches, Conventional Commits and pull requests.
- `.factory/standards/SECURITY.md`: secrets, input handling, dependencies (the security audit checks it).

The rules in this file win where they conflict with the standards. Do not edit the standards here: change them in
the software factory, and `/factory-update` brings them in. `/factory-update` also keeps this block current.
<!-- software-factory:standards:end -->
