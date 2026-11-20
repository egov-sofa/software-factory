# Plan: Evals for the agents and skills (roadmap I1, first step of E6.1)

**Status:** Approved (2026-11-20: every recommended answer in "Open questions" accepted)
**Request:** roadmap I1: "Evals for agents and skills. `claude plugin eval` cases per agent: reviewer finds a planted
off-by-one, security auditor finds a planted key and SQL injection, planner writes testable acceptance criteria,
`/factory-build` does not start by itself from a natural request (it runs only when typed, I23). Each case runs with
and without the agent, so the report shows what it adds. Run by hand from a `workflow_dispatch` job with a cost
ceiling." With the 2026-11-16 change: "I1 (evals) before the enterprise track, with a 'triggers from a natural
request' case per skill and a cost ceiling." And E6.1: "Evals for every agent and architect (extends I1), run before
each release." Also the end-to-end checks the I26 plan deferred to I1 (tester asked to fix `src/` reports instead;
both reviewers report from the review folder).

## Goal

A change to an agent's or skill's instructions can make it worse today and nothing notices. After this change one
command (locally, or a manual GitHub Actions job) runs a small suite of planted-defect cases against the factory's
agents and skills, each with and without the factory, and reports a score per case, the difference the factory makes
and the cost, under a hard cost ceiling.

## Facts this plan relies on

Checked 2026-11-19 with Claude Code 2.1.310: `claude plugin eval --help`, `claude plugin eval init --help`,
`claude plugin --help`, `claude plugin validate --help`, and the case schema and messages compiled into the CLI.
Nothing was run that costs money.

**What the help says (verbatim where quoted):**

- Usage: `claude plugin eval [options] [command] [target]`. "Run eval cases (`<eval dir>/**/case.yaml` or `prompt.md`
  + `graders/*.md`; the eval dir is `evals/` unless `--eval-dir` or the manifest says otherwise) against a plugin and
  report scored results. Target is a path, a plugin name, or a `plugin@marketplace` id — installed and skills-dir
  plugins both resolve (and add a no-plugin baseline arm)."
- It runs "on your machine, as you … The first run in an untrusted plugin directory asks you to confirm
  (`--trust-plugin` answers for CI)".
- `--ablation <none|with-without>`: "default: with-without whenever a plugin resolves — by name, or from the target
  path — and none when nothing does; under with-without, graders marked with-only, incl. `tool_used: Skill`, are a
  plugin-fired indicator rather than part of the score".
- `--max-cost-usd <usd>`: "Optional hard cost ceiling; abort and report partial results if hit (exit 2). The ceiling
  is checked before each run launches, so overrun is bounded to the runs in flight … paid graders (llm/baseline) are
  skipped while free graders still score it."
- `--threshold <0..1>`: "Exit 1 if any case score is below this threshold (default: 1.0)".
- `--runs <n>`: "Override per-case runs (default: case.runs ?? 3)". `-j, --concurrency <n>` 1 to 8, default 1, all
  runs share one rate limit.
- `--json [path]`: "the full run result (prompts, graders, per-run scores) as JSON". `--output-dir <dir>`: "Directory
  for aggregate-result.json (default: `./<eval dir>/results/<timestamp>/`)". `--report <path>`: self-contained HTML
  report. `--no-publish`: "Keep the HTML report local only; skip publishing it to claude.ai" (publishing is the
  default when the account supports it).
- `--allow-tools <tools...>`: "Operator grant for gated tools (Bash, Write, Edit, WebFetch, mcp__*). Supports
  Tool(pattern:*)". Only the read-only tools (Read, Glob, Grep, Skill, …) are available without a grant.
- `--scaffold`: "Run each case's scaffold_script (runs author-supplied bash as you; off by default — only use on case
  files you authored)". `--keep-temp` keeps the scaffolded folders. `--judge-model` defaults to Haiku. `--model`,
  `--case <glob>`, `--tag <tag...>`, `--disallow-tools`, `--mocks` (MCP stand-ins, not needed here).
- `--eval-dir <dir>`: below the plugin; default "the manifest's `experimental.evals` value, else `evals/`".
- `claude plugin eval init [--bare] [name]`: writes a case through an interview, or with `--bare` "a blank template
  (`prompt.md` + `graders/criteria.md`)".
- `claude plugin validate [--strict] [--json] <path>`: "Validate a plugin or marketplace manifest, or the skills,
  agents, and commands in a directory".

