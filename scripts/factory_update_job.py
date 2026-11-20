#!/usr/bin/env python3
"""The weekly factory update of a project, run by the factory-update action
(docs/plans/2026-11-19-project-updates-and-shipped-standards.md, criterion 8; docs/SHARED-SERVICES.md, "Updates").

Two steps, so the token is only present for the second:
  prepare   (no token) clones the factory named in .factory/answers.yml (public, no credentials), runs
            factory_update.py update on the checkout, takes the changes to .github/workflows/ back out (GITHUB_TOKEN
            cannot push them), commits the rest on branch factory-update/<version>, and writes what publish needs
            into the work folder.
  publish   (GH_TOKEN, GH_REPO) does nothing when an open pull request for that version exists; closes the open
            update pull requests and issue when the project is current; else pushes the branch and opens a pull
            request (a draft when it has conflicts), closing older update pull requests and the issue; when the
            repository does not let GitHub Actions open pull requests, or when only workflow files changed, it keeps
            one issue labelled factory-update up to date instead (an open issue never stops the pull request).

Usage:
  python3 -I scripts/factory_update_job.py prepare --workdir <dir> [--project <dir>] [--factory-url <url>]
  python3 -I scripts/factory_update_job.py publish --workdir <dir> [--project <dir>]

Nothing from the project runs: this script and factory_update.py come from the action (python -I keeps the checkout
off the import path), and every git command runs with hooks turned off. Exit code 0 if all is well, 1 when git or gh
fails, 2 on a usage error or a refusal of factory_update.py. Standard library only.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory_update as fu  # noqa: E402  (the action's own copy, next to this script)

LABEL = "factory-update"
BRANCH_PREFIX = "factory-update/"
WORKFLOWS = ".github/workflows/"
SRC_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HEADLINE_RE = re.compile(r"^(?:feat|fix|perf|security)(?:\([^)]*\))?!?: ")
NOT_ALLOWED_RE = re.compile(r"not permitted to create or approve pull requests", re.I)
BOT_NAME, BOT_EMAIL = "github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"
SETTING = ("Settings → Actions → General → Workflow permissions → \"Allow GitHub Actions to create and approve pull "
           "requests\"")
TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
# Hooks off for every git command: the job works on the project's content, and none of it may run. The identity and
# signing are set here, never read from the repository.
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}",
       "-c", "commit.gpgsign=false"]


class Problem(Exception):
    """git or gh failed; printed on stderr, exit 1."""


def git(repo, *args, check=True, env=None):
    done = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, check=False)
    if check and done.returncode != 0:
        raise Problem(f"git {args[0]} failed: {done.stderr.strip()}")
    return done


def no_token_env():
    """The environment without any token: the factory is public, and prepare never needs one."""
    env = {k: v for k, v in os.environ.items() if k not in TOKENS}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def notice(text):
    print(f"::notice::{text}" if os.environ.get("GITHUB_ACTIONS") else text)


def code(text):
    return "`" + str(text).replace("`", "'") + "`"


def headlines(factory, base, target):
    """The release notes' headlines between the two factory commits: their feat, fix, perf and security subjects."""
    log = git(factory, "log", "--format=%s", f"{base}..{target}", check=False).stdout.splitlines()
    seen = []
    for subject in log:
        if HEADLINE_RE.match(subject) and subject not in seen:
            seen.append(subject)
    return seen[:30]


def details(report, workflows, notes):
    """The Markdown shared by the pull request and the issue: the summary, the conflicts, the decisions, the workflow
    files left out, the release notes."""
    lines, to = [], report["to"]
    titles = dict(fu.Summary.TITLES)
    shown = {k: [i for i in v if not i.startswith(WORKFLOWS)] for k, v in report["items"].items()}
    summary = [(k, v) for k, v in shown.items() if v and k not in ("conflicts", "decide")]
    if summary:
        lines += ["### What changes", ""]
        lines += [f"- **{titles[k]}:** " + ", ".join(code(i) for i in v) for k, v in summary]
        lines.append("")
    if shown.get("conflicts"):
        lines += ["### Conflicts", "", "These files hold conflict markers (`<<<<<<< project` ... "
                  f"`>>>>>>> factory {to}`): resolve each one, keeping what the project needs, then mark this pull "
                  "request ready for review. `/factory-update` in Claude Code helps, file by file.", ""]
        lines += [f"- {code(i)}" for i in shown["conflicts"]] + [""]
    if shown.get("decide"):
        lines += ["### Needs a decision", ""] + [f"- {code(i)}" for i in shown["decide"]] + [""]
    if workflows:
        lines += ["### Workflow files left out", "",
                  "`GITHUB_TOKEN` cannot change files under `.github/workflows/`, so the factory's changes to these "
                  "are not here; `_workflows_from` in `.factory/answers.yml` records the factory commit they are "
                  "still at:", ""]
        lines += [f"- {code(p)}" for p in workflows]
        lines += ["", "Run `/factory-update` locally (after merging this, if it is a pull request): it merges them from "
                  "that commit and removes `_workflows_from`. Until then, this job keeps one issue open for them.", ""]
    if notes:
        lines += ["### Release notes", ""] + [f"- {code(n)}" for n in notes] + [""]
    return "\n".join(lines)


