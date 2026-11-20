---
name: factory-review
description: Run the factory's reviewer and security-auditor agents in parallel on the current branch or uncommitted changes, without changing anything.
argument-hint: "[optional: plan file or focus area]"
---

# Factory Review

Review the current changes using the factory's specialist reviewers. Do **not** modify any project file; the only
write is the review round in a plan that has pipeline state (step 6).

**Base branch:** the plan's `**Base:**` if a plan with pipeline state belongs to this branch (`$FS find --branch
"$(git branch --show-current)"`, then `$FS state <plan>`); else `git symbolic-ref --quiet --short
refs/remotes/origin/HEAD` without `origin/`; else `main` if it exists; else `master`; else ask the user. `$FS` is
`python3 "{{FACTORY_HOME}}/scripts/factory_state.py"` (or `python`).

Extra context from the user: $ARGUMENTS

1. Run `git status` and `git diff <base>...HEAD --stat` to confirm there is something to review. If there are no changes, say so and stop.
2. Look for a related plan in `docs/plans/` (the newest file, or the one named in the arguments).
3. Prepare the reviewers' input first: they have no shell, so they read it from files. With `<base>` the base branch
   above and `R="$(git rev-parse --absolute-git-dir)/factory-review"` (a folder git never commits, also in a worktree):
   ```bash
   mkdir -p "$R/reports"
   echo "<base>" > "$R/base.txt"
   { git diff <base>...HEAD; git diff HEAD; } > "$R/changes.diff"     # committed since <base>, then uncommitted
   { git diff --name-only <base>...HEAD; git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u > "$R/files.txt"
   ```
   Write `$R/checks.txt` with the latest test and lint results (the tester's report, or run the commands from
   `AGENTS.md`), followed by the dependency audit when the project has one (`npm audit --omit=dev`, or `pip-audit` /
   `uvx pip-audit`). Then pass the folder's full path to both reviewers.
4. Launch the `reviewer` and `security-auditor` agents **in parallel in one message**. Pass them the review folder, the base branch, the plan path (if any) and any focus area from the arguments.
   Save each report to `$R/reports/<agent>.md` and check it with `$FS report <agent> <file>`: gate on the values it
   prints. On exit 1, ask the same agent once for a corrected report; if it is still wrong, show the user and stop.
5. Merge the results into one prioritized table:

| # | Severity | Source | Location | Problem | Suggested fix |
|---|---|---|---|---|---|

6. **Plan with pipeline state** (`$FS state` prints `stage=…`): append this review to its `## Review rounds` as
   `### Round <n> (reviewed <short HEAD>) by /factory-review`, with `<n>` one more than the last round there, in the
   same table format `/factory-build` uses (IDs `REV-<n>.<k>`, `SEC-<n>.<k>`, and the `Result:` line with
   `blocking <count>`). Leave `Stage` and `Round` as they are, and commit the plan alone:
   `docs: review round <n> by /factory-review`. This lets `/factory-ship` tick "Reviewed" honestly. A legacy plan, or
   no plan: change nothing.
7. End with a clear verdict (**ready to ship** or **needs fixes**) and offer to fix the blocking items with the `implementer` agent.
