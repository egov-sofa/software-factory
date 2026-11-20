#!/usr/bin/env python3
"""Read the factory pipeline's state and check its agents' reports, so /factory-build gates on parsed values instead of
on the model reading free text (docs/plans/2026-11-19-pipeline-state-and-handoffs.md).

Usage:
  python3 scripts/factory_state.py report <agent> <report file> [--ids ID ...] [--round N]
      Check that the report starts with the agent's header lines and is consistent; print key=value lines.
      --ids: the finding IDs the agent must answer (implementer) or account for (reviewers, round 2 and later).
  python3 scripts/factory_state.py state <plan>
      Print stage, round, base and branch from the plan's header, or "legacy" for a plan without pipeline lines.
  python3 scripts/factory_state.py find --branch <name> [--plans docs/plans]
      Print the plans of that branch whose stage is not done, one per line.
  python3 scripts/factory_state.py last-reviewed <plan>
      Print the commit the newest review round reviewed.

Exit code 0 if all is well, 1 if a problem is found (message on stderr), 2 on a usage error. Standard library only.
"""
import argparse
import re
import sys
from pathlib import Path

# The header lines each agent's report starts with, in order: (key, allowed value as a regular expression).
# validate.py checks the agents' report formats against this table, and the I1 evals score reports with it.
HEADERS = {
    "planner": [("Plan", r"docs/plans/\S+\.md"), ("Criteria", r"\d+")],
    "implementer": [("Result", r"DONE|STOPPED"), ("Commands", r"PASS|FAIL")],
    "tester": [("Result", r"PASS|FAIL"), ("Failures", r"\d+")],
    "reviewer": [("Verdict", r"APPROVE|CHANGES_REQUESTED"), ("Blocking", r"\d+")],
    "security-auditor": [("Verdict", r"PASS|ISSUES_FOUND"), ("Blocking", r"\d+")],
    "docs-writer": [("Result", r"UPDATED|NO_CHANGES")],
}
# Severity tags that block, at the start of a numbered finding: "1. [MAJOR] src/a.ts:3: ..."
BLOCKING_TAGS = {"reviewer": ("BLOCKER", "MAJOR"), "security-auditor": ("CRITICAL", "HIGH")}
EARLIER_STATES = ("resolved", "still open", "disagreement accepted")
STAGES = ("implement", "test", "review", "fix", "docs", "done")
MAX_ROUNDS = 2
ID_RE = r"(?:REV|SEC|TEST)-\d+\.\d+"
STATE_RE = re.compile(r"^\*\*(Stage|Round|Base|Branch):\*\* (.+)$")
ROUND_RE = re.compile(r"^### Round (\d+) \(reviewed ([0-9a-f]{4,40})\)", re.M)
STATE_LINES = 15   # the pipeline lines sit right under "# Plan:"; a plan that quotes them later is not misread


class Problem(Exception):
    """Something the caller must fix; printed on stderr, exit 1."""


def header(agent, text):
    """The agent's header values as a dict, or Problem naming the first line that is wrong."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip().startswith("```"):
        i += 1   # a report wrapped in a code fence
    values = {}
    for key, pattern in HEADERS[agent]:
        expected = f"{key}: {pattern.replace('|', ' | ')}"
        found = lines[i].strip() if i < len(lines) else "(end of report)"
        m = re.fullmatch(rf"{key}: ({pattern})", found)
        if not m:
            raise Problem(f"{agent} report: line {i + 1} must be `{expected}` (plain text, nothing before it), "
                          f"found: {found[:80]!r}")
        values[key.lower()] = m.group(1)
        i += 1
    return values


def section(text, title):
    """The text of a `## <title>` section, up to the next `## ` heading; None without one. Words after the title are
    allowed: the report templates print `## Earlier findings (round 2 and later)` and `## Answers (when fixing ...)`."""
    m = re.search(rf"^##\s+{re.escape(title)}\b[^\n]*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def check_report(agent, text, ids=(), round_=1, root="."):
    """The report's header values, after checking its consistency rules; Problem if one fails."""
    values = header(agent, text)
    if agent == "planner":
        if not (Path(root) / values["plan"]).is_file():
            raise Problem(f"planner report: Plan: {values['plan']} does not exist")
        if int(values["criteria"]) < 1:
            raise Problem("planner report: Criteria: must be at least 1")
    elif agent == "tester":
        if (values["result"] == "PASS") != (int(values["failures"]) == 0):
            raise Problem(f"tester report: Result: {values['result']} does not match Failures: {values['failures']}")
    elif agent in BLOCKING_TAGS:
        tags = "|".join(BLOCKING_TAGS[agent])
        counted = len(re.findall(rf"^\s*\d+\.\s*\[(?:{tags})\]", text, re.M))
        # an earlier blocker the agent still sees open blocks as much as a new one (else round 2 could APPROVE it)
        still_open = len(re.findall(rf"^\s*-?\s*{ID_RE}\s*:\s*still open\b", section(text, "Earlier findings") or "", re.M))
        blocking = int(values["blocking"])
        if blocking != counted + still_open:
            raise Problem(f"{agent} report: Blocking: {blocking}, but {counted} finding(s) are tagged "
                          f"{' or '.join(BLOCKING_TAGS[agent])} and {still_open} earlier one(s) are still open")
        clean = "APPROVE" if agent == "reviewer" else "PASS"
        if values["verdict"] == clean and blocking:
            raise Problem(f"{agent} report: Verdict: {clean} with Blocking: {blocking}")
        if agent == "reviewer" and values["verdict"] != clean and not blocking:
            raise Problem("reviewer report: Verdict: CHANGES_REQUESTED with Blocking: 0")
        if round_ >= 2 and ids:
            earlier = section(text, "Earlier findings") or ""
            states = "|".join(EARLIER_STATES)
            missing = [i for i in ids if not re.search(rf"^\s*-?\s*{re.escape(i)}\s*:\s*(?:{states})\b", earlier, re.M)]
            if missing:
                raise Problem(f"{agent} report: `## Earlier findings` must account for {', '.join(missing)} "
                              f"(each as `<ID>: {' | '.join(EARLIER_STATES)}`)")
    elif agent == "implementer" and ids:
        answers = section(text, "Answers") or ""
        missing = [i for i in ids if not re.search(rf"^\s*-\s*{re.escape(i)}\s*:\s*(?:fixed|disagree)\s*:", answers, re.M)]
        if missing:
            raise Problem(f"implementer report: `## Answers` has no `- <ID>: fixed: ...` or `- <ID>: disagree: ...` "
                          f"for {', '.join(missing)}")
    return values