def restore(project, rel):
    """Take one file back to the last commit (an added file is removed)."""
    if git(project, "ls-files", "--error-unmatch", "--", rel, check=False).returncode == 0:
        git(project, "checkout", "-q", "HEAD", "--", rel)
    else:
        path = Path(project) / rel
        if path.is_file() or path.is_symlink():
            path.unlink()


def prepare(project, workdir, factory_url=None):
    project, workdir = Path(project), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    state = workdir / "state.json"
    if not (project / fu.ANSWERS).is_file():
        notice(f"no {fu.ANSWERS}: this project does not record its factory version (run /factory-update locally)")
        state.write_text(json.dumps({"action": "none"}), encoding="utf-8")
        return 0
    src = fu.read_answers(project)["_src_path"]
    if not SRC_RE.match(src):
        raise fu.Usage(f"{fu.ANSWERS}: _src_path '{src}' is not an owner/repository name")
    factory = workdir / "factory"
    git(workdir, "-c", "credential.helper=", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
        factory_url or f"https://github.com/{src}.git", str(factory), env=no_token_env())
    base_branch = git(project, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    report_file = workdir / "update.json"
    # keep_workflows: the workflow files stay as they are, and _workflows_from records the commit they are at, so
    # merging this pull request does not make the next run merge the same release again
    fu.update(project, factory, report=report_file, keep_workflows=True)   # 0 or 1 (conflicts); refusal: Usage
    report = json.loads(report_file.read_text(encoding="utf-8"))
    to = report["to"]
    if not REF_RE.match(to):   # it names a branch: a release tag, never anything git could read as an option
        raise fu.Usage(f"the target '{to}' is not a release name")
    if report["status"] == "current":
        notice(f"the project is already at or past software-factory {to}: nothing to update")
        # publish closes what is still open for an update that is done (a local /factory-update, a merged one)
        state.write_text(json.dumps({"action": "current", "version": report["from"]}), encoding="utf-8")
        return 0
    workflows = report.get("workflows", [])
    others = [p for p in report["changed"] if p != fu.ANSWERS]
    if report["status"] == "workflows-pending" or (workflows and not others):
        # Nothing to propose but workflow files, which the token cannot push: the issue says so, nothing is committed
        # (and the answers file is left as it was, so a local /factory-update does it all)
        restore(project, fu.ANSWERS)
    branch = BRANCH_PREFIX + to
    changes = bool(git(project, "status", "--porcelain", "--untracked-files=all").stdout.strip())
    notes = headlines(factory, report["base_commit"], report["commit"])
    title = f"chore: update from software-factory {to}"
    if changes:
        git(project, "checkout", "-q", "-b", branch)
        git(project, "add", "-A")
        message = workdir / "message.txt"
        message.write_text(title + "\n\n" + "".join(f"- {n}\n" for n in notes), encoding="utf-8")
        bot = {"GIT_AUTHOR_NAME": BOT_NAME, "GIT_AUTHOR_EMAIL": BOT_EMAIL, "GIT_COMMITTER_NAME": BOT_NAME,
               "GIT_COMMITTER_EMAIL": BOT_EMAIL}   # the environment wins over -c user.name: set both
        git(project, "commit", "--no-verify", "-q", "-F", str(message), env={**no_token_env(), **bot})
    conflicts = [i for i in report["items"].get("conflicts", []) if not i.startswith(WORKFLOWS)]
    (workdir / "details.md").write_text(details(report, workflows, notes), encoding="utf-8")
    state.write_text(json.dumps({"action": "pr" if changes else "issue", "from": report["from"], "to": to,
                                 "branch": branch, "base": base_branch, "title": title, "draft": bool(conflicts),
                                 "workflows": workflows, "src": src}, indent=2), encoding="utf-8")
    print(f"prepared: {'pull request from ' + branch if changes else 'issue (only workflow files changed)'}")
    return 0


class GhError(Exception):
    pass


class Gh:
    """The gh calls publish makes; GH_REPO and GH_TOKEN come from the environment. Tests pass a fake."""

    def run(self, *args):
        done = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              check=False)
        if done.returncode != 0:
            raise GhError(f"gh {args[0]} {args[1]} failed: {done.stderr.strip()}")
        return done.stdout

    def open_prs(self):
        return json.loads(self.run("pr", "list", "--state", "open", "--json",
                                   "number,headRefName,title,isCrossRepository", "--limit", "100") or "[]")

    def open_issue(self):
        found = json.loads(self.run("issue", "list", "--label", LABEL, "--state", "open", "--json", "number,title",
                                    "--limit", "1") or "[]")
        return found[0] if found else None

    def declined_pr(self, branch):
        """A pull request of this repository from the branch, closed without merging, or None."""
        found = json.loads(self.run("pr", "list", "--state", "closed", "--head", branch, "--json",
                                    "number,mergedAt,isCrossRepository", "--limit", "20") or "[]")
        return next((p for p in found if not p.get("mergedAt") and not p.get("isCrossRepository", False)), None)

    def declined_issue(self, title):
        """The factory-update issue with this title closed as not planned, or None. The job closes its own issues as
        completed, so only a person's "not planned" counts."""
        found = json.loads(self.run("issue", "list", "--label", LABEL, "--state", "closed", "--json",
                                    "number,title,stateReason", "--limit", "50") or "[]")
        return next((i for i in found if i["title"] == title and i.get("stateReason") == "NOT_PLANNED"), None)

    def create_pr(self, base, head, title, body, draft):
        url = self.run("pr", "create", "--base", base, "--head", head, "--title", title, "--body-file", str(body),
                       *(["--draft"] if draft else [])).strip()
        return int(url.rstrip("/").rsplit("/", 1)[-1])

    def comment(self, kind, number, text):
        self.run(kind, "comment", str(number), "--body", text)

    def close(self, kind, number):
        self.run(kind, "close", str(number))

    def save_issue(self, number, title, body):
        if number is not None:
            self.run("issue", "edit", str(number), "--title", title, "--body-file", str(body))
            return number
        try:
            self.run("label", "create", LABEL, "--color", "0e8a16", "--force",
                     "--description", "A newer software-factory release to bring in")
        except GhError:
            pass   # the label may exist already, or the token may not create labels: the issue still opens
        url = self.run("issue", "create", "--title", title, "--body-file", str(body), "--label", LABEL).strip()
        return int(url.rstrip("/").rsplit("/", 1)[-1])


