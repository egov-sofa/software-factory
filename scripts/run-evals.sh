#!/usr/bin/env bash
# Run the factory's evals (docs/plans/2026-11-19-evals-for-agents-and-skills.md, evals/README.md): build the agents
# and skills as a plugin in a temporary folder, and run `claude plugin eval` on it, each case with and without the
# plugin, under a cost ceiling.
#
#   bash scripts/run-evals.sh [--smoke] [--case <glob>] [--max-cost-usd <usd>] [--out <dir>] [--keep-traces]
#
#   --smoke          one run per case instead of three; default ceiling $6 instead of $20
#   --case <glob>    only the cases whose name matches
#   --max-cost-usd   the hard ceiling: the CLI stops launching runs once it is reached, and exits 2
#   --out <dir>      the results folder; default evals/results/<UTC time>/ (git-ignored)
#   --keep-traces    copy each run's trace into <out>/traces/ (CI uploads them)
#
# This costs money: every run calls the Claude API as you. The script sets no credential: it inherits the environment,
# so ANTHROPIC_CUSTOM_HEADERS (the workspace header some keys need, evals/README.md) reaches every run.
# Cases the machine's sandbox cannot run are left out, with a note: on Windows, or on Linux without bubblewrap and
# socat, the `shell` and `shell-commands` cases and the Bash grants; where the sandbox cannot nest a user namespace
# (GitHub's Ubuntu runners), the `shell-commands` cases. macOS sandboxes with Seatbelt and runs them all.
# EVALS_SANDBOX and EVALS_NESTED_SANDBOX (yes|no) skip the checks.
#
# Exit code: the CLI's (0 every case at or above the threshold, 1 a case below it, 2 the cost ceiling was hit);
# 2 also for a usage error or a missing or too old claude.
set -euo pipefail

CLAUDE_VERSION="2.1.310"   # the case schema was read from this version; CI installs exactly this one
THRESHOLD="0.66"           # a case passes at two thirds (0.666…, below 0.67): one unlucky run of three is noise
root="$(cd "$(dirname "$0")/.." && pwd)"

usage() { sed -n '6,12p' "$0" | sed 's/^# \{0,1\}//'; }
fail() { echo "error: $1" >&2; exit 2; }

smoke=false keep_traces=false case_glob="" max_cost="" out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --smoke) smoke=true ;;
    --keep-traces) keep_traces=true ;;
    --case|--max-cost-usd|--out)
      [ $# -ge 2 ] && [ -n "$2" ] || fail "$1 needs a value"
      case "$1" in
        --case) case_glob="$2" ;;
        --max-cost-usd) max_cost="$2" ;;
        --out) out="$2" ;;
      esac
      shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
  shift
done
if [ -z "$max_cost" ]; then
  if $smoke; then max_cost=6; else max_cost=20; fi
fi
[[ "$max_cost" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "--max-cost-usd must be a number of US dollars, got $max_cost"

command -v claude >/dev/null 2>&1 || fail "claude is not installed; install Claude Code $CLAUDE_VERSION or newer"
have="$(claude --version 2>/dev/null | awk '{print $1}')"
[ -n "$have" ] || fail "could not read the version of claude"
oldest="$(printf '%s\n%s\n' "$CLAUDE_VERSION" "$have" | sort -V | head -n 1)"
[ "$oldest" = "$CLAUDE_VERSION" ] || fail "claude $have is older than $CLAUDE_VERSION (the eval schema the cases use)"

PY=python3; "$PY" -c "" 2>/dev/null || PY=python

# Every case is tagged portable, shell (it is granted Bash) or shell-commands (its shell commands must really run),
# and --tag keeps a case that has any of the tags given: the probe (tagged probe) is never run from here.
# Claude Code runs each Bash command in a sandbox: on Linux bubblewrap (with socat), inside which its helper makes a
# second, nested user namespace. GitHub's Ubuntu runners refuse that nesting (it needs CAP_SYS_ADMIN there), so a
# command fails although the run starts. EVALS_SANDBOX=yes|no and EVALS_NESTED_SANDBOX=yes|no skip the checks.
has_sandbox() {
  case "${EVALS_SANDBOX:-}" in yes) return 0 ;; no) return 1 ;; esac
  command -v bwrap >/dev/null 2>&1 && command -v socat >/dev/null 2>&1
}
nested_sandbox() {
  case "${EVALS_NESTED_SANDBOX:-}" in yes) return 0 ;; no) return 1 ;; esac
  command -v unshare >/dev/null 2>&1 || return 1
  bwrap --ro-bind / / --dev /dev --proc /proc --unshare-user --unshare-pid -- \
    unshare --user sh -c 'echo deny > /proc/self/setgroups' >/dev/null 2>&1
}
tags=(portable)
grants=(Agent Edit Write)
no_shell() {
  echo "note: $1: the cases tagged shell or shell-commands are left out, and so are the Bash grants (a run cannot"
  echo "      confine a shell here, and a Bash grant would fail every run). Run them on Linux with bubblewrap and"
  echo "      socat, or on macOS."
}
shell_grants=("Bash(python -m unittest:*)" "Bash(python3 -m unittest:*)" "Bash(git:*)" "Bash(mkdir:*)"
              "Bash(sort:*)" "Bash(echo:*)")
