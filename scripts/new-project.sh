#!/usr/bin/env bash
# Creates a new project from a factory template.
#
# Usage:
#   bash scripts/new-project.sh <name> <template> [options]
#
# Options:
#   --dir <parent>             Where to create the project (default: the folder that contains
#                              the factory, or $FACTORY_PROJECTS_DIR if set)
#   --github private|public    Also create a GitHub repo and push to it
#   --owner <github-user>      GitHub owner for CI links (default: detected with gh)
#   --no-git                   Don't initialize a git repository
#
# Example:
#   bash scripts/new-project.sh my-api python --github private
set -euo pipefail

FACTORY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="$FACTORY_HOME/templates"

die() { printf '❌ %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  printf '\nTemplates: %s\n' "$(find "$TEMPLATES" -mindepth 1 -maxdepth 1 -type d ! -name '_*' -exec basename {} \; | sort | tr '\n' ' ')"
  exit 1
}

# ---- Parse arguments -------------------------------------------------------
[[ $# -lt 2 ]] && usage
NAME="$1"; TEMPLATE="$2"; shift 2
# New projects live next to the factory by default, so they share one workspace folder.
PARENT="${FACTORY_PROJECTS_DIR:-$(dirname "$FACTORY_HOME")}"; GITHUB=""; OWNER=""; INIT_GIT=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)    PARENT="${2:?--dir needs a value}"; shift 2 ;;
    --github) GITHUB="${2:?--github needs private or public}"; shift 2 ;;
    --owner)  OWNER="${2:?--owner needs a value}"; shift 2 ;;
    --no-git) INIT_GIT=false; shift ;;
    -h|--help) usage ;;
    *) die "Unknown option: $1" ;;
  esac
done

# ---- Validate --------------------------------------------------------------
[[ "$NAME" =~ ^[a-z][a-z0-9-]*$ ]] || die "Name must be lowercase letters, digits and dashes, starting with a letter (got '$NAME')."
[[ -d "$TEMPLATES/$TEMPLATE" && "$TEMPLATE" != _* ]] || { printf '❌ Unknown template: %s\n' "$TEMPLATE" >&2; usage; }
[[ -z "$GITHUB" || "$GITHUB" == "private" || "$GITHUB" == "public" ]] || die "--github must be 'private' or 'public'."
if [[ -n "$GITHUB" ]]; then
  $INIT_GIT || die "--github requires git (don't combine it with --no-git)."
  command -v gh >/dev/null || die "--github needs the GitHub CLI: https://cli.github.com"
fi

TARGET="$PARENT/$NAME"
[[ -e "$TARGET" ]] && die "$TARGET already exists."

# GitHub owner is used in CI links to the shared workflows.
if [[ -z "$OWNER" ]] && command -v gh >/dev/null; then
  OWNER="$(gh api user -q .login 2>/dev/null || true)"
fi
if [[ -z "$OWNER" ]]; then
  OWNER="YOUR_GITHUB_USER"
  echo "⚠️  Couldn't detect your GitHub username. Run 'gh auth login' or pass --owner; using a placeholder for now."
fi

PACKAGE_NAME="${NAME//-/_}"   # Python import names can't contain dashes
YEAR="$(date +%Y)"

# ---- Copy layers: shared files first, then the template on top ----------
echo "🏭 Creating $NAME from '$TEMPLATE' in $TARGET"
mkdir -p "$TARGET"
cp -R "$TEMPLATES/_shared/." "$TARGET/"
cp -R "$TEMPLATES/$TEMPLATE/." "$TARGET/"

# ---- Fill placeholders -----------------------------------------------------
# Rename paths first (deepest first so parent renames don't break child paths).
find "$TARGET" -depth -name '*{{PACKAGE_NAME}}*' | while read -r path; do
  mv "$path" "${path//\{\{PACKAGE_NAME\}\}/$PACKAGE_NAME}"
done
# Then file contents.
grep -rl '{{' "$TARGET" 2>/dev/null | while read -r file; do
  sed -i \
    -e "s|{{PROJECT_NAME}}|$NAME|g" \
    -e "s|{{PACKAGE_NAME}}|$PACKAGE_NAME|g" \
    -e "s|{{GITHUB_OWNER}}|$OWNER|g" \
    -e "s|{{YEAR}}|$YEAR|g" \
    "$file"
done

find "$TARGET" -name '*.sh' -exec chmod +x {} +

# ---- Git -------------------------------------------------------------------
if $INIT_GIT; then
  git -C "$TARGET" init -q -b main
  git -C "$TARGET" add -A
  # --chmod keeps scripts executable even when created on Windows
  find "$TARGET" -name '*.sh' -not -path '*/.git/*' | while read -r f; do
    git -C "$TARGET" update-index --chmod=+x "${f#"$TARGET"/}"
  done
  git -C "$TARGET" commit -q -m "chore: scaffold from software-factory ($TEMPLATE template)"
  echo "✅ Git repository initialized with first commit on 'main'"
fi

if [[ -n "$GITHUB" ]]; then
  echo "🌐 Creating $GITHUB GitHub repository $OWNER/$NAME"
  (cd "$TARGET" && gh repo create "$OWNER/$NAME" "--$GITHUB" --source . --remote origin --push)
fi

# ---- Next steps ------------------------------------------------------------
echo ""
echo "✅ Project ready: $TARGET"
echo ""
echo "Next steps:"
echo "  cd \"$TARGET\""
case "$TEMPLATE" in
  typescript) echo "  npm install && npm test" ;;
  python)     echo "  python -m venv .venv && source .venv/Scripts/activate   # macOS/Linux: .venv/bin/activate"
              echo "  pip install -e \".[dev]\" && pytest" ;;
  generic)    echo "  edit scripts/check.sh and CLAUDE.md for your language" ;;
esac
echo "  claude    # then: /factory-build <your first feature>"
