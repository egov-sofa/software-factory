"""Tests of scripts/eval_merge.py, the helpers of `run-evals.sh --one-at-a-time`: which cases to run, the budget left,
and the merged result that scripts/eval_summary.py reads.

Run: python3 -m unittest discover -s scripts/tests
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import support

sys.path.insert(0, str(support.SCRIPTS))
import eval_merge  # noqa: E402  (after the sys.path line above)
import eval_summary  # noqa: E402

EVALS = support.FACTORY / "evals"


def one_case(name, score, cost, delta=None, passed=None, **top):
    """A result of `claude plugin eval --case <name>`, in the shape of Claude Code 2.1.310's."""
    aggregates = {"score": score, "passRate": 1 if score >= 0.66 else 0, "scoreWithout": 0.5}
    if delta is not None:
        aggregates["delta"] = delta
    return {"schemaVersion": 1, "claudeVersion": "2.1.310", "startedAt": f"t-{name}", "durationSeconds": 30,
            "costUsd": cost, "partial": False, "suite": {"threshold": 0.66, "ablation": "with-without"},
            "cases": [{"name": name, "arms": {}, "aggregates": aggregates}],
            "aggregates": {"casesTotal": 1, "casesPassed": int(score >= 0.66 if passed is None else passed)}, **top}


