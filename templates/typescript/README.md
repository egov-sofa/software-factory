# {{PROJECT_NAME}}

> TypeScript / Node.js project. Includes Vitest for tests, ESLint for linting, and GitHub Actions CI.

## Getting started

```bash
npm install     # install dependencies
npm test        # run tests
npm run lint    # check code quality and types
npm run build   # compile to dist/
```

## Project layout

```
src/            application code
tests/          automated tests
docs/plans/     feature plans (created by /factory-build)
.github/        CI pipeline, PR template, Dependabot
```

## Development workflow

This project uses the [software-factory](https://github.com/{{GITHUB_OWNER}}/software-factory) pipeline:

```
/factory-build <feature>   plan → build → test → review → docs
/factory-ship              push and open a pull request
```
