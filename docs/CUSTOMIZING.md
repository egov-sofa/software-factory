# Customizing the Factory

The factory is meant to grow with you. The golden rule:

> **Edit files in `~/software-factory/`, never in `~/.claude/` directly.** Then run `scripts/install.sh` again and commit your change. Otherwise your edits are lost on the next install and are never backed up to GitHub.

---

## Change how an agent behaves

Open `claude/agents/<name>.md`. The top section (between `---` lines) is **frontmatter**:

```yaml
---
name: reviewer
description: When Claude should use this agent (Claude reads this to decide)
tools: Read, Grep, Glob, Bash   # what it's allowed to do; leave out Edit/Write = read-only
model: opus                     # opus | sonnet | haiku | inherit
---
```

Everything below is the agent's instructions, written in plain English. Edit them like a job description.

## Add a new agent

Create `claude/agents/my-agent.md` with the same structure, then run `install.sh`. Ideas:
- `ui-designer`: checks accessibility and responsive layout
- `db-migrator`: writes and checks database migrations
- `perf-auditor`: looks for slow code and N+1 queries

To include it in the pipeline, add a step to `claude/skills/factory-build/SKILL.md`.

## Add a new template (e.g. Go, .NET, Java)

1. Create `templates/<name>/` with the language-specific files.
2. Put a `CLAUDE.md` in it (it replaces the shared one) listing the exact build, test and lint commands.
3. Add `.github/workflows/ci.yml`. Either call an existing reusable workflow or create `reusable-<name>.yml` in `.github/workflows/`.
4. Add the template to the matrix in `.github/workflows/factory-selftest.yml`.
5. Test it: `bash scripts/new-project.sh test-app <name> --dir /tmp`.

Use `{{PROJECT_NAME}}`, `{{PACKAGE_NAME}}`, `{{GITHUB_OWNER}}` and `{{YEAR}}` anywhere in file contents.

## Change the CI pipeline (or another shared service) for all projects

Projects call the factory's workflows and actions at `@v1`, not `@main`. A merge to `main` changes nothing for them
until you **release** it:

1. Edit `.github/workflows/reusable-*.yml` (or another shared service) on a branch and merge it to `main`.
   To try a change in one project first, point that project's `uses:` line at your branch (`@my-branch`) for a while.
2. Preview the notes: `bash scripts/release-notes.sh v1.3.0`.
3. Tag and push: `git tag -a v1.3.0 -m "Short description" && git push origin v1.3.0`.
   The [Release workflow](../.github/workflows/release.yml) publishes the release and moves `v1` to it, so every
   project uses it on its next run.

> ⚠️ A **breaking** change (a removed or renamed input, a new required secret, behavior a project relies on) gets a
> new major version instead: tag `v2.0.0`. `v1` stays where it was, and each project moves to `@v2` when you choose.
> See [SHARED-SERVICES.md](SHARED-SERVICES.md#versioning-and-releases-of-the-factory).

## Private factory repo

A **public** factory repo needs no setup: any repository can call its workflows and actions. Everything in it is then
visible to anyone, so keep employer and customer details out (the content guard checks pull requests for them).

If the factory repo is **private**, other repos can use its workflows and actions only after you allow it once, under
GitHub → software-factory → **Settings → Actions → General → Access** (the section appears only on private repos):

| Factory owned by | Choose | From the terminal |
|---|---|---|
| your personal account | *Accessible from repositories owned by the user* | `gh api -X PUT repos/<you>/software-factory/actions/permissions/access -f access_level=user` |
| an organization | *Accessible from repositories in the organization* | `gh api -X PUT repos/<org>/software-factory/actions/permissions/access -f access_level=organization` |

> ⚠️ A private factory can only be shared **within one owner** (one user, one organization, or an enterprise's
> organizations). Repositories in another organization cannot call it. Keep the factory public, or keep it and its
> users under the same owner.

**In each repository that calls the factory:** its own Settings → Actions → General → *Actions permissions* must
allow the factory's workflows. "Allow all actions and reusable workflows" does; if a repo allows only its own
organization's, choose the "select" option and add `<owner>/software-factory/*`. Do not turn on "Require actions to
be pinned to a full-length commit SHA" there: projects call the factory at the tag `@v1`.

## Adding deployment (CD)

Add a `deploy` job to a project's `ci.yml` that runs only on `main` after CI passes:

```yaml
  deploy:
    needs: ci
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production        # lets you require manual approval in GitHub settings
    steps:
      - uses: actions/checkout@v4
      - run: echo "deploy commands here"   # e.g. vercel deploy, aws, az, docker push
        env:
          API_TOKEN: ${{ secrets.API_TOKEN }}   # add secrets in repo Settings → Secrets
```

When you've deployed the same way twice, move it into a `reusable-deploy-<target>.yml` in the factory.

## Make the pipeline faster or cheaper

In `claude/skills/factory-build/SKILL.md`:
- Skip the plan-approval pause by running `/factory-build --auto <feature>` (for small, low-risk tasks).
- Change `model: opus` to `sonnet` in the reviewer and planner agents to reduce cost.
- Lower the maximum fix rounds from 2 to 1.
