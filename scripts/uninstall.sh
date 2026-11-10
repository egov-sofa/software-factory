#!/usr/bin/env bash
# Removes everything install.sh added to Claude Code's config folder.
# Your own content in CLAUDE.md, and any agents or skills you created yourself, are left untouched.
set -euo pipefail

FACTORY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

for f in "$FACTORY_HOME"/claude/agents/*.md; do
  rm -fv "$CLAUDE_DIR/agents/$(basename "$f")"
done
for d in "$FACTORY_HOME"/claude/skills/*/; do
  rm -rfv "$CLAUDE_DIR/skills/$(basename "$d")"
done

target="$CLAUDE_DIR/CLAUDE.md"
if [[ -f "$target" ]]; then
  awk '
    $0 == "<!-- software-factory:start -->" { skip = 1; next }
    $0 == "<!-- software-factory:end -->"   { skip = 0; next }
    !skip
  ' "$target" > "$target.tmp" && mv "$target.tmp" "$target"
  # Delete the file if only blank lines remain.
  grep -q '[^[:space:]]' "$target" || rm -f "$target"
  echo "removed factory block from CLAUDE.md"
fi

echo "✅ software-factory uninstalled. Restart Claude Code."
