# Plan: Terraform for the organizations and the Claude services (roadmap E1.4)

**Status:** Proposed. Phase 1 (spike) half done: GitHub side done 2026-11-19, Anthropic side waits for an `org:admin`
run (see [Spike results](#spike-phase-1-results)).
**Request:** "Is it possible to also automate the `--apply --set-variables` run, which needs my admin login? My goal
is to automate as much as possible. Can we also use Terraform? Analyse the opportunity across all my organizations and
repositories." Then: "write the Terraform plan up and start the one-day test."

## Goal

Today every repository is set up by hand or by a command a person runs: create the repository, its federation rules,
its variables, its rulesets; and each organization's Actions settings are clicked in the UI. After this plan, all of it
is **code in one platform repository**: a pull request is reviewed with its plan, a merge you approve applies it, and nothing
else is needed per repository. Two side effects matter as much as the automation: settings changed by hand become
visible (drift), and every change is reviewed like code.

## Decisions needed

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Where the platform repository lives | a new repository in `pentagone-digital` (Team plan) / a public one in `egov-sofa` / a private one on a Free organization | **`pentagone-digital`**, private: the only organization whose plan lets a private repository protect `main` and require reviews; the platform repository can change every organization, so its `main` must be protected. Public works too but publishes the organizations' configuration |
| D2 | Anthropic provider | `ippontech/anthropic` / `mozilla/anthropic` | **Decide after the Anthropic spike run.** Today: ippontech is the mature one (9 contributors, 208 Go test files, 159 releases) but needs a long-lived Admin API key for workspaces until its issue #524 lands; mozilla manages everything with the one keyless token but is four weeks old with one maintainer |
| D3 | State backend | HCP Terraform / a cloud bucket you already run (S3, Azure Blob, GCS) with OIDC from Actions | whichever cloud the team already uses; **no secrets in state** (D5) makes the choice less critical |
| D4 | Rules per repository or one per organization | per repository (today) / one per organization with a wildcard subject and `job_workflow_ref` pinned to `reusable-claude-review.yml@refs/tags/v1` | **per repository** for now: with Terraform a rule per repository costs nothing more to write, and keeps cost and audit per project |
| D5 | Secrets | manage secret values in Terraform / keep them out | **out**: state would hold them. Terraform manages variables (IDs, not secrets) and settings only |
| D6 | First scope | the three repositories set up today (software-factory, claude-skills, struts-modernization) and their organizations | yes; the other organizations (egov-sandbox, egov-tech, pentagone-digital) follow in phase 3 |

## Facts this plan relies on (checked 2026-11-19)

- **No official Anthropic provider**; two community ones in the Terraform Registry manage the Admin API objects this
  plan needs (workspaces, service accounts, federation issuers and rules, spend limits), both MPL-2.0:
  `ippontech/anthropic` (110k downloads, 159 versions) and `mozilla/anthropic` (25k downloads, 3 versions, first
  release 2026-10-21). Both document `terraform import` for every resource this plan imports.
- **Both authenticate keyless in CI** with a `federation` block: the provider exchanges a GitHub OIDC token for an
  Anthropic token itself.
- **An `org:admin` federation rule can only be created in the Claude Console** by a person; both providers say so
  (they can import and read one). It is the one bootstrap step Terraform cannot do.
- **Federation rules created through the API** can only have the `workspace:developer` or `workspace:inference`
  scope, which is what the review and mention rules use.
- **`subject_prefix` accepts a trailing `:*` or `/*` wildcard** (mozilla's documentation), which D4's
  organization-wide option needs.
- **ippontech sends the `org:admin` token only to the service account and federation endpoints**; workspaces and spend
  limits need `admin_api_key` until its issue #524. **mozilla sends it to every endpoint.**
- **ippontech issue #378:** a create retried after a 5xx can leave a duplicate. Applies stay supervised (approval, D1).
- **The GitHub provider** (`integrations/github`, official) has every GitHub resource this plan names:
  `github_repository`, `github_actions_variable`, `github_actions_organization_variable`,
  `github_actions_organization_workflow_permissions` (incl. "allow GitHub Actions to create pull requests", which
  blocked the backend baseline of egov-legacy/struts-modernization), `github_repository_ruleset`,
  `github_organization_ruleset`, `github_actions_repository_oidc_subject_claim_customization_template`.
- **GitHub Free:** private repositories get no rulesets or required reviews; Terraform cannot change that. Only
  `pentagone-digital` is on the Team plan.

## Spike (phase 1) results

The question: can Terraform take over what exists today **with no change**? Method: import the existing objects,
generate their configuration (`terraform plan -generate-config-out`), then plan again; a pass is
`0 to add, 0 to change, 0 to destroy`. Read-only throughout: no `apply`, local state thrown away. The configuration is
in [2026-11-19-terraform-platform-spike/](2026-11-19-terraform-platform-spike/README.md).

### GitHub side: passed, with one exception

- **16 resources taken over with no change:** the 13 Actions variables of software-factory and claude-skills, and the
  Actions workflow permissions of egov-sofa, egov-ai and egov-legacy. Both plans:
  `Plan: 16 to import, 0 to add, 0 to change, 0 to destroy`.
- **Not representable: the repositories' OIDC subject setting.** Provider 6.13.0 generates
  `include_claim_keys = []` for a repository on the default template, which its own schema then rejects, and it has no
  field for `use_immutable_subject`, the ID-based subject (`repo:egov-sofa@<id>/software-factory@<id>:...`) every
  federation rule matches on. **Do not manage that resource** until the provider supports it: an apply could reset the
  format and break every rule. Removed from the spike; recorded as risk R1.
- **Found by reading the configuration:** egov-sofa gives every workflow's `GITHUB_TOKEN` **write** access by default
  (egov-ai and egov-legacy: read). The factory's workflows declare their own permissions, so nothing breaks today, but
  least privilege says `read`. This is the kind of drift the platform makes visible; not changed by the spike.
- **Local quirk, not a Terraform problem:** on a machine whose TLS is intercepted, Terraform cannot talk to its own
  plugins (`x509: certificate signed by unknown authority` in `GetProviderSchema`); `TF_DISABLE_PLUGIN_TLS=1` fixes it
  locally. CI runners are not affected.

### Anthropic side: to run (needs your `org:admin` login)

The configuration for both providers is ready and validated (`terraform validate`): the shared service account and
the four existing rules (software-factory's review rule; claude-skills' review, mention and evals rules), plus, with
mozilla, the two workspaces. One command runs both, read-only:

```bash
ant auth login --profile admin --scope "org:admin"
TF_DISABLE_PLUGIN_TLS=1 bash docs/plans/2026-11-19-terraform-platform-spike/run-anthropic.sh
```

**Pass:** both providers import every object and the second plan shows `0 to change`. Record here, per provider: the
import result, any diff on the second plan, and whether the generated configuration is readable enough to maintain.
That evidence settles D2.

### Provider comparison so far

| | ippontech/anthropic 1.91.2 | mozilla/anthropic 0.1.0 |
|---|---|---|
| Federation rules, issuers, service accounts | yes, import documented | yes, import in the code |
| Workspaces, spend limits with the keyless `org:admin` token | **no**: needs a long-lived Admin API key (issue #524) | **yes** |
| Maturity | 9 contributors, 208 Go test files, releases almost daily | 1 maintainer, 9 Go test files, first release 2026-10-21 |
| Known risks | #378 duplicates on retried creates; 104 open issues and pull requests | young; small team |
| Spike result | to run | to run |

## Target architecture

![How an approved change reaches GitHub and Anthropic: you review the pull request, whose job plans GitHub and validates the Anthropic code; after the merge the jobs on main plan both, wait for your approval and apply the saved plan; they get GitHub App installation tokens (read-only for pull requests, write only for the approved apply) and exchange their GitHub OIDC token at a Console-made org:admin federation rule for a 10-minute token to the Anthropic Admin API; state lives in a remote backend without secrets](../diagrams/terraform-platform.png)

- **One platform repository** (D1), one Terraform root per concern: `github/` (one provider alias per organization)
  and `anthropic/`. A module `factory-repo` holds everything one repository needs: the repository settings, its
  federation rules (review, mention; `job_workflow_ref` pinned to the factory's `@v1` workflow), and its variables,
  with `depends_on` so the two on switches (`ANTHROPIC_MENTION_FEDERATION_RULE_ID`, `CLAUDE_REVIEW_ENABLED`) come
  last, the order `claude_federation.py --set-variables` already enforces.
- **Per team:** a workspace with a spend limit and a service account. **Per organization:** Actions workflow
  permissions, organization variables, rulesets where the plan allows them.
- **Credentials:** Anthropic through one `org:admin` federation rule, made once in the Console and matching only the
  two jobs on `main`: the platform workflow's `job_workflow_ref` on `refs/heads/main`, and a CEL condition that the
  job's `environment` claim is `production-plan` or `production` (both environments limited to the `main` branch;
  the exact claim values to be confirmed against a real token in phase 4);
  GitHub through **two GitHub Apps** installed on each organization, because a pull request's Terraform code can run
  commands (`data "external"`) and so can reach any secret its job can:
  - `platform-read`: read permissions only (administration, variables, Actions: read; no contents). Its key is a
    repository secret, used by the pull request job and the plan job. Exposed to a pull request, it lets someone read
    the organizations' settings, nothing more.
  - `platform-write`: the write permissions the apply needs. Its key is a secret of the `production` environment
    only, so only the approved apply job can read it.
  The two App keys are the platform's only stored secrets.
  The **state backend** is reached through OIDC too, with two roles: read-only for pull request jobs (they plan
  with `-lock=false`), read-write only for the two jobs on `main`. A pull request can then neither rewrite nor
  delete state.
- **Where each plan runs.** Reading federation rules needs the `org:admin` token too (there is no read-only scope),
  and that token must never be reachable from code a pull request controls. So:
  - **pull requests** run `terraform plan` for `github/` only (with `platform-read`) and `terraform validate` for
    `anthropic/`, which needs no credential;
  - **after a merge, on `main`,** a plan job in the environment `production-plan` (no reviewer) runs
    `terraform plan -out` for both roots and shows the plan in the job summary; nothing is changed;
  - an **apply job** in the environment `production` waits for **your approval** (its required reviewer: the one
    approval per change) and applies exactly that saved plan, so what you approved is what runs.
  The Anthropic part of a change is therefore reviewed after the merge, before anything is applied; its code was
  reviewed in the pull request.

### A new repository, once the platform exists

![A new repository with the Terraform platform: /factory-new opens a platform pull request; platform CI plans the GitHub side; you review and merge; CI plans both sides on main; you approve the saved plan; CI applies it and creates the repository, its rules and its variables; the review is running](../diagrams/terraform-new-repo.png)

`/factory-new` stops running `gh repo create` and handing over a command: it adds one `module "<name>"` block to the
platform repository in a pull request. You review it, merge, and approve the saved plan. No login, no command per
repository.

## Phases

Each phase is useful on its own and can stop there.

| Phase | What | Acceptance | Size |
|---|---|---|---|
| 1. Spike | this document's spike | GitHub: done. Anthropic: both providers import with `0 to change`; D2 decided | S, half done |
| 2. Anthropic in code | the chosen provider manages the rules, service account (and workspaces, if the provider allows it keyless) of the three repositories, applied locally with your `ant` login | `plan` clean after import; one new rule created by Terraform works on a real pull request; `claude_federation.py` documented as the fallback | S |
| 3. GitHub in code | org workflow permissions and variables of all six organizations, repository settings and variables of the factory repositories; the GitHub Apps `platform-read` and `platform-write` | `plan` clean after import; the egov-sofa default token permission set to `read` through a reviewed change | M |
| 4. CI apply | platform repository (D1), state backend (D3), the Console `org:admin` rule, the environments `production-plan` and `production` | a pull request shows the GitHub plan and validates the Anthropic code; after a merge the plan on `main` shows both, and the saved plan is applied only after your approval, with no local login; a test pull request that edits the workflow gets neither an `org:admin` token nor the `platform-write` key (only `platform-read`, whose token cannot change anything), and its state access is read-only | M |
| 5. `/factory-new` through the platform | the skill opens the platform pull request instead of running commands | a new repository from `/factory-new` gets its review working with no command and no login | S |

## Risks / out of scope

- **R1 OIDC subject setting not representable** by the GitHub provider 6.13.0 (spike). Keep it out of Terraform;
  `claude_federation.py` already reads the prefix. Revisit with a provider release that supports
  `use_immutable_subject`.
- **R2 community providers on a beta API.** Pin exact versions (at least two weeks old), review upgrades like code,
  run `plan` on a schedule to catch API changes early. Keep `claude_federation.py` working as the fallback.
- **R3 the `org:admin` credential reachable from CI** (phase 4). Both jobs on `main` hold it: the plan job (no
  approval, but it only runs code already merged to the protected `main`) and the apply job (after your approval).
  Mitigations: the rule matches only those two jobs of one protected repository (workflow on `main`, two named
  environments limited to `main`); no pull request run matches it; the token lives ten minutes; the platform
  repository's `main` is protected and needs a review (D1). The `platform-write` App key is likewise readable only in
  the `production` environment; pull request jobs get `platform-read` and read-only state access only.
- **R4 drift is reverted.** A setting changed in the GitHub UI or the Console is undone at the next apply. The team
  changes settings through pull requests from phase 3 on; a scheduled `plan` reports drift without applying.
- **R5 ippontech duplicates on retried creates** (#378): applies stay supervised; check the Console after a failed
  apply.
- **Out of scope:** files inside repositories (the factory templates own them), secret values (D5), the legacy Struts
  repositories beyond their basic settings, GitHub plan upgrades.