**What the CLI's own schema says (read from the 2.1.310 binary, not from documentation, so verified in step 1):**

- **`case.yaml`:** `schema_version` (required, e.g. `"1.0"`), `name`, `description`, `tags`, `plugins`,
  `context: {scaffold_script, history_file, add_dirs}`, `execution: {prompt, max_turns (≤200, default 10),
  timeout_seconds (≤3600, default 300), model, allowed_tools, disallowed_tools, append_system_prompt, env, …}`,
  `runs` (≤50, default 3), `graders` (at least one, unique names), `expected_outcome`.
- **Graders**, each with `name`, `weight` (default 1) and `arm` (`with-only` or `both`):
  `regex` (`pattern`, `flags`, `match: contains | not_contains | count:N`, `target: last_message | trace | files |
  mock_calls | {source: file, path}`), `tool_used` (`tool`, `input_match`, `min`, `max`), `tool_order` (`before`,
  `after`), `file_exists` (`path`, `exists`), `llm` (`criteria`, `focus`), `baseline` (`baseline_file`, `criteria`).
  Only `llm` and `baseline` cost money.
- **Workspace:** each run gets a fresh sandboxed folder. `scaffold_script` (path relative to the case) runs as
  `bash <script>` with that folder as its working directory, a reduced environment (`PATH`, a sandbox `HOME`,
  `GIT_CONFIG_NOSYSTEM=1`) and a 120-second limit. `add_dirs` only grants reads inside the case or plugin folder.
  Fixture files must be plain files (no symlinks or hard links), and the eval folder has an entry limit.
- **Plugin resolution from a path:** `.claude-plugin/plugin.json` or `plugin.json` in the folder (or a `SKILL.md`
  for a one-skill folder). The child runs get `--plugin-dir <plugin>`, `--setting-sources user` with a sandbox
  config folder and `--permission-mode dontAsk`, so **nothing installed in `~/.claude` by `install.sh` is visible to
  a run**.
- **Report per case:** `name`, `score`, `pass_rate`, `runs[]` (`score`, `turns`, `cost_usd`, `judge_cost_usd`,
  `graders[]` with `passed` and `explanation`, `error`), and for two arms `score_without`, `pass_rate_without`,
  `runs_without`, `delta`. Console line: `✓ <case>  with 0.83  without 0.33  Δ +0.50  (6 runs)  $1.20`.
- **CI authentication:** the CLI reads `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`,
  `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_IDENTITY_TOKEN` or `ANTHROPIC_IDENTITY_TOKEN_FILE`, so it can use
  workload identity federation without `claude-code-action`.

**So, for the question "can it target the factory as it is?": no.** The factory is not a plugin, and a folder without
a manifest gives no baseline arm ("none when nothing does"). The installed copy in `~/.claude` is not loaded by the
runs either. The agents also hold `{{FACTORY_HOME}}` placeholders (in paths to `standards/` and to the hook script)
that only `install.sh` fills in. I1 therefore needs a **minimal plugin manifest in a built copy** (Design, part 1).

**From the factory itself:**

- Reviewer and security-auditor have `tools: Read, Grep, Glob` and read their input from the review folder
  `$(git rev-parse --absolute-git-dir)/factory-review/` (`changes.diff`, `files.txt`, `checks.txt`), which the
  conductor prepares (`factory-build` Stage 5, `factory-review` step 3). Report headers: reviewer
  `## Verdict: APPROVE | CHANGES_REQUESTED` with `[BLOCKER|MAJOR|MINOR] path:line`; security auditor
  `## Verdict: PASS | ISSUES_FOUND` with `[CRITICAL|HIGH|MEDIUM|LOW] path:line`.
- The planner, tester, docs-writer and implementer run `claude/hooks/agent_guard.py <agent>` as a PreToolUse hook
  from their frontmatter; a refused edit says "`<agent>` may only edit `<what>` (…); `<path>` is not one. Report what
  needs to change there instead of editing it."
- `factory-build`, `factory-new`, `factory-onboard` and `factory-ship` have `disable-model-invocation: true` (I23);
  `factory-review` does not (it changes nothing, so starting it from "review my changes" is wanted).
- The content guard (`scripts/check_content.py --all`, run by the self-test on the factory) has no path exclusions;
  a planted key written literally in a fixture would turn the self-test red.
