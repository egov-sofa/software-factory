# Customizing the Factory

The factory is meant to grow with you. The golden rule:

> **Edit files in `/c/DEV/PROJECTS/gitHub/egov-rdc/egov-sofa/software-factory/`, never in `~/.claude/` directly.** Then run `scripts/install.sh` again and commit your change. Otherwise your edits are lost on the next install and are never backed up to GitHub.

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

Use `{{PROJECT_NAME}}`, `{{PACKAGE_NAME}}`, `{{GITHUB_OWNER}}`, `{{FACTORY_REPO}}` and `{{YEAR}}` anywhere in file contents.

## Change the CI pipeline for all projects

Edit `.github/workflows/reusable-*.yml` and push to `main`. Every project that calls it uses the new version on its next run. No changes are needed in the projects themselves.

> ⚠️ This is powerful: a broken change breaks every project's CI. Test on a branch first. A project can pin to a branch or tag with `@my-branch` instead of `@main`.

## Why the factory repo is public

The factory lives in the `egov-sofa` org, but projects live in many orgs (`egov-ai`, `pentagone-digital`, …). GitHub only lets a **private** repo share its workflows with repos in the **same** org, so the factory is **public**. That way every project, in any org, can call its CI.

Public means anyone can *read* it, so **never put secrets, tokens, internal URLs or client data in this repo.** Projects keep their secrets in their own GitHub Secrets.

If you ever make it private again, only projects inside `egov-sofa` keep working. Turn on sharing in GitHub → software-factory → **Settings → Actions → General → Access** → *"Accessible from repositories in the 'egov-sofa' organization"*.

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
