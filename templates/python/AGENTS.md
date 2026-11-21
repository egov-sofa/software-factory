# {{PROJECT_NAME}}

Instructions for anyone changing this project: people and AI coding agents alike (Claude Code reads them through
`CLAUDE.md`; GitHub Copilot, Codex and Cursor read this file directly). Keep them current when commands change.

Python project scaffolded by software-factory.

## Commands
Uses [uv](https://docs.astral.sh/uv/): it creates `.venv`, installs exactly what `uv.lock` pins, and `uv run` runs a
command inside that environment (no activation needed).

| Task | Command |
|---|---|
| Install | `uv sync` (exactly as locked, as CI does: `uv sync --locked`) |
| Test | `uv run pytest` |
| Test + coverage | `uv run pytest --cov={{PACKAGE_NAME}}` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` (check only: `uv run ruff format --check .`) |
| Type check | `uv run mypy` |
| Build | `uv build` (outputs to `dist/`) |
| Add a dependency | `uv add <package>` (dev-only tool: `uv add --dev <tool>`) |

Run `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` before declaring any
change done.

## Structure
- `src/{{PACKAGE_NAME}}/`: application code (import as `{{PACKAGE_NAME}}`).
- `tests/`: pytest tests, named `test_<module>.py`.
- `docs/plans/`: feature plans written by the factory planner.

## Conventions
- Type hints on every public function. Use `from __future__ import annotations` if needed.
- Raise specific exceptions (`ValueError`, custom ones), never a bare `Exception`.
- Use `pathlib` for paths and `logging` instead of `print` in library code.
- Config comes from environment variables (`os.environ`); document every variable in `.env.example`.
- Add dependencies with `uv add` (runtime) or `uv add --dev` (dev-only tools), never by editing `pyproject.toml`
  alone: uv updates `uv.lock` too, and CI installs with `--locked`, so a stale lockfile fails the build. Commit
  `uv.lock` with the change.

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
