# {{PROJECT_NAME}}

Instructions for anyone changing this project: people and AI coding agents alike (Claude Code reads them through
`CLAUDE.md`; GitHub Copilot, Codex and Cursor read this file directly). Keep them current when commands change.

Python project scaffolded by software-factory.

## Commands
Uses [uv](https://docs.astral.sh/uv/): it creates `.venv`, installs exactly what `uv.lock` pins, and `uv run` runs a
command inside that environment (no activation needed).

| Task | Command |
|---|---|
| Install | `uv sync` |
| Test | `uv run pytest` |
| Test + coverage | `uv run pytest --cov={{PACKAGE_NAME}}` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` (check only: `uv run ruff format --check .`) |
| Type check | `uv run mypy` |
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
