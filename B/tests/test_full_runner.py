"""全量记录入口的无模型回归；控制评估入口，验证完整/中止记录不混淆。"""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "implementation"))
import run_whitebox
import evaluator
import quick_eval
import runbook_matcher as matcher


class FullRunnerTests(unittest.TestCase):
    def test_preflight_never_calls_model(self):
        captured = io.StringIO()
        with patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")), \
             contextlib.redirect_stdout(captured):
            self.assertEqual(run_whitebox.main(["--limit", "200"]), 0)
        plan = json.loads(captured.getvalue().splitlines()[0])
        self.assertEqual(plan["case_count"], 200)
        self.assertEqual(plan["generation_requests_before_run"], 0)
        self.assertIn("未调用模型", captured.getvalue())

    def test_previous_attempts_are_deducted_from_total_budget(self):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            run_whitebox.main(["--limit", "200", "--max-requests", "600", "--spent-requests", "65"])
        plan = json.loads(captured.getvalue().splitlines()[0])
        self.assertEqual(plan["max_requests"], 535)
        self.assertEqual(plan["requests_spent_before_run"], 65)

    def test_complete_and_incomplete_runs_are_distinct(self):
        cases = json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"][:3]
        for completed, exit_code, expected in [(3, 0, "complete"), (1, 1, "incomplete")]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                output_path = Path(tmp) / "run.jsonl"

                def fake_entry(argv):
                    for case in cases[:completed]:
                        evaluator.evaluate_case(case, {
                            "matched_runbook": "test-fixture", "api_call": case["api_call"],
                            "sql": case["sql"], "result": case["answer"], "error": None,
                        }, 1.0)
                    return exit_code

                with patch.object(quick_eval, "main", side_effect=fake_entry), \
                     patch.object(matcher, "_llm_client", None), patch.object(matcher, "_llm_events", []), \
                     contextlib.redirect_stdout(io.StringIO()):
                    status = run_whitebox.main(["--run", "--limit", "3", "--output", str(output_path)])
                    with self.assertRaises(FileExistsError):
                        run_whitebox.main(["--run", "--limit", "3", "--output", str(output_path)])
                rows = [json.loads(line) for line in output_path.read_text().splitlines()]
                summary = rows[-1]
                self.assertEqual(status, exit_code)
                self.assertEqual(summary["status"], expected)
                self.assertEqual(summary["completed_cases"], completed)
                self.assertEqual(summary["planned_cases"], 3)
                self.assertEqual(summary["total_score"], completed * 5)
                self.assertEqual(summary["generation_requests"], 0)
