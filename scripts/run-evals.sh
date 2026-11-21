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
# On Windows a run cannot be granted a shell, so there the cases tagged `shell` and the Bash grants are left out.
#
# Exit code: the CLI's (0 every case at or above the threshold, 1 a case below it, 2 the cost ceiling was hit);
# 2 also for a usage error or a missing or too old claude.
set -euo pipefail

CLAUDE_VERSION="2.1.310"   # the case schema was read from this version; CI installs exactly this one
THRESHOLD="0.67"           # a case passes when its runs average two thirds or more: one unlucky run of three is noise
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
[ "$oldest" = "$CLAUDE_VERSION" ] || fail "claude $have is older than $CLAUDE_VERSION, which has the eval schema the cases use"

PY=python3; "$PY" -c "" 2>/dev/null || PY=python

# Every case is tagged portable or shell, and --tag keeps a case that has any of the tags given: the probe (tagged
# probe) is never run from here.
tags=(portable shell)
grants=(Agent Edit Write)
case "$(uname -s)" in
  MINGW*|MSYS*)
    # a run with a shell grant fails at once here ("cannot confine it"), and these cases need one
    tags=(portable)
    echo "note: Windows: the cases tagged shell are left out, and so are the Bash grants (a run cannot confine a"
    echo "      shell on this system). Run them on Linux: the Evals workflow, or WSL."
    ;;
  *)
    grants+=("Bash(python -m unittest:*)" "Bash(python3 -m unittest:*)" "Bash(git:*)" "Bash(mkdir:*)"
             "Bash(sort:*)" "Bash(echo:*)")
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
fi
echo "results: $out (result.json, report.html)"
exit "$status"
