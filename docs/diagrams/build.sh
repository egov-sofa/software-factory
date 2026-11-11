#!/usr/bin/env bash
# Regenerates every diagram in docs/diagrams from its YAML sketch with the architecture-diagram engine of
# egov-ai/claude-skills: sketch -> .drawio (lint clean) -> .png (and a git-ignored .svg).
# The sketches are the source; never edit a .drawio or .png by hand. See docs/diagrams/README.md.
#
# Usage: bash docs/diagrams/build.sh [--check] [name ...]
#   --check   regenerate into a temporary folder and fail if a committed .drawio differs from its sketch
#   name      only these diagrams (file names without .yaml); default: all
#
# Needs: Python 3 with PyYAML, a clone of egov-ai/claude-skills (CLAUDE_SKILLS, default: next to this repo's org
# folder, <workspace>/egov-ai/claude-skills), and for PNG export the draw.io desktop CLI (the version in
# claude-skills' tests/golden/DRAWIO_VERSION; on Linux without a display it runs under xvfb-run).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FACTORY="$(cd "$HERE/../.." && pwd)"
SKILLS="${CLAUDE_SKILLS:-$FACTORY/../../egov-ai/claude-skills}"
ENGINE="$SKILLS/skills/architecture/architecture-diagram/scripts"
PY=python3
"$PY" -c "" >/dev/null 2>&1 || PY=python

die() { printf 'build.sh: %s\n' "$*" >&2; exit 1; }
[[ -f "$ENGINE/layout.py" ]] || die "architecture-diagram engine not found under $SKILLS; set CLAUDE_SKILLS to a clone of egov-ai/claude-skills"

CHECK=false
if [[ "${1:-}" == "--check" ]]; then CHECK=true; shift; fi

names=("$@")
if [[ ${#names[@]} -eq 0 ]]; then
  for f in "$HERE"/*.yaml; do
    n="$(basename "$f" .yaml)"
    # versions of a change diagram (<name>.before.yaml / <name>.after.yaml) are inputs, not diagrams of their own
    [[ "$n" == *.before || "$n" == *.after ]] && continue
    names+=("$n")
  done
fi

# Strict lint of one .drawio. One warning is tolerated: architecture-diagram 0.10.0 draws the legend sample of a
# trust boundary as an empty container and then reports it ("legend-bN: container without children"); the
# engine's own goldens use no trust boundary, so its tests do not see it. Remove this filter once the engine is fixed.
KNOWN='^ +W legend-b[0-9]+: container without children$'
lint() {
  local out rc=0
  out="$("$PY" "$ENGINE/lint_drawio.py" "$1" --strict)" || rc=$?
  printf '%s\n' "$out"
  [[ $rc -eq 0 ]] && return 0
  # fail on anything but the known warning: errors, other warnings, or a crash
  if printf '%s\n' "$out" | grep -E '^ +[EW] ' | grep -Evq "$KNOWN"; then return 1; fi
  printf '%s\n' "$out" | grep -Eq "$KNOWN" || return 1
  echo "  (tolerated: known engine issue with the trust-boundary legend sample, see docs/diagrams/README.md)"
}

# A change diagram is written by sketch_diff.py from its two versions, then drawn like any other sketch.
for n in "${names[@]}"; do
  if [[ -f "$HERE/$n.before.yaml" && -f "$HERE/$n.after.yaml" ]]; then
    "$PY" "$ENGINE/sketch_diff.py" "$HERE/$n.before.yaml" "$HERE/$n.after.yaml" -o "$HERE/$n.yaml" >/dev/null
  fi
done

if $CHECK; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  status=0
  for n in "${names[@]}"; do
    if ! { "$PY" "$ENGINE/layout.py" "$HERE/$n.yaml" -o "$tmp/$n.drawio" >/dev/null && lint "$tmp/$n.drawio" >/dev/null; }; then
      echo "lint failed: $n"; status=1; continue
    fi
    cmp -s "$tmp/$n.drawio" "$HERE/$n.drawio" || { echo "out of date: docs/diagrams/$n.drawio"; status=1; }
  done
  [[ $status -eq 0 ]] && echo "All ${#names[@]} diagrams match their sketches."
  exit $status
fi

for n in "${names[@]}"; do
  echo "== $n"
  "$PY" "$ENGINE/layout.py" "$HERE/$n.yaml" -o "$HERE/$n.drawio"
  lint "$HERE/$n.drawio"
  bash "$ENGINE/export.sh" "$HERE/$n.drawio" --png-scale 1
done
