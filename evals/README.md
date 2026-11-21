# Evals of the agents and skills

A change to an agent's or a skill's instructions can make it worse, and nothing else would notice. These cases give
the factory's agents and skills small projects with a planted defect, run each one **with and without the factory**
(`claude plugin eval`), and score what happened. The difference between the two is what the factory adds.

Plan and design: [docs/plans/2026-11-19-evals-for-agents-and-skills.md](../docs/plans/2026-11-19-evals-for-agents-and-skills.md)
(roadmap I1). **Every run calls the Claude API and costs money.**

## The cases

| Case | Tags | Planted | Decided by (free graders) |
|---|---|---|---|
| `reviewer-finds-off-by-one` | reviewer, core | `paginate()` drops the last item of every page; the tests only check the first item, so `checks.txt` is green | `Verdict: CHANGES_REQUESTED`; a `[BLOCKER]` or `[MAJOR]` finding on `paginate.py:<line>` |
| `reviewer-approves-clean-change` | reviewer, control | nothing: the same plan, correct and fully tested | `Verdict: APPROVE`; no `[BLOCKER]` or `[MAJOR]` in the answer |
| `security-finds-key-and-sqli` | security, core | a made-up AWS access key and secret in `accounts/settings.py`; `find_user()` builds its SQL from the request with an f-string | `Verdict: ISSUES_FOUND`; a `[CRITICAL]` or `[HIGH]` finding on `settings.py` and one on `users.py` (or `db.py`, `server.py`) |
| `security-passes-clean-change` | security, control | nothing: a parameterized query, the settings from the environment | `Verdict: PASS`; no `[CRITICAL]` or `[HIGH]` in the answer |
| `planner-writes-testable-criteria` | planner, core | a request: "add a `--limit` option to the list command" | a written plan with `## Acceptance criteria` and three or more `- [ ]` criteria; `src/cli.py` unchanged |
| `tester-reports-instead-of-fixing-src` | tester, guard, core, **shell** | `average()` uses `//` where the plan asks for true division; a test fails; the prompt asks to fix `src/` too | `src/calc.py` still holds the bug (the tester's guard refused the edit) |
| `factory-build-not-started-by-request` | skill, trigger, core | nothing: "Add a --verbose flag to the CLI." | the Skill tool never started `factory-build`; no "Factory Build Pipeline" in the trace |
| `factory-review-starts-from-request` | skill, trigger, **shell-commands** | the off-by-one of the first case; "Can you review my changes …?" | `Verdict: CHANGES_REQUESTED` (only the factory's reviewer writes it) |

The two control cases keep an agent that flags everything from scoring well. Some cases also have an `llm` grader
(Haiku, a few cents) for "found the right thing for the right reason", which a pattern cannot judge, and a `with-only`
grader that shows whether the factory's agent or skill was used (not part of the score). `_probe/` is the step-1 probe
of the plan (tag `probe`): it is never run by `run-evals.sh`.

Every case is tagged `portable`, `shell` or `shell-commands`. A `shell` case is granted `Bash`, which a run cannot get
on Windows; its outcome does not depend on the commands (the tester's guard refuses an edit either way). A
`shell-commands` case needs its commands to really run (`/factory-review` prepares the review folder with git), which
also needs a sandbox that can nest a user namespace: not on GitHub's Ubuntu runners (see below).

## Run them

You need Claude Code 2.1.310 or newer (`claude --version`), logged in with an account or key that has API credit,
Python 3, git and bash (Git Bash on Windows). From the repository root:

```bash
bash scripts/run-evals.sh --smoke                     # one run per case, ceiling $6
bash scripts/run-evals.sh                             # three runs per case, ceiling $20
bash scripts/run-evals.sh --case 'reviewer-*'         # only some cases
bash scripts/run-evals.sh --smoke --max-cost-usd 2    # a lower ceiling
```

The script builds the factory as a plugin in a temporary folder (`scripts/build_plugin.py`) and runs
`claude plugin eval` with `--scaffold --trust-plugin --no-publish --model sonnet --ablation with-without --threshold
0.66`, the cost ceiling, and the tool grants the cases need. Results go to `evals/results/<UTC time>/`
(git-ignored): `result.json`, `report.html` and `aggregate-result.json`. The exit code is the CLI's: 0 every case at
or above the threshold, 1 a case below it, 2 the cost ceiling was hit (the partial results are still written).

**The ceiling** is checked before each run starts, so a run can overshoot it by at most the run in flight (runs go
one at a time).

**Authentication.** The script sets no credential: each run uses yours. An organization API key that is not scoped to
a workspace fails every request with `must include the anthropic-workspace-id header`. Set the header in the
environment; the runs inherit it:

```bash
ANTHROPIC_CUSTOM_HEADERS="anthropic-workspace-id: wrkspc_..." bash scripts/run-evals.sh --smoke
```

### On Windows

A run that is granted a shell fails at once on Windows ("A shell tool … was granted but this machine cannot confine
it"). So in Git Bash `run-evals.sh` leaves out the `Bash(...)` grants and the cases tagged `shell` or `shell-commands`,
and says so; the other six run normally.

### On Linux

Claude Code sandboxes each Bash command with bubblewrap and socat; without a working bubblewrap `run-evals.sh`
behaves as on Windows (a Bash grant would fail every run). `plugin eval` runs each run in bubblewrap too, so the Bash
sandbox is nested. On GitHub's Ubuntu runners every command then fails (`apply-seccomp: … nested userns is
capability-restricted`; neither the AppArmor sysctls nor removing the bwrap AppArmor profile changes that). In WSL
(Ubuntu 26.04) it works. No cheap check tells the two apart, so the `shell-commands` case is **opt-in on Linux**:

```bash
EVALS_NESTED_SANDBOX=yes bash scripts/run-evals.sh --smoke --case factory-review-starts-from-request
```

It then gets a plain `Bash` grant: `/factory-review` chains commands and sets variables, which no `Bash(prefix:*)`
rule approves, and every command still runs inside the sandbox. `EVALS_SANDBOX=yes|no` skips the bubblewrap check.
macOS runs every case (Claude Code sandboxes with Seatbelt there).

**Known failure (2026-11-21):** in WSL the commands run, but `/factory-review` cannot write its review folder:
`.git` is read-only inside Claude Code's sandbox. The fix is planned in
[docs/plans/2026-11-21-review-folder-outside-git.md](../docs/plans/2026-11-21-review-folder-outside-git.md); until
then this case fails.

### In GitHub Actions

Actions, **Evals**, Run workflow (on `main` only): `smoke` (default on), `case` (a glob, empty for all) and
`max-cost-usd` (0 for the default). The job authenticates by workload identity federation with its own rule; until an
`org:admin` has created it, the job fails at its first step, before any spend
([CLAUDE-SERVICES-AUTH.md](../docs/CLAUDE-SERVICES-AUTH.md#the-factorys-evals-rule)). It writes the table below to
the job summary and keeps `result.json`, `report.html` and the run traces as an artifact for 30 days. A failing eval
fails the job but blocks nothing: it is not a release gate.

## Read the report

The job summary (or `python3 scripts/eval_summary.py evals/results/<time>/result.json` locally) has one row per case:

| Column | Meaning |
|---|---|
| Score with | the weighted share of the scored graders that passed, averaged over the runs with the factory |
| Score without | the same with no plugin: plain Claude Code doing the same task its own way |
| Δ | with minus without: what the factory adds. The agents bring their own model (Opus for the planner, reviewer and security auditor; the conversation is Sonnet in both arms), so Δ includes that choice |
| Pass rate | the share of runs that passed every scored grader |
| Failed graders (with) | which graders failed in the runs with the factory, and how often: start here |
| Notes | runs that ended in an error (an API error, a timeout), and paid graders skipped at the ceiling: a low score from these says nothing about the agent |

A case passes at a score of 0.66, two thirds (two runs of three, or two graders of three: 0.666… is below 0.67). It shows **error** instead when a run with the plugin ended
on an error: that run was not graded, and graders that need nothing to happen would score it 1.0. An error in a run
without the plugin only shows in Notes (Δ is then unreliable). `factory-build-not-started-by-request` scores 1.0 in both arms
by design; a drop in the with-plugin arm is the regression it guards against. Three runs still vary: re-run a case
near the threshold before acting on it. `report.html` shows every run with its graders' explanations; the trace of a
run (every message and tool call) is in the CI artifact, or kept locally with `--keep-traces`.

## Costs measured

| Run | Cost | Date |
|---|---|---|
| The probe, four runs of `_probe` (`--runs 1 --ablation none`) | about $0.15 in all | 2026-11-21 |
| `--smoke` on Windows (six portable cases, both arms), 357 s | $1.03 | 2026-11-21 |
| Re-run of the two cases fixed after it (planner, factory-build) | $0.39 | 2026-11-21 |
| Evals workflow `--smoke` (eight cases, both arms; shell commands failed in the nested sandbox), 384 s | $1.49 | 2026-11-21 |
| WSL, `factory-review-starts-from-request` three times while finding its grants | $0.44 | 2026-11-21 |
| Full run (all eight cases, both arms, three runs) | to be filled in (estimate $10–18) | |

## Add a case

1. Make a folder `evals/<case-name>/` with `case.yaml`, `scaffold.sh` and the fixture: `repo/` (the project on
   `main`), and as needed `change/` (the feature branch, copied over `repo/`), `plan.md` (committed as
   `docs/plans/2026-11-19-<slug>.md`) and `checks.txt` (the test and lint results of a review folder). Copy a
   neighbouring case.
2. `scaffold.sh` sources `../_lib/make_repo.sh` and calls `base_repo`, then `commit_change` and, for a review case,
   `review_folder`. It runs in the run's empty folder with a reduced environment and no network; run it by hand in an
   empty folder to check it.
3. In `case.yaml` (Claude Code 2.1.310's schema, strict: an unknown key fails the whole suite): `name` equal to the
   folder, tags with `portable`, `shell` or `shell-commands` (one of the last two when `allowed_tools` holds a `Bash(...)`), `max_turns`,
   `timeout_seconds`, and at least one free grader (`regex`, `tool_used`, `file_exists`) that decides the outcome; at
   most two `llm` graders. Match the factory's fixed formats (report headers, `[BLOCKER] path:line`, the guard's
   refusal `hook error: <agent> may only edit`), never the agent's prose: an agent can write "my edit was refused"
   while the edit went through.
4. Never commit something the content guard flags (`python3 scripts/check_content.py --all`), and never a
   key-shaped value, whole or split into parts: make a planted secret random in `scaffold.sh` when it runs, as
   `security-finds-key-and-sqli` does (`random_chars`). The factory's pull request review treats a stored key under
   `evals/` as a blocker.
5. Add the case to `SCAFFOLDS` in `scripts/tests/test_evals_suite.py` (branch, planted line, review folder) and run
   `python3 -m unittest discover -s scripts/tests`.
6. Run it once: `bash scripts/run-evals.sh --smoke --case <case-name>`.

**Run the probe** (to check a new Claude Code version cheaply, about $0.03):

```bash
out="$(mktemp -d)" && python3 scripts/build_plugin.py --out "$out" && claude plugin eval "$out/software-factory" \
  --case _probe --runs 1 --ablation none --scaffold --trust-plugin --no-publish --model sonnet \
  --allow-tools Agent Edit Write
```

**Why a built plugin.** The runs see only the plugin folder and the case folder, so `build_plugin.py` copies the
agents, skills, standards, the guard and these cases into one folder with a manifest, and fills in the
`{{FACTORY_HOME}}` paths. Claude Code does not run the `hooks:` of a plugin's agents, so the built plugin declares the
guard once in `hooks/hooks.json` (`agent_guard.py --agent-from-input`); the agents installed by `install.sh` keep
their own hooks.
