# {{PROJECT_NAME}}

> Python project. Includes uv for dependencies (with a lockfile), pytest for tests, Ruff for linting and
> formatting, mypy for type checks, and GitHub Actions CI.

## Getting started

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) once, then:

```bash
uv sync                  # create .venv and install exactly what uv.lock pins
uv run pytest            # run tests
uv run ruff check .      # lint
uv run mypy              # type check
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
