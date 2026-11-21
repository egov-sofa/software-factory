# Plan: Stack manifest and a real self-test (roadmap I31)

**Status:** Implemented (2026-11-20; decisions: the recommended answer to every open question)
**Request:** "draft the I31 plan": roadmap I31: "Stack manifest and a real self-test. One `stacks.yaml` drives
templates, CI, the self-test matrix, `new-project.sh` and the catalog (I10). The self-test calls the real
`reusable-*.yml` and the content-guard action, on Linux, macOS and Windows. Why: adding a stack means five edits; a
broken reusable workflow is found by the projects after `v1` moves."

## Goal

Two things. First, one file describes each stack (typescript, python, generic). Every other place that names a stack
is either read from that file or checked against it by a test. Adding a stack then means a template folder plus one
manifest entry, and the tests list every edit that is still missing. Second, the self-test runs the real
`reusable-*.yml` workflows and the content-guard action from the pull request's own commit, so a broken shared service
fails before a release moves `v1`. Today it is found only after the move, by the projects.

## Facts this plan relies on (checked 2026-11-19 in the repository)

- **Places that name the stacks today:** the `templates/<name>/` folders. `new-project.sh` lists templates from those
  folders and has two `case "$TEMPLATE"` blocks (lockfile: `lock npm|uv`; next steps). `factory-selftest.yml` has the
  matrix `[typescript, python, generic]` and two hand-written `case` blocks (lockfile name; the CI commands copied from
  the reusable workflows). `test_new_project.py` has `TEMPLATES = (...)`. The README has a Templates table.
  `claude/skills/factory-new/SKILL.md` has the description, the `argument-hint` and the recommendation sentence.
  `docs/CUSTOMIZING.md` "Add a new template" has 5 steps. Each `templates/<name>/.github/workflows/ci.yml` names its
  reusable workflow and inputs.
- **The reusable workflows hard-code `runs-on: ubuntu-latest`.** `reusable-node.yml` and `reusable-python.yml` have a
  `working-directory` input. **`reusable-generic.yml` does not:** it runs `bash "${{ inputs.check-script }}"` from
  the repository root.
- **Release gate:** `release.yml` refuses to tag unless `factory-selftest.yml` passed on that SHA with
  `--event push`. Anything the self-test runs on push to `main` is therefore part of the gate before `v1` moves.
- **The content-guard action** fails at once without `github.event.pull_request`. It checks out `head.sha` into the
  workspace and runs `$GITHUB_ACTION_PATH/../../../scripts/check_content.py`. Denylist terms are matched
  case-insensitively, as whole words, and are never printed.
- **`test_selftest_workflow.py::test_actions_pinned_by_sha`** requires every `uses:` to be `owner/repo@<sha>`. It
  would reject `./.github/workflows/...`. `test_shared_workflows.py` already skips `./`.
- **Python is optional for `new-project.sh`.** The script never runs Python. The git hooks skip the guard when there
  is no `python3` or `python`.
- **No template uses `{{YEAR}}`** in a file, so a committed fixture does not change on 1 January.
- **The factory repository is public** (`egov-sofa/software-factory`).

## Assumptions (GitHub Actions behaviour to confirm on the first run)

