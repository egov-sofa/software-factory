# {{PROJECT_NAME}}

Instructions for anyone changing this project: people and AI coding agents alike (Claude Code reads them through
`CLAUDE.md`; GitHub Copilot, Codex and Cursor read this file directly). Keep them current when commands change.

TypeScript / Node.js project scaffolded by software-factory.

## Commands
| Task | Command |
|---|---|
| Install | `npm install` (use `npm ci` in CI) |
| Test | `npm test` |
| Test (watch) | `npm run test:watch` |
| Lint + typecheck | `npm run lint` |
| Build | `npm run build` (outputs to `dist/`) |

Run `npm run lint && npm test` before declaring any change done.

## Structure
- `src/`: application code. `src/index.ts` is the entry point.
- `tests/`: Vitest tests, named `<module>.test.ts`, mirroring `src/`.
- `docs/plans/`: feature plans written by the factory planner.

## Conventions
- ES modules: relative imports use the `.js` extension (`import { x } from "./util.js"`), as required by NodeNext.
- Strict TypeScript: no `any`; prefer `unknown` and narrow it. Validate external input at boundaries.
- Named exports only, no default exports.
- Throw `Error` with a descriptive message; don't return `null` to signal failure.
- Config comes from `process.env`; document every variable in `.env.example`.

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