- The Claude review's federation rule only matches `event_name: pull_request`, so it cannot serve a manual job.

## Assumptions

- **The suite lives in the factory repository** under `evals/`, and is copied into the built plugin (the eval folder
  must sit below the plugin).
- **Python fixtures.** The planted-defect projects are tiny Python projects (standard library only, `unittest`), so
  a run needs nothing installed; one stack is enough to show an agent's behaviour.
- **The main conversation model is pinned** (`--model sonnet`) so the two arms differ only by the plugin. The agents
  keep their own models (`opus` for planner, reviewer and security-auditor), so "what the factory adds" includes
  its model choice; the report says so.
- **The planted secret is assembled by the scaffold script** at run time (two halves joined with `printf`), so the
  repository never holds a string the content guard matches, and no `content-ok` marker hints at it to the auditor.
- **Step 1 is a probe:** one cheap case (under $1) that confirms the facts marked "verified in step 1" before the
  other cases are written. Where the probe disproves a fact, the fallback named in Design applies.

## Acceptance criteria

1. **Built plugin.** `python3 scripts/build_plugin.py --out <dir>` writes `<dir>/software-factory/` with
   `.claude-plugin/plugin.json` (`name: software-factory`, `version` from `git describe --tags --always`,
   `description`, `experimental: {evals: "evals"}`), `agents/`, `skills/`, `claude/hooks/agent_guard.py`,
   `standards/` and `evals/` (without `evals/results/`). Every `{{FACTORY_HOME}}` is replaced by the built folder's
   absolute path; the script fails if any placeholder is left. `claude plugin validate --strict <dir>/software-factory`
   passes.
2. **Eight cases** under `evals/<case>/` (list in Design, part 2), each with `case.yaml`, a `scaffold.sh` and its
   fixture files; every case has at least one free grader (`regex`, `tool_used` or `file_exists`) that decides the
   main outcome, and at most two `llm` graders.
3. **Fixtures build a real git repository:** each `scaffold.sh` creates a `main` commit from `repo/`, a feature
   branch commit from `change/`, and, for review cases, the review folder (`changes.diff`, `files.txt`, `checks.txt`)
   exactly as `factory-review` step 3 would. Running a `scaffold.sh` by hand in an empty folder works without
   network and without a Claude call.
4. **One entry point:** `bash scripts/run-evals.sh [--smoke] [--case <glob>] [--max-cost-usd <usd>]` builds the
   plugin into a temporary folder and runs `claude plugin eval` with `--scaffold --trust-plugin --no-publish
   --model sonnet --ablation with-without --threshold <t> --max-cost-usd <c> --json <out>/result.json --report
   <out>/report.html --output-dir <out>` and the tool grants of Design, part 3. `--smoke` adds `--runs 1`. Results go
   to `evals/results/<timestamp>/` locally (git-ignored).
5. **Cost ceiling:** the default ceiling is $20 for a full run and $6 for `--smoke` (open question 1). A run that hits
   it exits 2 and still writes the partial report.
6. **Manual CI job:** `.github/workflows/evals.yml` runs only on `workflow_dispatch` (inputs: `smoke` boolean, `case`
   glob, `max-cost-usd` number), on `main` only, `timeout-minutes: 90`, `permissions: {contents: read, id-token:
   write}`, every action pinned by SHA, the Claude Code CLI installed at a pinned version, `concurrency: evals`
   (never two at once).
7. **CI authentication by federation:** the job requests a GitHub OIDC token for audience `https://api.anthropic.com`,
   writes it to a file refreshed every 4 minutes in the background, and runs the CLI with
   `ANTHROPIC_IDENTITY_TOKEN_FILE` and the `ANTHROPIC_EVALS_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID` and
   `ANTHROPIC_SERVICE_ACCOUNT_ID` variables. If the rule variable is missing the job fails at once with a message
   pointing to CLAUDE-SERVICES-AUTH.md, before any spend. No API key secret is used.
8. **Evals rule from the script:** `scripts/claude_federation.py --evals` previews (and with `--apply` creates or
   reuses) a rule `<repo>-evals`: subject `<prefix>:ref:refs/heads/main`, claims `repository_owner`,
   `repository_owner_id`, `event_name: workflow_dispatch` and `job_workflow_ref:
   <owner>/<repo>/.github/workflows/evals.yml@refs/heads/main`; with `--set-variables` it sets
   `ANTHROPIC_EVALS_FEDERATION_RULE_ID`.
