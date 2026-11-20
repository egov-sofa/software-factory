# Plan: Pipeline state and typed handoffs (roadmap I29)

**Status:** Implemented (2026-11-20; decisions: the recommended answer to every open question)
**Amended 2026-11-20 (second review of #26):** `Blocking:` also counts the earlier findings the reviewer reports
`still open`, so a round-2 review cannot `APPROVE` while an earlier blocker is unfixed (criterion 6).
**Request:** "Write an implementation plan for roadmap item I29" — roadmap I29: "Pipeline state and typed handoffs.
`Stage:` and `Round:` in the plan, a 'Review rounds' log, `/factory-build --resume`, re-reviews that receive earlier
findings, strict `Verdict:` and `Blocking:` headers, the base branch passed to every agent. Why: state lives only in
the conversation; a crash or compaction loses it and re-reviews move the target."

## Goal

Make a `/factory-build` run survive a crash or a context compaction, and make its fix loop converge. After this
change the plan file records where the pipeline is (stage, fix round, base branch, branch) and what every review
round found and how the implementer answered; `/factory-build --resume` continues from that record; re-reviews see
the earlier findings and judge the answers instead of starting fresh; every agent report starts with fixed header
lines that a small script checks, so the conductor gates on parsed values instead of reading free text; and no agent
or skill assumes the base branch is `main`.

## Facts this plan relies on (checked 2026-11-19 in this repository)

- **State today:** the plan has one state line, `**Status:** Proposed`, changed to `Implemented` by the docs-writer
  (`claude/agents/docs-writer.md` step 5). The round counter of Stage 6 exists only in the conductor's context
  (`claude/skills/factory-build/SKILL.md`). Older plans also use `Done` (the I6 plan).
- **Commits per stage already exist** (I22): plan alone after Stage 2, `feat:` after Stage 3 (only the files the
  implementer lists), `test:` after Stage 4 if tests were added, `fix: address review findings` in Stage 6, `docs:`
  after Stage 7. Stages 4 and 7 can end with nothing to commit; Stage 5 never commits.
- **Re-reviews get no memory:** Stage 6 step 3 re-runs the reviewers with the plan path and the review folder only.
  The implementer answers "fixed (how) or disagree (why)" per finding (`implementer.md`), but nothing forwards those
  answers.
- **Review folder** (I26): `$(git rev-parse --absolute-git-dir)/factory-review/` with `changes.diff`, `files.txt`,
  `checks.txt`, written by the conductor; the reviewer and security-auditor have only Read, Grep, Glob.
- **Guard paths** (`claude/hooks/agent_guard.py`, `PATHS`): planner `docs/plans/**`; docs-writer `**/README*`,
  `**/CHANGELOG*`, `*.md`, `.env.example`, `docs/**`; implementer unrestricted; tester test paths only. The guard does
  not apply to the conductor (the main conversation). An agent's Write into `.git/` is refused (outside its paths).
- **Report formats today:** reviewer `## Verdict: APPROVE | CHANGES_REQUESTED` as a heading; security-auditor
  `## Verdict: PASS | ISSUES_FOUND`; tester `## Result: PASS | FAIL`; implementer, planner and docs-writer have no
  status line (the conductor infers "stopped" and "a command failed" from prose).
- **Skills are rendered by `install.sh`** (`{{FACTORY_HOME}}` is replaced in agents and skills, `scripts/install.sh`
  lines 44–45, 87–92), so a skill can call `python "{{FACTORY_HOME}}/scripts/<script>.py"`, as `factory-new` already
  calls `new-project.sh`.
- **`validate.py`** checks frontmatter only; `scripts/tests/` uses `unittest`, run by `factory-selftest.yml`
  (`python -m unittest discover -s scripts/tests -v`).
- **Hard-coded `main` in `claude/`** (`grep -rn '\bmain\b\|master' claude/`):

  | Location | Text | Action |
  |---|---|---|
  | `claude/agents/tester.md:18` | `git diff main...HEAD --stat` | use the base it is given |
  | `claude/agents/docs-writer.md:19` | `git diff main...HEAD --stat` | use the base it is given |
  | `claude/skills/factory-build/SKILL.md:19` | "Find the base branch (`main`, or `master`)", "non-main feature branch" | one detection rule, record it |
  | `claude/skills/factory-review/SKILL.md:12,15` | `git diff main...HEAD --stat (use master if …)`, base for the folder | same detection rule |
  | `claude/skills/factory-ship/SKILL.md:16` | `git diff origin/main...HEAD … \|\| git diff main...HEAD` | use the base |
  | `claude/skills/factory-ship/SKILL.md:28` | `git log main..HEAD` | use the base |
  | `claude/skills/factory-ship/SKILL.md:45` | `gh pr create --base main` | use the base |
  | `claude/skills/factory-ship/SKILL.md:13` | must not be `main`/`master` | keep, add "or the detected base" |
  | `claude/CLAUDE.md:12,24` | "never directly on `main`", "Push to `main`" | keep: policy text |
  | `claude/skills/factory-onboard/SKILL.md:34` | "never `@main`" | keep: a ref of the factory's workflows |
  | `claude/agents/planner.md:59`, `agent_guard.py:289,318` | "main risk", `def main` | not a branch |

## Assumptions

- **State lives in the plan file**, as the roadmap item says, not in the git dir: it is committed with each stage, so
  it survives a crash, a compaction, a new session and a clone; it is visible in the pull request; `/factory-ship`
  already ticks "Reviewed" only when "its result is in the plan"; and E1.5 (evidence records "next to the plan") can
  build on it. The git dir would avoid the extra commits but is lost with a worktree and invisible in review. A
  separate state file next to the plan is the alternative (open question 1).
- **The conductor writes the state, not the agents.** The planner and docs-writer only have to leave it alone, and
  their guard paths already cover `docs/plans/**`, so `agent_guard.py` needs no change.
- **Every checkpoint is a commit.** A stage that produces no files (Stage 4 with no new tests, Stage 5, Stage 7 with
  no docs changes) still commits the plan's state change. These small commits disappear in the recommended squash
  merge, and a state that is only on disk would be lost by the "stash" answer on resume.
- **A new small stdlib script parses headers and state** (`scripts/factory_state.py`), so gating does not depend on
  the model reading text correctly, the rules are unit-tested, and the I1 evals can reuse it to score reports. If
  Python is missing, the conductor applies the same rules by reading (documented fallback, like the guard's fail
  open).
- **Backwards compatible:** a plan without the new lines is a "legacy" plan: `/factory-build` runs as today,
  `/factory-ship` and `/factory-review` fall back to base detection, and only `--resume` refuses it (with the reason).
  Plans are not migrated.
- **Agents and skills are installed together** (`install.sh`), so an old agent format next to a new conductor is not
  supported; an old report simply fails the header check and gets the retry of criterion 7.

## Acceptance criteria

1. **Pipeline lines in the plan.** When the plan is approved (Stage 2), the conductor inserts four lines directly
   under `**Status:**`, in this order and form, and commits them with the plan:
   ```
   **Stage:** implement
   **Round:** 0
   **Base:** <base branch>
   **Branch:** <feature branch>
   ```
   `Stage` is the **next** stage to run: `implement`, `test`, `review`, `fix`, `docs` or `done`. `Round` is the number
   of fix rounds completed, `0` to `2`.
2. **Every checkpoint updates the state in its commit:** Stage 3 commit sets `Stage: test`; Stage 4 sets
   `Stage: review` (in the `test:` commit, or alone as `chore: factory pipeline at review` when no tests were added);
   Stage 5 appends the round to the log (criterion 3) and sets `Stage: fix` or `Stage: docs`
   (`docs: review round <n>`); Stage 6 records the answers, increments `Round` and sets `Stage: test` in the `fix:`
   commit; Stage 7 sets `Stage: done` in the `docs:` commit (alone if the docs-writer changed nothing).
3. **Review rounds log.** After each review the conductor appends to a `## Review rounds` section at the end of the
   plan (created on the first round):
   ```
   ### Round 1 (reviewed a1b2c3d)
   | ID | Severity | Location | Finding | Answer |
   |---|---|---|---|---|
   | REV-1.1 | BLOCKER | src/page.ts:42 | off-by-one on the last page | |
   | SEC-1.1 | HIGH | src/db.ts:10 | SQL built from the query string | |
   Result: reviewer CHANGES_REQUESTED, security ISSUES_FOUND, tests PASS; blocking 2
   Not blocking: REV-1.2 (MINOR) naming in src/page.ts
   ```
   IDs are `REV-<round>.<n>` and `SEC-<round>.<n>` (`n` = the finding's number in the report); a test failure is
   `TEST-<round>.<n>`. The commit reviewed is the `HEAD` the review folder was built from. After the fix, the
   **Answer** column holds the implementer's `fixed: <how>` or `disagree: <why>`, and later the outcome
   (`resolved in round 2`, `kept`, `user: drop`, `user: fix`).
4. **Re-reviews receive earlier findings.** For round 2 and later, the conductor also writes `$R/round.diff`
   (`git diff <last reviewed commit>..HEAD`, plus uncommitted changes) and tells both reviewers the round number. The
   reviewer and security-auditor then (a) read `## Review rounds` in the plan; (b) list every earlier blocking finding
   of their own under `## Earlier findings` as `<ID>: resolved | still open | disagreement accepted` with one line of
   reason; (c) report a **new** finding on code outside `round.diff` only if it is BLOCKER (reviewer) or CRITICAL
   (security), marked `(missed earlier)`. New findings on code in `round.diff` follow the normal rules.
5. **Disagreements do not loop.** A finding the implementer answered `disagree` and the reviewer reports
   `still open` is **disputed**: the conductor does not send it to the implementer again; it shows the finding, the
   answer and the reviewer's reply to the user, asks fix or drop, and records `user: fix` or `user: drop`. Remaining
   undisputed blockers continue in the fix loop; the hard 2-round cap of I22 is unchanged and is read from `Round`.
6. **Strict report headers.** Every agent's report starts with these lines, before anything else, one per line, no
   bold or heading marks (a surrounding code fence is tolerated):

   | Agent | Header lines | Consistency rule checked |
   |---|---|---|
   | planner | `Plan: docs/plans/<file>.md`, `Criteria: <n>` | the file exists; `n` ≥ 1 |
   | implementer | `Result: DONE\|STOPPED`, `Commands: PASS\|FAIL` | in fix mode an `## Answers` section with `- <ID>: fixed: …` or `- <ID>: disagree: …` for **every** ID it was sent |
   | tester | `Result: PASS\|FAIL`, `Failures: <n>` | `PASS` ⇔ `n` = 0 |
   | reviewer | `Verdict: APPROVE\|CHANGES_REQUESTED`, `Blocking: <n>` | `APPROVE` ⇔ `n` = 0; `n` = number of `[BLOCKER]`/`[MAJOR]` findings; round ≥ 2: every earlier own blocking ID listed under `## Earlier findings` |
   | security-auditor | `Verdict: PASS\|ISSUES_FOUND`, `Blocking: <n>` | `PASS` ⇒ `n` = 0; `n` = number of `[CRITICAL]`/`[HIGH]` findings; same earlier-findings rule |
   | docs-writer | `Result: UPDATED\|NO_CHANGES` | — |

   The rest of each report keeps its current sections (the `## Verdict:` / `## Result:` headings are replaced by the
   header lines).
7. **Missing or malformed header.** The conductor saves each report to `$R/reports/<agent>.md` and runs
   `python "{{FACTORY_HOME}}/scripts/factory_state.py" report <agent> <file> [--ids …] [--round n]`. On exit 1 it
   sends the parser's message back to the same agent **once** asking for a corrected report (no new work). If the
   second report also fails, it does not guess: it stops and shows the user the report and the parser message, and
   offers rerun, decide by hand, or stop. A rejected report never counts as a pass (fail closed) and never consumes a
   fix round.
8. **`/factory-build --resume [plan path]`.** Without a path, it picks the plan in `docs/plans/` whose `**Branch:**`
   equals the current branch and whose `Stage` is not `done`. None → say so and offer a fresh run; more than one →
   list them and ask. With a path whose `Branch` is not the current branch → offer to switch (only on a clean tree).
   A legacy plan (no `**Stage:**`) → refuse with "this plan was written before pipeline state; continue by hand or
   with /factory-review". `Stage: done` → say so and suggest `/factory-ship`. Otherwise it announces stage and round
   and continues at that stage (`fix` with `Round: 2` → the cap was reached: present the open blockers, as today).
   `--resume` combines with `--auto` (which then only skips approvals of plan revisions).
9. **Dirty tree on resume.** If `git status --porcelain` is not empty, the conductor shows the changes and asks:
   **stash** (recommended: `git stash push -u -m "factory-resume <stage>"`, then rerun the stage from its
   checkpoint), **keep** (rerun the stage on top; the implementer is told uncommitted changes are present), or
   **stop**. It never discards changes.
10. **Base branch to every agent.** Stage 0 detects the base once: the plan's `**Base:**` if resuming, else
    `git symbolic-ref --quiet --short refs/remotes/origin/HEAD` without `origin/`, else `main` if it exists, else
    `master`, else ask the user. Every agent prompt includes `Base branch: <base>`. The tester and docs-writer use
    `git diff <base>...HEAD --stat` ("the base branch you were given; if none, `main`, or `master` if there is no
    `main`"). The review folder also holds `base.txt`. `/factory-review` and `/factory-ship` use the same detection
    (plan `Base` first) for their diffs, `git log <base>..HEAD` and `gh pr create --base <base>`. No `main...HEAD`,
    `main..HEAD` or `--base main` remains in `claude/`.
11. **The planner and docs-writer leave the state alone.** The planner, when revising an approved plan, keeps the
    four pipeline lines and `## Review rounds` unchanged; the docs-writer changes only `**Status:**` and the criteria
    ticks. The conductor checks the pipeline lines after each of their runs (`factory_state.py state`) and restores
    them if they were changed.
12. **The conductor trusts the plan over its memory:** the skill says that after an interruption, a compaction, or
    whenever unsure, it reads stage, round and base from the plan header.
13. **`scripts/factory_state.py`** (stdlib only) offers `report` (criterion 7), `state <plan>` (prints the four
    values, or `legacy`; exit 1 on an invalid `Stage`/`Round`/missing `Base`/`Branch` in a non-legacy plan),
    `find --branch <name> [--plans docs/plans]` (criterion 8) and `last-reviewed <plan>` (the commit of the newest
    round, for `round.diff`). Exit 0 ok, 1 problem found (message on stderr), 2 usage error, like `validate.py`.
14. **`validate.py`** checks that each agent's `## Report` / `## Report format` fenced block starts with that agent's
    header lines (taken from one table in `factory_state.py`), and that no file under `claude/` contains
    `main...HEAD`, `main..HEAD` or `--base main`.
15. **`/factory-ship`** ticks "Reviewed by factory reviewer + security-auditor" when the plan's last review round
    reads `blocking 0` (or disputed findings marked `user: drop`), in addition to today's conversation rule.
16. **Docs:** `docs/HOW-IT-WORKS.md` describes the pipeline lines, the review rounds log, `--resume` and the report
    headers; `docs/ROADMAP.md` marks I29.

## Design

**One source of truth for formats.** `scripts/factory_state.py` holds `HEADERS = {agent: [(key, regex), …]}`, the
`STAGES` list and the ID pattern. The conductor calls it, `validate.py` imports `HEADERS` to check the agent files,
and the I1 evals can import it to score reports. Why a script rather than prompt rules alone: the round cap and the
pass/fail gate are the decisions that cost money or ship a bug when misread, and a parser can be unit-tested.

**Header parsing.** Skip leading blank lines and at most one opening ```` ``` ```` line; then the agent's header
lines must follow in order, matching `^(Key): (VALUE)$` exactly (`**Verdict:**` and `## Verdict:` are rejected, so
the old formats fail loudly instead of half-passing). Consistency rules from criterion 6 run on the body: counting
`[BLOCKER]`/`[MAJOR]` (or `[CRITICAL]`/`[HIGH]`) tags at the start of numbered findings, the `## Earlier findings`
and `## Answers` IDs against `--ids`. Output on success: `key=value` lines, so the conductor reads values verbatim.

**State parsing.** The four lines are read only from the block right under `# Plan:` (the first 15 lines), matching
`^\*\*(Stage|Round|Base|Branch):\*\* (.+)$`, so a plan that quotes the format in its text (like this one) is not
misread. No `**Stage:**` line → `legacy`. `find` scans `docs/plans/*.md`, keeps non-legacy plans whose Branch matches
and Stage ≠ `done`. `last-reviewed` returns the hash in the newest `### Round <n> (reviewed <hash>)` heading.

**The conductor writes state with Edit**, not through the script: the edits are two or three lines and keeping the
script read-only keeps it trivially safe to run anywhere.

**Why the log is in the plan and not only in the review folder:** the reviewers already receive the plan path, so
the earlier findings reach them with no new plumbing, and the log is committed with the fix it belongs to. Only the
per-round `round.diff`, `base.txt` and the saved reports go in the git-dir folder (scratch, regenerated each round).

**Stage map in the skill** (added as a short table): which commit closes each stage, and which `Stage` value it
writes; `--resume` jumps to the stage named. Stage 6 step 3 becomes "set `Stage: test`, commit, continue at Stage 4".

## Files

| File | Change |
|---|---|
| `scripts/factory_state.py` | New: header and state parser, `report` / `state` / `find` / `last-reviewed` |
| `scripts/tests/test_factory_state.py` | New: unit tests |
| `scripts/validate.py`, `scripts/tests/test_validate.py` | Report-block header check; no hard-coded `main` diff in `claude/` |
| `claude/skills/factory-build/SKILL.md` | `--resume` (argument-hint too), base detection, pipeline lines, stage map, review rounds log, `round.diff` and `base.txt`, header check and retry, disputed findings, "trust the plan" rule |
| `claude/skills/factory-review/SKILL.md` | Base detection (plan first), `base.txt`, header check of both reports |
| `claude/skills/factory-ship/SKILL.md` | Base from plan or detection for the secret scan, `git log` and `--base`; "Reviewed" from the log |
| `claude/agents/reviewer.md`, `claude/agents/security-auditor.md` | Header lines; `## Earlier findings`; re-review rules (criterion 4) |
| `claude/agents/implementer.md` | Header lines; `## Answers` with IDs in fix mode |
| `claude/agents/tester.md`, `claude/agents/docs-writer.md` | Header lines; `git diff <base>...HEAD`; docs-writer leaves pipeline lines alone |
| `claude/agents/planner.md` | Header lines in its Output; keep pipeline lines and `## Review rounds` when revising |
| `docs/HOW-IT-WORKS.md`, `docs/ROADMAP.md` | Pipeline state, resume, headers; I29 status |

No change to `claude/hooks/agent_guard.py`: the planner's and docs-writer's paths already include `docs/plans/`, and
the conductor, which writes the state, is not guarded.

## Test plan

Unit tests (`python -m unittest discover -s scripts/tests`):
- **`report`, per agent:** a valid header passes and prints values; missing header; wrong order; bold or heading
  form rejected; an unknown value (`Verdict: LGTM`); a fenced report accepted; `APPROVE` with `Blocking: 1`;
  `Blocking: 1` with two `[MAJOR]` findings; tester `PASS` with `Failures: 2`; implementer missing an answer for one
  of `--ids`; reviewer round 2 missing an earlier ID; planner path that does not exist.
- **`state`:** full header; legacy plan (this repo's two older plans as fixtures); invalid `Stage`; `Round: 3`;
  missing `Base`; the format quoted in the plan body is ignored.
- **`find`:** one match, none, two (both listed), a `done` plan skipped, a legacy plan skipped.
- **`last-reviewed`:** no rounds → exit 1; two rounds → the second hash.
- **`validate.py`:** a reviewer whose report block lacks `Blocking:` is reported; an agent file with
  `git diff main...HEAD` is reported; the real `claude/` tree passes.

Needs the I1 evals (prompt behaviour; by hand until then, on a scratch project):
- Kill the session after Stage 4, run `/factory-build --resume`: it continues at review, round 0.
- A planted disagreement: the implementer disagrees with a finding, the re-review reports `still open`, the
  conductor asks the user instead of spending round 2.
- Round 2 reviewer does not raise new MINOR/MAJOR findings on unchanged code.
- Each agent's real report passes `factory_state.py report` (header fidelity rate across runs).
- A repository whose base is `master`: tester, docs-writer, reviewers and `/factory-ship --base` all use `master`.

## Risks / out of scope

- **More commits per run** (up to about four state-only ones). Squash merge hides them; open question 1 offers the
  sibling-file alternative, which has the same commits.
- **Header retries cost an agent call**; a reviewer that keeps getting the header wrong stops the run for the user
  rather than looping.
- **The "no new findings on unchanged code" rule can hide a real MAJOR bug found late.** Mitigated: BLOCKER and
  CRITICAL are always allowed (`missed earlier`). A late MAJOR on unchanged code is not raised as a finding (so it
  does not count in `Blocking:`); the reviewer may mention it in prose, and the conductor lists it in the summary as
  not fixed (amendment 2026-11-20, review of #26: the earlier wording contradicted criterion 6). If the user prefers fresh eyes each round, drop rule 4(c) (open question 3).
- **The model can still edit the state wrongly**; the `state` check after planner and docs-writer runs and the
  "trust the plan" rule reduce this, they do not prevent it.
- **Out of scope:** resuming legacy plans; `/factory-review` writing to the plan's log (open question 2); evidence
  records with model and cost (E1.5); a state writer in the script; changing the guard; the evals themselves (I1).

## Open questions for the user

**Answered 2026-11-20:** the maintainer accepted the recommended option for every question below;
build to those.

1. **Where the state lives.** Recommended: in the plan (four header lines and `## Review rounds`). Alternative: a
   sibling `docs/plans/<plan>.state.md` written by the conductor, which keeps the approved plan's text untouched after
   Stage 2 (I22's "any later change to the approved plan shows up in the diff" then needs no exception). Not the git
   dir: it does not survive a new clone or a removed worktree and is invisible in the PR.
2. **Should standalone `/factory-review` append a round to the plan's log** when a plan with pipeline lines exists?
   Yes would let `/factory-ship` tick "Reviewed" after a manual review too; it would also be the first time
   `/factory-review` writes a file (it says "Do not modify any files" today).
3. **Re-review scope (criterion 4c):** limit new findings on unchanged code to BLOCKER/CRITICAL (recommended, so the
   target stops moving), or let reviewers raise anything each round as today?
4. **State-only commits:** `chore: factory pipeline at <stage>` and `docs: review round <n>` as proposed, or fold
   the review log into the next `fix:` commit (fewer commits, but a crash between review and fix loses an Opus
   review)?