def push(project, branch):
    """Push the branch with the job's token, given to git through the environment for this one command (the checkout
    keeps none). --force: the factory-update/ branches belong to this job, and an earlier run may have left one."""
    env = dict(os.environ)
    token = os.environ.get("GH_TOKEN")
    if token:
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        basic = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0=f"http.{server}/.extraheader",
                   GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}")
    git(project, "push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{branch}", env=env)


CI_NOTE = ("### CI has not run on this pull request\n\nA pull request opened with `GITHUB_TOKEN` starts no workflows. "
           "To run CI, close and reopen it, or push a commit to `{branch}`.\n")


NO_DRAFT_RE = re.compile(r"draft[^\n]*not (?:supported|available)|not (?:supported|available)[^\n]*draft", re.I)
NO_DRAFT_NOTE = ("**Draft pull requests are not available in this repository, so this one is open for review although "
                 "it has unresolved conflicts: resolve them (see Conflicts below) before merging.**\n\n")


def create_update_pr(gh, state, branch, title, body):
    """Open the pull request, a draft when it has conflicts. Private repositories on GitHub Free have no drafts: then
    it opens as a normal one, marked [conflicts] in the title and the first line, instead of failing every week."""
    try:
        return gh.create_pr(state["base"], branch, title, body, state["draft"])
    except GhError as ex:
        if not (state["draft"] and NO_DRAFT_RE.search(str(ex))):
            raise
    body.write_text(NO_DRAFT_NOTE + body.read_text(encoding="utf-8"), encoding="utf-8")
    return gh.create_pr(state["base"], branch, f"[conflicts] {title}", body, False)


