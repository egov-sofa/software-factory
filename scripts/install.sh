#!/usr/bin/env bash
# Installs the factory's agents, skills and global rules into Claude Code's config folder.
# Safe to re-run: it updates what it installed before and backs up anything it replaces.
#
# Usage: bash scripts/install.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Absolute path of the factory repo. `pwd -W` gives a Windows-style path (C:/...) in Git Bash,
# which works both in bash and in Claude's file tools.
FACTORY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && (pwd -W 2>/dev/null || pwd))"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BACKUP_DIR="$CLAUDE_DIR/backups/software-factory-$(date +%Y%m%d-%H%M%S)"
MARK_START="<!-- software-factory:start -->"
MARK_END="<!-- software-factory:end -->"

say() { printf '%s\n' "$*"; }

# Fill {{FACTORY_HOME}} so agents can find the standards folder.
render() { sed "s|{{FACTORY_HOME}}|$FACTORY_HOME|g" "$1"; }

backup() {
  local file="$1" rel
  rel="${file#"$CLAUDE_DIR"/}"
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp "$file" "$BACKUP_DIR/$rel"
}

# Copy one file into place, backing up the old version only if it actually changed.
install_file() {
  local src="$1" dest="$2" tmp
  tmp="$(mktemp)"
  render "$src" > "$tmp"
  if [[ -f "$dest" ]] && cmp -s "$tmp" "$dest"; then
    say "  = ${dest#"$CLAUDE_DIR"/} (unchanged)"
  else
    if $DRY_RUN; then
      say "  ~ ${dest#"$CLAUDE_DIR"/} (would install)"
    else
      [[ -f "$dest" ]] && backup "$dest"
      mkdir -p "$(dirname "$dest")"
      cp "$tmp" "$dest"
      say "  + ${dest#"$CLAUDE_DIR"/}"
    fi
  fi
  rm -f "$tmp"
}

say "🏭 Installing software-factory"
say "   from: $FACTORY_HOME"
say "   into: $CLAUDE_DIR"
$DRY_RUN && say "   (dry run: nothing will be written)"
say ""

say "Agents:"
for f in "$FACTORY_HOME"/claude/agents/*.md; do
  install_file "$f" "$CLAUDE_DIR/agents/$(basename "$f")"
done

say "Skills (slash commands):"
for d in "$FACTORY_HOME"/claude/skills/*/; do
  name="$(basename "$d")"
  for f in "$d"*; do
    install_file "$f" "$CLAUDE_DIR/skills/$name/$(basename "$f")"
  done
done

# Global CLAUDE.md: manage only our marked block, so the user's own rules are never lost.
say "Global rules (CLAUDE.md):"
target="$CLAUDE_DIR/CLAUDE.md"
block="$(mktemp)"
{ say "$MARK_START"; render "$FACTORY_HOME/claude/CLAUDE.md"; say "$MARK_END"; } > "$block"
if $DRY_RUN; then
  say "  ~ CLAUDE.md (would update factory block)"
else
  mkdir -p "$CLAUDE_DIR"
  if [[ -f "$target" ]] && grep -qF "$MARK_START" "$target"; then
    backup "$target"
    # Replace everything between the markers with the new block.
    awk -v start="$MARK_START" -v end="$MARK_END" -v blockfile="$block" '
      $0 == start { while ((getline line < blockfile) > 0) print line; skip = 1; next }
      $0 == end   { skip = 0; next }
      !skip
    ' "$target" > "$target.tmp" && mv "$target.tmp" "$target"
    say "  ~ CLAUDE.md (factory block updated; your own content kept)"
  elif [[ -f "$target" ]]; then
    backup "$target"
    { printf '\n'; cat "$block"; } >> "$target"
    say "  + CLAUDE.md (factory block appended; your own content kept)"
  else
    cp "$block" "$target"
    say "  + CLAUDE.md"
  fi
fi
rm -f "$block"

say ""
[[ -d "$BACKUP_DIR" ]] && say "Backups of replaced files: $BACKUP_DIR"
say "✅ Done. Restart Claude Code, then try: /factory-build <feature>"
