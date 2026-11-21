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
tools: Read, Grep, Glob         # what it's allowed to do; no Edit, Write or Bash = read-only
model: opus                     # opus | sonnet | haiku | inherit
---
```

Everything below is the agent's instructions, written in plain English. Edit them like a job description.

After changing the frontmatter of an agent or skill, run `python scripts/validate.py`. It catches a misspelled key,
a `name` that does not match the file, an unknown model or tool, a write tool or a shell given to a read-only agent,
and a planner, tester, docs-writer or implementer without its guard hook; the self-test runs it on every pull
request too. The paths each agent may edit are the tables at the top of `claude/hooks/agent_guard.py`: change them
there (with a test in `scripts/tests/test_agent_guard.py`) when a stack keeps its tests or docs somewhere else.

## Add a new agent

Create `claude/agents/my-agent.md` with the same structure, then run `install.sh`. Ideas:
- `ui-designer`: checks accessibility and responsive layout
- `db-migrator`: writes and checks database migrations
- `perf-auditor`: looks for slow code and N+1 queries

To include it in the pipeline, add a step to `claude/skills/factory-build/SKILL.md`.

## Add a new template (e.g. Go, .NET, Java)

1. Create `templates/<name>/` with the language-specific files, an `AGENTS.md` listing the exact install, lint,
   build and test commands (every AI coding agent reads it; the shared `CLAUDE.md` imports it for Claude Code), and
   `.github/workflows/ci.yml` calling an existing reusable workflow, or a new `reusable-<name>.yml`.
2. Add a `[stacks.<name>]` entry to [`templates/stacks.toml`](../templates/stacks.toml): what it is for, its
   tools, its commands, its lockfile and its CI. `python scripts/stacks.py check` validates it.
3. Generate its fixture project: `python scripts/stacks.py fixtures <name>`. The self-test runs the shared workflow on
   it, and on every pull request a test checks it still matches a fresh scaffold.
4. Run `python -m unittest discover -s scripts/tests` and do what the failing tests name: the README row, the
   `new-project.sh` branches, the `ci-<name>` job and the matrix entry in `factory-selftest.yml`, the `/factory-new`
   recommendation. Every place that names a stack is checked against the manifest, so none can be forgotten.

Use `{{PROJECT_NAME}}`, `{{PACKAGE_NAME}}`, `{{GITHUB_OWNER}}`, `{{FACTORY_REPO}}` and `{{YEAR}}` anywhere in file contents.

### Classify a new template file

Every file a template adds has a kind, which decides what `/factory-update` does with it in existing projects. Add a
rule to [`templates/file-kinds.txt`](../templates/file-kinds.txt) (`<kind> <glob>`, the first matching rule wins) or
leave it seeded, the default:

- **managed** when projects must never change it and every update replaces it (the content guard, its hooks, the
  standards). Only Markdown files and files with `#` comments can be managed: scaffolding adds a header saying
  "Managed by software-factory: /factory-update replaces this file", as an HTML comment in Markdown and after the
  shebang line in a script. A managed file a project has edited fails `factory_update.py check`, and its edit is
  replaced (and reported) at the next update.
- **merged** when the factory keeps improving it but a project may adapt it (caller workflows, config files): an update
  merges both sides, leaving conflict markers where they overlap.
- **seeded** for everything a project makes its own (`AGENTS.md`, `README.md`, the code). Updates never touch it. If
  the factory must keep part of a seeded file current, put that part between the `software-factory:standards` markers,
  as `AGENTS.md` and the review checklist do.

`python scripts/validate.py` fails when a managed rule matches no file a template renders. Changing the scaffold
means changing both renderers, `new-project.sh` and `scripts/factory_update.py`; the parity test in
`scripts/tests/test_factory_update.py` fails until they agree.

## Change the CI pipeline (or another shared service) for all projects

Projects call the factory's workflows and actions at `@v1`, not `@main`. A merge to `main` changes nothing for them
until you **release** it:

1. Edit `.github/workflows/reusable-*.yml` (or another shared service) on a branch and merge it to `main`.
   To try a change in one project first, point that project's `uses:` line at your branch (`@my-branch`) for a while.
2. Release it, either way:
   - On GitHub: Actions → **Release** → *Run workflow* on `main`, with the version (`v1.3.0`).
   - In a terminal: preview with `bash scripts/release-notes.sh v1.3.0`, then
     `git tag -a v1.3.0 -m "Short description" && git push origin v1.3.0`.

   The [Release workflow](../.github/workflows/release.yml) publishes the release and moves `v1` to it, so every
   project uses it on its next run.

   ![Releasing the factory, as a process from merge to rollout](diagrams/release-flow.png)

> ⚠️ A **breaking** change (a removed or renamed input, a new required secret, behavior a project relies on) gets a
> new major version instead: tag `v2.0.0`. `v1` stays where it was, and each project moves to `@v2` when you choose.
> See [SHARED-SERVICES.md](SHARED-SERVICES.md#versioning-and-releases-of-the-factory).

## Why the factory repo is public

The factory lives in the `egov-sofa` org, but projects live in many orgs (`egov-ai`, `egov-infra`, …). GitHub only lets a **private** repo share its workflows with repos in the **same** org, so the factory is **public**. That way every project, in any org, can call its CI and shared services.

Public means anyone can *read* it, so **never put secrets, tokens, internal URLs or client data in this repo.** Projects keep their secrets in their own GitHub Secrets. The content guard checks pull requests for such details.

![If the factory were made private: calls from other organizations fail with "workflow was not found"](diagrams/cross-org-access-2.png)

If you ever make it private again, only projects inside `egov-sofa` keep working. Turn on sharing in GitHub → software-factory → **Settings → Actions → General → Access** → *"Accessible from repositories in the 'egov-sofa' organization"*, or from the terminal:
`gh api -X PUT repos/egov-sofa/software-factory/actions/permissions/access -f access_level=organization`.

**In each repository that calls the factory:** its own Settings → Actions → General → *Actions permissions* must
allow the factory's workflows. "Allow all actions and reusable workflows" does; if a repo allows only its own
organization's, choose the "select" option and add `egov-sofa/software-factory/*`. Do not turn on "Require actions to
be pinned to a full-length commit SHA" there: projects call the factory at the tag `@v1`.

## Change or add a diagram

Every diagram in `docs/` is generated from a YAML sketch in [`docs/diagrams/`](diagrams/) by the architecture-diagram
skill of `egov-ai/claude-skills`. Edit the sketch, never the `.drawio` or `.png`, then regenerate and look at the PNG:

```bash
bash docs/diagrams/build.sh <name>
```

`build.sh` needs a clone of claude-skills (`CLAUDE_SKILLS=/path` if it is not next to the factory's org folder) and,
for the PNG, the pinned draw.io CLI. To add a diagram, copy the sketch closest to what you need, add it to the index in
[diagrams/README.md](diagrams/README.md) and embed the PNG where it is explained. In Claude Code, the
`architecture-diagram` skill does all of this when you ask for a diagram.

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