class Cases(unittest.TestCase):
    def test_the_tags_of_a_case(self):
        self.assertEqual(("a", ["portable", "core"]), eval_merge.case_tags("name: a\ntags: [portable, 'core']\n"))
        for text in ("name: a\n", "name: a\ntags:\n  - portable\n", "tags: [portable]\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):   # never skipped silently
                eval_merge.case_tags(text)

    def test_the_suite_by_tag_and_glob(self):
        portable = eval_merge.select_cases(EVALS, ["portable"])
        self.assertIn("reviewer-finds-off-by-one", portable)
        self.assertNotIn("tester-reports-instead-of-fixing-src", portable)   # tagged shell
        self.assertEqual(sorted(portable), portable)
        self.assertIn("tester-reports-instead-of-fixing-src", eval_merge.select_cases(EVALS, ["portable", "shell"]))
        self.assertEqual(["security-finds-key-and-sqli", "security-passes-clean-change"],
                         eval_merge.select_cases(EVALS, ["portable"], "security-*"))
        self.assertNotIn("_probe", eval_merge.select_cases(EVALS, ["portable", "probe"]))   # never the probe

    def test_an_unreadable_case_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x").mkdir()
            (Path(tmp) / "x" / "case.yaml").write_bytes(b"name: x\n")
            with self.assertRaisesRegex(ValueError, "case.yaml"):
                eval_merge.select_cases(tmp, ["portable"])


class Budget(unittest.TestCase):
    def test_what_is_left_rounded_down_to_the_cent(self):
        self.assertEqual(Decimal("20.00"), eval_merge.budget_left(Decimal(20), []))
        self.assertEqual(Decimal("18.63"), eval_merge.budget_left(Decimal(20), [{"costUsd": 1.37}]))   # not 18.62
        self.assertEqual(Decimal("0.05"), eval_merge.budget_left(Decimal(2), [{"costUsd": 1.9}, {"costUsd": 0.05}]))
        self.assertEqual(Decimal("1.23"), eval_merge.budget_left(Decimal("1.239"), [{}]))   # no cost recorded

    def test_nothing_below_five_cents(self):
        self.assertIsNone(eval_merge.budget_left(Decimal("1.23"), [{"costUsd": 0.6}, {"costUsd": 0.6}]))
        self.assertIsNone(eval_merge.budget_left(Decimal(2), [{"costUsd": 2.4}]))   # the CLI overshot


class Merge(unittest.TestCase):
    def test_the_cases_as_one_result(self):
        merged = eval_merge.merge([one_case("a", 1.0, 0.5, delta=0.5), one_case("b", 0.5, 0.25, delta=-0.25),
                                   one_case("c", 1.0, 0.75)])
        self.assertEqual((1, "2.1.310", "t-a"), (merged["schemaVersion"], merged["claudeVersion"],
                                                 merged["startedAt"]))
        self.assertEqual({"threshold": 0.66, "ablation": "with-without"}, merged["suite"])
        self.assertEqual(["a", "b", "c"], [case["name"] for case in merged["cases"]])
        self.assertEqual((1.5, 90, False), (merged["costUsd"], merged["durationSeconds"], merged["partial"]))
        self.assertNotIn("partialReason", merged)
        totals = merged["aggregates"]
        self.assertEqual((3, 2), (totals["casesTotal"], totals["casesPassed"]))
        self.assertAlmostEqual(2.5 / 3, totals["overallScore"])
        self.assertAlmostEqual(2 / 3, totals["overallPassRate"])
        self.assertAlmostEqual(0.125, totals["meanDelta"])   # of the cases that have one

    def test_no_delta_without_two_arms(self):
        self.assertNotIn("meanDelta", eval_merge.merge([one_case("a", 1.0, 0.1)])["aggregates"])

    def test_partial(self):
        auth = one_case("b", 0.0, 0.0, partial=True, partialReason="auth_failed")
        merged = eval_merge.merge([one_case("a", 1.0, 0.1), auth])
        self.assertEqual((True, "auth_failed"), (merged["partial"], merged["partialReason"]))
        merged = eval_merge.merge([one_case("a", 1.0, 0.1), auth], "cost_ceiling")   # why the run stopped wins
        self.assertEqual((True, "cost_ceiling"), (merged["partial"], merged["partialReason"]))

    def test_no_case_ran(self):
        merged = eval_merge.merge([], "interrupted")
        self.assertEqual(([], 0, True, "interrupted"), (merged["cases"], merged["costUsd"], merged["partial"],
                                                        merged["partialReason"]))
        self.assertEqual({"casesTotal": 0, "casesPassed": 0, "overallScore": 0, "overallPassRate": 0},
                         merged["aggregates"])
        self.assertIn("**Interrupted:**", eval_summary.summary(merged))

    def test_the_summary_reads_the_merged_result(self):
        text = eval_summary.summary(eval_merge.merge([one_case("a", 1.0, 0.5, delta=0.5),
                                                      one_case("b", 0.5, 0.25, delta=0.0)], "cost_ceiling"))
        self.assertIn("**Cost ceiling hit:**", text)
        self.assertIn("Cases passed: 1 of 2; overall score 0.75, mean difference +0.25. Cost $0.75, 60 s.", text)
        self.assertIn("| b | **below threshold** | 0.50 | 0.50 | +0.00 |", text)


class Main(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = eval_merge.main(list(argv))
            except SystemExit as ex:   # argparse's usage errors
                code = ex.code
        return code, out.getvalue(), err.getvalue()

    def test_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for result in (one_case("a", 1.0, 0.5), one_case("b", 1.0, 1.25)):
                paths.append(str(Path(tmp) / f"{result['cases'][0]['name']}.json"))
                Path(paths[-1]).write_text(json.dumps(result), encoding="utf-8")
            self.assertEqual((0, "18.25\n", ""), self.run_main("budget", "20", *paths))
            self.assertEqual((0, "0.05\n", ""), self.run_main("budget", "1.8", *paths))
            self.assertEqual((0, "", ""), self.run_main("budget", "1.79", *paths))   # 0.04 left: not worth a case
            out = Path(tmp) / "result.json"
            self.assertEqual(0, self.run_main("merge", str(out), "--partial", "cost_ceiling", *paths)[0])
            merged = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((["a", "b"], "cost_ceiling"), ([c["name"] for c in merged["cases"]],
                                                            merged["partialReason"]))
            self.assertEqual("reviewer-finds-off-by-one\n",
                             self.run_main("cases", str(EVALS), "--case", "*-off-by-one", "--tag", "portable")[1])

    def test_errors(self):
        code, _, err = self.run_main("merge", "out.json", "no-such-result.json")
        self.assertEqual(2, code)
        self.assertIn("error:", err)
        self.assertEqual(2, self.run_main("budget", "lots")[0])


if __name__ == "__main__":
    unittest.main()
