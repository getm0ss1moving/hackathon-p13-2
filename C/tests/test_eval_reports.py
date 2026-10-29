"""No-network checks using fixtures and the unchanged official score function."""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
TEST_KEY = "fixture-key-never-sent"


class ReportTests(unittest.TestCase):
    def setUp(self):
        reports = REPO / "C/reports"
        reports.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=reports)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        impl = self.root / "implementation"
        impl.mkdir()
        (impl / "runbook_system.py").write_text("# fixture implementation\n", encoding="utf-8")
        shutil.copyfile(REPO / "implementation/evaluator.py", impl / "evaluator.py")
        self.cases = [{"case_id": f"fixture-{i}", "question": f"测试问题 {i}",
                       "api_call": {"url": "/fixture"}, "sql": "SELECT total FROM fixture",
                       "answer": {"columns": ["total"], "rows": [{"total": 1}], "row_count": 1}}
                      for i in range(2)]
        self.write_cases()
        old_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        self.connect = patch("socket.socket.connect", side_effect=AssertionError("network disabled in tests"))
        self.connect.start()
        self.addCleanup(self.connect.stop)

    def write_cases(self):
        for label, count in [("白盒", 200), ("黑盒", 100)]:
            # Synthetic test fixtures, never official black-box test data.
            (self.root / f"CMDB用例集-{label}{count}.json").write_text(
                json.dumps({"cases": self.cases}, ensure_ascii=False), encoding="utf-8")

    def entry(self, name="quick_eval"):
        spec = importlib.util.spec_from_file_location("fixture_" + name, REPO / f"C/implementation/{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module._ROOT = self.root
        return module

    def correct(self, case=None):
        case = case or self.cases[0]
        return {"matched_runbook": "fixture", "api_call": case["api_call"],
                "sql": case["sql"], "result": case["answer"], "error": None}

    def run_entry(self, outputs, elapsed=None, name="quick_eval", report_name="run.json", extra=(), init_error=None):
        module = self.entry(name)
        report_path = self.root / "C/reports" / report_name
        fake_module = types.ModuleType("runbook_system")
        events = []
        remaining = iter(outputs)

        class FakeSystem:
            items = [{}, {}]

            def __init__(self):
                events.append("initialize")
                if init_error:
                    raise init_error

            def query(self, question):
                events.append("query")
                answer = next(remaining)
                if isinstance(answer, BaseException):
                    raise answer
                return answer

        fake_module.RunbookQuerySystem = FakeSystem
        times = []
        for index, seconds in enumerate(elapsed or [0.1] * len(outputs)):
            times.extend([index * 100, index * 100 + seconds])
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": TEST_KEY}), \
                patch.dict(sys.modules, {"runbook_system": fake_module}), \
                patch.object(module.http.client, "HTTPConnection") as connection, \
                patch.object(module.time, "perf_counter", side_effect=times), \
                patch.object(module, "_git", return_value="fixture-revision"), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"ci_name":"VM_NOVA","columns":["id"],"row_count":1}'
            code = module.main([str(len(outputs)), "--report", str(report_path), *extra])
        self.assertTrue(report_path.exists(), (code, stdout.getvalue(), stderr.getvalue()))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return code, report, report_path, events, stdout.getvalue() + stderr.getvalue()

    def test_completed_reports_for_both_entries(self):
        for entry in ("quick_eval", "blackbox_eval"):
            with self.subTest(entry=entry):
                code, report, path, _, console = self.run_entry(
                    [self.correct(), self.correct(self.cases[1])], name=entry, report_name=entry + ".json")
                self.assertEqual(code, 0)
                self.assertEqual(report["status"], "completed")
                self.assertEqual(report["summary"]["total_score"], 10)
                self.assertEqual(report["summary"]["completed_cases"], 2)
                self.assertIn("pct=100.0%", console)
                self.assertEqual(report["template_count"], 2)
                self.assertEqual(report["scorer_sha256"], hashlib.sha256(
                    (REPO / "implementation/evaluator.py").read_bytes()).hexdigest())
                self.assertEqual(len(path.with_name(path.stem + "-failures.csv").read_text(
                    encoding="utf-8-sig").splitlines()), 1)

    def test_outcomes_follow_official_reasons_not_score_buckets(self):
        conditional = {"constraint": [{"simple": {"name": "status", "value": "active"}}]}
        scenarios = [
            ("correct_slow", self.correct(), 5, 4, "correct", 1),
            ("abstain_slow", None, 9, 0, "abstained", 0),
            ("wrong", {**self.correct(), "result": {"columns": ["total"], "rows": [{"total": 999}], "row_count": 1}}, .1, -1, "wrong", 0),
            ("execution", {**self.correct(), "error": "fixture error"}, .1, -1, "execution_error", 0),
        ]
        for label, output, seconds, score, outcome, penalty in scenarios:
            with self.subTest(label=label):
                _, report, path, _, _ = self.run_entry([output], [seconds], report_name=label + ".json")
                detail = report["details"][0]
                self.assertEqual((detail["score"], detail["outcome"], detail["time_penalty"]), (score, outcome, penalty))
                with path.with_name(path.stem + "-failures.csv").open(encoding="utf-8-sig", newline="") as handle:
                    self.assertEqual(len(list(csv.DictReader(handle))), 1)
        self.cases[0]["api_call"]["condition"] = conditional
        self.write_cases()
        output = self.correct()
        output["api_call"] = {"url": "/fixture"}
        _, report, _, _, _ = self.run_entry([output], [9], report_name="condition.json")
        self.assertEqual(report["details"][0]["outcome"], "api_condition_missing")
        self.assertEqual(report["details"][0]["score"], 0)
        self.assertEqual(report["details"][0]["time_penalty"], 0)

    def test_partial_answer_preserves_official_score(self):
        output = self.correct()
        self.cases[0]["answer"] = {"columns": ["total"], "rows": [{"total": 1}, {"total": 2}], "row_count": 2}
        self.write_cases()
        _, report, _, _, _ = self.run_entry([output])
        self.assertEqual(report["details"][0]["score"], 2.5)
        self.assertEqual(report["details"][0]["outcome"], "partial")

    def test_midrun_exception_preserves_completed_cases(self):
        code, report, _, events, console = self.run_entry([self.correct(), RuntimeError(TEST_KEY)])
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "aborted")
        self.assertEqual(report["summary"]["completed_cases"], 1)
        self.assertEqual(report["summary"]["requested_cases"], 2)
        self.assertEqual(report["abort"]["case_id"], self.cases[1]["case_id"])
        self.assertEqual(events.count("query"), 2)
        self.assertNotIn(TEST_KEY, json.dumps(report) + console)

    def test_interrupt_is_incomplete_and_returns_130(self):
        code, report, _, _, _ = self.run_entry([KeyboardInterrupt()])
        self.assertEqual(code, 130)
        self.assertEqual(report["status"], "aborted")
        self.assertEqual(report["summary"]["completed_cases"], 0)
        self.assertIsNone(report["summary"]["score_percent_completed"])

    def test_initialization_failure_is_not_an_answer(self):
        code, report, _, events, _ = self.run_entry([self.correct()], init_error=RuntimeError())
        self.assertEqual(code, 1)
        self.assertEqual(report["abort"]["phase"], "initialization")
        self.assertNotIn("query", events)
        self.assertEqual(report["summary"]["completed_cases"], 0)

    def test_bad_output_stops_during_grading(self):
        code, report, _, _, _ = self.run_entry(["invalid system output"])
        self.assertEqual(code, 1)
        self.assertEqual(report["abort"]["phase"], "grading")
        self.assertEqual(report["status"], "aborted")

    def test_diagnostics_are_selected_and_key_is_masked(self):
        output = self.correct()
        output["sql"] += " -- " + TEST_KEY
        output["diagnostics"] = {"match_seconds": .01, "execute_seconds": .02,
            "prompt": "private prompt should be absent", "llm_calls": [
                {"stage": "select", "status": "ok", "seconds": .01, "prompt_tokens": 3,
                 "completion_tokens": 1, "raw_response": "private response should be absent"}]}
        _, report, path, _, console = self.run_entry([output])
        saved = path.read_text(encoding="utf-8") + console
        self.assertNotIn(TEST_KEY, saved)
        self.assertNotIn("private prompt", saved)
        self.assertNotIn("private response", saved)
        self.assertEqual(report["details"][0]["diagnostics"]["llm_calls"][0]["prompt_tokens"], 3)

    def test_report_failure_stops_before_system_initialization(self):
        module = self.entry()
        path = self.root / "out.json"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": TEST_KEY}), \
                patch.dict(sys.modules, {"runbook_system": types.SimpleNamespace(RunbookQuerySystem=unittest.mock.Mock())}), \
                patch.object(module.http.client, "HTTPConnection") as connection, \
                patch.object(module, "_git", return_value="fixture"), \
                patch.object(module, "_write_report", side_effect=OSError()), \
                contextlib.redirect_stderr(io.StringIO()):
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"ci_name":"VM_NOVA","columns":["id"],"row_count":1}'
            code = module.main(["1", "--report", str(path)])
            sys.modules["runbook_system"].RunbookQuerySystem.assert_not_called()
        self.assertEqual(code, 1)

    def test_existing_report_is_not_overwritten(self):
        path = self.root / "out.json"
        path.write_text("existing result", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.entry().main(["1", "--report", str(path)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(path.read_text(encoding="utf-8"), "existing result")

    def test_csv_is_excel_readable_and_escapes_formula_text(self):
        self.cases[0]["question"] = "=1+1"
        self.write_cases()
        _, _, path, _, _ = self.run_entry([None])
        failure_path = path.with_name(path.stem + "-failures.csv")
        self.assertTrue(failure_path.read_bytes().startswith(b'\xef\xbb\xbf'))
        with failure_path.open(encoding="utf-8-sig", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["question"], "'=1+1")

    def test_entry_logic_matches_except_dataset_constants(self):
        white = (REPO / "C/implementation/quick_eval.py").read_text(encoding="utf-8")
        black = (REPO / "C/implementation/blackbox_eval.py").read_text(encoding="utf-8")
        self.assertEqual(black, white.replace('_LABEL = "白盒"', '_LABEL = "黑盒"')
            .replace('_DATASET = "white"', '_DATASET = "black"')
            .replace('_DEFAULT_N = 20', '_DEFAULT_N = 100')
            .replace('_CASE_FILE = "CMDB用例集-白盒200.json"', '_CASE_FILE = "CMDB用例集-黑盒100.json"'))


if __name__ == "__main__":
    unittest.main()
