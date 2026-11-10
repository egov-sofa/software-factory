# {{PROJECT_NAME}}

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
