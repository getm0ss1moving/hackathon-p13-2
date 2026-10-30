"""全量记录入口的无模型回归；控制评估入口，验证完整/中止记录不混淆。"""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "implementation"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_whitebox
import evaluator
import quick_eval
import runbook_matcher as matcher
from test_llm_runtime import completion


class FullRunnerTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"RUNBOOK_RULE_ONLY_FILL": "0", "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "0",
                                              "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0", "RUNBOOK_BOUNDED_API": "0",
                                              "RUNBOOK_PRESERVE_ROW_SEMANTICS": "0", "RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": "0"})
        environment.start()
        self.addCleanup(environment.stop)

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

    def test_explicit_feature_flags_and_frozen_plan_preflight(self):
        args = ["--limit", "200", "--preserve-template-columns", "--rule-only-fill", "--no-validate-api-dependencies",
                "--preserve-row-semantics", "--resource-attribute-roles", "--no-bounded-api"]
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")):
            self.assertEqual(run_whitebox.main(args), 0)
        plan = json.loads(captured.getvalue().splitlines()[0])
        self.assertEqual(plan["feature_flags"], {"RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1", "RUNBOOK_RULE_ONLY_FILL": "1",
                                                 "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0", "RUNBOOK_BOUNDED_API": "0",
                                                 "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1", "RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": "1"})
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "plan.json"
            expected.write_text(json.dumps(plan))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_whitebox.main([*args, "--expected-plan", str(expected)]), 0)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_whitebox.main([*args, "--no-rule-only-fill", "--expected-plan", str(expected)])

    def test_new_records_preserve_full_question_instead_of_scorer_prefix(self):
        case = copy.deepcopy(json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"][0])
        case["question"] += "完整查询条件" * 20
        def fake_entry(argv):
            evaluator.evaluate_case(case, {"matched_runbook": "fixture", "api_call": case["api_call"],
                                          "sql": case["sql"], "result": case["answer"], "error": None}, 0)
            return 0
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "full_question.jsonl"
            with patch.object(quick_eval, "main", side_effect=fake_entry), patch.object(matcher, "_llm_client", None), \
                 patch.object(matcher, "_llm_events", []), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_whitebox.main(["--run", "--limit", "1", "--output", str(output)]), 0)
            record = next(json.loads(line) for line in output.read_text().splitlines() if json.loads(line)["type"] == "case")
            self.assertEqual(record["question"], case["question"])
            self.assertGreater(len(record["question"]), 60)

    def test_runtime_flag_or_source_drift_stops_without_model_requests(self):
        case = json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"][0]
        for kind in ["flag", "source"]:
            changed = [False]
            native_sha = run_whitebox.file_sha
            def digest(path):
                return "0" * 64 if changed[0] and kind == "source" and path.name == "runbook_matcher.py" else native_sha(path)
            def fake_entry(argv):
                changed[0] = True
                if kind == "flag": os.environ["RUNBOOK_RULE_ONLY_FILL"] = "0"
                evaluator.evaluate_case(case, {"matched_runbook": "fixture", "result": case["answer"]}, 0)
                return 0
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "drift.jsonl"
                with patch.object(quick_eval, "main", side_effect=fake_entry), patch.object(run_whitebox, "file_sha", side_effect=digest), \
                     patch.object(matcher, "_llm_client", None), patch.object(matcher, "_llm_events", []), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(run_whitebox.main(["--run", "--limit", "1", "--rule-only-fill", "--output", str(output)]), 1)
                summary = json.loads(output.read_text().splitlines()[-1])
                self.assertEqual(summary["status"], "incomplete")
                self.assertEqual(summary["generation_requests"], 0)


@unittest.skipUnless(os.environ.get("RUNBOOK_TEST_LOCAL_API") == "1", "需启动本地数据服务")
class FullRunnerModelIdentityTests(unittest.TestCase):
    def test_returned_model_is_recorded_and_mismatch_stops_after_one_mock_request(self):
        case = json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"][0]
        for returned_model, expected_exit, requests_expected in [("deepseek-chat", 0, 2), ("unexpected-model", 1, 1)]:
            requests = []
            answers = iter(["1", case["sql"]])
            def handler(request):
                requests.append(request)
                body = completion(next(answers))
                body["model"] = returned_model
                return httpx.Response(200, json=body)
            with self.subTest(returned_model=returned_model), tempfile.TemporaryDirectory() as tmp, \
                 OpenAI(api_key="local-test-only", base_url="https://local-test.invalid/v1", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
                output = Path(tmp) / "identity.jsonl"
                with patch.object(matcher, "_llm_client", client), patch.object(matcher, "_llm_events", []), \
                     patch.object(matcher, "DEEPSEEK_MODEL", "deepseek-chat"), patch.dict(os.environ, {}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    status = run_whitebox.main(["--run", "--limit", "1", "--max-requests", "2", "--rule-only-fill",
                                               "--preserve-template-columns", "--no-validate-api-dependencies", "--output", str(output)])
                self.assertEqual(status, expected_exit)
                records = [json.loads(line) for line in output.read_text().splitlines()]
                events = [row for row in records if row["type"] == "request"]
                self.assertEqual(len(requests), requests_expected)
                self.assertEqual(len(events), requests_expected)
                self.assertEqual({row["response_model"] for row in events}, {returned_model})
                self.assertEqual(bool(records[-1]["model_identity_mismatches"]), expected_exit != 0)
