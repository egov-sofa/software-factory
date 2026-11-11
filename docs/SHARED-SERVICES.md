# Shared Services: the factory as a platform

**Decision (2026-11-11):** my other repositories, starting with `claude-skills`, use services provided by the software
factory, but only as **opt-in, versioned building blocks**. The factory does not own them. Anything only one project
needs stays in that project.

This page records why, the rules that keep the coupling safe, and which services exist. The work that follows from it
is tracked in [ROADMAP.md](ROADMAP.md).

---

## Why share at all

I am one person maintaining several repositories. Without a shared source, I would solve the same problems in each
one: pinning actions, setting up Claude review and its authentication, guarding against leaked secrets and internal
names, Dependabot, standard CI steps. `claude-skills` shows the cost: its review workflow, federation auth and content
guard took many pull requests to get right (see its `docs/roadmap.md`). Rebuilding that in every new repository would
be wasted work, and the copies would slowly diverge.

## The risk, and how it is managed

The danger is **coupling**. If every project follows the factory's `main`, one bad push breaks all of them at once.
If the factory tries to fit every project's quirks, its workflows grow inputs nobody understands. Four rules prevent
both:

1. **Pin versions.** Projects call `…/reusable-claude-review.yml@v1`, never `@main`. `v1` is a moving tag that only
   receives compatible changes. A breaking change gets `v2`, and each project moves when I choose.
2. **Share only what is the same everywhere.** Rule of thumb: centralize something once two or three projects need it
   *in the same form*. Domain-specific logic stays local.
3. **Keep each service small.** One job per reusable workflow or action, so a project can take the Claude review
   without the CI pipeline, or the reverse.
4. **Always leave an escape route.** Any project can replace a `uses:` line with a local copy and diverge. Nothing
   locks it in.

## Who uses what

| Project | Uses from the factory | Keeps locally |
|---|---|---|
| New projects (from `new-project.sh`) | CI pipeline, Claude review, `@claude` mentions, content guard, hooks, standards | Their code, their `CLAUDE.md` and review checklist |
| Existing projects (via `/factory-onboard`) | The same, chosen one by one | Anything they already do differently |
| `claude-skills` | Claude review, `@claude` mentions, content guard; later the evals runner, Dependabot setup and lint jobs | `validate.py`, `build.py`, taxonomy and catalog, draw.io golden PNG tests, skill packaging and release zips, `version_check.py`, its skill eval cases |

Most of the shared column was **built first in `claude-skills`**. The order of work is therefore: move it into the
factory, generalize it, then let `claude-skills` use it. That makes `claude-skills` the first real user of the
factory, which is the best test it can get.

## When a project should evolve on its own

Do not adopt the factory's services when:
- the project has unusual CI needs that would force project-specific options into a shared workflow
- it is short-lived (a spike or a throwaway prototype)
- it will move to someone else's infrastructure. For example, work skills that may move to an employer's repository
  must not depend on my personal factory.

---

## The services

All of them are referenced as `<owner>/software-factory/...@v1`. Templates already contain the callers; for an
existing project, copy the caller files from [`templates/_shared/`](../templates/_shared/) or run `/factory-onboard`.

| Service | Kind | What it does | Caller file in projects |
|---|---|---|---|
| CI pipeline | reusable workflow: `reusable-node.yml`, `reusable-python.yml`, `reusable-generic.yml` | Install, lint, build, test | `.github/workflows/ci.yml` |
| Claude review | reusable workflow: `reusable-claude-review.yml` | Claude Code reviews each pull request against the project's checklist and posts inline comments plus a summary | `.github/workflows/claude-review.yml` |
| Claude on demand | reusable workflow: `reusable-claude-mention.yml` | Answers a pull request comment starting with `@claude` (write access only) | `.github/workflows/claude-mention.yml` |
| Content guard | composite action: `.github/actions/content-guard` | Blocks secrets, public IP addresses, internal host names and denylisted terms in a pull request | `.github/workflows/content-guard.yml` |
| Local hooks | files copied into the project | Run the same guard before each commit | `scripts/hooks/`, `scripts/check_content.py` |

