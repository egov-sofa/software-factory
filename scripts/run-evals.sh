#!/usr/bin/env bash
# Run the factory's evals (docs/plans/2026-11-19-evals-for-agents-and-skills.md, evals/README.md): build the agents
# and skills as a plugin in a temporary folder, and run `claude plugin eval` on it, each case with and without the
# plugin, under a cost ceiling.
#
#   bash scripts/run-evals.sh [--smoke] [--case <glob>] [--max-cost-usd <usd>] [--out <dir>] [--keep-traces]
#                             [--one-at-a-time]
#
#   --smoke          one run per case instead of three; default ceiling $6 instead of $20
#   --case <glob>    only the cases whose name matches
#   --max-cost-usd   the hard ceiling: the CLI stops launching runs once it is reached, and exits 2
#   --out <dir>      the results folder; default evals/results/<UTC time>/ (git-ignored)
#   --keep-traces    copy each run's trace into <out>/traces/ (CI uploads them)
#   --one-at-a-time  one `claude plugin eval` per case, into <out>/cases/<name>/, each after the command in
#                    EVALS_BEFORE_EACH if set, under one ceiling; <out>/result.json merges them
#
# This costs money: every run calls the Claude API as you. The script sets no credential: it inherits the environment,
# so ANTHROPIC_CUSTOM_HEADERS (the workspace header some keys need, evals/README.md) reaches every run.
# Cases the machine's sandbox cannot run are left out, with a note: on Windows, or on Linux without bubblewrap and
# socat, the `shell` and `shell-commands` cases and the Bash grants. On Linux the `shell-commands` cases run only with
# EVALS_NESTED_SANDBOX=yes (see below). macOS sandboxes with Seatbelt and runs them all. EVALS_SANDBOX=yes|no skips
# the bubblewrap check.
#
# --one-at-a-time is for the Evals workflow: GitHub's OIDC token lives 300 s and Anthropic accepts each one once (its
# jti), so a token refreshed during a long run was exchanged by two of its processes and the second was refused
# (jti_reused, then 401 for every run). A case is short enough for one token, and EVALS_BEFORE_EACH fetches it.
#
# Exit code: the CLI's (0 every case at or above the threshold, 1 a case below it, 2 the cost ceiling was hit), with
# --one-at-a-time the worst of the cases'; 2 also for a usage error, a missing or too old claude, or a failed
# EVALS_BEFORE_EACH.
set -euo pipefail

CLAUDE_VERSION="2.1.310"   # the case schema was read from this version; CI installs exactly this one
THRESHOLD="0.66"           # a case passes at two thirds (0.666…, below 0.67): one unlucky run of three is noise
root="$(cd "$(dirname "$0")/.." && pwd)"

usage() { sed -n '6,15p' "$0" | sed 's/^# \{0,1\}//'; }
fail() { echo "error: $1" >&2; exit 2; }

smoke=false keep_traces=false one_at_a_time=false case_glob="" max_cost="" out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --smoke) smoke=true ;;
    --keep-traces) keep_traces=true ;;
    --one-at-a-time) one_at_a_time=true ;;
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
# Claude Code runs each Bash command in a sandbox, on Linux bubblewrap (with socat), and plugin eval runs each run in
# bubblewrap too, so the Bash sandbox is nested. On GitHub's Ubuntu runners every command then fails ("apply-seccomp:
# … nested userns is capability-restricted"); in WSL it works. No cheap check tells the two apart (a hand-made nested
# namespace fails in both), so the shell-commands cases are opt-in on Linux: EVALS_NESTED_SANDBOX=yes.
has_sandbox() {
  case "${EVALS_SANDBOX:-}" in yes) return 0 ;; no) return 1 ;; esac
  command -v bwrap >/dev/null 2>&1 && command -v socat >/dev/null 2>&1 || return 1
  # installed is not enough: in a container, or with user namespaces off, bubblewrap cannot start at all
  bwrap --ro-bind / / --unshare-user --unshare-pid true >/dev/null 2>&1
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
    grants+=("${shell_grants[@]}" Bash)
    ;;
  *)
    if ! has_sandbox; then
      no_shell "no working bubblewrap and socat"
    else
      tags+=(shell)
      grants+=("${shell_grants[@]}")
      if [ "${EVALS_NESTED_SANDBOX:-}" = yes ]; then
        tags+=(shell-commands)
        # a shell-commands case grants itself plain Bash: its skill chains commands and sets variables, which no
        # Bash(prefix:*) rule approves; every command still runs in the sandbox
        grants+=(Bash)
        echo "note: the shell-commands case is known to fail under plugin eval for now: no Bash write succeeds in"
        echo "      its nested sandbox (evals/README.md). It runs, to show when that changes."
      else
        echo "note: the cases tagged shell-commands are left out: their commands fail where Claude Code's sandbox"
        echo "      cannot nest (GitHub's runners). Where it can (WSL), set EVALS_NESTED_SANDBOX=yes."
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

