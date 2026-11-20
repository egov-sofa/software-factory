"""Tests of scripts/factory_update_job.py, the weekly update job: prepare (clone, update, workflow files out, commit
with hooks off) against a throwaway factory, and publish against a fake gh and a local bare repository as origin.

Run: python3 -m unittest discover -s scripts/tests
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import support
from test_factory_update import ANSWERS, T0, DAY, V1, commit, git, write

import sys
sys.path.insert(0, str(support.SCRIPTS))
import factory_update as fu  # noqa: E402
import factory_update_job as job  # noqa: E402

CHANGES = {
    "scripts/check_content.py": "#!/usr/bin/env python3\nprint('guard v2')\n",
    "templates/_shared/.github/workflows/ci.yml": "jobs:\n  ci:\n    uses: x/y/.github/workflows/ci.yml@v1\n# v2\n",
}


class FakeGh:
    """Records the calls; prs and issue are what GitHub has open; deny makes pull request creation fail as GitHub
    does when the repository setting is off."""

    def __init__(self, prs=(), issue=None, deny=False, no_draft=False, closed_prs=(), closed_issues=()):
        self.prs, self.issue, self.deny, self.calls, self.created = list(prs), issue, deny, [], 0
        self.no_draft = no_draft   # a private repository on GitHub Free: no draft pull requests
        self.closed_prs, self.closed_issues = list(closed_prs), list(closed_issues)   # what the real gh would filter

    def open_prs(self):
        return self.prs

    def open_issue(self):
        return self.issue

    def declined_pr(self, branch):
        return next((p for p in self.closed_prs if p["headRefName"] == branch), None)

    def declined_issue(self, title):
        return next((i for i in self.closed_issues if i["title"] == title), None)

    def create_pr(self, base, head, title, body, draft):
        self.calls.append(("create_pr", base, head, title, Path(body).read_text(encoding="utf-8"), draft))
        if self.deny:
            raise job.GhError("gh pr create failed: GitHub Actions is not permitted to create or approve pull requests")
        if draft and self.no_draft:
            raise job.GhError("gh pr create failed: GraphQL: Draft pull requests are not supported in this "
                              "repository. (createPullRequest)")
        self.prs.append({"number": 42, "headRefName": head, "title": title})
        return 42

    def comment(self, kind, number, text):
        self.calls.append(("comment", kind, number, text))

    def close(self, kind, number):
        self.calls.append(("close", kind, number))
        if kind == "issue" and self.issue and self.issue["number"] == number:
            self.issue = None
        self.prs = [p for p in self.prs if not (kind == "pr" and p["number"] == number)]

    def save_issue(self, number, title, body):
        self.calls.append(("save_issue", number, title, Path(body).read_text(encoding="utf-8")))
        if number is None:
            self.created += 1
            self.issue = {"number": 7, "title": title}
        return number or 7

    def names(self):
        return [c[0] for c in self.calls]


class Base(unittest.TestCase):
    CHANGES = CHANGES

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.env = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GITHUB_ACTIONS")}
        os.environ.update({k: v for k, v in support.environment().items() if k.startswith("GIT_")})
        os.environ.pop("GITHUB_ACTIONS", None)
        self.addCleanup(self.restore_env)
        self.factory = self.tmp / "factory"
        self.factory.mkdir()
        git(self.factory, "init", "-q", "-b", "main")
        write(self.factory, V1)
        commit(self.factory, "feat: the first release", when=T0)
        git(self.factory, "tag", "v1.0.0")
        write(self.factory, self.CHANGES)
        commit(self.factory, "fix: a better guard", when=T0 + 60 * DAY)
        git(self.factory, "tag", "v1.1.0")
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "init", "-q", "--bare", str(self.origin))
        self.project = self.tmp / "my-app"
        files, _, _ = fu.render(self.factory, "v1.0.0", ANSWERS)
        write(self.project, files)
        git(self.project, "init", "-q", "-b", "main")
        commit(self.project, "chore: scaffold from software-factory (generic template)")
        git(self.project, "remote", "add", "origin", str(self.origin))
        git(self.project, "push", "-q", "origin", "main")
        self.work = self.tmp / "work"

    def restore_env(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def prepare(self):
        self.assertEqual(0, job.prepare(self.project, self.work, factory_url=str(self.factory)))
        return json.loads((self.work / "state.json").read_text(encoding="utf-8"))

    def head_file(self, rel):
        return git(self.project, "show", f"HEAD:{rel}")


class Prepare(Base):
    def test_commits_the_update_without_workflow_files_and_without_hooks(self):
        # pre-commit is skipped by --no-verify; prepare-commit-msg is not, only by core.hooksPath=/dev/null
        for name in ("pre-commit", "prepare-commit-msg"):
            hook = self.project / ".git" / "hooks" / name
            hook.write_text("#!/bin/sh\necho hook ran >&2\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)
        state = self.prepare()
        self.assertEqual({"action": "pr", "to": "v1.1.0", "branch": "factory-update/v1.1.0", "base": "main",
                          "draft": False, "workflows": [".github/workflows/ci.yml"]},
                         {k: state[k] for k in ("action", "to", "branch", "base", "draft", "workflows")})
        self.assertEqual("factory-update/v1.1.0", git(self.project, "branch", "--show-current").strip())
        self.assertIn("guard v2", self.head_file("scripts/check_content.py"))
        self.assertNotIn("# v2", self.head_file(".github/workflows/ci.yml"))   # left out
        recorded = fu.parse_answers(self.head_file(fu.ANSWERS))
        self.assertEqual(("v1.1.0", git(self.factory, "rev-parse", "v1.0.0").strip()),
                         (recorded["version"], recorded["_workflows_from"]))   # the workflow files' own base
        self.assertEqual("", git(self.project, "status", "--porcelain"))
        self.assertEqual(f"{job.BOT_NAME}\n", git(self.project, "log", "-1", "--format=%an"))
        self.assertIn("- fix: a better guard", git(self.project, "log", "-1", "--format=%B"))
        details = (self.work / "details.md").read_text(encoding="utf-8")
        self.assertIn("### Workflow files left out", details)
        self.assertIn("`.github/workflows/ci.yml`", details)
        self.assertIn("Run `/factory-update` locally", details)
        self.assertIn("- `fix: a better guard`", details)
        self.assertNotIn("feat: the first release", details)   # before the base

    def test_nothing_when_current(self):
        git(self.project, "checkout", "-q", "-b", "other")
        answers = fu.parse_answers((self.project / fu.ANSWERS).read_text(encoding="utf-8"))
        write(self.project, {fu.ANSWERS: fu.dump_answers({**answers, "_commit": "unknown", "version": "v1.1.0"})})
        commit(self.project, "pretend v1.1.0")
        self.assertEqual("current", self.prepare()["action"])
        self.assertEqual("other", git(self.project, "branch", "--show-current").strip())

    def test_skips_without_answers_file(self):
        (self.project / fu.ANSWERS).unlink()
        commit(self.project, "no answers")
        self.assertEqual("none", self.prepare()["action"])
        self.assertFalse((self.work / "factory").exists())

    def test_bad_source_is_refused(self):
        answers = fu.parse_answers((self.project / fu.ANSWERS).read_text(encoding="utf-8"))
        write(self.project, {fu.ANSWERS: fu.dump_answers({**answers, "_src_path": "--upload-pack=x/y"})})
        commit(self.project, "bad source")
        with self.assertRaises(fu.Usage):
            job.prepare(self.project, self.work)


class OnlyWorkflows(Base):
    CHANGES = {"templates/_shared/.github/workflows/ci.yml": CHANGES["templates/_shared/.github/workflows/ci.yml"]}

    def test_issue_and_no_commit(self):
        state = self.prepare()
        self.assertEqual("issue", state["action"])
        self.assertEqual("main", git(self.project, "branch", "--show-current").strip())
        self.assertEqual("", git(self.project, "status", "--porcelain"))
        gh = FakeGh()
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        (call,) = gh.calls
        self.assertEqual(("save_issue", None, "chore: update from software-factory v1.1.0"), call[:3])
        self.assertIn("Only workflow files are left to update", call[3])
        self.assertNotIn("_workflows_from", (self.project / fu.ANSWERS).read_text(encoding="utf-8"))
        self.assertEqual("", git(self.origin, "branch", "--list", "factory-update/*"))   # nothing pushed

    def test_an_issue_closed_as_not_planned_declines_the_release(self):
        self.prepare()
        gh = FakeGh(closed_issues=[{"number": 7, "title": "chore: update from software-factory v1.1.0"}])
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual([], gh.calls)


class WorkflowsPending(Base):
    """A release that changes a managed file and a workflow file: the merged pull request records _workflows_from, so
    the next run does not merge the same release again (review of #32)."""

    def merge_the_pull_request(self):
        self.prepare()
        git(self.project, "checkout", "-q", "main")
        git(self.project, "merge", "-q", "--ff-only", "factory-update/v1.1.0")
        self.work = self.tmp / "work-2"

    def local_update(self):
        done = subprocess.run([sys.executable, str(support.SCRIPTS / "factory_update.py"), "update", "--project",
                               str(self.project), "--factory", str(self.factory)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=support.environment(), check=False)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        return done

    def answers(self):
        return fu.parse_answers((self.project / fu.ANSWERS).read_text(encoding="utf-8"))

    def test_next_run_keeps_an_issue_and_merges_nothing_again(self):
        self.merge_the_pull_request()
        mine = "#!/usr/bin/env python3\nprint('a local override')\n"
        write(self.project, {"scripts/check_content.py": mine})
        commit(self.project, "local override after the merge")
        head = git(self.project, "rev-parse", "HEAD").strip()
        state = self.prepare()
        self.assertEqual(("issue", "v1.1.0", [".github/workflows/ci.yml"]),
                         (state["action"], state["to"], state["workflows"]))
        self.assertEqual(mine, (self.project / "scripts/check_content.py").read_text(encoding="utf-8"))
        self.assertEqual("", git(self.project, "status", "--porcelain"))
        self.assertEqual(head, git(self.project, "rev-parse", "HEAD").strip())   # no commit
        gh = FakeGh()
        job.publish(self.project, self.work, gh)
        self.assertEqual(["save_issue"], gh.names())
        self.assertIn("`.github/workflows/ci.yml`", gh.calls[0][3])
        self.assertEqual("", git(self.origin, "branch", "--list", "factory-update/*"))   # nothing pushed

    def test_check_passes_while_workflows_are_pending(self):
        self.merge_the_pull_request()
        self.assertIn("_workflows_from", self.answers())
        self.assertEqual(0, fu.check(self.project, self.factory, out=lambda text: None))

    def test_local_update_merges_the_workflows_and_removes_the_key(self):
        self.merge_the_pull_request()
        write(self.project, {"scripts/check_content.py": "#!/usr/bin/env python3\nprint('a local override')\n"})
        commit(self.project, "local override")
        self.local_update()
        self.assertIn("# v2", (self.project / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        self.assertNotIn("_workflows_from", self.answers())
        self.assertEqual("v1.1.0", self.answers()["version"])
        self.assertIn("a local override", (self.project / "scripts/check_content.py").read_text(encoding="utf-8"))

    def test_a_newer_release_merges_workflows_from_their_own_base(self):
        self.merge_the_pull_request()
        write(self.factory, {"templates/_shared/.github/workflows/ci.yml":
                             CHANGES["templates/_shared/.github/workflows/ci.yml"] + "# v3\n"})
        commit(self.factory, "fix: workflow v3")
        git(self.factory, "tag", "v1.2.0")
        self.local_update()
        ci = (self.project / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        # from _commit (v1.1.0) the merge would read "# v2" as removed here and drop it silently
        self.assertIn("# v2\n# v3\n", ci)
        self.assertNotIn("<<<<<<<", ci)
        self.assertEqual("v1.2.0", self.answers()["version"])
        self.assertNotIn("_workflows_from", self.answers())


class Conflicts(Base):
    CHANGES = {"templates/_shared/CLAUDE.md": "# Claude\n\nfactory line\n"}

    def test_draft(self):
        write(self.project, {"CLAUDE.md": "# Claude\n\nproject line\n"})
        commit(self.project, "own CLAUDE.md")
        state = self.prepare()
        self.assertTrue(state["draft"])
        self.assertIn("### Conflicts", (self.work / "details.md").read_text(encoding="utf-8"))
        gh = FakeGh()
        job.publish(self.project, self.work, gh)
        self.assertTrue(gh.calls[0][5])   # --draft

    def test_no_drafts_here_opens_a_marked_pull_request(self):
        """Review of #32: private repositories on GitHub Free have no drafts; the job must not fail every week."""
        write(self.project, {"CLAUDE.md": "# Claude\n\nproject line\n"})
        commit(self.project, "own CLAUDE.md")
        self.prepare()
        gh = FakeGh(no_draft=True)
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual(["create_pr", "create_pr"], gh.names())
        _, _, _, title, body, draft = gh.calls[1]
        self.assertEqual("[conflicts] chore: update from software-factory v1.1.0", title)
        self.assertFalse(draft)
        self.assertTrue(body.startswith("**Draft pull requests are not available in this repository"))
        self.assertIn("### Conflicts", body)
        self.assertEqual(1, body.count("Draft pull requests are not available"))

    def test_the_no_draft_message_is_recognised(self):
        for text in ("Draft pull requests are not supported in this repository",
                     "draft PRs are NOT AVAILABLE for this plan", "not supported: draft"):
            self.assertRegex(text, job.NO_DRAFT_RE)
        self.assertNotRegex("GitHub Actions is not permitted to create or approve pull requests", job.NO_DRAFT_RE)


class Publish(Base):
    def test_a_fork_branch_with_the_same_name_is_not_the_jobs(self):
        """Review of #32: a fork's factory-update/<version> branch neither stops the update nor gets closed."""
        self.prepare()
        fork = {"number": 8, "headRefName": "factory-update/v1.1.0", "title": "contributor", "isCrossRepository": True}
        gh = FakeGh(prs=[fork])
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual(["create_pr"], gh.names())   # opened, and the fork's pull request is not superseded
        self.assertIn(fork, gh.prs)

    def test_current_project_leaves_fork_pull_requests_open(self):
        answers = fu.parse_answers((self.project / fu.ANSWERS).read_text(encoding="utf-8"))
        write(self.project, {fu.ANSWERS: fu.dump_answers({**answers, "_commit": "unknown", "version": "v1.1.0"})})
        commit(self.project, "updated locally")
        self.prepare()
        gh = FakeGh(prs=[{"number": 8, "headRefName": "factory-update/v1.0.9", "title": "x", "isCrossRepository": True},
                         {"number": 3, "headRefName": "factory-update/v1.1.0", "title": "y", "isCrossRepository": False}])
        job.publish(self.project, self.work, gh)
        self.assertEqual([("comment", "pr", 3, "The project is at v1.1.0 now; nothing to update."), ("close", "pr", 3)],
                         gh.calls)

    def test_pr_list_asks_whether_the_branch_is_a_fork(self):
        calls = []

        class Recording(job.Gh):
            def run(self, *args):
                calls.append(args)
                return "[]"
        Recording().open_prs()
        self.assertIn("isCrossRepository", calls[0][calls[0].index("--json") + 1])

    def test_a_pull_request_closed_without_merging_declines_the_release(self):
        """Review of #32: closing the update pull request must not bring it back every Monday."""
        self.prepare()
        gh = FakeGh(closed_prs=[{"number": 9, "headRefName": "factory-update/v1.1.0"}])
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual([], gh.calls)
        self.assertEqual("", git(self.origin, "branch", "--list", "factory-update/*"))   # nothing pushed

    def test_the_fallback_issue_closed_as_not_planned_declines_the_release(self):
        """Review of #32: where Actions may not open pull requests, the issue is what the maintainer closes."""
        self.prepare()
        gh = FakeGh(deny=True, closed_issues=[{"number": 7, "title": "chore: update from software-factory v1.1.0"}])
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual([], gh.calls)
        self.assertEqual("", git(self.origin, "branch", "--list", "factory-update/*"))   # nothing pushed

    def test_a_declined_older_release_does_not_stop_the_next_one(self):
        self.prepare()
        gh = FakeGh(closed_prs=[{"number": 9, "headRefName": "factory-update/v1.0.9"}])
        job.publish(self.project, self.work, gh)
        self.assertEqual(["create_pr"], gh.names())

    def test_declined_lookups_keep_only_unmerged_same_repository_and_not_planned(self):
        class Canned(job.Gh):
            def run(self, *args):
                self.args = args
                if args[0] == "pr":
                    return json.dumps([{"number": 1, "mergedAt": "2026-11-01T00:00:00Z", "isCrossRepository": False},
                                       {"number": 2, "mergedAt": None, "isCrossRepository": True},
                                       {"number": 3, "mergedAt": None, "isCrossRepository": False}])
                title = "chore: update from software-factory v1.1.0"
                return json.dumps([{"number": 4, "title": title, "stateReason": "COMPLETED"},
                                   {"number": 5, "title": "chore: update from software-factory v1.0.9",
                                    "stateReason": "NOT_PLANNED"},
                                   {"number": 6, "title": title, "stateReason": "NOT_PLANNED"}])
        gh = Canned()
        self.assertEqual(3, gh.declined_pr("factory-update/v1.1.0")["number"])
        self.assertEqual(("--head", "factory-update/v1.1.0"), gh.args[4:6])
        self.assertEqual(6, gh.declined_issue("chore: update from software-factory v1.1.0")["number"])
        self.assertIsNone(Canned().declined_issue("chore: update from software-factory v1.2.0"))

    def test_pushes_opens_and_closes_older_ones(self):
        self.prepare()
        gh = FakeGh(prs=[{"number": 3, "headRefName": "factory-update/v1.0.9", "title": "old"},
                         {"number": 4, "headRefName": "feat/other", "title": "theirs"}],
                    issue={"number": 5, "title": "chore: update from software-factory v1.0.9"})
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        create = gh.calls[0]
        self.assertEqual(("create_pr", "main", "factory-update/v1.1.0", "chore: update from software-factory v1.1.0"),
                         create[:4])
        self.assertIn("### CI has not run on this pull request", create[4])
        self.assertIn("close and reopen it, or push a commit to `factory-update/v1.1.0`", create[4])
        self.assertFalse(create[5])
        self.assertIn(("comment", "pr", 3, "Superseded by #42 (software-factory v1.1.0)."), gh.calls)
        self.assertIn(("close", "pr", 3), gh.calls)
        self.assertNotIn(("close", "pr", 4), gh.calls)   # not an update pull request
        self.assertIn(("close", "issue", 5), gh.calls)
        pushed = git(self.origin, "rev-parse", "refs/heads/factory-update/v1.1.0").strip()
        self.assertEqual(git(self.project, "rev-parse", "HEAD").strip(), pushed)

    def test_nothing_when_a_pull_request_for_the_version_exists(self):
        self.prepare()
        gh = FakeGh(prs=[{"number": 9, "headRefName": "factory-update/v1.1.0", "title": "x"}],
                    issue={"number": 5, "title": "chore: update from software-factory v1.1.0"})
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual([], gh.calls)
        self.assertEqual("", git(self.origin, "branch", "--list", "factory-update/*"))

    def test_the_pull_request_opens_once_the_setting_is_on(self):
        """Review of #32: the fallback issue says to turn the setting on and run again; that run must open the pull
        request, not stop at the issue it opened itself."""
        self.prepare()
        gh = FakeGh(deny=True)
        job.publish(self.project, self.work, gh)
        self.assertEqual((1, 7), (gh.created, gh.issue["number"]))
        job.publish(self.project, self.work, gh)   # the setting is still off: the same issue is refreshed
        self.assertEqual(["create_pr", "save_issue", "create_pr", "save_issue"], gh.names())
        self.assertEqual(7, gh.calls[-1][1])
        gh.deny, gh.calls = False, []   # the maintainer turns the setting on
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        self.assertEqual(["create_pr", "comment", "close"], gh.names())
        self.assertEqual(("comment", "issue", 7, "Superseded by pull request #42 (software-factory v1.1.0)."),
                         gh.calls[1])
        self.assertIsNone(gh.issue)
        self.assertEqual(1, gh.created)   # one issue, ever
        gh.calls = []
        job.publish(self.project, self.work, gh)   # the next run: the pull request is open, nothing more
        self.assertEqual([], gh.calls)

    def test_current_project_closes_open_update_pull_requests_and_the_issue(self):
        answers = fu.parse_answers((self.project / fu.ANSWERS).read_text(encoding="utf-8"))
        write(self.project, {fu.ANSWERS: fu.dump_answers({**answers, "_commit": "unknown", "version": "v1.1.0"})})
        commit(self.project, "updated locally")
        self.assertEqual({"action": "current", "version": "v1.1.0"}, self.prepare())
        gh = FakeGh(prs=[{"number": 3, "headRefName": "factory-update/v1.1.0", "title": "update"},
                         {"number": 4, "headRefName": "feat/other", "title": "theirs"}],
                    issue={"number": 5, "title": "chore: update from software-factory v1.1.0"})
        self.assertEqual(0, job.publish(self.project, self.work, gh))
        text = "The project is at v1.1.0 now; nothing to update."
        self.assertEqual([("comment", "pr", 3, text), ("close", "pr", 3), ("comment", "issue", 5, text),
                          ("close", "issue", 5)], gh.calls)
        self.assertEqual([4], [p["number"] for p in gh.prs])   # not an update pull request: untouched
        gh = FakeGh(prs=[{"number": 4, "headRefName": "feat/other", "title": "theirs"}])
        job.publish(self.project, self.work, gh)
        self.assertEqual([], gh.calls)   # nothing open for updates: nothing to do

    def test_no_answers_file_touches_nothing(self):
        (self.project / fu.ANSWERS).unlink()
        commit(self.project, "no answers")
        self.prepare()
        gh = FakeGh(prs=[{"number": 3, "headRefName": "factory-update/v1.1.0", "title": "update"}],
                    issue={"number": 5, "title": "x"})
        job.publish(self.project, self.work, gh)
        self.assertEqual([], gh.calls)

    def test_falls_back_to_one_issue_naming_the_setting(self):
        self.prepare()
        for issue, expected in ((None, None), ({"number": 5, "title": "chore: update from software-factory v1.0.9"}, 5)):
            with self.subTest(issue=issue):
                gh = FakeGh(issue=issue, deny=True)
                self.assertEqual(0, job.publish(self.project, self.work, gh))
                self.assertEqual(["create_pr", "save_issue"], gh.names())
                saved = gh.calls[1]
                self.assertEqual(expected, saved[1])   # the open issue is updated, never a second one
                self.assertIn("Allow GitHub Actions to create and approve pull requests", saved[3])
                self.assertIn("`factory-update/v1.1.0`", saved[3])

    def test_other_gh_errors_fail(self):
        self.prepare()

        class Broken(FakeGh):
            def create_pr(self, *args):
                raise job.GhError("gh pr create failed: HTTP 500")
        with self.assertRaises(job.GhError):
            job.publish(self.project, self.work, Broken())


class Safety(unittest.TestCase):
    """The rules the action relies on, read from the script itself."""

    def test_git_runs_with_hooks_off_and_commits_without_verify(self):
        self.assertEqual(["git", "-c", "core.hooksPath=/dev/null"], job.GIT[:3])
        text = (support.SCRIPTS / "factory_update_job.py").read_text(encoding="utf-8")
        self.assertIn('git(project, "commit", "--no-verify"', text)
        self.assertNotIn("shell=True", text)
        self.assertEqual(1, text.count("subprocess.run([*GIT"))   # every git call goes through git()

    def test_prepare_drops_every_token(self):
        os.environ["GH_TOKEN"] = "x"
        self.addCleanup(os.environ.pop, "GH_TOKEN", None)
        self.assertNotIn("GH_TOKEN", job.no_token_env())
        self.assertEqual("0", job.no_token_env()["GIT_TERMINAL_PROMPT"])


if __name__ == "__main__":
    unittest.main()