### Why the content guard is an action, not a reusable workflow

The guard must run code that comes from the factory, never from the pull request it checks. A composite action gets
its own files at the pinned tag (`$GITHUB_ACTION_PATH`), so the script that runs is the factory's `v1` copy, outside
the checkout, in isolated mode (`python3 -I`). A reusable workflow has no reliable way to find its own repository's
files. The caller runs on `pull_request_target`, so GitHub also takes the caller workflow from the base branch: a pull
request cannot edit the check it is held to, or read the denylist secret.

### Turning on the Claude services

The Claude review costs API credit on every push, so it is **off until you turn it on**:

1. Install the Claude GitHub app on the repository: <https://github.com/apps/claude> (or `/install-github-app` in
   Claude Code).
2. Give it access to the Claude API. Preferred: workload identity federation, which stores no secret. Create it in
   the Claude Console (Workload identity → Connect workload → GitHub Actions), then set the repository variables
   `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID` and `ANTHROPIC_SERVICE_ACCOUNT_ID`
   (and `ANTHROPIC_WORKSPACE_ID` if the rule covers several workspaces). Alternative: a secret `ANTHROPIC_API_KEY`
   or `CLAUDE_CODE_OAUTH_TOKEN`. A secret wins over federation, so set only one.
3. Set the repository variable `CLAUDE_REVIEW_ENABLED` to `true`.
4. Optional, for `@claude` mentions: a second federation rule that matches only the mention workflow, with its ID in
   the variable `ANTHROPIC_MENTION_FEDERATION_RULE_ID`. Until it is set, mentions are ignored.

Each project edits **its own** checklist in `.claude/skills/pr-review/SKILL.md`. The review always reads it from the
default branch, so a pull request cannot change how it is reviewed. The label `skip-review` skips the review for the
pushes that follow, and a project's caller can add `paths-ignore` for files that never need one.

When a review fails without a reason, set the variable `CLAUDE_REVIEW_DEBUG` to `true`, rerun, read the log, then
delete the variable.

### Turning on the denylist

Built-in rules (secrets, public IPs, internal hosts) work with no setup. To also block customer, employer or internal
system names:

1. Write them in `.content-denylist` at the project root, one per line (the file is git-ignored).
2. Store the same list as a secret: `gh secret set CONTENT_DENYLIST < .content-denylist`.

Findings never print a denylisted term, only its number.

---

## Versioning and releases of the factory

- Every merge to `main` is **not** a release. A release is a tag `vX.Y.Z` on `main`.
- The [Release workflow](../.github/workflows/release.yml) checks the tag is on `main`, publishes release notes grouped
  by Conventional Commit type, and moves the major tag (`v1`) to the new release.
- **Compatible** change (new optional input, a fix, a stricter check that existing projects pass): minor or patch
  release, `v1` moves, every project picks it up on its next run.
- **Breaking** change (a removed or renamed input, a new required secret, different behavior a project relies on):
  major release `v2`. `v1` stays where it was until each project chooses to move.

```bash
git checkout main && git pull
bash scripts/release-notes.sh v1.1.0   # preview
git tag -a v1.1.0 -m "Short description"
git push origin v1.1.0
```

## Who can call the factory

The factory repository (`egov-sofa/software-factory`) is **public**, so any repository can call its services with no
setup on the factory side. Two things follow:
- Everything in the factory is public: keep employer and customer details out of it.
- Each calling repository must allow it under its own Settings → Actions → General → *Actions permissions*: "Allow
  all actions and reusable workflows", or the "select" option with `egov-sofa/software-factory/*` added. This matters
  for `egov-ai/claude-skills`, which lives in another organization.

If the factory is ever made private, it can only serve repositories of the same owner: private workflows cannot be
shared across organizations. See [CUSTOMIZING.md](CUSTOMIZING.md#why-the-factory-repo-is-public).
