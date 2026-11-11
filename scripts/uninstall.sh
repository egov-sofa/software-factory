#!/usr/bin/env bash
# Removes everything install.sh added to Claude Code's config folder.
# Your own content in CLAUDE.md, and any agents or skills you created yourself, are left untouched.
set -euo pipefail

FACTORY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
MARK_START="<!-- software-factory:start -->"
MARK_END="<!-- software-factory:end -->"
target="$CLAUDE_DIR/CLAUDE.md"

# Same check as install.sh, made before anything is removed: with a marker missing, doubled, out of order or not on
# its own line, removing "the block" could delete the user's own content, so nothing is touched at all.
if [[ -f "$target" ]] && ! awk -v start="$MARK_START" -v end="$MARK_END" '
    index($0, start) || index($0, end) {
      if ($0 == start && !open && !seen) { open = 1; next }
      if ($0 == end && open) { open = 0; seen = 1; next }
      bad = 1
    }
    END { exit (bad || open) }
  ' "$target"; then
  printf '❌ %s\n' "$target has broken software-factory markers: expected one '$MARK_START' line, later one '$MARK_END' line, each on its own line. Fix or remove them by hand, then run this again. Nothing was removed." >&2
  exit 1
fi

for f in "$FACTORY_HOME"/claude/agents/*.md; do
  rm -fv "$CLAUDE_DIR/agents/$(basename "$f")"
done
for d in "$FACTORY_HOME"/claude/skills/*/; do
  rm -rfv "$CLAUDE_DIR/skills/$(basename "$d")"
done

if [[ -f "$target" ]]; then
  awk -v start="$MARK_START" -v end="$MARK_END" '
    $0 == start { skip = 1; next }
    $0 == end   { skip = 0; next }
    !skip
  ' "$target" > "$target.tmp" && mv "$target.tmp" "$target"
  # Delete the file if only blank lines remain.
  grep -q '[^[:space:]]' "$target" || rm -f "$target"
  echo "removed factory block from CLAUDE.md"
fi

echo "✅ software-factory uninstalled. Restart Claude Code."
