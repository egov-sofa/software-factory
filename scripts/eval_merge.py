#!/usr/bin/env python3
"""The helpers of `run-evals.sh --one-at-a-time` (evals/README.md), which runs `claude plugin eval` once per case:
which cases to run, the budget left for the next one, and one result.json made of the cases' own.

    python3 scripts/eval_merge.py cases EVALS_DIR [--case GLOB] --tag TAG...
                                    the names of the cases that have one of the tags (and match GLOB), one per line
    python3 scripts/eval_merge.py budget CEILING [RESULT_JSON...]
                                    the dollars left under CEILING after the results' costs, rounded down to the cent;
                                    nothing when less than $0.05 is left (not worth starting a case)
    python3 scripts/eval_merge.py merge OUT_JSON [--partial REASON] [RESULT_JSON...]
                                    write the results as one, in the shape scripts/eval_summary.py reads

The tags are read from the `tags: [...]` line of each case.yaml, the one form the cases use (no YAML library needed:
CI installs none). The probe (tag probe) is never chosen.

Exit code 0, 2 on a usage error or a case or result that cannot be read.
"""
import argparse
import fnmatch
import json
import re
import sys
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

MIN_LEFT = Decimal("0.05")   # less than one cheap run: starting a case would only hit the ceiling at once


def case_tags(text):
    """The name and tags of a case.yaml, or ValueError: a case the script cannot read must not be skipped silently."""
    name = re.search(r"^name:\s*['\"]?([^'\"\s]+)", text, re.M)
    tags = re.search(r"^tags:\s*\[(.*)\]\s*$", text, re.M)
    if not name or not tags:
        raise ValueError("no `name:` or no one-line `tags: [...]`")
    return name.group(1), [tag.strip().strip("'\"") for tag in tags.group(1).split(",") if tag.strip()]


def select_cases(evals_dir, tags, glob=None):
    """The names of the cases with any of the tags, and matching the glob when one is given, sorted."""
    chosen = []
    for path in sorted(Path(evals_dir).glob("*/case.yaml")):
        try:
            name, have = case_tags(path.read_text(encoding="utf-8"))
        except ValueError as ex:
            raise ValueError(f"{path}: {ex}") from None
        if "probe" in have or not set(have) & set(tags):
            continue
        if glob and not fnmatch.fnmatchcase(name, glob):
            continue
        chosen.append(name)
    return chosen


def budget_left(ceiling, results):
    """The dollars left under the ceiling, rounded down to the cent (never above what is really left), or None when
    less than MIN_LEFT is. Decimal: 20 - 1.37 must give 18.63, not 18.62 from a float's 18.629999…"""
    spent = sum((Decimal(str(result.get("costUsd") or 0)) for result in results), Decimal(0))
    left = (Decimal(str(ceiling)) - spent).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return left if left >= MIN_LEFT else None


def dollars(text):
    """A number of US dollars, for argparse (which shows a ValueError as a usage error, not Decimal's own error)."""
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", text):
        raise ValueError(text)
    return Decimal(text)


def mean(values):
    return sum(values) / len(values) if values else 0


def merge(results, stopped=None):
    """One result from the per-case ones. `stopped` is why the run stopped before every case ran (cost_ceiling,
    interrupted); without it, a case's own partial result makes the whole one partial, with that case's reason."""
    first = results[0] if results else {}
    cases = [case for result in results for case in result.get("cases") or []]
    reasons = [result.get("partialReason") for result in results if result.get("partial")]
    merged = {key: first[key] for key in ("schemaVersion", "claudeVersion", "startedAt") if key in first}
    merged["durationSeconds"] = sum(result.get("durationSeconds") or 0 for result in results)
    merged["costUsd"] = round(sum(result.get("costUsd") or 0 for result in results), 6)
    merged["partial"] = bool(stopped or reasons)
    reason = stopped or next((r for r in reasons if r), None)
    if reason:
        merged["partialReason"] = reason
    if "suite" in first:
        merged["suite"] = first["suite"]
    merged["cases"] = cases
    aggregates = [case.get("aggregates") or {} for case in cases]
    merged["aggregates"] = {
        "casesTotal": len(cases),
        "casesPassed": sum((result.get("aggregates") or {}).get("casesPassed", 0) for result in results),
        "overallScore": mean([agg.get("score", 0) for agg in aggregates]),
        "overallPassRate": mean([agg.get("passRate", 0) for agg in aggregates]),
    }
    deltas = [agg["delta"] for agg in aggregates if agg.get("delta") is not None]
    if deltas:
        merged["aggregates"]["meanDelta"] = mean(deltas)
    return merged


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    cases = sub.add_parser("cases", help="the cases to run, one name per line")
    cases.add_argument("evals_dir")
    cases.add_argument("--case", default="", help="only the names that match this glob")
    cases.add_argument("--tag", nargs="+", required=True)
    budget = sub.add_parser("budget", help="the dollars left, or nothing below $0.05")
    budget.add_argument("ceiling", type=dollars)
    budget.add_argument("results", nargs="*")
    merging = sub.add_parser("merge", help="write the merged result")
    merging.add_argument("out")
    merging.add_argument("--partial", metavar="REASON", help="the run stopped before every case ran, for this reason")
    merging.add_argument("results", nargs="*")
    a = p.parse_args(argv)
    try:
        if a.command == "cases":
            for name in select_cases(a.evals_dir, a.tag, a.case):
                print(name)
        elif a.command == "budget":
            left = budget_left(a.ceiling, [read(path) for path in a.results])
            if left is not None:
                print(left)
        else:
            merged = merge([read(path) for path in a.results], a.partial)
            Path(a.out).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
