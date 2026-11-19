# Terraform spike (phase 1 of the Terraform platform plan)

The question this spike answers: **can Terraform take over what is set up by hand today, with no change?** It imports
the existing objects and generates their configuration; a pass is a second `terraform plan` that shows
`0 to add, 0 to change, 0 to destroy`. Results and decisions: [the plan](../2026-11-19-terraform-platform.md#spike-phase-1-results).

**Read-only.** Run `terraform plan` only, never `apply`: there is no backend, the state is local and thrown away.

| Folder | Provider | Imports | Credential |
|---|---|---|---|
| `github/` | `integrations/github` 6.13.0 | 13 Actions variables of software-factory and claude-skills; the Actions workflow permissions of egov-sofa, egov-ai and egov-legacy | `GITHUB_TOKEN` (here `gh auth token`) |
| `anthropic/ippontech/` | `ippontech/anthropic` 1.91.2 | the shared service account, 4 federation rules | org:admin token in `ANTHROPIC_AUTH_TOKEN` |
| `anthropic/mozilla/` | `mozilla/anthropic` 0.1.0 | the same, plus the 2 workspaces | org:admin token in `ANTHROPIC_OAUTH_TOKEN` |

Versions are the newest released at least two weeks before the spike.

## Run it

GitHub side:
```bash
cd docs/plans/2026-11-19-terraform-platform-spike/github
terraform init
GITHUB_TOKEN="$(gh auth token)" terraform plan -generate-config-out=generated.tf
GITHUB_TOKEN="$(gh auth token)" terraform plan
```

Anthropic side (needs an `org:admin` login: `ant auth login --profile admin --scope "org:admin"`): copy each
`anthropic/<provider>/terraform.tfvars.example` to `terraform.tfvars`, fill in the IDs from the repositories'
variables (`gh variable list -R ...`), then:
```bash
bash docs/plans/2026-11-19-terraform-platform-spike/run-anthropic.sh
```

**On a machine whose TLS is intercepted** (an antivirus or proxy that re-signs certificates), Terraform cannot talk to
its own provider plugins: `plan` stops with "Failed to load plugin schemas", and `TF_LOG=DEBUG` shows
`x509: certificate signed by unknown authority` in `GetProviderSchema`. Prefix the commands with
`TF_DISABLE_PLUGIN_TLS=1`. It turns off the TLS of the local connection between Terraform and its plugins only; the
calls to GitHub and Anthropic stay HTTPS.

## What is committed and what is not

The repository is public. Committed: the configuration, the import blocks, the lock files and the `.example` files.
Not committed (`.gitignore`): `terraform.tfvars`, `generated.tf` and the state, which hold the real IDs.
