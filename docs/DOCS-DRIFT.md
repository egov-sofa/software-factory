# Docs drift: a kind of Dependabot for documentation

Dependabot tells you when a dependency is out of date. **Docs drift** tells you when a document is out of date: when
something it describes changed after the document did. It works for every project and every kind of document (an
architecture document, a runbook, a README), and it can follow sources in other repositories, for example the
deployment manifests that an architecture document describes.

It has three parts:

| Part | Where | What it does |
|---|---|---|
| The manifest | `.factory/docs.yml` in each project | Lists the project's documents and, for each one, the sources it describes |
| The check | the factory's `docs-drift` action, called at `@v1` from `.github/workflows/docs-drift.yml` | On a pull request: reports a source that changes while its document does not. Every Monday: keeps one issue, labelled `docs-drift`, in step with the state of every document |
| The dashboard | a private registry repository, made from [`templates/_docs-registry/`](../templates/_docs-registry/) | Every Monday: one issue that shows the documentation of all projects together |

Every member of the enterprise can read the factory, so it holds only the engine. The list of your projects and the
state of their documents stay in the projects themselves and in the private registry. The dashboard checks out the
factory's scripts with the factory's read-only GitHub App: set `FACTORY_APP_CLIENT_ID` and `FACTORY_APP_PRIVATE_KEY` in
the registry's organization (see [Reading the factory from a job](SHARED-SERVICES.md#reading-the-factory-from-a-job)).

## How a document is judged

For each document, the check compares the date of the last commit that touched the document with the date of the last
commit that touched each of its sources.

| State | Meaning | What to do |
|---|---|---|
| ok | No source changed after the document | Nothing |
| drift | At least one source changed after the document. The report names it and its commit | Update the document. If it is still right, say so in a commit that touches it (for example its "Date" line) |
| overdue | No source changed, but nobody touched the document for longer than its `review_every_days` | Review it and record the review in the document |
| unknown | A source could not be read: no token, or the token has no access to that repository | Give the check a token that can read it (below) |
| missing | The document does not exist | Write it, or remove it from the manifest |

"Unknown" is never counted as fine: a source the check cannot see is reported, not ignored.

## Step 1: list the documents

Create `.factory/docs.yml` in the project:

```yaml
version: 1
docs:
  - id: payments-sad                      # unique and stable: the dashboard uses it
    title: Payments software architecture document
    path: docs/architecture/payments/sad.md
    review_every_days: 180                # optional
    sources:
      - path: docs/architecture/payments/sketches/   # a folder: every file below it (the / is optional)
      - path: src/payments/**/*.py                   # a glob
      - repo: example-org/platform-gitops            # a path in another repository
        path: apps/payments/
        ref: main                                    # optional, default: its default branch
```

Run `python3 scripts/docs_drift.py validate --root .` from a factory checkout to check the file, and
`python3 scripts/docs_drift.py scan --root .` to see the report locally.

## Step 2: turn on the check

New projects already have the caller, `.github/workflows/docs-drift.yml`. For an existing project, copy it from
[`templates/_shared/.github/workflows/docs-drift.yml`](../templates/_shared/.github/workflows/docs-drift.yml) and
replace `{{FACTORY_REPO}}` with `egov-sofa/software-factory`. Without a manifest the check skips with a notice, so the
caller costs nothing in a project that does not use it.

The pull request check is read-only and only reports. To make it block a merge, add `strict: "true"` to its step.

## Step 3: let it read other repositories (GitHub App)

A source in another repository needs a token that can read that repository. Use a GitHub App: its tokens last one
hour, are not tied to a person, and give only the permissions you choose. One App serves every project and the
dashboard.

1. **Create the App.** GitHub → your organization (or your account) → Settings → Developer settings → GitHub Apps →
   *New GitHub App*.
   - Name: for example `docs-drift-reader`. Homepage: the factory repository.
   - Webhook: switch *Active* off.
   - Repository permissions: **Contents: Read-only**. Metadata: Read-only is set by GitHub. Nothing else.
   - Where can it be installed: *Any account*, if your projects are in more than one organization.
2. **Note the Client ID** on the App's page, and **generate a private key** (a `.pem` file is downloaded).
3. **Install the App** on each owner (organization or account) whose repositories are read: App page → *Install App*
   → choose the owner → *Only select repositories* → pick the repositories that are sources or are in the registry.
4. **Give the projects the App.** In each project that has sources in other repositories, or once per organization:
   ```bash
   gh variable set DOCS_DRIFT_APP_CLIENT_ID --body "<client id>" --repo OWNER/NAME
   gh secret set DOCS_DRIFT_APP_PRIVATE_KEY < docs-drift-reader.private-key.pem --repo OWNER/NAME
   ```
   Use `--org ORG` instead of `--repo` to set them once for every repository of an organization.
5. Delete the `.pem` file from your computer once the secrets are set.

A token from an App installation reads only the repositories of **one owner**. A project's weekly check asks for a
token for its own owner, so a source in another organization stays "unknown" there; the dashboard asks for one token
per owner and sees everything.

## Step 4: the dashboard of all projects

1. Create a **private** repository, for example `docs-registry`, in the organization where you keep shared tooling.
2. Copy into it the files of [`templates/_docs-registry/`](../templates/_docs-registry/).
3. List the repositories to follow in `registry.yml`.
4. In `.github/workflows/docs-dashboard.yml`, keep one "Token for ..." step per owner in the list, and pass each token
   as `DOCS_DRIFT_TOKEN_<OWNER>` (upper case, `-` becomes `_`).
5. Set the App's client ID and private key on the registry repository (step 3, point 4), and install the App on every
   owner with the repositories selected.
6. Run the workflow once by hand (Actions → Docs dashboard → *Run workflow*). It opens the issue "Documentation
   dashboard" if anything needs attention.

A repository in the registry without a readable `.factory/docs.yml` shows as "unknown": either it has no manifest yet,
or the App is not installed on it.

## Limits

- Dates are commit dates. A commit that only reformats a source still counts as a change.
- The weekly check in a project dates each change by when it reached the branch (`git log --first-parent`). The
  dashboard reads dates through GitHub's commits API, which has no such option, so it uses each commit's own date.
  The two can disagree for a pull request that is merged with a merge commit and updates the document in an earlier
  commit than its source: the project shows ok, the dashboard shows drift. With squash merges (the factory's
  recommended way, standards/GIT-WORKFLOW.md) both show the same, because the pull request becomes one commit.
- A source given as a glob is followed through the folder before its first wildcard (`src/**/*.py` follows `src/`),
  so a change to another file in that folder counts as well. Name narrower folders to avoid noise.
- The check says *that* a document may be out of date, not *what* to change. A later version can ask Claude to propose
  the update as a pull request, as Dependabot does for dependencies.
