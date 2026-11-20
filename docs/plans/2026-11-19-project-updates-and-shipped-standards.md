# Plan: An update path for projects, with the standards shipped into them (roadmap I30 and the rest of I28)

**Status:** Approved (2026-11-20: every recommended answer in "Open questions" accepted)
**Amended 2026-11-20 (review of #26):** `new-project.sh` stays Python-free (two renderers, one parity test, see
Design); the I31 fixture check ignores the `_commit` and `version` lines of `.factory/answers.yml`.
**Request:** "Write an implementation plan for roadmap items I30 and the remaining part of I28." Roadmap I30: "Update
path for existing projects. `.factory-answers.yml` at scaffold, files marked managed or seeded, `/factory-update` with
a 3-way merge, and a weekly drift workflow that opens a pull request (the Copier and cruft pattern); or adopt Copier.
Why: scaffolded files, including each project's local copy of the content guard, drift with no way back." Roadmap I28,
open part: "standards shipped into the project instead of read from `{{FACTORY_HOME}}`. Why: Copilot, Codex and Cursor
read AGENTS.md; CI cannot reach a local factory path."

## Goal

A project created by the factory, or onboarded into it, can take the factory's later changes: the content guard and
its hooks are replaced, the caller workflows and config files are merged with the project's own edits, and the
project's code and instructions are left alone. The standards travel with the project in `.factory/standards/`, so
every AI tool and the CI review read the same rules a local Claude Code session reads. A weekly job proposes the
update as a pull request, so drift is visible instead of silent.

## Facts this plan relies on (checked 2026-11-19 in this repository)

- **Scaffolding** (`scripts/new-project.sh`): copies `templates/_shared/` then `templates/<stack>/` on top, then
  `scripts/check_content.py` and `scripts/hooks/*` from the factory, renames `{{PACKAGE_NAME}}` paths, replaces
  `{{PROJECT_NAME}}`, `{{PACKAGE_NAME}}`, `{{GITHUB_OWNER}}`, `{{FACTORY_REPO}}`, `{{YEAR}}` with `sed`, makes scripts
  executable, writes a lockfile, and commits `chore: scaffold from software-factory (<stack> template)`. It records
  nothing about the factory version or the answers, so a project cannot be re-rendered later.
- **What follows `@v1` and what is copied** (`docs/SHARED-SERVICES.md`): CI, the Claude review and mentions, the
  content guard and docs drift run from the factory at `@v1`; only the thin caller files live in the project. The
  content guard's local copy (`scripts/check_content.py`) and the hooks are copies, and nothing updates them.
- **Standards today:** `claude/agents/reviewer.md` and `security-auditor.md` read `{{FACTORY_HOME}}/standards/*.md`,
  and `claude/CLAUDE.md` points at `{{FACTORY_HOME}}/standards/`; `install.sh` fills in the factory clone's absolute
  path. No template file mentions the standards. The four files total 144 lines.
- **CI review** (`reusable-claude-review.yml`): checks out the pull request head with `persist-credentials: false`;
  the action reads `.claude/` from the default branch, but any other file Claude reads (such as `AGENTS.md`) comes from
  the pull request. It has no way to read the factory's files.
- **Composite actions find their own files** through `$GITHUB_ACTION_PATH/../../../scripts/` and run them with
  `python -I` (content-guard, docs-drift); `SHARED-SERVICES.md` records why a reusable workflow cannot do this.
- **The docs-drift caller** is the precedent for a weekly job: a caller workflow in the project with `schedule` and
  `workflow_dispatch`, calling an action at `@v1`, skipping with a notice until the project opts in (`.factory/docs.yml`),
  keeping one issue up to date with `issues: write`. `.factory/` is already the project's folder for factory metadata.
- **Marker blocks:** `install.sh` already maintains a factory-owned block between markers inside the user's own
  `CLAUDE.md`, and refuses when the markers are broken.
- **Constraints:** the factory's scripts are Python standard library only (PyYAML is installed only inside the
  docs-drift action); tests are `unittest` in `scripts/tests`, shell scripts run through `scripts/tests/support.py`;
  everything must run in Git Bash on Windows, macOS and Linux. Projects have `* text=auto eol=lf`.
