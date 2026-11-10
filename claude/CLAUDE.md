# Global Working Rules (installed by software-factory)

These rules apply to every project. A project's own `CLAUDE.md` overrides them where they conflict.
Full standards: `{{FACTORY_HOME}}/standards/`

## About me
- I'm building my skills: when you make a non-obvious decision, explain **why** in one or two plain sentences.
- My projects use mixed stacks (TypeScript, Python, others). Detect the stack from the project files; don't assume.

## How to work
- Read the project's `CLAUDE.md` and existing code before changing anything. Match existing style.
- Work on a branch, never directly on `main`. Branch names: `feat/…`, `fix/…`, `chore/…`, `docs/…`.
- Commits follow Conventional Commits: `feat: …`, `fix: …`, `docs: …`, `test: …`, `refactor: …`, `chore: …`.
- Every behavior change comes with tests. Run the test suite before saying something works.
- Report results honestly: if tests fail or a step was skipped, say so.
- Keep changes focused: no unrelated refactors or "while I'm here" edits.

## Factory pipeline
For anything bigger than a small fix, suggest `/factory-build <feature>` (plan → build → test → review → docs).
Plans live in `docs/plans/`. Other commands: `/factory-new`, `/factory-review`, `/factory-ship`, `/factory-onboard`.

## Never
- Commit secrets, `.env` files, or credentials.
- Push to `main`, force-push, or delete branches without asking.
- Disable or skip tests or lint rules to make CI pass.
- Add a dependency without saying why.
