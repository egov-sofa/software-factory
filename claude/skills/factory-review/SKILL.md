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
3. Launch the `reviewer` and `security-auditor` agents **in parallel in one message**. Pass them the plan path (if any) and any focus area from the arguments.
4. Merge the results into one prioritized table:

| # | Severity | Source | Location | Problem | Suggested fix |
|---|---|---|---|---|---|

5. End with a clear verdict (**ready to ship** or **needs fixes**) and offer to fix the blocking items with the `implementer` agent.