- **Releases:** tags `vX.Y.Z`, a moving `v1` that only moves forward (`release-check.sh`); `v1.0.0` to `v1.2.0` exist.
- **GitHub rules for `GITHUB_TOKEN`** (GitHub Actions documentation, to re-check while implementing): it cannot create
  or change files under `.github/workflows/` (that needs the `workflows` permission, which it cannot have); a pull
  request it opens or pushes to starts no `pull_request` workflow runs; and it can open pull requests only when the
  repository (or organization) setting "Allow GitHub Actions to create and approve pull requests" is on, which is off
  by default.
- **Copier, cruft, projen** (from the 2026-11-16 research, to re-check if Copier is chosen): Copier records
  `_src_path` and `_commit` in `.copier-answers.yml` and `copier update` renders the old and new template versions
  and merges them into the project (3-way), with inline conflict markers; its known pitfall is silent divergence when
  the recorded base is wrong, fixed with `copier recopy`. Templates are Jinja; `_skip_if_exists` gives "write once"
  files; `_envops` changes the delimiters. cruft runs `cruft check` in CI and a weekly update pull request. projen
  marks generated files with a "do not edit" header and fails CI when they are edited.

## Assumptions

- **Home-made, not Copier** (recommended below; open question 1). The plan is written for that choice.
- **The answers file is `.factory/answers.yml`,** not `.factory-answers.yml` as the roadmap says: `.factory/` already
  holds `docs.yml` and will hold the standards, so one folder holds everything the factory writes for itself.
- **Standards go to `.factory/standards/`** (open question 2), as managed files. A project adds its own rules to
  `AGENTS.md`, which wins where they conflict (as `claude/CLAUDE.md` already says); it never edits the shipped copies.
- **Updates stay on the project's major version:** a project at `v1.x` is updated to the newest stable `v1.y.z`, the
  release `v1` points to. Moving to `v2` is a deliberate local `/factory-update --to v2.0.0`.
- **Drift pull requests are automatic where the repository allows it, and fall back to an issue** (open question 3).
- **The format of the answers file is a small YAML subset** (`key: value` scalars and one list of strings), read and
  written by the script itself, so no YAML library is needed.

## Copier or home-made

| | Adopt Copier | Home-made `factory_update.py` |
|---|---|---|
| New dependency | Copier (Python package) for every user, the self-test and the drift job | None: git and Python are already required by the content guard |
| Templates | Rewrite every `{{X}}` to Jinja; the workflows' `${{ ... }}` clash with Jinja, so either `{% raw %}` everywhere or custom delimiters through `_envops` | Unchanged |
| Layering (`_shared` + stack) | One template per tree; the stack layer becomes conditional file names or one template per stack with shared parts duplicated or included | Unchanged |
| 3-way merge | Mature, with migrations and `recopy` | The same core (`git merge-file` on old render, new render and the project's file), plus about 400 lines of our own around it |
| Managed files (always replaced) | No such kind: every file is merged; overwriting needs exclusions and a custom task | A file kind of its own, with a header and a check |
| Marker blocks inside a seeded file | No | Yes, reusing the `install.sh` pattern |
| Upkeep | Theirs; breaking Copier releases are ours to follow | Ours, covered by tests |

**Recommendation: home-made.** Copier's real value is the merge, and that part is `git merge-file`, which we can call
directly; everything else Copier would bring (Jinja, one-tree templates) means rewriting every template and fighting
the workflows' `${{ }}` syntax, and it would still not give the managed and marker-block kinds this plan needs.
To keep the way to Copier open, the answers file uses Copier's key names for the source and commit (`_src_path`,
`_commit`).

## Acceptance criteria

1. **File kinds are declared in one place,** `templates/file-kinds.txt`, one rule per line (`<kind> <glob>`, first
   match wins, `#` comments), with three kinds:
   - **managed:** the factory owns it; every update replaces it whole. It carries a header saying so. Files:
     `scripts/check_content.py`, `scripts/hooks/*`, `.factory/standards/*.md`.
   - **merged:** the factory provides it and the project may edit it; an update merges both (3-way). Files:
     `.github/workflows/*.yml`, `.github/dependabot.yml`, `.github/pull_request_template.md`, `.editorconfig`,
     `.gitattributes`, `.gitignore`, `CLAUDE.md`, `eslint.config.js`, `tsconfig*.json`.
   - **seeded:** written once at scaffold; the project owns it and updates never touch it. Everything else, including
     `AGENTS.md`, `README.md`, `CHANGELOG.md`, `.env.example`, `.claude/skills/pr-review/SKILL.md`, `package.json`,
     `pyproject.toml`, `scripts/check.sh`, `src/**`, `tests/**`. This is the default for a file no rule names.
   Classification always comes from the **target** version's `file-kinds.txt`.
