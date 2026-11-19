#!/usr/bin/env python3
"""Find documentation that has drifted from what it describes: a kind of Dependabot for documents.

Shared service of the software factory (docs/SHARED-SERVICES.md, "Docs drift"). A project lists its documents in
.factory/docs.yml, each with the sources it describes: files of the same repository, or paths in another repository.
A document has drifted when one of its sources changed after the document did.

    version: 1
    docs:
      - id: payments-sad                       # unique, stable
        title: Payments software architecture document
        path: docs/architecture/payments/sad.md
        review_every_days: 180                 # optional: also report a document nobody touched for this long
        sources:
          - path: docs/architecture/payments/sketches/   # a folder: every file below it (the / is optional)
          - path: src/payments/**/*.py                   # a glob
          - repo: example-org/platform-gitops            # another repository (needs a token that can read it)
            path: apps/payments/
            ref: main                                    # optional, default: that repository's default branch

Commands:
  validate          check the manifest
  pr --base REF     list the documents whose sources the current branch changes (git diff REF...HEAD) while the
                    document itself is not changed; for the pull request check
  scan              the state of every document: ok, drift, overdue, missing or unknown; for the weekly issue
  dashboard --registry FILE
                    scan every repository listed in a registry file through the GitHub API, for one overview of all
                    projects (the private docs registry, docs/DOCS-DRIFT.md). The file:
                        version: 1
                        repos:
                          - example-org/payments
                          - other-org/website

Common options:
  --root DIR        a local checkout (default: the current directory); dates come from git
  --repo OWNER/NAME read the manifest and all dates through the GitHub API instead of a checkout (registry mode)
  --ref REF         with --repo: the branch to read (default: the default branch)
  --json FILE       also write the result as JSON
  --markdown FILE   also write the result as Markdown (for an issue body or $GITHUB_STEP_SUMMARY)
  --strict          pr: exit 1 when a document is missing its update (default: report only)

The GitHub API token comes from the environment variable DOCS_DRIFT_TOKEN, else GITHUB_TOKEN. A token for one owner
can be given as DOCS_DRIFT_TOKEN_<OWNER> (upper case, - becomes _), because a GitHub App token covers one owner only.
Without a token, or when it cannot read a repository, the sources there are reported as "unknown", never as fine.

Exit code 0 when the run worked (also with findings, unless --strict), 1 for pr --strict with findings, 2 on a usage
or manifest error.
"""
import argparse
import base64
import calendar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MANIFEST = ".factory/docs.yml"
API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
STATES = ("missing", "drift", "unknown", "overdue", "ok")   # worst first
ICONS = {"ok": "✅", "drift": "🔴", "overdue": "🟠", "missing": "❌", "unknown": "⚪"}


class ManifestError(Exception):
    pass


# --- manifest -------------------------------------------------------------------------------------------------------

def load_yaml(text):
    try:
        import yaml
    except ImportError:
        raise ManifestError("PyYAML is needed to read the YAML files (pip install pyyaml)")
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ManifestError(f"not valid YAML: {e}")


def parse_manifest(text):
    return check_manifest(load_yaml(text))


