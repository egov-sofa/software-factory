#!/usr/bin/env bash
# Prints release notes for a factory release: the commits since the previous release tag, grouped by their
# Conventional Commit type. Breaking changes (`feat!:` or a `BREAKING CHANGE:` footer) are listed first, because
# they need a new major tag.
#
# Usage: bash scripts/release-notes.sh <tag> [<previous-tag>]
#   <tag>           the release being made, e.g. v1.1.0 (it does not have to exist yet; HEAD is used then)
#   <previous-tag>  default: the latest vX.Y.Z tag before <tag>
set -euo pipefail

TAG="${1:?usage: release-notes.sh <tag> [<previous-tag>]}"
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then TO="$TAG"; else TO="HEAD"; fi
PREV="${2:-$(git describe --tags --abbrev=0 --match 'v[0-9]*.[0-9]*.[0-9]*' "$TO^" 2>/dev/null || true)}"
RANGE="${PREV:+$PREV..}$TO"

# One line per commit: <sha> <subject>, plus a marker when its body has a breaking-change footer.
commits="$(git log --no-merges --format='%h%x09%s%x09%b%x1e' "$RANGE" | awk -v RS='\x1e' -F'\t' '
  NF >= 2 {
    gsub(/^\n+/, "", $1)
    breaking = ($3 ~ /(^|\n)BREAKING[ -]CHANGE:/) ? "!" : ""
    print $1 "\t" $2 "\t" breaking
  }')"

section() {   # section <title> <awk condition on the type>
  local lines
  lines="$(printf '%s\n' "$commits" | awk -F'\t' -v cond="$2" '
    NF >= 2 {
      type = $2; sub(/[(:!].*/, "", type)
      breaking = ($3 == "!" || $2 ~ /^[a-z]+(\([^)]*\))?!:/)
      known = (type ~ /^(feat|fix|docs|test|refactor|perf|ci|build|chore|style|revert)$/)
      if ((cond == "breaking" && breaking) ||
          (!breaking && cond == "other" && !known) ||
          (!breaking && cond != "breaking" && cond != "other" && type ~ ("^(" cond ")$")))
        print "- " $2 " (" $1 ")"
    }')"
  [[ -n "$lines" ]] && printf '### %s\n\n%s\n\n' "$1" "$lines"
  return 0
}

printf '## %s\n\n' "$TAG"
if [[ -n "$PREV" ]]; then printf 'Changes since %s.\n\n' "$PREV"; else printf 'First release.\n\n'; fi
section "⚠️ Breaking changes (projects must move to a new major tag)" breaking
section "Features" feat
section "Fixes" fix
section "Documentation" docs
section "Tests" test
section "Maintenance" "refactor|perf|ci|build|chore|style|revert"
section "Other" other