2. **Marker blocks:** `AGENTS.md` (all three stacks) and the `pr-review` checklist hold one factory block between
   `<!-- software-factory:standards:start -->` and `<!-- software-factory:standards:end -->`. An update replaces the
   block's content, appends the block at the end when it is missing, and refuses (naming the file) when only one
   marker is present or they are out of order; the rest of the file is never changed.
3. **Scaffolding ships the standards and records the answers.** `new-project.sh` copies the factory's
   `standards/*.md` to `.factory/standards/`, adds the managed header to every managed file (after the shebang line of
   scripts; an HTML comment for Markdown), and writes `.factory/answers.yml`:
   ```yaml
   # Written by software-factory; /factory-update reads it. Edit only "skip".
   _src_path: egov-sofa/software-factory
   _commit: <full sha of the factory commit the project was rendered from>
   version: v1.3.0            # git describe --tags of that commit
   template: python
   project_name: my-api
   package_name: my_api
   github_owner: egov-ai
   year: "2026"               # kept, so a re-render does not change the licence year
   onboarded: false
   skip: []                   # files the project does not want from the factory
   ```
   When the factory clone has uncommitted changes in `templates/`, `standards/` or the copied scripts, it warns that
   the base cannot be reproduced exactly. All of this is in the first commit.
4. **References point at the shipped standards:**
   - the `AGENTS.md` block lists the four files in `.factory/standards/`, says what each is for in one line, says the
     project's own rules win where they conflict, and says to change the standards in the factory, not here;
   - the `pr-review` block tells the reviewer to read `.factory/standards/DEFINITION-OF-DONE.md` and `SECURITY.md`;
   - `claude/agents/reviewer.md` and `security-auditor.md` read `.factory/standards/<file>` in the project when it
     exists, and `{{FACTORY_HOME}}/standards/<file>` otherwise (projects not updated yet, or not factory projects);
   - `claude/CLAUDE.md` says the same in its "Full standards" line, and lists `/factory-update`.
5. **The CI review reads the standards from the base branch,** never from the pull request:
   `reusable-claude-review.yml` copies `.factory/standards/` from the pull request's base commit into
   `$RUNNER_TEMP/factory-standards/` (`git fetch --depth=1` of the base sha, then `git archive` or `git show`; no
   checkout of it) and its prompt says to read the standards there when the folder is not empty. A project without
   `.factory/standards/` is reviewed as today. No input is added or removed.