def check_manifest(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ManifestError("the manifest needs 'version: 1' at the top")
    docs = data.get("docs")
    if not isinstance(docs, list) or not docs:
        raise ManifestError("'docs' must be a non-empty list")
    seen = set()
    for i, doc in enumerate(docs, 1):
        where = f"docs[{i}]"
        if not isinstance(doc, dict):
            raise ManifestError(f"{where} must be a mapping")
        for key in ("id", "path"):
            if not isinstance(doc.get(key), str) or not doc[key].strip():
                raise ManifestError(f"{where} needs '{key}'")
        if doc["id"] in seen:
            raise ManifestError(f"{where}: id '{doc['id']}' is used twice")
        seen.add(doc["id"])
        every = doc.get("review_every_days")
        if every is not None and (not isinstance(every, int) or isinstance(every, bool) or every < 1):
            raise ManifestError(f"{where}: review_every_days must be a whole number of days, 1 or more")
        sources = doc.get("sources", [])
        if not isinstance(sources, list):
            raise ManifestError(f"{where}: 'sources' must be a list")
        for j, src in enumerate(sources, 1):
            if not isinstance(src, dict) or not isinstance(src.get("path"), str) or not src["path"].strip():
                raise ManifestError(f"{where}.sources[{j}] needs 'path'")
            repo = src.get("repo")
            if repo is not None and (not isinstance(repo, str) or repo.count("/") != 1):
                raise ManifestError(f"{where}.sources[{j}]: repo must be OWNER/NAME")
            if src["path"].startswith("/") or ".." in Path(src["path"]).parts:
                raise ManifestError(f"{where}.sources[{j}]: path must be relative and stay inside the repository")
    return data


def matches(pattern, path):
    """A source pattern matches a file path: a glob by its wildcards, otherwise the file itself or anything below it
    when it is a folder (with or without a trailing /), the same way git log -- PATH does in scan."""
    if any(c in pattern for c in "*?["):
        return glob_regex(pattern).fullmatch(path) is not None
    return path == pattern or path.startswith(pattern.rstrip("/") + "/")


def glob_regex(pattern):
    """A glob as git's :(glob) pathspec reads it: * and ? stop at /, **/ is zero or more folders, a final /** is
    everything below, [...] is a character class."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:[^/]*/)*")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("/.*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[" and "]" in pattern[i + 2:]:
            end = pattern.index("]", i + 2)
            body = pattern[i + 1:end]
            out.append("[" + ("^" + body[1:] if body.startswith("!") else body).replace("\\", "\\\\") + "]")
            i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def api_path(pattern):
    """The path to ask the commits API about: the part of a pattern before its first wildcard."""
    cut = len(pattern)
    for c in "*?[":
        if c in pattern:
            cut = min(cut, pattern.index(c))
    head = pattern[:cut]
    return head.rsplit("/", 1)[0] if cut < len(pattern) else head.rstrip("/")


# --- where dates come from ------------------------------------------------------------------------------------------

def owner_tokens(env):
    """{owner key: token} from DOCS_DRIFT_TOKEN_<OWNER> variables."""
    prefix = "DOCS_DRIFT_TOKEN_"
    return {k[len(prefix):]: v for k, v in env.items() if k.startswith(prefix) and v}


def owner_key(repo):
    return repo.split("/")[0].upper().replace("-", "_").replace(".", "_")


class GitHub:
    def __init__(self, token, per_owner=None):
        self.token = token
        self.per_owner = per_owner or {}
        self.cache = {}

    def get(self, url, repo=None):
        if url in self.cache:
            return self.cache[url]
        token = self.per_owner.get(owner_key(repo), self.token) if repo else self.token
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "X-GitHub-Api-Version": "2022-11-28",
                                                   "User-Agent": "software-factory-docs-drift"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                value = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            value = {"_error": e.code}
        except (urllib.error.URLError, TimeoutError) as e:
            value = {"_error": str(e)}
        self.cache[url] = value
        return value

    def last_change(self, repo, path, ref=None):
        """(unix time, short sha) of the last commit touching path in repo, None if none, or an error string."""
        query = {"path": path, "per_page": "1"}
        if ref:
            query["sha"] = ref
        data = self.get(f"{API}/repos/{repo}/commits?{urllib.parse.urlencode(query)}", repo)
        if isinstance(data, dict) and "_error" in data:
            return f"cannot read {repo} ({data['_error']})"
        if not data:
            return None
        when = data[0]["commit"]["committer"]["date"]
        return calendar.timegm(time.strptime(when, "%Y-%m-%dT%H:%M:%SZ")), data[0]["sha"][:7]

    def exists(self, repo, path, ref=None):
        """True or False, or an error string when GitHub cannot tell (no access, rate limit)."""
        query = f"?ref={urllib.parse.quote(ref)}" if ref else ""
        data = self.get(f"{API}/repos/{repo}/contents/{urllib.parse.quote(path)}{query}", repo)
        if isinstance(data, dict) and "_error" in data:
            return False if data["_error"] == 404 else f"cannot read {repo} ({data['_error']})"
        return True

    def read_file(self, repo, path, ref=None):
        query = f"?ref={urllib.parse.quote(ref)}" if ref else ""
        data = self.get(f"{API}/repos/{repo}/contents/{urllib.parse.quote(path)}{query}", repo)
        if isinstance(data, dict) and "_error" in data:
            return None
        return base64.b64decode(data["content"]).decode("utf-8")


class Local:
    def __init__(self, root):
        self.root = Path(root)

    def git(self, *args):
        out = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=False)
        if out.returncode != 0:
            raise ManifestError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
        return out.stdout

    def last_change(self, pattern):
        spec = pattern if not any(c in pattern for c in "*?[") else f":(glob){pattern}"
        # --first-parent: the date a change reached this branch, so a merged pull request dates the document and
        # its sources at the same merge commit, not at the branch's own (earlier) commits
        out = self.git("log", "-1", "--first-parent", "--format=%ct %h", "--", spec).strip()
        if not out:
            return None
        when, sha = out.split()
        return int(when), sha

    def exists(self, path):
        return (self.root / path).exists()

    def changed_files(self, base):
        return [f for f in self.git("diff", "--name-only", f"{base}...HEAD").splitlines() if f]


# --- the checks -----------------------------------------------------------------------------------------------------

def scan(docs, *, local=None, github=None, repo=None, ref=None, now=None):
    """The state of each document. With local, dates of the repository come from git; with repo, from the API."""
    now = now or int(time.time())
    results = []
    for doc in docs:
        result = {"id": doc["id"], "title": doc.get("title", doc["id"]), "path": doc["path"], "newer": [],
                  "unknown": [], "state": "ok"}
        if local:
            doc_change = local.last_change(doc["path"]) if local.exists(doc["path"]) else None
        else:
            # the commits API also returns the commit that deleted a file, so ask whether the file is there first;
            # a read error is "unknown", never "missing"
            there = github.exists(repo, doc["path"], ref)
            doc_change = github.last_change(repo, doc["path"], ref) if there is True else None
            problem = there if isinstance(there, str) else doc_change if isinstance(doc_change, str) else None
            if problem:
                result["state"] = "unknown"
                result["unknown"].append({"source": doc["path"], "reason": problem})
                results.append(result)
                continue
        if doc_change is None:
            result["state"] = "missing"
            results.append(result)
            continue
        result["changed"], result["sha"] = doc_change
        for src in doc.get("sources", []):
            label = f"{src['repo']}:{src['path']}" if src.get("repo") else src["path"]
            if src.get("repo") or not local:
                change = github.last_change(src.get("repo", repo), api_path(src["path"]), src.get("ref", ref)) \
                    if github else "no GitHub token"
            else:
                change = local.last_change(src["path"])
            if isinstance(change, str):
                result["unknown"].append({"source": label, "reason": change})
            elif change is None:
                result["unknown"].append({"source": label, "reason": "matches no file (a typo, or moved or deleted)"})
            elif change[0] > doc_change[0]:
                result["newer"].append({"source": label, "changed": change[0], "sha": change[1]})
        every = doc.get("review_every_days")
        if result["newer"]:
            result["state"] = "drift"
        elif result["unknown"]:
            result["state"] = "unknown"
        elif every and now - doc_change[0] > every * 86400:
            result["state"] = "overdue"
        results.append(result)
    return results


def pr_findings(docs, changed):
    """Documents whose local sources the change touches while the document itself is untouched."""
    changed = set(changed)
    out = []
    for doc in docs:
        if doc["path"] in changed:
            continue
        hits = sorted({f for src in doc.get("sources", []) if not src.get("repo")
                       for f in changed if matches(src["path"], f)})
        if hits:
            out.append({"id": doc["id"], "title": doc.get("title", doc["id"]), "path": doc["path"], "files": hits})
    return out


def dashboard(repos, github, now=None):
    """Scan each repository of the registry through the API. A repository without a readable manifest gets one row
    with state "unknown"."""
    rows = []
    for repo in repos:
        text = github.read_file(repo, MANIFEST)
        if text is None:
            rows.append({"repo": repo, "id": "-", "title": "no readable .factory/docs.yml", "path": MANIFEST,
                         "state": "unknown", "newer": [], "unknown": [{"source": repo, "reason": "no manifest"}]})
            continue
        try:
            docs = parse_manifest(text)["docs"]
        except ManifestError as e:
            rows.append({"repo": repo, "id": "-", "title": f"broken manifest: {e}", "path": MANIFEST,
                         "state": "unknown", "newer": [], "unknown": []})
            continue
        rows += [{"repo": repo, **r} for r in scan(docs, github=github, repo=repo, now=now)]
    return rows


def check_registry(data):
    repos = data.get("repos") if isinstance(data, dict) and data.get("version") == 1 else None
    if not isinstance(repos, list) or not repos or not all(isinstance(r, str) and r.count("/") == 1 for r in repos):
        raise ManifestError("the registry needs 'version: 1' and 'repos', a list of OWNER/NAME")
    return repos


# --- output ---------------------------------------------------------------------------------------------------------

def md(text):
    """Text from a manifest, safe in a Markdown table cell: | would break the table, and @name would ping someone
    from the issue every week."""
    return str(text).replace("|", "\\|").replace("@", "@\u200d")


def day(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def scan_markdown(results, repo=None):
    worst = sorted(results, key=lambda r: (STATES.index(r["state"]), r.get("repo", "")))
    by_repo = any("repo" in r for r in results)
    counts = {s: sum(r["state"] == s for r in results) for s in STATES}
    lines = [f"Documentation drift{f' of {repo}' if repo else ''}: "
             + ", ".join(f"{counts[s]} {s}" for s in STATES if counts[s]) + ".", "",
             "| | " + ("Repository | " if by_repo else "") + "Document | State | Last change | Why |",
             "|---|" + ("---|" if by_repo else "") + "---|---|---|---|"]
    for r in worst:
        why = []
        why += [f"`{md(n['source'])}` changed {day(n['changed'])} ({n['sha']})" for n in r["newer"]]
        why += [f"`{md(u['source'])}`: {md(u['reason'])}" for u in r["unknown"]]
        if r["state"] == "overdue":
            why.append("not reviewed within its review period")
        if r["state"] == "missing":
            why.append("the document does not exist")
        last = f"{day(r['changed'])} ({r['sha']})" if "changed" in r else "-"
        lines.append(f"| {ICONS[r['state']]} | " + (f"{md(r['repo'])} | " if by_repo else "")
                     + f"{md(r['title'])} (`{md(r['path'])}`) | {r['state']} | {last} | "
                     + ("<br>".join(why) or "-") + " |")
    lines += ["", ("A document drifts when a source it describes changed after it. Update the document (or confirm it "
                   "is still right with a commit that touches it), and this list updates on the next run.")]
    return "\n".join(lines) + "\n"


def pr_markdown(findings):
    if not findings:
        return "Docs drift: every document whose sources this pull request changes is updated too.\n"
    lines = ["Docs drift: this pull request changes what these documents describe, but not the documents.", ""]
    for f in findings:
        lines.append(f"- **{md(f['title'])}** (`{md(f['path'])}`): " + ", ".join(f"`{md(x)}`" for x in f["files"]))
    lines += ["", "Update each document in this pull request, or say in the description why it is still right."]
    return "\n".join(lines) + "\n"


# --- command line ---------------------------------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Find documentation that has drifted from what it describes.")
    p.add_argument("command", choices=["validate", "pr", "scan", "dashboard"])
    p.add_argument("--registry")
    p.add_argument("--root", default=".")
    p.add_argument("--repo")
    p.add_argument("--ref")
    p.add_argument("--base")
    p.add_argument("--json")
    p.add_argument("--markdown")
    p.add_argument("--strict", action="store_true")
    a = p.parse_args(argv)
    token = os.environ.get("DOCS_DRIFT_TOKEN") or os.environ.get("GITHUB_TOKEN")
    per_owner = owner_tokens(os.environ)
    github = GitHub(token, per_owner) if token or per_owner else None
    try:
        if a.command == "dashboard":
            if not a.registry:
                raise ManifestError("dashboard needs --registry")
            repos = check_registry(load_yaml(Path(a.registry).read_text(encoding="utf-8")))
            result = dashboard(repos, github or GitHub(None))
            text_out = scan_markdown(result)
            print(text_out, end="")
            if a.markdown:
                Path(a.markdown).write_text(text_out, encoding="utf-8")
            if a.json:
                Path(a.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            return 0
        if a.repo:
            if a.command == "pr":
                raise ManifestError("pr needs a local checkout, not --repo")
            github = github or GitHub(None)   # public repositories can be read without a token
            text = github.read_file(a.repo, MANIFEST, a.ref)
            if text is None:
                raise ManifestError(f"{a.repo} has no readable {MANIFEST}")
            local = None
        else:
            path = Path(a.root) / MANIFEST
            if not path.is_file():
                raise ManifestError(f"{path} not found")
            text = path.read_text(encoding="utf-8")
            local = Local(a.root)
        docs = parse_manifest(text)["docs"]
        if a.command == "validate":
            print(f"ok: {len(docs)} document(s) in {MANIFEST}")
            return 0
        if a.command == "pr":
            if not a.base:
                raise ManifestError("pr needs --base")
            result = pr_findings(docs, local.changed_files(a.base))
            text_out = pr_markdown(result)
        else:
            result = scan(docs, local=local, github=github, repo=a.repo, ref=a.ref)
            text_out = scan_markdown(result, a.repo)
    except ManifestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(text_out, end="")
    if a.markdown:
        Path(a.markdown).write_text(text_out, encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 1 if a.command == "pr" and a.strict and result else 0


if __name__ == "__main__":
    sys.exit(main())
