"""固定资源诊断入口的预算与证据回归；全部模型和查询响应均为测试夹具。"""

import contextlib
import copy
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "implementation"))
from experiments import run_resource_20261029 as runner
import runbook_matcher as matcher
import runbook_system as system_module


class ResourceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.scope = json.loads((HERE / "experiments/resource_gate_20261029_plan.json").read_text())
        # 仅在 mock 入口测试中冻结工作区字节，不要求为了跑测试先 commit。
        # 真实入口、历史计划及其他 Git 引用仍走真实的源码漂移检查。
        self.scope["candidate_commit"] = "unittest-frozen-working-tree"
        frozen = {path.name: path.read_bytes() for path in (HERE / "implementation").glob("*.py")}
        native_git = runner.subprocess.check_output

        def fixture_git(command, *args, **kwargs):
            prefix = "unittest-frozen-working-tree:B/implementation/"
            if len(command) == 3 and command[:2] == ["git", "show"] and command[2].startswith(prefix):
                return frozen[command[2][len(prefix):]]
            return native_git(command, *args, **kwargs)

        git_fixture = patch.object(runner.subprocess, "check_output", side_effect=fixture_git)
        git_fixture.start()
        self.addCleanup(git_fixture.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.plan_file = Path(temp.name) / "fixture_plan.json"
        self.plan_file.write_text(json.dumps(self.scope))
        self.original_read = Path.read_text

    def args(self, *values):
        return ["--plan", str(self.plan_file), *values]

    def safe_read(self, path, *args, **kwargs):
        if path == HERE / ".env.local":
            return "DEEPSEEK_API_KEY=local-test-only\nDEEPSEEK_MODEL=deepseek-flash\nDEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        return self.original_read(path, *args, **kwargs)

    def test_selector_refusal_does_not_prove_empty_lookup_guard(self):
        answer = {"matched_runbook": None, "diagnostics": {"matching": {"reason": "selector_refused"}}}
        observed = runner.diagnostic_outcome("DEV-NONEXISTENT-HOST", answer, 0, self.scope)
        self.assertTrue(observed["match_expectation_observed"])
        self.assertFalse(observed["expected_path_exercised"])
        self.assertFalse(observed["diagnostic_passed"])
        answer["diagnostics"]["matching"] = {"reason": "invalid_resource_lookup", "resource_lookup": {"valid": False}}
        self.assertTrue(runner.diagnostic_outcome("DEV-NONEXISTENT-HOST", answer, 0, self.scope)["diagnostic_passed"])

    def test_exercised_lookup_with_wrong_answer_is_not_passed(self):
        answer = {"matched_runbook": "fixture", "diagnostics": {"matching": {
            "reason": "matched", "resource_lookup": {"valid": True}}}}
        observed = runner.diagnostic_outcome("CMDB-036", answer, -1, self.scope)
        self.assertTrue(observed["expected_path_exercised"])
        self.assertFalse(observed["diagnostic_passed"])

    def test_invalid_budgets_and_mixed_experiment_are_rejected(self):
        for field, value in [("max_requests", 0), ("max_requests", 25), ("max_output_tokens", 1025),
                             ("sdk_max_retries", 1), ("RUNBOOK_PRESERVE_TEMPLATE_COLUMNS", "1")]:
            scope = copy.deepcopy(self.scope)
            scope[field] = value

            def read(path, *args, **kwargs):
                if path == self.plan_file:
                    return json.dumps(scope)
                return self.safe_read(path, *args, **kwargs)

            with self.subTest(field=field, value=value), patch.object(Path, "read_text", read), \
                 patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")) as llm, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): runner.main(self.args())
                llm.assert_not_called()

    def test_source_drift_stops_before_model_call(self):
        scope = copy.deepcopy(self.scope)
        scope["candidate_commit"] = "3b99aaf"
        self.plan_file.write_text(json.dumps(scope))
        with patch.object(Path, "read_text", lambda path, *a, **k: self.safe_read(path, *a, **k)), \
             patch.dict(os.environ, {}), patch.object(matcher, "_llm_events", []), \
             patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")) as llm, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): runner.main(self.args())
            llm.assert_not_called()

    def test_preflight_has_no_model_requests_and_fixes_runtime_bounds(self):
        captured = io.StringIO()
        with patch.object(Path, "read_text", lambda path, *a, **k: self.safe_read(path, *a, **k)), patch.dict(os.environ, {}), \
             patch.object(matcher, "_llm_events", []), \
             patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")) as llm, \
             contextlib.redirect_stdout(captured):
            self.assertEqual(runner.main(self.args()), 0)
            self.assertEqual(os.environ["RUNBOOK_MAX_LLM_CALLS"], "24")
            self.assertEqual(os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"], "1024")
            self.assertEqual(os.environ["RUNBOOK_PRESERVE_TEMPLATE_COLUMNS"], "0")
            llm.assert_not_called()
        self.assertIn("预检完成，未调用模型", captured.getvalue())

    def test_working_tree_drift_from_frozen_fixture_still_stops_before_model(self):
        original_sha = runner.sha

        def drift(path):
            return "0" * 64 if path == HERE / "implementation/runbook_matcher.py" else original_sha(path)

        with patch.object(runner, "sha", side_effect=drift), \
             patch.object(Path, "read_text", lambda path, *a, **k: self.safe_read(path, *a, **k)), \
             patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")) as llm, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): runner.main(self.args())
            llm.assert_not_called()

    def run_fake_system(self, output, factory):
        captured = io.StringIO()
        previous_logging = logging.root.manager.disable
        with patch.object(Path, "read_text", lambda path, *a, **k: self.safe_read(path, *a, **k)), patch.dict(os.environ, {}), \
             patch.object(matcher, "_llm_events", []), patch.object(matcher, "_llm_client", None), \
             patch.object(matcher, "llm_ask", side_effect=AssertionError("不得调用模型")) as llm, \
             patch.object(system_module, "RunbookQuerySystem", factory), contextlib.redirect_stdout(captured):
            status = runner.main(self.args("--run", "--output", str(output)))
            llm.assert_not_called()
        self.assertEqual(logging.root.manager.disable, previous_logging)
        return status, [json.loads(line) for line in output.read_text().splitlines()]

    def test_official_and_derived_cases_stay_separate_and_output_is_not_overwritten(self):
        official = json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"]
        cases = {c["question"]: c for c in [*official, *self.scope["derived_cases"]]}

        def query(question):
            case = cases[question]
            case_id = case["case_id"]
            if self.scope["expected_match"][case_id]:
                matching = {"reason": "matched"}
                if case_id in {"CMDB-036", "DEV-HOST-REPLACED"}: matching["resource_lookup"] = {"valid": True}
                return {"matched_runbook": "fixture", "api_call": case["api_call"], "sql": case["sql"],
                        "result": case["answer"], "error": None, "diagnostics": {"matching": matching}}
            matching = {"reason": "resource_mismatch"}
            if case_id == "DEV-NONEXISTENT-HOST":
                matching = {"reason": "invalid_resource_lookup", "resource_lookup": {"valid": False}}
            return {"matched_runbook": None, "result": None, "error": "未命中", "diagnostics": {"matching": matching}}

        fake = Mock(initialization_metrics={"template_count": 200}, query=Mock(side_effect=query))
        factory = Mock(return_value=fake)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "fake.jsonl"
            status, rows = self.run_fake_system(output, factory)
            self.assertEqual(status, 0)
            summary = rows[-1]
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["official_cases"], 6)
            self.assertEqual(summary["official_score"], 15)
            self.assertEqual(summary["diagnostics_passed"], 8)
            self.assertEqual(summary["generation_requests"], 0)
            self.assertEqual(summary["previous_600_request_budget_used"], 594)
            self.assertEqual(summary["combined_requests_for_previous_budget_and_this_check"], 594)
            derived = [r for r in rows if r.get("group") == "derived_diagnostic"]
            self.assertEqual(len(derived), 2)
            self.assertEqual(sum(r["score"] for r in derived), 5)
            factory.reset_mock()
            with self.assertRaises(FileExistsError): self.run_fake_system(output, factory)
            factory.assert_not_called()

    def test_interruption_is_incomplete(self):
        fake = Mock(initialization_metrics={"template_count": 200}, query=Mock(side_effect=TimeoutError("fixture")))
        with tempfile.TemporaryDirectory() as tmp:
            status, rows = self.run_fake_system(Path(tmp) / "incomplete.jsonl", Mock(return_value=fake))
        self.assertEqual(status, 1)
        self.assertEqual(rows[-1]["status"], "incomplete")
        self.assertEqual(rows[-1]["completed_cases"], 0)
        self.assertEqual(rows[-1]["diagnostics_passed"], 0)
        self.assertTrue(any(r.get("error_type") == "TimeoutError" for r in rows))


if __name__ == "__main__":
    unittest.main()
