# Docs registry

The private overview of the documentation of all my projects. Every Monday, the
[Docs dashboard](.github/workflows/docs-dashboard.yml) workflow reads each repository in [registry.yml](registry.yml),
checks every document listed in its `.factory/docs.yml`, and keeps one issue here, labelled `docs-drift`, up to date.

Keep this repository **private**: `registry.yml` names private repositories.

- Add a project: add `OWNER/NAME` to `registry.yml`. If the owner is new, add a "Token for ..." step for it in the
  workflow, install the GitHub App on that owner, and pass the token as `DOCS_DRIFT_TOKEN_<OWNER>`.
- How it works and how to set up the GitHub App: `docs/DOCS-DRIFT.md` in the software factory.