9. **Results visible:** the job writes a Markdown table to the job summary (case, score with, score without, Δ, pass
   rate, cost, and a "cost ceiling hit" or "API error" note) made by `scripts/eval_summary.py` from the JSON, and
   uploads `result.json`, `report.html` and the traces as an artifact kept 30 days. The HTML report is not published
   to claude.ai.
10. **Not a release gate yet:** a failing eval fails the job (exit 1 or 2) but blocks nothing; `release.yml` is
    unchanged (open question 3 for E6.1).
11. **Free checks in the self-test:** `validate.py` fails if `factory-build`, `factory-new`, `factory-onboard` or
    `factory-ship` lacks `disable-model-invocation: true`; new unit tests (Test plan) check the build, the summary,
    every case's structure and every scaffold script, with no Claude call.
12. **Documentation:** `evals/README.md` (how to run, read the report, add a case, what each case plants);
    CLAUDE-SERVICES-AUTH.md gains the evals rule; ROADMAP.md marks I1 in progress with this plan; the factory's own
    `.claude/skills/pr-review/SKILL.md` says the defects under `evals/*/repo/` and `evals/*/change/` are planted on
    purpose.

## Design

### Part 1: the built plugin (coordinated with I7)

`scripts/build_plugin.py --out DIR` copies `claude/agents/*.md` to `agents/`, `claude/skills/*/` to `skills/`, and
`claude/hooks/`, `standards/` and `evals/` under the same relative paths, rendering `{{FACTORY_HOME}}` to the built
folder (as `install.sh`'s `render` does), then writes the manifest:

```json
{
  "name": "software-factory",
  "version": "<git describe --tags --always>",
  "description": "Software factory agents and skills (built for evals)",
  "experimental": { "evals": "evals" }
}
```

**Why a built copy and not a manifest at the repository root:** the runs see only the plugin folder and the case
folder, so `standards/` and the guard must be inside it, and the `{{FACTORY_HOME}}` paths must be filled in; a
manifest at the root would leave the placeholders unresolved, and the hook command would point at a file that does not
exist. **Coordination with I7:** this is the smallest form of I7's build step (the roadmap names `scripts/build.py`);
I7 keeps the script, adds `.claude-plugin/marketplace.json`, and decides how the distributed plugin fills the paths
(probably `${CLAUDE_PLUGIN_ROOT}`, which hook commands expand). I1 adds no manifest to the repository root, so I7's
choices stay open.

**Probe (step 1), one case `evals/_probe/` tagged `probe`, run with `--case _probe --runs 1 --ablation none`:**
the tester is asked to edit `src/x.py` in a scaffolded repository, and to read
`$(git rev-parse --absolute-git-dir)/factory-review/probe.txt`. It confirms: (a) the scaffold runs `git`;
(b) the agent can read the review folder inside `.git`; (c) the guard in a **plugin** agent's frontmatter fires;
(d) the JSON fields `scripts/eval_summary.py` reads. Fallbacks:
- (b) fails: the scaffold also writes the folder to `.factory-review/` and the prompts pass that path (the agents
  read "the review folder you were given", so they need no change).
- (c) fails (Claude Code may ignore `hooks:` in a plugin's agents): the build also writes `hooks/hooks.json`, a
  plugin-level PreToolUse hook running `agent_guard.py --agent-from-input`, a new mode that takes the agent from the
  hook input's `agent_type` (stripping the `software-factory:` prefix) and allows calls from the main conversation
  and from other agents. This is also what I7 needs, so it is done once; its unit tests go into
  `test_agent_guard.py`.

### Part 2: the cases

Each case folder:

```
evals/<case>/
  case.yaml        prompt, limits, tools, graders
  scaffold.sh      sources ../_lib/make_repo.sh; builds the repository in the run's folder
  repo/            files of the base commit on main
  change/          files of the feature branch commit (overlaid on repo/)
  plan.md          the approved plan the change claims to implement (review and tester cases)
  checks.txt       test and lint results for the review folder (review cases)
```

`evals/_lib/make_repo.sh` (no `case.yaml`, so it is not a case): `git init -b main`, local `user.name` and
`user.email` (the sandbox has no global git config), commit `repo/` and `plan.md` (as `docs/plans/…`), `git switch -c
feat/<case>`, copy `change/`, commit, then for review cases write the review folder with the same commands as
`factory-review` step 3 and copy `checks.txt` into it.

| # | Case | Tags | Planted | Prompt (shortened) | Free graders (decide the outcome) | LLM grader |
|---|---|---|---|---|---|---|
| 1 | `reviewer-finds-off-by-one` | reviewer, core | `paginate(items, page, size)` returns `items[start:end - 1]`; the tests only check page 1 of an uneven list, so `checks.txt` is green | "Use the reviewer agent on this branch. Plan: `docs/plans/…`; review folder: `<path>`. Give me its report unchanged." | `trace` regex `Verdict:\s*CHANGES_REQUESTED`; `trace` regex `\[(BLOCKER\|MAJOR)\][^\n]*paginate\.py:\d+`; `tool_used Agent input_match reviewer min 1` (with-only) | "Names the dropped last item per page with a concrete input" |
| 2 | `reviewer-approves-clean-change` | reviewer, control | none: a correct change with tests | as 1 | `trace` regex `Verdict:\s*APPROVE`; `last_message` regex `\[(BLOCKER\|MAJOR)\]` `not_contains` | none |
| 3 | `security-finds-key-and-sqli` | security, core | `settings.py` with an AWS-style access key and secret (assembled by the scaffold); `find_user(name)` builds `f"SELECT … WHERE name = '{name}'"` from a request argument | "Use the security-auditor agent on this branch …; give me its report unchanged." | `trace` regex `Verdict:\s*ISSUES_FOUND`; `trace` regex `\[(CRITICAL\|HIGH)\][^\n]*settings\.py:\d+`; `trace` regex `\[(CRITICAL\|HIGH)\][^\n]*(users\|db)\.py:\d+` | "Gives an exploit for the injection (input such as `' OR '1'='1`) and parameterized queries as the fix" |
| 4 | `security-passes-clean-change` | security, control | none: a parameterized query, a placeholder in `.env.example` | as 3 | `trace` regex `Verdict:\s*PASS`; `last_message` regex `\[(CRITICAL\|HIGH)\]` `not_contains` | none |
| 5 | `planner-writes-testable-criteria` | planner, core | a small CLI with a `list` command; request "add a `--limit` option" | "Use the planner agent: add a --limit option to the list command. Today is 2026-11-19." | `files` regex `## Acceptance criteria`; `files` regex `(- \[ \][^\n]*\n){3,}`; `{source: file, path: src/cli.py}` regex on an original line, `contains` (code untouched) | "Each criterion is observable and testable; at least one covers an error or edge case (0, negative, not a number); no vague words such as 'works well'" |
| 6 | `tester-reports-instead-of-fixing-src` | tester, guard, core | `src/calc.py` divides with `//` where the plan says true division; a test of it fails | "Use the tester agent on plan `docs/plans/…`. If production code is wrong, also fix it in src/." | `{source: file, path: src/calc.py}` regex `//` `contains` (still unfixed); `trace` regex `may only edit test files` (with-only: the guard refused) | "The report names the bug in `src/calc.py` and says production code must change, instead of claiming it fixed it" |
| 7 | `factory-build-not-started-by-request` | skill, trigger, core | none: a small project | "Add a --verbose flag to the CLI." | `tool_used Skill input_match factory-build max 0` (arm both); `trace` regex `Factory Build Pipeline` `not_contains` | none |
| 8 | `factory-review-starts-from-request` | skill, trigger | the off-by-one of case 1 | "Can you review my changes on this branch before I open a pull request?" | `tool_used Skill input_match factory-review min 1` (with-only indicator); `trace` regex `Verdict:` | "Reports the dropped last item as a blocking finding" |

**Limits:** `max_turns` 30 for agent cases, 40 for case 8, 6 for case 7; `timeout_seconds` 600 (900 for case 8);
`runs` 3 (`--smoke` makes it 1). **Tools per case** (`allowed_tools`): read-only tools and `Agent` for cases 1 to 5
and 7; `Bash(python -m unittest:*)`, `Edit`, `Write` for case 6; `Bash(git:*)`, `Bash(mkdir:*)`, `Bash(sort:*)`, `Bash(echo:*)`, the fixture's test command (`Bash(python -m
unittest:*)`) and `Write` for case 8 (the skill prepares the review folder and `checks.txt`; amendment 2026-11-20,
review of #26). The planner writes its plan, so case 5 also gets `Write`.

**Free versus model graders:** the outcome of each case is decided by free graders on the strict report headers and on
file contents, because they never drift and cost nothing; an `llm` grader (Haiku) is added only where the point is
"found the right thing for the right reason", which a regex cannot judge. The control cases 2 and 4 keep an agent that
flags everything from scoring well. **What the baseline shows:** without the plugin there is no reviewer, no report
format, no guard and no skill, so Claude does the task in its own way; the Δ column is what the factory adds. Case 7
scores 1.0 in both arms by design (a regression shows as the with-arm dropping).

**Not in I1 (E6.1):** cases for the implementer (implements a plan's criteria and stops on an impossible plan) and
the docs-writer (edits docs only, flips the plan status), negative trigger cases for `factory-new`, `factory-onboard`
and `factory-ship` (their flag is checked for free by `validate.py`), a full `/factory-build` run, and architects.

### Part 3: running it

`scripts/run-evals.sh` (bash, like the other scripts; checked by shellcheck): builds into `mktemp -d`, runs the
command of criterion 4 with `--allow-tools Agent "Bash(python -m unittest:*)" "Bash(git:*)" "Bash(mkdir:*)" Edit
Write` (the operator grant; each case still lists what it may use), prints where the results are, and exits with the
CLI's code. It refuses to start if `claude` is missing or older than the pinned version.

**Cost estimate** (from one review of a mid-size pull request ≈ $0.50; these fixtures are a few files): a run with the
plugin ≈ $0.20–0.60 (Opus agent plus Sonnet conductor), without ≈ $0.05–0.20, case 8 ≈ $1, case 7 ≈ $0.05.
Full suite: 8 cases × 2 arms × 3 runs ≈ 48 runs ≈ **$10–18**; `--smoke` ≈ **$3–6**. Hence the default ceilings of
$20 and $6; the first real run records the actual figures in `evals/README.md`.

**Threshold:** `--threshold 0.67` (a case passes when the average run scores at least two thirds), because the default
1.0 fails on a single unlucky run of three. The job summary shows the score, not only pass or fail.

**CI job (`evals.yml`):** checkout (`persist-credentials: false`), setup-python, setup-node, `npm install -g
@anthropic-ai/claude-code@<pinned>` (a CI tool, not a project dependency; pinned because `plugin eval` is new and
its schema may change), the OIDC token step and refresher, `scripts/run-evals.sh`, then always: `eval_summary.py`
into `$GITHUB_STEP_SUMMARY` and `actions/upload-artifact` (pinned). **Why a new rule and not the review rule:** that
rule matches pull request runs only (`event_name: pull_request`), and a separate rule pinned to `evals.yml` on `main`
lets a spend limit or revocation apply to evals alone. **Why the token file is refreshed:** a GitHub OIDC token and
the Claude token it buys each live about ten minutes, and a full run takes longer.

## Files

| File | Change |
|---|---|
| `scripts/build_plugin.py` | New: builds the rendered plugin with its manifest and the evals (seed of I7's build step) |
| `scripts/run-evals.sh` | New: the one entry point, locally and in CI |
| `scripts/eval_summary.py` | New: JSON result to a Markdown table for the job summary |
| `evals/README.md` | New: run, read, add a case; the planted defects; measured cost |
| `evals/_lib/make_repo.sh` | New: shared scaffold helper |
| `evals/_probe/` | New: step-1 probe case (tag `probe`, excluded from normal runs with `--tag core,control,trigger`) |
| `evals/<8 cases>/` | New: `case.yaml`, `scaffold.sh`, `repo/`, `change/`, `plan.md`, `checks.txt` |
| `.github/workflows/evals.yml` | New: manual job |
| `scripts/claude_federation.py` | `--evals` rule and its variable |
| `scripts/validate.py` | The four side-effect skills must have `disable-model-invocation: true` |
| `claude/hooks/agent_guard.py` | Only if the probe's check (c) fails: `--agent-from-input` mode |
| `scripts/tests/test_build_plugin.py`, `test_eval_summary.py`, `test_evals_suite.py` | New unit tests |
| `scripts/tests/test_validate.py`, `test_claude_federation.py`, `test_shared_workflows.py` (and `test_agent_guard.py` if (c) fails) | Extended |
| `.github/workflows/factory-selftest.yml` | shellcheck also covers `scripts/run-evals.sh`, `evals/**/*.sh` |
| `.gitignore` | `evals/results/` |
| `.claude/skills/pr-review/SKILL.md` | The planted defects under `evals/` are intended |
| `docs/CLAUDE-SERVICES-AUTH.md`, `docs/ROADMAP.md` | Evals rule; I1 status and plan link |

## Test plan

All free, run by the self-test:

- **build_plugin:** the manifest has the four fields and is valid JSON; agents, skills, hooks, standards and evals
  are present; no `{{FACTORY_HOME}}` remains anywhere; `evals/results/` is not copied; a leftover placeholder makes
  the script fail.
- **evals suite:** every `evals/*/case.yaml` (except `_lib`) parses, has `schema_version`, a `name` equal to its
  folder, tags, unique grader names, at least one free grader, at most two `llm` graders, `max_turns` and
  `timeout_seconds` set; every `scaffold_script` exists. No fixture file holds a string the content guard flags
  (`check_content.py` over `evals/`).
- **scaffolds:** each `scaffold.sh` run in a temporary folder gives a repository on `feat/<case>` with two commits,
  the planted line present, and for review cases a review folder whose `changes.diff` contains the planted line;
  case 3's working tree contains the assembled key.
- **eval_summary:** a recorded `result.json` (saved from the probe run) gives the expected table; a partial result
  (ceiling hit), a case with an `error` run and a single-arm case (no `delta`) are each shown, not crashing.
- **validate.py:** a side-effect skill without `disable-model-invocation: true` is reported.
- **claude_federation.py --evals:** the preview shows the rule's subject and claims and the variable; an existing rule
  is reused.
- **evals.yml:** `workflow_dispatch` only, `id-token: write`, actions pinned, `--max-cost-usd` passed, `--no-publish`
  passed.
- **By hand, once (costs money):** the probe (under $1), then `--smoke` (≈ $5), then a full run (≈ $15); record the
  actual costs and the with/without scores in `evals/README.md`. Then the same from the Actions tab.

## Risks / out of scope

- **`plugin eval` is new** (the manifest key is literally `experimental.evals`). The schema above is read from one CLI
  version; pinning the CLI in CI and the probe case keep a change from breaking the suite silently.
- **Plugin agents may ignore `hooks:`.** If the probe shows it, the guard case tests the plugin-level hook of the
  fallback, not the frontmatter hook that `install.sh` users get today. Both run the same script; it also tells I7
  that the frontmatter hooks will not survive the move to a plugin.
- **Noise.** Three runs per case still vary; scores near the threshold need a re-run before anyone acts on them.
- **Cost overrun** is bounded by the ceiling to the runs in flight (one, as concurrency stays 1).
- **Running author-written bash** (`--scaffold`, `--trust-plugin`): acceptable because the cases are the factory's own
  and the job runs only on `main`; never run the suite from a fork or a pull request.
- **The factory's Claude review** may flag the planted defects in the pull request that adds them; the pr-review
  checklist line covers it.
- **Out of scope:** release gating (E6.1), cases for the implementer, docs-writer and the other skills (E6.1), other
  stacks, publishing the report to claude.ai, the main conversation's push guard (I7).

## Open questions for the user

**Answered 2026-11-20:** the maintainer accepted the recommended option for every question below;
build to those.

1. **Budget per run.** Default ceilings of $20 (full) and $6 (smoke), and three runs per case: right, or lower (for
   example two runs per case, ≈ $8–12)? Should the evals also get their own Anthropic workspace with a monthly spend
   limit, as a second guard behind `--max-cost-usd`?
2. **CI or local only for now.** CI needs a new federation rule (an `org:admin` runs `claude_federation.py --evals
   --apply --set-variables`). Do you want the CI job in I1, or local runs first and the job once the costs are known?
3. **Gating releases (E6.1).** Proposed: not in I1. Later, `release.yml` would require a successful Evals run on the
   released commit, but only when `claude/` changed since the previous tag, so documentation-only releases cost
   nothing. Agree, or gate from the start, or never gate (advisory only)?
4. **Threshold.** 0.67 per case (two of three runs), or stricter for the core cases?
5. **Main model.** Pin the conductor to Sonnet in both arms (cheaper, and the Δ isolates the plugin), or use Opus as
   most users do?
