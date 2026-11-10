# {{PROJECT_NAME}}

Python project scaffolded by software-factory.

## Commands
Activate the virtual environment first: `source .venv/Scripts/activate` (Windows Git Bash) or `source .venv/bin/activate` (macOS/Linux).

| Task | Command |
|---|---|
| Create venv | `python -m venv .venv` |
| Install | `pip install -e ".[dev]"` |
| Test | `pytest` |
| Test + coverage | `pytest --cov={{PACKAGE_NAME}}` |
| Lint | `ruff check .` |
| Format | `ruff format .` (check only: `ruff format --check .`) |

Run `ruff check . && ruff format --check . && pytest` before declaring any change done.

## Structure
- `src/{{PACKAGE_NAME}}/`: application code (import as `{{PACKAGE_NAME}}`).
- `tests/`: pytest tests, named `test_<module>.py`.
- `docs/plans/`: feature plans written by the factory planner.

## Conventions
- Type hints on every public function. Use `from __future__ import annotations` if needed.
- Raise specific exceptions (`ValueError`, custom ones), never a bare `Exception`.
- Use `pathlib` for paths and `logging` instead of `print` in library code.
- Config comes from environment variables (`os.environ`); document every variable in `.env.example`.
- Add runtime dependencies to `[project].dependencies` in `pyproject.toml`; dev-only tools to `[project.optional-dependencies].dev`.
