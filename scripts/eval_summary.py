#!/usr/bin/env python3
"""Turn the result of `claude plugin eval --json` into a Markdown table, for the Evals job's summary (roadmap I1).

    python3 scripts/eval_summary.py RESULT_JSON                 the table on stdout
    python3 scripts/eval_summary.py --copy-traces DIR RESULT_JSON
                                                                instead, copy each run's trace (kept by --keep-temp)
                                                                to DIR/<case>/<arm>-<n>.jsonl, for the job's artifact

One row per case: the score with the plugin, without it, the difference (what the factory adds), the pass rate, the
cost, and the graders that failed. A run stopped by the cost ceiling, and runs that ended in an error (an API error,
a timeout), are said so: a low score from them says nothing about the agents.

The field names are those of Claude Code 2.1.310's result (docs/plans/2026-11-19-evals-for-agents-and-skills.md,
Probe results); the without side, the difference and partialReason only exist in some results.

Exit code 0, 1 when the result file is missing or unreadable (the summary says so), 2 on a usage error.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

PARTIAL = {
    "cost_ceiling": "**Cost ceiling hit:** the run stopped launching runs at --max-cost-usd; the cases below are "
                    "partial, and paid graders were skipped where noted.",
    "interrupted": "**Interrupted:** the run was stopped before every case ran; the cases below are partial.",
    "auth_failed": "**Authentication failed:** the runs could not reach the Claude API (see evals/README.md, the "
                   "workspace header); the scores below mean nothing.",
}


def money(value):
    return f"${value:.2f}"


def cell(text):
    """Text safe in a Markdown table cell: one line, no column breaks."""
    return " ".join(str(text).split()).replace("|", "\\|")


def runs_of(case):
    arms = case.get("arms") or {}
    return [*(arms.get("with") or []), *(arms.get("without") or [])]


def case_cost(case):
    return sum((run.get("costUsd") or 0) + (run.get("judgeCostUsd") or 0) for run in runs_of(case))


def failed_graders(case):
    """The scored graders that failed in a run with the plugin, with how often: `name (2/3)`."""
    runs = (case.get("arms") or {}).get("with") or []
    counts = {}
    for run in runs:
        for grader in run.get("graders") or []:
            if grader.get("scored", True) and not grader.get("passed"):
                counts[grader["name"]] = counts.get(grader["name"], 0) + 1
    return [f"{name} ({n}/{len(runs)})" for name, n in counts.items()]


def notes(case):
    found = []
    errors = [run["error"] for run in runs_of(case) if run.get("error")]
    if errors:
        found.append(f"error in {len(errors)} run(s): {' '.join(str(errors[0]).split())[:120]}")
    if any(run.get("skippedPaidGraders") for run in runs_of(case)):
        found.append("paid graders skipped (cost ceiling)")
    return found


def summary(result):
    suite = result.get("suite") or {}
    threshold = suite.get("threshold", 0)
    two_arms = suite.get("ablation") == "with-without"
    totals = result.get("aggregates") or {}
    plugins = ", ".join(f"{p.get('name')} {p.get('version', '')}".strip() for p in suite.get("plugins") or [])
    lines = ["## Evals", ""]
    if result.get("partial"):
        lines += [PARTIAL.get(result.get("partialReason"), "**Partial result:** not every case ran."), ""]
    lines += [f"Claude Code {result.get('claudeVersion', '?')}, plugin {plugins or '?'}, model "
              f"{suite.get('modelOverride') or 'default'}, {'with and without the plugin' if two_arms else 'one arm'}"
              f", threshold {threshold}. Cases passed: {totals.get('casesPassed', 0)} of "
              f"{totals.get('casesTotal', 0)}; overall score {totals.get('overallScore', 0):.2f}"
              + (f", mean difference {totals['meanDelta']:+.2f}" if totals.get("meanDelta") is not None else "")
              + f". Cost {money(result.get('costUsd') or 0)}, {result.get('durationSeconds', 0)} s.", ""]
    lines += ["| Case | Result | Score with | Score without | Δ | Pass rate | Cost | Failed graders (with) | Notes |",
              "|---|---|---|---|---|---|---|---|---|"]
    for case in result.get("cases") or []:
        agg = case.get("aggregates") or {}
        score = agg.get("score", 0)
        without = agg.get("scoreWithout")
        delta = agg.get("delta")
        # a run that ended on an error was not graded: a case can "pass" on graders that need nothing to happen
        # (the first Actions run showed one at 1.00 with both runs errored), so an error of the with-plugin arm wins
        # over the score. A baseline error only shows in Notes: it makes Δ unreliable, not the factory's result.
        if any(run.get("error") for run in (case.get("arms") or {}).get("with") or []):
            verdict = "**error**"
        else:
            verdict = "pass" if score >= threshold else "**below threshold**"
        lines.append("| " + " | ".join([
            cell(case.get("name", "?")), verdict, f"{score:.2f}",
            f"{without:.2f}" if without is not None else "–",
            f"{delta:+.2f}" if delta is not None else "–",
            f"{agg.get('passRate', 0):.0%}", money(case_cost(case)),
            cell(", ".join(failed_graders(case))) or "–", cell("; ".join(notes(case))) or "–"]) + " |")
    lines += ["", "Score: the weighted share of graders passed, averaged over the runs. Δ: score with the plugin "
              "minus without, what the factory adds (its agents also bring their own model). Graders marked "
              "with-only show whether the plugin fired and are not scored.", ""]
    return "\n".join(lines)


def copy_traces(result, dest):
    """Copy each run's trace (kept by --keep-temp) to dest/<case>/<arm>-<n>.jsonl; returns how many were copied."""
    copied = 0
    for case in result.get("cases") or []:
        for arm, runs in (case.get("arms") or {}).items():
            for n, run in enumerate(runs or [], 1):
                trace = Path(run.get("tracePath") or "")
                if run.get("tracePath") and trace.is_file():
                    target = Path(dest) / case.get("name", "case") / f"{arm}-{n}.jsonl"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(trace, target)
                    copied += 1
    return copied


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("result", help="result.json written by claude plugin eval --json")
    p.add_argument("--copy-traces", metavar="DIR", help="also copy each run's trace into DIR")
    a = p.parse_args(argv)
    try:
        result = json.loads(Path(a.result).read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        print(f"## Evals\n\nNo result to show: {a.result} could not be read ({type(ex).__name__}). The run stopped "
              "before the CLI wrote it; see the job log.")
        return 1
    if a.copy_traces:
        print(f"traces: {copy_traces(result, a.copy_traces)} copied to {a.copy_traces}", file=sys.stderr)
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Δ and – on a Windows console too
    print(summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