def state(plan_text):
    """The plan's pipeline lines as a dict, None for a legacy plan; Problem if they are invalid."""
    found = {}
    for line in plan_text.splitlines()[:STATE_LINES]:
        m = STATE_RE.match(line.strip())
        if m:
            found[m.group(1).lower()] = m.group(2).strip()
    if "stage" not in found:
        return None
    if found["stage"] not in STAGES:
        raise Problem(f"plan: Stage: {found['stage']} is not one of {', '.join(STAGES)}")
    if not re.fullmatch(r"\d+", found.get("round", "")) or int(found["round"]) > MAX_ROUNDS:
        raise Problem(f"plan: Round: must be a number from 0 to {MAX_ROUNDS}, found {found.get('round', '(none)')!r}")
    for key in ("base", "branch"):
        if not found.get(key):
            raise Problem(f"plan: **{key.capitalize()}:** is missing")
    return {key: found[key] for key in ("stage", "round", "base", "branch")}


def find(plans_dir, branch):
    """The plans of a branch that are not done (legacy plans skipped), sorted."""
    matches = []
    for path in sorted(Path(plans_dir).glob("*.md")):
        try:
            values = state(path.read_text(encoding="utf-8"))
        except Problem:
            continue   # an invalid plan cannot be resumed; `state` on it explains why
        if values and values["branch"] == branch and values["stage"] != "done":
            matches.append(path)
    return matches


def last_reviewed(plan_text):
    """The commit the newest review round reviewed."""
    rounds = ROUND_RE.findall(plan_text)
    if not rounds:
        raise Problem("plan: no `### Round <n> (reviewed <commit>)` under `## Review rounds` yet")
    return max(rounds, key=lambda r: int(r[0]))[1]


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as ex:
        raise Problem(f"cannot read {path}: {ex.strerror or ex}") from None


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("report")
    r.add_argument("agent", choices=sorted(HEADERS))
    r.add_argument("file")
    r.add_argument("--ids", nargs="*", default=[])
    r.add_argument("--round", type=int, default=1)
    s = sub.add_parser("state")
    s.add_argument("plan")
    f = sub.add_parser("find")
    f.add_argument("--branch", required=True)
    f.add_argument("--plans", default="docs/plans")
    lr = sub.add_parser("last-reviewed")
    lr.add_argument("plan")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if a.command == "report":
            values = check_report(a.agent, read(a.file), a.ids, a.round)
            print("\n".join(f"{k}={v}" for k, v in values.items()))
        elif a.command == "state":
            values = state(read(a.plan))
            print("legacy" if values is None else "\n".join(f"{k}={v}" for k, v in values.items()))
        elif a.command == "find":
            matches = find(a.plans, a.branch)
            if not matches:
                raise Problem(f"no plan in {a.plans} for branch {a.branch} that is not done")
            print("\n".join(path.as_posix() for path in matches))
        else:
            print(last_reviewed(read(a.plan)))
    except Problem as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