# the plugin first, and --tag and --allow-tools last: they take every word after them
eval_args() {   # $1 the ceiling, $2 the results folder, $3 the --case glob or nothing
  args=("$plugin" --scaffold --trust-plugin --no-publish --model sonnet --ablation with-without
        --threshold "$THRESHOLD" --max-cost-usd "$1"
        --json "$2/result.json" --report "$2/report.html" --output-dir "$2")
  if $smoke; then args+=(--runs 1); fi
  if [ -n "$3" ]; then args+=(--case "$3"); fi
  if $keep_traces; then args+=(--keep-temp); fi
  args+=(--tag "${tags[@]}" --allow-tools "${grants[@]}")
}

keep_traces_of() {   # $1 a result.json, $2 the folder to copy its traces into
  "$PY" "$root/scripts/eval_summary.py" --copy-traces "$2" "$1" || true
  # --keep-temp kept each run's whole folder; the CLI asks for them to be removed once read. Only claude-eval-*
  # folders, named in the result itself, are removed. On Linux the CLI seals them read-only, so they are opened
  # first; a folder that still cannot go is reported, never a reason to fail the run.
  local kept_folders kept
  kept_folders="$("$PY" - "$1" <<'EOF' || true
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
}

if ! $one_at_a_time; then
  eval_args "$max_cost" "$out" "$case_glob"
  echo "+ claude plugin eval ${args[*]}"
  status=0
  claude plugin eval "${args[@]}" || status=$?
  if $keep_traces && [ -f "$out/result.json" ]; then keep_traces_of "$out/result.json" "$out/traces"; fi
  echo "results: $out (result.json, report.html)"
  exit "$status"
fi

# --one-at-a-time: the cases the CLI would choose (the same tags and glob), then one run of the CLI per case
names="$("$PY" "$root/scripts/eval_merge.py" cases "$root/evals" --case "$case_glob" --tag "${tags[@]}")" \
  || fail "could not read the cases under $root/evals"
cases=()
while IFS= read -r name; do
  name="${name%$'\r'}"
  [ -z "$name" ] || cases+=("$name")
done <<< "$names"
[ "${#cases[@]}" -gt 0 ] || fail "no case has the tags ${tags[*]}${case_glob:+ and matches $case_glob}"

status=0 stopped="" results=()
for name in "${cases[@]}"; do
  # one ceiling for the whole run: each case may spend what the cases before it left
  left="$("$PY" "$root/scripts/eval_merge.py" budget "$max_cost" ${results[@]+"${results[@]}"})" \
    || fail "could not read the cost of the cases run so far"
  left="${left%$'\r'}"
  if [ -z "$left" ]; then stopped=cost_ceiling; break; fi
  if [ -n "${EVALS_BEFORE_EACH:-}" ] && ! bash -c "$EVALS_BEFORE_EACH"; then
    echo "error: EVALS_BEFORE_EACH failed before the case $name; no further case runs" >&2
    stopped=interrupted
    break
  fi
  dest="$out/cases/$name"
  mkdir -p "$dest"
  eval_args "$left" "$dest" "$name"
  echo "+ claude plugin eval ${args[*]}"
  case_status=0
  claude plugin eval "${args[@]}" || case_status=$?
  if [ "$case_status" -gt "$status" ]; then status=$case_status; fi
  if [ ! -f "$dest/result.json" ]; then
    # without its result the case's cost is unknown, so the budget of the next one would be a guess
    echo "error: the case $name wrote no result.json (claude exited $case_status); no further case runs" >&2
    stopped=interrupted
    break
  fi
  results+=("$dest/result.json")
  if $keep_traces; then keep_traces_of "$dest/result.json" "$dest/traces"; fi
  if [ "$case_status" -eq 2 ]; then stopped=cost_ceiling; break; fi   # the CLI reached what was left
done

if [ -n "$stopped" ]; then
  status=2
  if [ "$stopped" = cost_ceiling ]; then
    echo "note: the cost ceiling of \$$max_cost is reached; the cases after it did not run"
  fi
fi
merge=(merge "$out/result.json")
if [ -n "$stopped" ]; then merge+=(--partial "$stopped"); fi
"$PY" "$root/scripts/eval_merge.py" "${merge[@]}" ${results[@]+"${results[@]}"} || fail "could not merge the results"
echo "results: $out (result.json, and each case's in cases/)"
exit "$status"
