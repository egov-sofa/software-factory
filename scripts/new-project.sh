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
  # Without gh, or with gh logged out, there are just no options to show. `|| true` keeps a failing gh from
  # ending the script here (set -e with pipefail) before the message below is printed.
  choices=""
  if command -v gh >/dev/null; then
    choices="$({ gh api user -q .login; gh api user/orgs -q '.[].login'; } 2>/dev/null | tr '\n' ' ' || true)"
  fi
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

# The factory version the project is rendered from, recorded in .factory/answers.yml: /factory-update renders it
# again as the base of its 3-way merge. --match skips the moving major tag (v1), which points at the newest release
# and would make an untagged commit look like a release.
FACTORY_COMMIT="$(git -C "$FACTORY_HOME" rev-parse -q --verify 'HEAD^{commit}' 2>/dev/null || true)"
FACTORY_VERSION=""
if [[ -n "$FACTORY_COMMIT" ]]; then
  FACTORY_VERSION="$(git -C "$FACTORY_HOME" describe --tags --abbrev=0 --match 'v[0-9]*.[0-9]*.[0-9]*' 2>/dev/null || true)"
  if [[ -n "$(git -C "$FACTORY_HOME" status --porcelain -- templates standards scripts/check_content.py scripts/hooks 2>/dev/null)" ]]; then
    echo "⚠️  The factory has uncommitted changes in its templates, standards or content guard: /factory-update cannot reproduce this project's starting point exactly."
  fi
fi
if [[ -z "$FACTORY_COMMIT" || -z "$FACTORY_VERSION" ]]; then
  echo "⚠️  The factory clone has no commit or no release tag: .factory/answers.yml records the version as unknown, so /factory-update will need --to and a base. Fetch the tags (git fetch --tags) to avoid this."
fi
FACTORY_COMMIT="${FACTORY_COMMIT:-unknown}"
FACTORY_VERSION="${FACTORY_VERSION:-unknown}"

# ---- Copy layers: shared files first, then the template on top ----------
echo "🏭 Creating $NAME from '$TEMPLATE' in $TARGET"
# From here on a failure removes the half-built project, so running the script again does not stop at
# "already exists". TARGET did not exist before (checked above), so only what this run created is removed.
tmp=""
cleanup() {
  local status=$?
  [[ -n "$tmp" ]] && rm -f "$tmp"
  if [[ $status -ne 0 && -d "$TARGET" ]]; then
    rm -rf "$TARGET"
    printf '❌ Project creation failed; removed the partial %s
' "$TARGET" >&2
  fi
}
trap cleanup EXIT
mkdir -p "$TARGET"
cp -R "$TEMPLATES/_shared/." "$TARGET/"
cp -R "$TEMPLATES/$TEMPLATE/." "$TARGET/"
# The content guard and its git hooks come from the factory itself (one source); CI runs the factory's copy at @v1.
mkdir -p "$TARGET/scripts/hooks"
cp "$FACTORY_HOME/scripts/check_content.py" "$TARGET/scripts/"
cp "$FACTORY_HOME/scripts/hooks/"* "$TARGET/scripts/hooks/"
# The standards travel with the project, so every AI tool and the CI review read the same rules (the AGENTS.md block).
mkdir -p "$TARGET/.factory/standards"
cp "$FACTORY_HOME/standards/"*.md "$TARGET/.factory/standards/"

# ---- Fill placeholders -----------------------------------------------------
# Rename paths first (deepest first so parent renames don't break child paths).
find "$TARGET" -depth -name '*{{PACKAGE_NAME}}*' | while read -r path; do
  mv "$path" "${path//\{\{PACKAGE_NAME\}\}/$PACKAGE_NAME}"
done
# Then file contents. Through a temporary file rather than `sed -i`, whose syntax differs between GNU sed and the
# BSD sed of macOS. The temporary file lives outside the project, so grep never lists it; copying back with cat
# keeps the file's mode.
tmp="$(mktemp)"
grep -rl '{{' "$TARGET" 2>/dev/null | while read -r file; do
  sed \
    -e "s|{{PROJECT_NAME}}|$NAME|g" \
    -e "s|{{PACKAGE_NAME}}|$PACKAGE_NAME|g" \
    -e "s|{{GITHUB_OWNER}}|$OWNER|g" \
    -e "s|{{FACTORY_REPO}}|$FACTORY_REPO|g" \
    -e "s|{{YEAR}}|$YEAR|g" \
    "$file" > "$tmp"
  cat "$tmp" > "$file"
done
rm -f "$tmp"

