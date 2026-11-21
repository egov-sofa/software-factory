#!/usr/bin/env bash
# Shared scaffold helper of the eval cases (no case.yaml here, so `claude plugin eval` does not take it for a case).
# A case's scaffold.sh sources it and runs in the run's empty folder:
#
#   . "$(dirname "$0")/../_lib/make_repo.sh"
#   base_repo <fixture> <slug>      main: <fixture>/repo/ and <fixture>/plan.md as docs/plans/2026-11-19-<slug>.md;
#                                   then switches to the branch feat/<slug>
#   commit_change <fixture> <slug>  the branch: <fixture>/change/ copied over the tree, one commit
#   review_folder <fixture>         the review folder exactly as /factory-review step 3 writes it, with
#                                   <fixture>/checks.txt as the test and lint results
#
# <fixture> is a folder with repo/, and optionally change/, plan.md and checks.txt. Everything is local: no network,
# no Claude call. The run has no global git config, so the identity is set in the repository.

base_repo() {
  local fixture="$1" slug="$2"
  git init -q -b main
  git config user.name "Eval Scaffold"
  git config user.email "evals@example.invalid"
  git config commit.gpgsign false
  cp -R "$fixture/repo/." .
  if [ -f "$fixture/plan.md" ]; then
    mkdir -p docs/plans
    cp "$fixture/plan.md" "docs/plans/2026-11-19-$slug.md"
  fi
  git add -A
  git commit -q -m "chore: the project before $slug"
  git switch -q -c "feat/$slug"
}

commit_change() {
  local fixture="$1" slug="$2"
  if [ -d "$fixture/change" ]; then
    cp -R "$fixture/change/." .
  fi
  git add -A
  git commit -q -m "feat: $slug"
}

# The same commands as claude/skills/factory-review/SKILL.md step 3, with main as the base branch: keep them in step.
review_folder() {
  local fixture="$1" R
  R="$(git rev-parse --absolute-git-dir)/factory-review"
  mkdir -p "$R/reports"
  echo "main" > "$R/base.txt"
  { git diff main...HEAD; git diff HEAD; } > "$R/changes.diff"
  { git diff --name-only main...HEAD; git diff --name-only HEAD; git ls-files --others --exclude-standard; } \
    | sort -u > "$R/files.txt"
  cp "$fixture/checks.txt" "$R/checks.txt"
}
