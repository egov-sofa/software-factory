# {{PROJECT_NAME}}

> Python project. Includes pytest for tests, Ruff for linting and formatting, and GitHub Actions CI.

## Getting started

```bash
python -m venv .venv                 # create an isolated environment
source .venv/Scripts/activate        # Windows Git Bash  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"              # install the project + dev tools
pytest                               # run tests
ruff check .                         # lint
```

## Project layout

```
src/{{PACKAGE_NAME}}/   application code
tests/                  automated tests
docs/plans/             feature plans (created by /factory-build)
.github/                CI pipeline, PR template, Dependabot
```

## Development workflow

This project uses the [software-factory](https://github.com/{{FACTORY_REPO}}) pipeline:

```
/factory-build <feature>   plan → build → test → review → docs
/factory-ship              push and open a pull request
```