find "$TARGET" -name '*.sh' -exec chmod +x {} +
chmod +x "$TARGET/scripts/check_content.py" "$TARGET/scripts/hooks/"*

# ---- Managed files and the answers file ------------------------------------
# scripts/factory_update.py renders the same project for updates; both must agree byte for byte, which
# scripts/tests/test_factory_update.py checks. Change one, change the other.
KINDS="$TEMPLATES/file-kinds.txt"
MANAGED_HEADER="Managed by software-factory: /factory-update replaces this file. Change it in the factory, not here."

# The kind of a project path (managed, merged or seeded): the first rule of file-kinds.txt whose glob matches.
kind_of() {
  local rel="$1" kind glob
  while read -r kind glob _; do
    glob="${glob%$'\r'}"
    [[ -z "$kind" || "$kind" == \#* || -z "$glob" ]] && continue
    # shellcheck disable=SC2053  # the glob is a pattern on purpose
    if [[ "$rel" == $glob ]]; then
      printf '%s\n' "$kind"
      return
    fi
  done < "$KINDS"
  echo seeded
}

# The header says the factory owns the file: a comment after the shebang line, or an HTML comment for Markdown.
add_header() {
  local file="$1" first=""
  IFS= read -r first < "$file" || true   # a last line without a newline is still read
  if [[ "$file" == *.md ]]; then
    { printf '<!-- %s -->\n' "$MANAGED_HEADER"; cat "$file"; } > "$tmp"
  elif [[ "$first" == '#!'* ]]; then
    { printf '%s\n# %s\n' "$first" "$MANAGED_HEADER"; tail -n +2 "$file"; } > "$tmp"
  else
    { printf '# %s\n' "$MANAGED_HEADER"; cat "$file"; } > "$tmp"
  fi
  cat "$tmp" > "$file"
}

# A YAML scalar as factory_update.py writes it: plain when it cannot be read as anything but a string, else quoted.
yaml_value() {
  local value="$1" lower
  lower="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  if [[ "$value" =~ ^[A-Za-z_./][A-Za-z0-9_./-]*$ ]] && ! [[ "$lower" =~ ^(true|false|yes|no|on|off|null)$ ]]; then
    printf '%s' "$value"
  else
    value="${value//\\/\\\\}"
    printf '"%s"' "${value//\"/\\\"}"
  fi
}

tmp="$(mktemp)"
find "$TARGET" -type f | while read -r file; do
  if [[ "$(kind_of "${file#"$TARGET"/}")" == managed ]]; then
    add_header "$file"
  fi
done
rm -f "$tmp"

# What /factory-update needs to render this project again; in the first commit.
{
  echo '# Written by software-factory; /factory-update reads it. Edit only "skip".'
  echo "_src_path: $(yaml_value "$FACTORY_REPO")"
  echo "_commit: $(yaml_value "$FACTORY_COMMIT")"
  echo "version: $(yaml_value "$FACTORY_VERSION")"
  echo "template: $(yaml_value "$TEMPLATE")"
  echo "project_name: $(yaml_value "$NAME")"
  echo "package_name: $(yaml_value "$PACKAGE_NAME")"
  echo "github_owner: $(yaml_value "$OWNER")"
  echo "year: $(yaml_value "$YEAR")"
  echo "onboarded: false"
  echo "skip: []"
} > "$TARGET/.factory/answers.yml"

# ---- Lockfile --------------------------------------------------------------
# Versions are pinned by a lockfile (standards/CODING-STANDARDS.md), and it is in the first commit, so CI installs
# exactly what was resolved here. Without the tool, or offline, the project is still created: lock it later.
lock() {   # lock <tool> <lockfile> <command...>
  local tool="$1" file="$2"; shift 2
  if ! command -v "$tool" >/dev/null; then
    echo "⚠️  $tool not found: no $file yet. Install $tool, run '${*}' in the project and commit $file."
  elif (cd "$TARGET" && "$@" >/dev/null 2>&1) && [[ -f "$TARGET/$file" ]]; then
    echo "🔒 $file created"
  else
    echo "⚠️  '${*}' failed (offline?): no $file yet. Run it in the project and commit $file."
  fi
}
case "$TEMPLATE" in
  typescript) lock npm package-lock.json npm install --package-lock-only --no-audit --no-fund ;;
  python)     lock uv uv.lock uv lock ;;
esac

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

# The local project is complete: a failure creating the GitHub repository below must not remove it
trap - EXIT

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
  python)     echo "  uv sync && uv run pytest" ;;
  generic)    echo "  edit scripts/check.sh and AGENTS.md for your language" ;;
esac
echo "  claude    # then: /factory-build <your first feature>"