- A job-level `uses: ./.github/workflows/reusable-x.yml` runs the reusable workflow **from the caller's commit**
  (the pull request's merge commit). The job can pass `with:` inputs and use `strategy.matrix`. It cannot call a file
  created at run time, so the reusable workflows run on a **committed fixture project**.
- A local composite action (`uses: ./.github/actions/content-guard`) needs a checkout first. On a `pull_request`
  event it runs like it does on `pull_request_target`, with a read-only token and no secrets on forks.
- On Windows runners the default `run:` shell is PowerShell. The self-test's own jobs set
  `defaults: run: shell: bash`, which is Git Bash. `setup-python` on Windows provides `python`, and `python3` may be
  missing, so steps use the `PY=python3 … || PY=python` fallback the hooks already use.
- Standard GitHub-hosted runners are free for public repositories, so the cost is wall-clock time and macOS
  concurrency, not paid minutes. Copies of the factory in private organisations would pay: macOS minutes cost about
  10x Linux minutes, Windows about 2x.
- `tomllib` (standard library since Python 3.11) is acceptable for the factory's own scripts and tests. The CI uses
  3.12, and Python 3.10 reached end of life in October 2026.

## Decisions proposed (the user can override them under Open questions)

1. **Format: TOML, `templates/stacks.toml`, read with `tomllib`.** It is in the standard library, allows comments
   (each field can say why) and has multi-line strings. A YAML file would need either PyYAML (today it is only
   installed in CI, for docs-drift) or a hand-written subset parser that looks like YAML but rejects valid YAML. JSON
   has no comments. A Python module is code, not data. The manifest lives under `templates/` because
   `new-project.sh`, the tests' `fake_factory()` copy and the template folders are all there.
2. **Checked by a test, not generated, everywhere except the self-test's stack commands.** The places listed above
   are short and readable, and a generator would add a build step for 3 entries. A test that names the missing line
   gives the same safety. I10 can later turn the README check into generation without changing the manifest.
3. **`new-project.sh` does not read the manifest.** Reading it would make Python a hard requirement for scaffolding.
   Its two `case` blocks are checked against the manifest by a test instead.
4. **The real reusable workflows run on Linux only,** because Linux is the only OS they declare. Running them on macOS
   or Windows would mean a new `runs-on` input for every `@v1` caller. The Windows default shell (pwsh) would also
   break their bash steps, unless `shell: bash` is set, and that turns on `pipefail` for existing callers. Cross-OS
   coverage goes where it matters: `new-project.sh` and each template's own commands, on Linux, macOS and Windows.
5. **OS matrix:** every pull request runs Linux. Push to `main`, a weekly schedule and `workflow_dispatch` run Linux,
   macOS and Windows. Because the release gate checks the push run, no release ships a Windows or macOS break. The
   weekly run catches runner-image drift.

## Acceptance criteria

1. `templates/stacks.toml` has one `[stacks.<name>]` table per template folder (not counting `_*` folders), with:
   `description` (the README "Use it for" text), `tools` (README "Tools included"), `recommend_for` (the phrase used by
   `/factory-new`), `lockfile` (`tool`, `file`, `command`; omitted for generic), `commands` (an ordered list: install,
   lint, type check, test, build, as a developer runs them), `next_steps` (the text `new-project.sh` prints), and
   `ci` (`workflow` = a file in `.github/workflows/`, `with` = the inputs the template's `ci.yml` passes).
2. `scripts/stacks.py` loads and validates the manifest. Validation fails, naming the stack and field, when: a
   required field is missing or an unknown field is present, a stack has no template folder, a template folder has no
   stack, a `ci.workflow` file does not exist, or a `ci.with` key is not an input of that workflow. Subcommands:
   `list`; `get <stack> <dotted.field>`; `commands <stack>` (one per line, LF line endings on Windows too);
   `fixtures [--check] [<stack>...]`.
3. **Checked by `scripts/tests/test_stacks.py`**, each failure naming the file and the line to add or fix:
   - `templates/<stack>/.github/workflows/ci.yml` calls `{{FACTORY_REPO}}/.github/workflows/<ci.workflow>@v1` with
     exactly the `ci.with` inputs;
   - `new-project.sh`: the lockfile `case` has `<stack>) lock <tool> <file> <command>` for each stack with a lockfile
     and no other branch, and the next-steps `case` prints `next_steps` for every stack;
   - `factory-selftest.yml`: the scaffold matrix lists exactly the manifest's stacks, and a `ci-<stack>` job per stack
     calls `./.github/workflows/<ci.workflow>` with `ci.with` plus `working-directory: tests/fixtures/<stack>`;
   - README Templates table: one row per stack, in manifest order, with `description` and `tools` verbatim;
   - `claude/skills/factory-new/SKILL.md`: the description and `argument-hint` list the manifest's stacks, and the
     recommendation sentence contains each `recommend_for` phrase;
   - each entry of `commands` appears verbatim in `templates/<stack>/AGENTS.md`.
4. `test_new_project.py` takes its template list from the manifest instead of a hard-coded tuple.
5. `tests/fixtures/<stack>/` holds a scaffolded project per stack, made with `python scripts/stacks.py fixtures`
   (name `selftest-app`, owner `example`, factory remote `example/software-factory`, no git), lockfile included.
   `fixtures --check` (and a unit test that calls it with the fake npm and uv of `test_new_project.py`) fails when
   any file other than the lockfile differs from a fresh scaffold, or when a file is missing or extra. (Amendment
   2026-11-20, review of #26: once I30 writes `.factory/answers.yml`, its `_commit` and `version` lines, which name
   the factory commit, are not compared either; I30 adds that rule to `stacks.compare`.)
6. `reusable-generic.yml` gets a `working-directory` input (default `"."`) used as `defaults.run.working-directory`.
   Its behaviour for existing callers is unchanged, and `test_shared_workflows.py` checks the default.
7. `factory-selftest.yml`:
   - `ci-typescript`, `ci-python`, `ci-generic` call the real reusable workflows (`uses: ./…`) on the fixtures, on
     every pull request and push;
   - `content-guard` (pull requests only) runs `./.github/actions/content-guard` twice: with no denylist it must pass
     on the pull request itself; with a denylist term taken from the pull request title (first word of 4 or more
     letters, passed through `env`, never interpolated into a script) it must fail (`continue-on-error` plus a
     check that the outcome is `failure`). If the title has no such word, the second run is skipped with a notice;
   - `scaffold` runs over matrix `stack × os`. `os` is `[ubuntu-latest]` on `pull_request`, and `[ubuntu-latest,
     macos-latest, windows-latest]` on `push`, `schedule` (weekly) and `workflow_dispatch`. It scaffolds with
     `new-project.sh`, checks placeholders, hooks and the lockfile (name from `stacks.py get`), runs each line of
     `stacks.py commands <stack>`, then checks that `git status --porcelain` is empty, so no command rewrote a
     tracked file such as the lockfile;
   - the hand-written `case` blocks are gone; the toolchain pins (node 22, python 3.12, uv 0.13.7, action SHAs)
     stay as they are.
8. `test_selftest_workflow.py` accepts `./` local uses and keeps the SHA rule for every other `uses:`.
9. `templates/python/AGENTS.md` shows the locked install (`uv sync --locked`) and `uv build`, so criterion 3's
   AGENTS.md check holds without the manifest inventing commands.
10. `docs/CUSTOMIZING.md` "Add a new template" becomes: folder + `AGENTS.md` + `ci.yml`; manifest entry;
    `python scripts/stacks.py fixtures <name>`; run the tests and follow what they name (README row, `new-project.sh`
    branches, a `ci-<name>` job). `docs/HOW-IT-WORKS.md` and `docs/SHARED-SERVICES.md` describe what the self-test
    now covers and the new generic input; `docs/ROADMAP.md` marks I31.
11. The full suite passes locally on Windows (Git Bash) and in CI. With Python older than 3.11, `stacks.py` exits with
    "needs Python 3.11 or later" instead of a traceback.

## Design

**Manifest** (`templates/stacks.toml`, sketch):
```toml
# One entry per template folder. Tests check README, new-project.sh, the self-test, /factory-new and each ci.yml
# against this file; scripts/stacks.py reads it.
[stacks.python]
description = "APIs, scripts, data and AI work"
tools = "uv (dependencies, `uv.lock`), pytest (tests), Ruff (lint + format), mypy (types)"
recommend_for = "data, AI or scripting"
next_steps = "uv sync && uv run pytest"
commands = ["uv sync --locked", "uv run ruff check .", "uv run ruff format --check .", "uv run mypy",
            "uv run pytest", "uv build"]
lockfile = { tool = "uv", file = "uv.lock", command = "uv lock" }
ci = { workflow = "reusable-python.yml", with = { python-version = "3.12", package-manager = "uv" } }
```

**Why committed fixtures to exercise the reusable workflows:** a reusable workflow does its own checkout in a new
job, so it cannot see a project scaffolded by another job. The alternatives were an "artifact to download" input or a
"template to scaffold" input on the shared workflows. Both would add test-only inputs to the `@v1` interface every
project sees. Fixtures need nothing new in that interface except the generic `working-directory`, which projects with
a subfolder also need. A fixture going stale is caught twice: `fixtures --check` compares it with a fresh scaffold,
and `npm ci` / `uv sync --locked` in the real workflow fail when the lockfile no longer matches.

**Reading the workflow text:** the tests keep the existing style, regexes over the workflow text with no YAML
library, so they run anywhere with the standard library. `stacks.py` validates the `ci.with` keys against the
`inputs:` block of the reusable workflow with the same regex approach `test_shared_workflows.py` uses.

**Selftest commands per stack** come from `stacks.py commands`, run in a bash loop that echoes each command
(`+ npm ci`) so the log reads like today's. This is the only place where the manifest is read at run time, because
it removes the copied `case` block that drifted from the reusable workflows.

## Files

| File | Change |
|---|---|
| `templates/stacks.toml` | New: the manifest |
| `scripts/stacks.py` | New: load/validate, `list`, `get`, `commands`, `fixtures [--check]` |
| `scripts/tests/test_stacks.py` | New: validation cases and every cross-check of criterion 3; fixture check |
| `scripts/tests/test_new_project.py` | Template list from the manifest |
| `scripts/tests/test_selftest_workflow.py` | Allow `./` uses; per-stack jobs |
| `scripts/tests/test_shared_workflows.py` | Generic `working-directory` input and default |
| `tests/fixtures/{typescript,python,generic}/` | New: generated fixture projects with lockfiles |
| `.github/workflows/factory-selftest.yml` | `ci-*` jobs, `content-guard` job, OS matrix and triggers, commands from the manifest |
| `.github/workflows/reusable-generic.yml` | `working-directory` input (additive, `@v1`-compatible) |
| `templates/python/AGENTS.md` | Mention `uv sync --locked` and `uv build` |
| `docs/CUSTOMIZING.md`, `docs/HOW-IT-WORKS.md`, `docs/SHARED-SERVICES.md`, `docs/ROADMAP.md` | Add-a-stack steps, self-test coverage, new input, I31 status |

`scripts/new-project.sh`, `README.md` and `claude/skills/factory-new/SKILL.md` should need no change: the tests check
them as they are. If a check fails, the manifest text is aligned to them, not the other way round.

## Test plan

- **stacks.py validation:** missing field, unknown field, stack without folder, folder without stack, unknown
  workflow, unknown `with` input. Each gives one clear message and exit 1.
- **Cross-checks:** for each check in criterion 3, a test on a temporary copy where one line is removed or changed
  (for example, delete the python branch of the lockfile `case`) fails with a message naming that line.
- **Fixtures:** `fixtures --check` passes on the committed fixtures, and fails after a template file is edited
  without regenerating.
- **Reusable generic input:** default `"."` and used in `defaults.run`.
- **In CI (first pull request):** the three `ci-*` jobs pass on the fixtures; the content-guard pass/fail pair
  behaves as specified; the Linux scaffold matrix passes. Then, by hand with `workflow_dispatch` on the branch, the
  macOS and Windows legs pass. Deliberately break `reusable-node.yml` (an extra `exit 1`) on a throwaway branch and
  check that `ci-typescript` goes red.

## Risks / out of scope

- **Fixture churn:** each template change needs `stacks.py fixtures`, and lockfiles add a few thousand lines.
  `npm audit` and `pip-audit` on a fixture can turn the self-test red when a new advisory appears, with no factory
  change. That is a real signal (the template's pinned versions are vulnerable) and the fix is to bump the template
  and regenerate, but it can block an unrelated pull request.
- **Windows path and shell details** (CRLF from Python, `bash` resolving to WSL, `python3` missing) are the most
  likely first-run failures; criterion 7 and the assumptions above address the known ones.
- **The content guard is tested from the pull request's copy,** which is what a self-test needs. The security
  property (taking the guard from the base branch) stays with `content-guard.yml` and is not weakened.
- **Out of scope:** running the reusable workflows on macOS/Windows (decision 4), `reusable-claude-*.yml` and the
  docs-drift action (they need secrets or cost money), `/factory-onboard`'s stack detection line, generating the
  README (I10), and the update path for existing projects (I30).

## Open questions for the user

**Answered 2026-11-20:** the maintainer accepted the recommended option for every question below;
build to those.

1. **Format and name:** `templates/stacks.toml` with stdlib `tomllib` (proposed), or keep the roadmap's
   `stacks.yaml`? YAML would mean making PyYAML a requirement for the factory's scripts, or a hand-written subset
   parser.
2. **Real reusable workflows on macOS and Windows:** accept decision 4 (Linux only; cross-OS for `new-project.sh`
   and template commands), or add a `runs-on` input to the reusable workflows so projects can run CI on other
   operating systems? The second is a new `@v1` feature with the `pipefail` caveat.
3. **When macOS and Windows run:** on push, weekly and on demand (proposed), or on every pull request too? The
   repository is public, so it is free, but each pull request would wait for the slower runners (a few minutes,
   plus macOS queueing).
4. **`new-project.sh`:** keep it independent of Python and checked by a test (proposed), or let it read the manifest
   at run time so a new stack needs no edit there, at the cost of making Python required for scaffolding?
5. **Committed fixtures with lockfiles** (proposed), or an `artifact` input on the reusable workflows, which avoids the
   committed files but adds a test-only input to the `@v1` interface?
