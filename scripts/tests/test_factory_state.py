"""Tests of scripts/factory_state.py: the pipeline state in a plan, and the header lines of each agent's report.

Run: python3 -m unittest discover -s scripts/tests
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "factory_state.py"
sys.path.insert(0, str(SCRIPT.parent))
import factory_state as fs  # noqa: E402  (after the sys.path line above)

PLANS = SCRIPT.parents[1] / "docs" / "plans"

REVIEW = """\
Verdict: CHANGES_REQUESTED
Blocking: 2

## Findings
1. [BLOCKER] src/page.ts:42: off-by-one on the last page
2. [MAJOR] src/page.ts:50: no test for an empty list
3. [MINOR] src/page.ts:7: naming
"""


def plan(*lines, body="## Goal\nSomething.\n"):
    return "# Plan: x\n\n**Status:** Approved\n" + "".join(f"{line}\n" for line in lines) + "\n" + body


FULL = ("**Stage:** review", "**Round:** 1", "**Base:** main", "**Branch:** feat/x")


class Headers(unittest.TestCase):
    def check(self, agent, text, **kw):
        return fs.check_report(agent, textwrap.dedent(text), **kw)

    def test_valid_reports_pass_and_return_their_values(self):
        self.assertEqual({"verdict": "CHANGES_REQUESTED", "blocking": "2"}, self.check("reviewer", REVIEW))
        self.assertEqual({"result": "DONE", "commands": "PASS"}, self.check("implementer", "Result: DONE\nCommands: PASS\n"))
        self.assertEqual({"result": "PASS", "failures": "0"}, self.check("tester", "Result: PASS\nFailures: 0\n"))
        self.assertEqual({"verdict": "PASS", "blocking": "0"}, self.check("security-auditor", "Verdict: PASS\nBlocking: 0\n"))
        self.assertEqual({"result": "NO_CHANGES"}, self.check("docs-writer", "Result: NO_CHANGES\n## Report\nnothing\n"))

    def test_a_fenced_report_with_leading_blank_lines_is_accepted(self):
        self.assertEqual("CHANGES_REQUESTED", self.check("reviewer", "\n\n```\n" + REVIEW + "```\n")["verdict"])

    def test_missing_out_of_order_or_decorated_headers_are_refused(self):
        for text in ("## Findings\nnothing", "Blocking: 0\nVerdict: APPROVE\n", "**Verdict:** APPROVE\nBlocking: 0\n",
                     "## Verdict: APPROVE\nBlocking: 0\n", "Some intro.\nVerdict: APPROVE\nBlocking: 0\n", ""):
            with self.subTest(text=text), self.assertRaisesRegex(fs.Problem, "must be `Verdict: APPROVE | CHANGES"):
                self.check("reviewer", text)

    def test_unknown_values_are_refused(self):
        with self.assertRaisesRegex(fs.Problem, "line 1"):
            self.check("reviewer", "Verdict: LGTM\nBlocking: 0\n")
        with self.assertRaisesRegex(fs.Problem, "line 2 must be `Commands: PASS | FAIL`"):
            self.check("implementer", "Result: DONE\nCommands: OK\n")

    def test_verdict_and_blocking_must_agree(self):
        with self.assertRaisesRegex(fs.Problem, "Verdict: APPROVE with Blocking: 1"):
            self.check("reviewer", "Verdict: APPROVE\nBlocking: 1\n1. [MAJOR] a.py:1: x\n")
        with self.assertRaisesRegex(fs.Problem, "CHANGES_REQUESTED with Blocking: 0"):
            self.check("reviewer", "Verdict: CHANGES_REQUESTED\nBlocking: 0\n")
        with self.assertRaisesRegex(fs.Problem, "Verdict: PASS with Blocking: 1"):
            self.check("security-auditor", "Verdict: PASS\nBlocking: 1\n1. [HIGH] a.py:1: x\n")
        # ISSUES_FOUND with only low findings is fine: they do not block
        self.check("security-auditor", "Verdict: ISSUES_FOUND\nBlocking: 0\n1. [LOW] a.py:1: x\n")

    def test_blocking_must_match_the_tagged_findings(self):
        with self.assertRaisesRegex(fs.Problem, "Blocking: 1, but 2 finding"):
            self.check("reviewer", REVIEW.replace("Blocking: 2", "Blocking: 1"))

    def test_tester_result_matches_failures(self):
        with self.assertRaisesRegex(fs.Problem, "Result: PASS does not match Failures: 2"):
            self.check("tester", "Result: PASS\nFailures: 2\n")
        with self.assertRaisesRegex(fs.Problem, "Result: FAIL does not match Failures: 0"):
            self.check("tester", "Result: FAIL\nFailures: 0\n")

    def test_implementer_answers_every_finding_it_was_sent(self):
        text = "Result: DONE\nCommands: PASS\n\n## Answers\n- REV-1.1: fixed: guarded the last page\n"
        self.check("implementer", text, ids=["REV-1.1"])
        with self.assertRaisesRegex(fs.Problem, "SEC-1.1"):
            self.check("implementer", text, ids=["REV-1.1", "SEC-1.1"])
        self.check("implementer", text + "- SEC-1.1: disagree: the input is a constant\n", ids=["REV-1.1", "SEC-1.1"])

    def test_re_review_accounts_for_every_earlier_finding(self):
        earlier = "\n## Earlier findings\n- REV-1.1: resolved: guarded\n"
        approve = "Verdict: APPROVE\nBlocking: 0\n" + earlier
        self.check("reviewer", approve, ids=["REV-1.1"], round_=2)
        with self.assertRaisesRegex(fs.Problem, "REV-1.2"):
            self.check("reviewer", approve, ids=["REV-1.1", "REV-1.2"], round_=2)
        self.check("reviewer", approve, ids=["REV-1.1", "REV-1.2"], round_=1)   # round 1 has no earlier findings

    def test_an_earlier_blocker_still_open_blocks(self):
        """Round 2 with REV-1.1 unfixed and nothing new must not APPROVE (second review of #26)."""
        earlier = "\n## Earlier findings\n- REV-1.1: still open: the last page is still skipped\n"
        ok = "Verdict: CHANGES_REQUESTED\nBlocking: 1\n" + earlier
        self.assertEqual("1", self.check("reviewer", ok, ids=["REV-1.1"], round_=2)["blocking"])
        with self.assertRaisesRegex(fs.Problem, "Verdict: APPROVE with Blocking: 1|0 finding\\(s\\) are tagged .* 1 earlier"):
            self.check("reviewer", "Verdict: APPROVE\nBlocking: 0\n" + earlier, ids=["REV-1.1"], round_=2)
        # a new MAJOR and an earlier one still open: 2
        two = "Verdict: CHANGES_REQUESTED\nBlocking: 2\n1. [MAJOR] a.py:1: x\n" + earlier
        self.check("reviewer", two, ids=["REV-1.1"], round_=2)
        sec = "Verdict: ISSUES_FOUND\nBlocking: 1\n\n## Earlier findings\n- SEC-1.1: still open: the query is built from input\n"
        self.check("security-auditor", sec, ids=["SEC-1.1"], round_=2)

    def test_a_finding_the_user_dropped_does_not_block(self):
        """REV-1.2 was dropped by the user, so the conductor does not pass it; even if listed still open, it is not
        counted (review of #28)."""
        earlier = ("\n## Earlier findings\n- REV-1.1: resolved: guarded\n"
                   "- REV-1.2: still open: the reviewer still disagrees\n")
        self.check("reviewer", "Verdict: APPROVE\nBlocking: 0\n" + earlier, ids=["REV-1.1"], round_=2)

    def test_section_headings_as_the_templates_print_them(self):
        """The agents' report templates add words after the section name; a copied template must pass (review of #28)."""
        earlier = "\n## Earlier findings (round 2 and later)\n- REV-1.1: still open: not fixed\n"
        self.check("reviewer", "Verdict: CHANGES_REQUESTED\nBlocking: 1\n" + earlier, ids=["REV-1.1"], round_=2)
        answers = "Result: DONE\nCommands: PASS\n\n## Answers (when fixing findings)\n- REV-1.1: fixed: guarded\n"
        self.check("implementer", answers, ids=["REV-1.1"])
        # the real templates, as written in the agent files
        for agent, title in (("reviewer", "Earlier findings"), ("security-auditor", "Earlier findings"),
                             ("implementer", "Answers")):
            text = (SCRIPT.parents[1] / "claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")
            with self.subTest(agent):
                self.assertIsNotNone(fs.section(text, title), f"{agent}.md: no `## {title}` heading the parser finds")

    def test_planner_names_a_plan_that_exists(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "docs" / "plans").mkdir(parents=True)
            (Path(root) / "docs" / "plans" / "p.md").write_text("# Plan: p\n")
            self.check("planner", "Plan: docs/plans/p.md\nCriteria: 3\n", root=root)
            with self.assertRaisesRegex(fs.Problem, "does not exist"):
                self.check("planner", "Plan: docs/plans/q.md\nCriteria: 3\n", root=root)
            with self.assertRaisesRegex(fs.Problem, "at least 1"):
                self.check("planner", "Plan: docs/plans/p.md\nCriteria: 0\n", root=root)


class State(unittest.TestCase):
    def test_full_header(self):
        self.assertEqual({"stage": "review", "round": "1", "base": "main", "branch": "feat/x"}, fs.state(plan(*FULL)))

    def test_older_plans_are_legacy(self):
        for name in ("2026-11-11-validate-and-test-factory-scripts.md", "2026-11-19-enforce-agent-limits-with-hooks.md"):
            with self.subTest(name):
                self.assertIsNone(fs.state((PLANS / name).read_text(encoding="utf-8")))

    def test_the_format_quoted_in_the_plan_body_is_ignored(self):
        body = "## Design\n" + "\n" * 20 + "**Stage:** implement\n**Round:** 0\n"
        self.assertIsNone(fs.state(plan(body=body)))

    def test_invalid_values_are_refused(self):
        for lines, message in ((("**Stage:** build",) + FULL[1:], "Stage: build"),
                               (FULL[:1] + ("**Round:** 3",) + FULL[2:], "Round:"),
                               (FULL[:2] + FULL[3:], "Base"),
                               (FULL[:3], "Branch")):
            with self.subTest(message), self.assertRaisesRegex(fs.Problem, message):
                fs.state(plan(*lines))


class FindAndRounds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        (self.dir / name).write_text(text, encoding="utf-8")

    def test_find_keeps_open_plans_of_the_branch(self):
        self.write("a.md", plan(*FULL))
        self.write("b.md", plan("**Stage:** done", *FULL[1:]))
        self.write("c.md", plan(*FULL[:3], "**Branch:** feat/other"))
        self.write("d.md", plan())   # legacy
        self.assertEqual(["a.md"], [p.name for p in fs.find(self.dir, "feat/x")])
        self.write("e.md", plan("**Stage:** fix", *FULL[1:]))
        self.assertEqual(["a.md", "e.md"], [p.name for p in fs.find(self.dir, "feat/x")])
        self.assertEqual([], fs.find(self.dir, "feat/none"))

    def test_last_reviewed_is_the_newest_round(self):
        with self.assertRaisesRegex(fs.Problem, "no `### Round"):
            fs.last_reviewed(plan(*FULL))
        rounds = "## Review rounds\n### Round 1 (reviewed a1b2c3d)\n| ID |\n### Round 2 (reviewed 9f8e7d6)\n| ID |\n"
        self.assertEqual("9f8e7d6", fs.last_reviewed(plan(*FULL, body=rounds)))


class CommandLine(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False)

    def test_exit_codes_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "review.md"
            report.write_text(REVIEW, encoding="utf-8")
            ok = self.run_script("report", "reviewer", str(report))
            self.assertEqual((0, "verdict=CHANGES_REQUESTED\nblocking=2\n"), (ok.returncode, ok.stdout))
            report.write_text("Looks fine.\n", encoding="utf-8")
            bad = self.run_script("report", "reviewer", str(report))
            self.assertEqual(1, bad.returncode)
            self.assertIn("must be `Verdict:", bad.stderr)
            p = Path(tmp) / "plan.md"
            p.write_text(plan(*FULL), encoding="utf-8")
            self.assertEqual("stage=review\nround=1\nbase=main\nbranch=feat/x\n", self.run_script("state", str(p)).stdout)
            p.write_text(plan(), encoding="utf-8")
            self.assertEqual("legacy\n", self.run_script("state", str(p)).stdout)
            self.assertEqual(1, self.run_script("find", "--branch", "feat/x", "--plans", tmp).returncode)
        self.assertEqual(2, self.run_script("report", "nobody", "x").returncode)
        self.assertEqual(2, self.run_script().returncode)


if __name__ == "__main__":
    unittest.main()