case "$(uname -s)" in
  MINGW*|MSYS*) no_shell Windows ;;
  Darwin)   # Seatbelt: no bubblewrap, no user namespaces to nest
    tags+=(shell shell-commands)
    grants+=("${shell_grants[@]}")
    ;;
  *)
    if ! has_sandbox; then
      no_shell "no bubblewrap or socat"
    else
      tags+=(shell)
      grants+=("${shell_grants[@]}")
      if nested_sandbox; then
        tags+=(shell-commands)
      else
        echo "note: the sandbox cannot nest a user namespace here (GitHub's Ubuntu runners), so shell commands"
        echo "      fail: the cases tagged shell-commands are left out. Run them where it can (WSL, Linux, macOS)."
      fi
    fi
    ;;
esac

out="${out:-$root/evals/results/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
plugin="$("$PY" "$root/scripts/build_plugin.py" --out "$build")"

# the plugin first: --tag and --allow-tools take every word after them
args=("$plugin" --scaffold --trust-plugin --no-publish --model sonnet --ablation with-without
      --threshold "$THRESHOLD" --max-cost-usd "$max_cost"
      --json "$out/result.json" --report "$out/report.html" --output-dir "$out")
if $smoke; then args+=(--runs 1); fi
if [ -n "$case_glob" ]; then args+=(--case "$case_glob"); fi
if $keep_traces; then args+=(--keep-temp); fi
args+=(--tag "${tags[@]}" --allow-tools "${grants[@]}")

echo "+ claude plugin eval ${args[*]}"
status=0
claude plugin eval "${args[@]}" || status=$?

if $keep_traces && [ -f "$out/result.json" ]; then
  "$PY" "$root/scripts/eval_summary.py" --copy-traces "$out/traces" "$out/result.json" || true
  # --keep-temp kept each run's whole folder; the CLI asks for them to be removed once read. Only claude-eval-*
  # folders, named in the result itself, are removed. On Linux the CLI seals them read-only, so they are opened
  # first; a folder that still cannot go is reported, never a reason to fail the run.
  kept_folders="$("$PY" - "$out/result.json" <<'EOF' || true
import json, sys
from pathlib import Path
for case in json.load(open(sys.argv[1], encoding="utf-8")).get("cases", []):
    for runs in (case.get("arms") or {}).values():
        for run in runs:
            folder = Path(run.get("tracePath") or "x/x/x").parent.parent
            if folder.name.startswith("claude-eval-") and folder.is_dir():
                print(folder.as_posix())
EOF
)"
  while IFS= read -r kept; do
    kept="${kept%$'\r'}"   # Python on Windows ends its lines with CRLF
    [ -n "$kept" ] || continue
    chmod -R u+rwx -- "$kept" 2>/dev/null || true
    rm -rf -- "$kept" 2>/dev/null || echo "note: could not remove $kept" >&2
  done <<< "$kept_folders"
fi
echo "results: $out (result.json, report.html)"
exit "$status"