6. **`scripts/factory_update.py`** (standard library only) has these commands:
   - `render --factory <dir> --ref <ref> --answers <file> --out <dir>`: renders one factory version for one project,
     exactly as that version's `new-project.sh` would have (layers, path renames, placeholders, guard and hooks; the
     standards, headers and marker blocks only for versions whose tree has `templates/file-kinds.txt`). `skip` files
     are left out.
   - `update [--to <ref>]` (default: the newest stable tag of the recorded major): needs a clean working tree; renders
     the base (`_commit`, or the tag in `version` when that commit is not in the factory's history, with a warning) and
     the target, then per file:

     | Kind | Base | Project | Target | Result |
     |---|---|---|---|---|
     | managed | any | any | present | written from the target; when the project's copy differed from the base, reported as "local changes replaced" |
     | merged | present | present | present | `git merge-file` (labels `project`, `factory <old>`, `factory <new>`); conflicts left as markers and reported |
     | merged or managed | absent | absent | present | added |
     | merged | present | deleted | changed | not re-added; reported as "deleted here, changed in the factory" |
     | any | present | unchanged | removed | deleted |
     | any | present | changed | removed | kept; reported |
     | seeded | any | any | any | untouched, except its marker block (criterion 2) |

     Executable bits of managed scripts are set (`git update-index --chmod=+x`), files are written with LF endings,
     and a file with a NUL byte is never merged (managed: replaced; otherwise reported). It updates `_commit` and
     `version`, writes nothing outside the project, and prints a summary (replaced, merged, conflicts, added, removed,
     needs a decision) and exits 0 when clean, 1 with conflicts, 2 on a usage error.
   - `check`: exits 1 and names the files when a managed file differs from the render of the recorded version
     (projen's anti-tamper check), or when the recorded version is behind the newest stable tag of its major
     (printed as information, separate exit code 3, so CI can choose).
   - `adopt [--onboarded]`: writes `.factory/answers.yml` for a project that has none (criteria 9 and 10) after
     showing the inferred answers; refuses when the file exists.
7. **`/factory-update` skill** (`claude/skills/factory-update/SKILL.md`, `disable-model-invocation: true`): checks for
   a clean tree, creates `chore/factory-update-<version>`, runs `factory_update.py update` with the factory clone
   (fetching its tags first), shows the summary, helps resolve each conflict with the user (never choosing alone
   when both sides changed meaning), runs the project's checks from `AGENTS.md`, and commits
   `chore: update from software-factory <version>`, listing the release notes' headlines. It suggests `/factory-ship`.
8. **Weekly drift job.** A new composite action `.github/actions/factory-update` and a caller
   `templates/_shared/.github/workflows/factory-update.yml` (Mondays, plus `workflow_dispatch`). The action:
   - skips with a notice when `.factory/answers.yml` is missing;
   - clones the factory named in `_src_path` without a token (`git clone --filter=blob:none`, it is public) and runs
     its own `scripts/factory_update.py` at the pinned tag with `python3 -I`; nothing from the project runs;
   - does nothing when the project is at the target already, or when an open pull request (or issue) for the same
     target exists;
   - otherwise pushes branch `factory-update/<version>` and opens a pull request with the summary, the release notes'
     headlines, the conflicts (left as markers; the pull request is then a draft) and the decisions needed; an older
     open update pull request is closed with a comment pointing at the new one;
   - leaves changes to `.github/workflows/*` out of the pull request (`GITHUB_TOKEN` cannot push them) and lists
     them in the body with "run `/factory-update` locally";
   - says in the body that CI has not run on this pull request and how to start it (close and reopen, or push a
     commit), because a `GITHUB_TOKEN` pull request starts no workflows;
   - falls back to one issue labelled `factory-update` with the same summary when opening a pull request is not
     allowed, and says which setting allows it.
   Permissions in the caller: `contents: write`, `pull-requests: write`, `issues: write`; no secret beyond
   `GITHUB_TOKEN`; `timeout-minutes: 10`; actions pinned by SHA.
9. **Projects scaffolded before this change** run `/factory-update`, which sees no answers file and runs `adopt`:
   template from the files (`package.json` → typescript, `pyproject.toml` → python, else generic), project and
   package name from the folder, owner and factory repository from `origin` and the `uses:` line of
   `.github/workflows/ci.yml`, year and base from the scaffold commit (`chore: scaffold from software-factory`): the
   base is the newest factory tag created **at or before** that commit's date. The user confirms or corrects every
   answer before it is written. Then the normal update runs.
10. **Onboarded projects** (`adopt --onboarded`): no template base exists, so the target version is recorded as the
    base; managed files and the standards are written (the guard's diff is shown), marker blocks are added, template
    files the project does not have go to `skip`, and merged files that differ from the factory's are listed for a
    look by hand and not changed. `/factory-onboard` ends with this step, so every onboarded project has the file.
11. **`@v1` compatibility:** nothing existing is renamed or removed; projects without `.factory/` behave exactly as
    today (review, agents, onboarding); the release is a minor version.
12. `validate.py` checks that every `managed` rule in `file-kinds.txt` matches at least one rendered file, and that
    `factory-update` has `disable-model-invocation: true` (as the other skills with side effects).
13. Docs: `SHARED-SERVICES.md` (the update service, the "Local hooks" row now updated by it, the file kinds),
    `CUSTOMIZING.md` (how to classify a new template file, what a managed header means), `HOW-IT-WORKS.md`, the
    README's command table, `GLOSSARY.md` (managed, merged and seeded file; answers file), and `ROADMAP.md` (I28 done,
    I30 status).

## Design

**Why the base matters.** A 3-way merge needs what the project looked like when the factory last wrote it. Rendering
that version again from the factory's history, with the recorded answers, gives it without storing copies in the
project. A base that is too **old** only produces extra conflicts; a base that is too **new** makes the merge keep the
project's old lines silently (Copier's known pitfall). So every guess (`adopt`, a missing `_commit`) rounds down to
an older tag, never up.

**Two renderers, one parity test** (amendment 2026-11-20, review of #26). `new-project.sh` stays free of Python, as
the approved and built I31 plan decided (scaffolding must not need Python): it keeps rendering in bash and writes
`.factory/answers.yml` itself. `factory_update.py render` is the Python renderer that updates use for the old and
new versions. A **parity test** renders every template both ways at `HEAD` (and at `v1.2.0`) and requires identical
output, except `.git`, the lockfile and the answers file's `_commit` and `version` lines, so the two cannot drift.
The original text, kept for the record: `new-project.sh` keeps its argument handling, checks, lockfile, git and
GitHub steps, and calls `factory_update.py render` for the copy-and-fill part, so a scaffold and an update's
"target" are the same code and cannot drift. Python is already needed for the content guard hooks. The existing
`test_new_project.py` tests guard the move. Old factory versions are rendered from `git archive <ref>` of the factory into a temporary
folder; their layout is the same since `v1.0.0`, and the presence of `templates/file-kinds.txt` tells the renderer
whether that version shipped the standards.

**Why marker blocks instead of making `AGENTS.md` merged.** `AGENTS.md` is rewritten heavily by every project (onboarding
writes it from scratch), so a 3-way merge of the template's wording would conflict on every update. Only the
standards reference needs to stay current, and a marker block does exactly that, as `install.sh` already does for the
global `CLAUDE.md`.

**Why the CI review reads the base branch's standards.** The pull request is untrusted: if the review read
`.factory/standards/` from the pull request, a change could weaken the rules it is reviewed against. The base commit's
copy is what the project agreed to.

**Why an action and not a reusable workflow for the weekly job.** The job must run the factory's own script at the
pinned tag; an action finds it through `$GITHUB_ACTION_PATH`, as content-guard and docs-drift do. It still clones the
factory, because the merge needs the old version's files from history; the clone is of a public repository and needs
no token.

**Delivery in two pull requests.** (1) File kinds, renderer, answers file, shipped standards and references,
`update`/`check`/`adopt`, the skill, the review change, docs (closes I28). (2) The weekly action and its caller
(closes I30). The first is useful alone through `/factory-update`.

## Files

| File | Change |
|---|---|
| `templates/file-kinds.txt` | New: the managed, merged and seeded rules |
| `scripts/factory_update.py` | New: `render`, `update`, `check`, `adopt` |
| `scripts/new-project.sh` | Writes `.factory/answers.yml` and the managed headers in bash (no Python, I31); executable bits as today |
| `templates/{typescript,python,generic}/AGENTS.md` | The standards marker block |
| `templates/_shared/.claude/skills/pr-review/SKILL.md` | The standards marker block |
| `templates/_shared/.github/workflows/factory-update.yml` | New: weekly caller (second pull request) |
| `.github/actions/factory-update/action.yml` | New: the weekly job (second pull request) |
| `.github/workflows/reusable-claude-review.yml` | Base branch's `.factory/standards/` into `$RUNNER_TEMP`; prompt line |
| `claude/agents/reviewer.md`, `claude/agents/security-auditor.md`, `claude/CLAUDE.md` | Project standards first, factory path as fallback; `/factory-update` listed |
| `claude/skills/factory-update/SKILL.md` | New: the interactive update |
| `claude/skills/factory-onboard/SKILL.md` | Ends with `adopt --onboarded`; the guard and hooks come from it instead of a hand copy |
| `scripts/validate.py`, `scripts/tests/test_validate.py` | Criterion 12 |
| `scripts/tests/test_factory_update.py` | New: see the test plan |
| `scripts/tests/test_new_project.py`, `scripts/tests/test_shared_workflows.py`, `scripts/tests/test_install.py` | Answers file and standards; review step; agents' fallback text |
| `.github/workflows/factory-selftest.yml` | After scaffolding: `factory_update.py check` passes; `.factory/standards/` present; shellcheck covers nothing new |
| `docs/SHARED-SERVICES.md`, `docs/CUSTOMIZING.md`, `docs/HOW-IT-WORKS.md`, `docs/GLOSSARY.md`, `README.md`, `docs/ROADMAP.md` | Criterion 13 |

## Test plan

`scripts/tests/test_factory_update.py` builds a throwaway factory git repository in a temporary folder with two
tagged versions (`v1.0.0`, `v1.1.0`) of a small template, scaffolds from the first, edits, and updates to the second.
Shell calls go through `support.py` (isolated git config), so it runs in Git Bash on Windows too.

- **Render parity:** for each real template, `render` at `HEAD` equals what `new-project.sh` produces (except
  `.git` and the lockfile); rendering the real `v1.2.0` tag gives no `.factory/standards/` and no headers.
- **Managed:** a factory change to the guard replaces it; a local edit is replaced and reported; the header is
  present; the executable bit is set in the index.
- **Merged:** non-overlapping edits merge cleanly; overlapping edits leave markers and exit 1; a file deleted here and
  changed in the factory is not re-added and is reported; a new factory file is added; a file in `skip` is never added.
- **Seeded:** a changed seeded file in the factory leaves the project's file byte-identical, apart from its block.
- **Marker blocks:** replaced; appended when missing; a lone or reversed marker refuses with the file name.
- **Answers file:** written at scaffold with all keys; round-trips through the parser; a value outside the subset
  (nested map) is refused with a clear message; a dirty factory clone warns.
- **Base selection:** `_commit` missing from history falls back to the `version` tag with a warning; `adopt` picks
  the newest tag at or before the scaffold commit, never a later one; `--to` is limited to the recorded major unless
  given explicitly.
- **Guards:** a dirty working tree refuses; nothing is written outside the project; CRLF input files come out LF.
- **check:** clean project exits 0; a tampered managed file exits 1 naming it; a behind version exits 3.
- **Workflows (`test_shared_workflows.py`):** the review step reads the base sha, not the head, and does not check
  it out; the update caller has exactly the three write permissions and no secrets; actions are pinned by SHA.
- **Self-test:** scaffold every template, then `factory_update.py check` exits 0.
- **By hand, before releasing:** update a real project scaffolded from `v1.2.0` (adopt, conflicts, commit), and run
  the weekly job by `workflow_dispatch` in a scratch repository with the "Allow GitHub Actions to create pull
  requests" setting off (issue fallback) and on (pull request, workflow file listed but not pushed).

## Risks / out of scope

- **`GITHUB_TOKEN` limits the weekly pull request:** no workflow file changes, no CI run until a person nudges it,
  and the repository setting must be turned on. A GitHub App token (as docs-drift's optional one) would remove all
  three; left out because the request rules out secrets, and offered as open question 3.
- **Other AI tools may not open linked files:** Copilot, Codex and Cursor read `AGENTS.md`, but whether they follow
  its links to `.factory/standards/` varies. Inlining the 144 lines in the block is the alternative (open question 2).
- **Wrong answers at adoption** produce a noisy first update; rounding the base down keeps it noisy rather than
  silent. The user confirms the answers first.
- **The renderer must stay compatible with every old tag** of the current major; the render-parity test at `v1.2.0`
  catches a break, and a layout change in a future version needs a renderer that knows both.
- **Out of scope:** `v1` to `v2` automation; migrations (scripted steps between versions, as Copier has); a per-pull
  request tamper check in CI (`check` exists, wiring it in can follow); updating `~/.claude` (I7, I8); `stacks.yaml`
  (I31, which will change `file-kinds.txt` and the renderer's layer list); the docs registry template.

## Open questions for the user

**Answered 2026-11-20:** the maintainer accepted the recommended option for every question below;
build to those.

1. **Copier or home-made?** The plan recommends home-made (no new dependency, templates unchanged, managed files and
   marker blocks possible). Choose Copier if you would rather depend on a maintained tool and accept rewriting every
   template to Jinja with custom delimiters.
2. **Where do the standards live in a project?** (a) `.factory/standards/` (recommended: clearly the factory's, next
   to `answers.yml` and `docs.yml`); (b) `docs/standards/` (more visible to people and tools, but mixed with the
   project's own docs); (c) inline in `AGENTS.md`'s marker block (every tool sees them with no link to follow, at the
   cost of a 180-line `AGENTS.md`).
3. **Should drift pull requests be opened automatically?** (a) Pull request when the repository allows it, issue
   otherwise (recommended, no secret); (b) issue only, the update always run locally with `/factory-update`;
   (c) pull request with an optional GitHub App token, which also updates workflow files and starts CI. And should
   new projects get the weekly caller turned on by default?
4. **Answers file name:** `.factory/answers.yml` (this plan) or `.factory-answers.yml` (the roadmap's wording, closer
   to Copier's `.copier-answers.yml`)?
