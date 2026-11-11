#!/usr/bin/env bash
# Creates a new project from a factory template.
#
# Usage:
#   bash scripts/new-project.sh <name> <template> [options]
#
# Options:
#   --owner <org-or-user>      GitHub org/user that owns the project (required unless --dir is given)
#   --dir <parent>             Where to create the project (default: <workspace>/<owner>, where the
#                              workspace is the folder above the factory's org folder, or $FACTORY_WORKSPACE)
#   --github private|public    Also create the GitHub repo <owner>/<name> and push to it
#   --no-git                   Don't initialize a git repository
#
# Example:
#   bash scripts/new-project.sh my-api python --owner egov-ai --github private
set -euo pipefail

FACTORY_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="$FACTORY_HOME/templates"

die() { printf '❌ %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  printf '\nTemplates: %s\n' "$(find "$TEMPLATES" -mindepth 1 -maxdepth 1 -type d ! -name '_*' -exec basename {} \; | sort | tr '\n' ' ')"
  exit 1
}

# ---- Parse arguments -------------------------------------------------------
[[ $# -lt 2 ]] && usage
NAME="$1"; TEMPLATE="$2"; shift 2
PARENT=""; GITHUB=""; OWNER=""; INIT_GIT=true

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

# The owner is a deliberate choice per project (it decides the GitHub org and the local folder),
# so it's never guessed.
if [[ -z "$OWNER" && ( -z "$PARENT" || -n "$GITHUB" ) ]]; then
  choices="$(command -v gh >/dev/null && { gh api user -q .login; gh api user/orgs -q '.[].login'; } 2>/dev/null | tr '\n' ' ')"
  die "Choose who owns the project with --owner <org-or-user>.${choices:+ Options: $choices}"
fi
[[ -z "$OWNER" || "$OWNER" =~ ^[A-Za-z0-9-]+$ ]] || die "Invalid --owner '$OWNER'."

# Local layout mirrors GitHub: <workspace>/<owner>/<project>. The factory itself lives at
# <workspace>/<factory-org>/software-factory, so the workspace is two levels up.
if [[ -z "$PARENT" ]]; then
  WORKSPACE="${FACTORY_WORKSPACE:-$(dirname "$(dirname "$FACTORY_HOME")")}"
  PARENT="$WORKSPACE/$OWNER"
fi

TARGET="$PARENT/$NAME"
[[ -e "$TARGET" ]] && die "$TARGET already exists."

# Where the shared CI workflows live (e.g. egov-sofa/software-factory), read from the factory's own git remote.
FACTORY_REPO="$(git -C "$FACTORY_HOME" remote get-url origin 2>/dev/null | sed -E 's#\.git$##; s#^.*[:/]([^/]+/[^/]+)$#\1#' || true)"
if [[ -z "$FACTORY_REPO" ]]; then
  FACTORY_REPO="YOUR_ORG/software-factory"
  echo "⚠️  The factory has no git remote, so CI can't find the shared workflows. Fix .github/workflows/ci.yml later."
fi

PACKAGE_NAME="${NAME//-/_}"   # Python import names can't contain dashes
YEAR="$(date +%Y)"

# ---- Copy layers: shared files first, then the template on top ----------
echo "🏭 Creating $NAME from '$TEMPLATE' in $TARGET"
mkdir -p "$TARGET"
cp -R "$TEMPLATES/_shared/." "$TARGET/"
cp -R "$TEMPLATES/$TEMPLATE/." "$TARGET/"
# The content guard and its git hooks come from the factory itself (one source); CI runs the factory's copy at @v1.
mkdir -p "$TARGET/scripts/hooks"
cp "$FACTORY_HOME/scripts/check_content.py" "$TARGET/scripts/"
cp "$FACTORY_HOME/scripts/hooks/"* "$TARGET/scripts/hooks/"

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
    -e "s|{{FACTORY_REPO}}|$FACTORY_REPO|g" \
    -e "s|{{YEAR}}|$YEAR|g" \
    "$file"
done

find "$TARGET" -name '*.sh' -exec chmod +x {} +
chmod +x "$TARGET/scripts/check_content.py" "$TARGET/scripts/hooks/"*

# ---- Git -------------------------------------------------------------------
if $INIT_GIT; then
  git -C "$TARGET" init -q -b main
  git -C "$TARGET" add -A
  # --chmod keeps scripts executable even when created on Windows
  { find "$TARGET" -name '*.sh' -not -path '*/.git/*'
    echo "$TARGET/scripts/check_content.py"
    find "$TARGET/scripts/hooks" -type f
  } | while read -r f; do
    git -C "$TARGET" update-index --chmod=+x "${f#"$TARGET"/}"
  done
  git -C "$TARGET" commit -q -m "chore: scaffold from software-factory ($TEMPLATE template)"
  # From now on every commit runs the content guard (secrets, public IPs, internal hosts, denylist).
  git -C "$TARGET" config core.hooksPath scripts/hooks
  echo "✅ Git repository initialized with first commit on 'main' (content guard hooks on)"
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
