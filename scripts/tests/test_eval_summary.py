"""Tests of scripts/eval_summary.py: the Evals job's summary table, from a result recorded by the probe run (Claude
Code 2.1.310, paths made neutral) and variants of it in the same shape.

Run: python3 -m unittest discover -s scripts/tests
"""
import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import support

sys.path.insert(0, str(support.SCRIPTS))
import eval_summary  # noqa: E402  (after the sys.path line above)

PROBE = Path(__file__).resolve().parent / "data" / "eval-result-probe.json"


def probe():
    return json.loads(PROBE.read_text(encoding="utf-8"))


def two_arms():
    """The probe's case run with and without the plugin, as `--ablation with-without` writes it."""
    result = probe()
    result["suite"]["ablation"] = "with-without"
    result["suite"]["threshold"] = 0.67
    case = result["cases"][0]
    run = case["arms"]["with"][0]
    without = copy.deepcopy(run)
    without.update(score=0.25, costUsd=0.01, judgeCostUsd=0.005)
    for grader in without["graders"]:
        grader["passed"] = grader["name"] == "read-review-folder"
    case["arms"]["without"] = [without]
    case["aggregates"].update(scoreWithout=0.25, passRateWithout=0, delta=0.5)
    result["aggregates"]["meanDelta"] = 0.5
    return result


def table_row(text, name):
    (row,) = [line for line in text.splitlines() if line.startswith(f"| {name} |")]
    return [c.strip() for c in re.split(r"(?<!\\)\|", row.strip("|"))]   # not at an escaped \|


class Summary(unittest.TestCase):
    def test_recorded_probe_result(self):
        text = eval_summary.summary(probe())
        self.assertIn("Claude Code 2.1.310, plugin software-factory v1.4.0, model sonnet, one arm", text)
        self.assertIn("Cases passed: 1 of 1; overall score 0.75", text)
        self.assertEqual(["_probe", "pass", "0.75", "–", "–", "0%", "$0.03", "guard-refused (1/1)", "–"],
                         table_row(text, "_probe"))

    def test_two_arms_show_the_difference(self):
        text = eval_summary.summary(two_arms())
        self.assertIn("with and without the plugin, threshold 0.67", text)
        self.assertIn("mean difference +0.50", text)
        row = table_row(text, "_probe")
        self.assertEqual(["pass", "0.75", "0.25", "+0.50"], row[1:5])
        self.assertEqual("$0.05", row[6])   # both arms and the judge
        self.assertEqual("guard-refused (1/1)", row[7])   # failures of the with-plugin arm only

    def test_below_threshold_is_marked(self):
        result = two_arms()
        result["cases"][0]["aggregates"]["score"] = 0.5
        self.assertEqual("**below threshold**", table_row(eval_summary.summary(result), "_probe")[1])

    def test_cost_ceiling_is_said(self):
        result = two_arms()
        result.update(partial=True, partialReason="cost_ceiling")
        result["cases"][0]["arms"]["without"][0]["skippedPaidGraders"] = True
        text = eval_summary.summary(result)
        self.assertIn("**Cost ceiling hit:**", text)
        self.assertIn("paid graders skipped (cost ceiling)", table_row(text, "_probe")[8])

    def test_other_partial_results(self):
        for reason, says in (("auth_failed", "Authentication failed"), ("interrupted", "Interrupted"),
                             (None, "Partial result")):
            with self.subTest(reason=reason):
                result = probe()
                result["partial"] = True
                if reason:
                    result["partialReason"] = reason
                self.assertIn(says, eval_summary.summary(result))

    def test_error_run_is_shown(self):
        result = two_arms()
        result["cases"][0]["arms"]["with"][0]["error"] = "API Error: 529 overloaded |\nretry later"
        row = table_row(eval_summary.summary(result), "_probe")
        self.assertIn("error in 1 run(s): API Error: 529 overloaded \\| retry later", row[8])
        # the first Actions run: every run errored, yet a case whose graders need nothing to happen scored 1.00
        result["cases"][0]["aggregates"]["score"] = 1.0
        self.assertEqual("**error**", table_row(eval_summary.summary(result), "_probe")[1])

    def test_a_baseline_error_leaves_the_verdict_to_the_with_arm(self):
        """Review of #37: an errored run without the plugin makes Δ unreliable, not the factory's result."""
        result = two_arms()
        result["cases"][0]["arms"]["without"][0]["error"] = "API Error: 529 overloaded"
        row = table_row(eval_summary.summary(result), "_probe")
        self.assertEqual("pass", row[1])
        self.assertIn("error in 1 run(s): API Error: 529 overloaded", row[8])

    def test_unscored_graders_are_not_failures(self):
        result = probe()
        for grader in result["cases"][0]["arms"]["with"][0]["graders"]:
            if grader["name"] == "guard-refused":
                grader.update(withOnly=True, scored=False)
        self.assertEqual("–", table_row(eval_summary.summary(result), "_probe")[7])

    def test_case_with_no_runs(self):
        result = probe()
        result["cases"][0]["arms"] = {"with": []}
        result["cases"][0]["aggregates"] = {"score": 0, "passRate": 0}
        self.assertEqual("$0.00", table_row(eval_summary.summary(result), "_probe")[6])


class CommandLine(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = eval_summary.main(list(argv))
        return code, out.getvalue()

    def test_prints_the_table(self):
        code, out = self.run_main(str(PROBE))
        self.assertEqual(0, code)
        self.assertIn("| _probe | pass |", out)

    def test_missing_result_is_explained(self):
        code, out = self.run_main("no/such/result.json")
        self.assertEqual(1, code)
        self.assertIn("No result to show", out)

    def test_copies_the_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            trace.write_bytes(b'{"type":"x"}\n')
            result = two_arms()
            result["cases"][0]["arms"]["with"][0]["tracePath"] = str(trace)   # the without run's trace is gone
            path = Path(tmp) / "result.json"
            path.write_bytes(json.dumps(result).encode("utf-8"))
            code, _ = self.run_main("--copy-traces", str(Path(tmp) / "traces"), str(path))
            self.assertEqual(0, code)
            self.assertEqual(b'{"type":"x"}\n', (Path(tmp) / "traces" / "_probe" / "with-1.jsonl").read_bytes())
            self.assertFalse((Path(tmp) / "traces" / "_probe" / "without-1.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
