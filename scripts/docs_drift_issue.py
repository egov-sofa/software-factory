#!/usr/bin/env python3
"""Keep one GitHub issue in step with a docs drift report, the way Dependabot keeps its pull requests in step.

Shared service of the software factory (docs/SHARED-SERVICES.md, "Docs drift"). Reads the JSON and Markdown that
docs_drift.py scan (or the registry dashboard) wrote, then with the gh CLI:
  - something is not ok, no open issue    -> opens one, labelled docs-drift
  - something is not ok, an open issue    -> replaces its body
  - everything is ok, an open issue       -> comments and closes it
  - everything is ok, no open issue       -> does nothing

Options:
  --report FILE   the JSON report: a list of documents, each with a "state"
  --body FILE     the Markdown to put in the issue
  --title TEXT    the issue title (default: "Documentation drift")
  --label NAME    the label that finds the issue again (default: docs-drift)
  --dry-run       print what it would do

gh reads the repository from GH_REPO and the token from GH_TOKEN.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def gh(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"gh {args[0]} {args[1]} failed: {out.stderr.strip()}")
    return out.stdout


def plan(states, open_issue):
    """What to do: 'open', 'update', 'close' or 'nothing'."""
    problems = any(s != "ok" for s in states)
    if problems:
        return "update" if open_issue else "open"
    return "close" if open_issue else "nothing"


def main(argv=None):
    p = argparse.ArgumentParser(description="Keep one issue in step with a docs drift report.")
    p.add_argument("--report", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--title", default="Documentation drift")
    p.add_argument("--label", default="docs-drift")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    states = [doc["state"] for doc in json.loads(Path(a.report).read_text(encoding="utf-8"))]
    body = Path(a.body).read_text(encoding="utf-8")
    try:
        found = json.loads(gh("issue", "list", "--label", a.label, "--state", "open", "--json", "number",
                              "--limit", "1") or "[]") if not a.dry_run else []
        number = str(found[0]["number"]) if found else None
        action = plan(states, number)
        print(f"docs drift issue: {action}" + (f" #{number}" if number else ""))
        if a.dry_run or action == "nothing":
            return 0
        if action == "open":
            gh("label", "create", a.label, "--color", "d93f0b", "--force",
               "--description", "Documentation that no longer matches what it describes")
            gh("issue", "create", "--title", a.title, "--label", a.label, "--body", body)
        elif action == "update":
            gh("issue", "edit", number, "--body", body)
        else:
            gh("issue", "close", number, "--comment", "Every document is up to date again.")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