def publish(project, workdir, gh=None):
    gh = gh or Gh()
    workdir = Path(workdir)
    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    if state["action"] == "none":
        print("nothing to publish")
        return 0
    # The job's own pull requests: a branch of this repository. A fork's branch can have the same name; it must
    # neither stop the update nor be closed by it.
    updates = [p for p in gh.open_prs()
               if p["headRefName"].startswith(BRANCH_PREFIX) and not p.get("isCrossRepository", False)]
    issue = gh.open_issue()
    if state["action"] == "current":
        text = f"The project is at {state['version']} now; nothing to update."
        for kind, number in [("pr", p["number"]) for p in updates] + ([("issue", issue["number"])] if issue else []):
            gh.comment(kind, number, text)
            gh.close(kind, number)
        print(f"nothing to update; closed {len(updates)} pull request(s) and {1 if issue else 0} issue")
        return 0
    to, branch, title = state["to"], state["branch"], state["title"]
    same = [p for p in updates if p["headRefName"] == branch]
    if same:
        notice(f"pull request #{same[0]['number']} already proposes software-factory {to}")
        return 0
    # An open issue stops only the workflow-only case. With a commit to propose, the pull request is tried again
    # every run: the issue may say the repository did not allow it, and the setting may be on now.
    if state["action"] == "issue" and issue and f"software-factory {to}" in issue["title"]:
        notice(f"issue #{issue['number']} already tracks software-factory {to}")
        return 0
    # A maintainer who closes the update (a pull request without merging it, the issue as not planned) declines that
    # release: it is not proposed again, and the next release is.
    declined = (("pull request", gh.declined_pr(branch)) if state["action"] == "pr"
                else ("issue", gh.declined_issue(title)))
    if declined[1]:
        notice(f"{declined[0]} #{declined[1]['number']} declined software-factory {to}; the job waits for the next "
               "release")
        return 0
    details_md = (workdir / "details.md").read_text(encoding="utf-8")
    intro = f"Updates this project from software-factory {state['from']} to {to}, opened by the weekly factory-update job."
    if state["action"] == "pr":
        push(project, branch)
        body = workdir / "pr.md"
        body.write_text(f"{intro}\n\n{details_md}\n{CI_NOTE.format(branch=branch)}", encoding="utf-8")
        try:
            number = create_update_pr(gh, state, branch, title, body)
        except GhError as ex:
            if not NOT_ALLOWED_RE.search(str(ex)):
                raise
            reason = (f"This repository does not let GitHub Actions open pull requests. The changes are on branch "
                      f"`{branch}`: open a pull request from it, or turn on {SETTING} and run this workflow again.")
            return keep_issue(gh, issue, title, workdir, reason, details_md)
        print(f"opened pull request #{number}" + (" (draft: conflicts)" if state["draft"] else ""))
        for old in updates:
            gh.comment("pr", old["number"], f"Superseded by #{number} (software-factory {to}).")
            gh.close("pr", old["number"])
        if issue:
            gh.comment("issue", issue["number"], f"Superseded by pull request #{number} (software-factory {to}).")
            gh.close("issue", issue["number"])
        return 0
    reason = ("Only workflow files are left to update, and `GITHUB_TOKEN` cannot push those: run `/factory-update` "
              "locally to bring them in.")
    return keep_issue(gh, issue, title, workdir, reason, details_md)


def keep_issue(gh, issue, title, workdir, reason, details_md):
    """One issue labelled factory-update: updated when it is open, opened otherwise."""
    body = workdir / "issue.md"
    body.write_text(f"software-factory {title.rsplit(' ', 1)[-1]} is available. {reason}\n\n{details_md}",
                    encoding="utf-8")
    number = gh.save_issue(issue["number"] if issue else None, title, body)
    print(f"issue #{number} {'updated' if issue else 'opened'}")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("prepare", "publish"):
        c = sub.add_parser(name)
        c.add_argument("--workdir", required=True)
        c.add_argument("--project", default=".")
        if name == "prepare":
            c.add_argument("--factory-url", help="clone the factory from here instead of https://github.com/<_src_path>")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if a.command == "prepare":
            return prepare(a.project, a.workdir, a.factory_url)
        return publish(a.project, a.workdir)
    except fu.Usage as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    except (Problem, GhError, OSError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
