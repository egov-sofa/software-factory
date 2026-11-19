#!/usr/bin/env bash
# Check that a release moves forward, before its tag is created or the major tag moves: every project calling the
# factory at @v1 follows the major tag, so a release must never take it back to older code.
#   - the version is newer than the latest release of the same major (v1.2.0-rc.1 counts as v1.2.0); a v1
#     maintenance release stays possible after v2.0.0, for the projects still on @v1
#   - the commit contains the commit the major tag points to now
# Usage: release-check.sh <tag> <commit>    Exit code 0 when the release may go ahead, 1 otherwise.
set -euo pipefail

tag="${1:?usage: release-check.sh <tag> <commit>}"
commit="${2:?usage: release-check.sh <tag> <commit>}"
base="${tag%%-*}"   # v1.2.0-rc.1 -> v1.2.0
major="${base%%.*}"   # v1.2.0 -> v1

latest=$(git tag --list "$major.[0-9]*.[0-9]*" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | grep -vxF "$tag" \
  | sort -V | tail -n 1 || true)
if [ -n "$latest" ]; then
  newest=$(printf '%s\n%s\n' "$latest" "$base" | sort -V | tail -n 1)
  if [ "$latest" = "$base" ] || [ "$newest" != "$base" ]; then
    echo "::error::$tag is not newer than the latest release $latest"
    exit 1
  fi
fi

if git rev-parse -q --verify "refs/tags/$major" >/dev/null; then
  current=$(git rev-parse "$major^{commit}")
  if ! git merge-base --is-ancestor "$current" "$commit"; then
    echo "::error::$major points to ${current:0:7}, which $tag does not contain; releasing it would move $major back"
    exit 1
  fi
fi
echo "$tag moves forward from ${latest:-no earlier release}"
