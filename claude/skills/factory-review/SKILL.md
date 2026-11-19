---
name: factory-review
description: Run the factory's reviewer and security-auditor agents in parallel on the current branch or uncommitted changes, without changing anything.
argument-hint: "[optional: plan file or focus area]"
---

# Factory Review

Review the current changes using the factory's specialist reviewers. Do **not** modify any files.
Extra context from the user: $ARGUMENTS

1. Run `git status` and `git diff main...HEAD --stat` (use `master` if there is no `main`) to confirm there is something to review. If there are no changes, say so and stop.
2. Look for a related plan in `docs/plans/` (the newest file, or the one named in the arguments).
3. Prepare the reviewers' input first: they have no shell, so they read it from files. With `<base>` the base branch
   (`main`, or `master` if there is no `main`) and `R="$(git rev-parse --absolute-git-dir)/factory-review"` (a folder git never commits, also in a worktree):
   ```bash
   mkdir -p "$R"
   { git diff <base>...HEAD; git diff HEAD; } > "$R/changes.diff"     # committed since <base>, then uncommitted
   { git diff --name-only <base>...HEAD; git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u > "$R/files.txt"
   ```
   Write `$R/checks.txt` with the latest test and lint results (the tester's report, or run the commands from
   `AGENTS.md`), followed by the dependency audit when the project has one (`npm audit --omit=dev`, or `pip-audit` /
   `uvx pip-audit`). Then pass the folder's full path to both reviewers.
4. Launch the `reviewer` and `security-auditor` agents **in parallel in one message**. Pass them the review folder, the plan path (if any) and any focus area from the arguments.
5. Merge the results into one prioritized table:

| # | Severity | Source | Location | Problem | Suggested fix |
|---|---|---|---|---|---|

6. End with a clear verdict (**ready to ship** or **needs fixes**) and offer to fix the blocking items with the `implementer` agent.
