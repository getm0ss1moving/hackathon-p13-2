"""全部规则参数明确才省略 fill；真实模型均由 mock 或内存 transport 替代。"""

import copy
from contextlib import redirect_stdout
import io
import json
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import OpenAI

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
from C import quick_eval_diagnostics as quick_eval
import runbook_matcher as matcher
import runbook_system as system_module
from test_llm_runtime import completion
from test_params import template


class RuleFillTests(unittest.TestCase):
    def setUp(self):
        self.retriever = Mock()
        self.retriever.retrieve.return_value = [SimpleNamespace(id="fixture", tier="strong")]
        for target, value in [
            ("_schema_columns", {"VM_NOVA": ["name", "logicalRegionName", "status", "management", "port", "nativeId"]}),
            ("_schema_values", {"VM_NOVA": {"status": ["active"], "management": [False]}}),
        ]:
            context = patch.object(matcher, target, value)
            context.start()
            self.addCleanup(context.stop)

    def match(self, item, question, parameters, enabled):
        original = copy.deepcopy(item)
        answers = {"select": "1", "fill": json.dumps(parameters), "refine": item["sql"]}
        details = {}
        with patch.dict(os.environ, {"RUNBOOK_RULE_ONLY_FILL": str(enabled), "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0",
                                     "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "0"}), \
             patch.object(matcher, "_get_table_schemas", return_value="schema fixture"), \
             patch.object(matcher, "llm_ask", side_effect=lambda prompt, stage: answers[stage]) as model:
            result = matcher.match_runbook(question, [item], self.retriever, details)
        self.assertEqual(item, original)
        return result, details, [call.kwargs["stage"] for call in model.call_args_list]

    def test_complete_rules_skip_only_fill_and_preserve_api_sql_and_sources(self):
        item = template("logicalRegionName", "status")
        question = "查询区域region_lab9下运行中ECS的名称"
        old, old_details, old_stages = self.match(item, question, {"logicalRegionName": "wrong", "status": "wrong"}, 0)
        new, details, stages = self.match(item, question, {}, 1)
        self.assertIsNotNone(new)
        self.assertEqual(old, new)
        self.assertEqual(old_details["parameter_sources"], details["parameter_sources"])
        self.assertEqual(old_stages, ["select", "fill", "refine"])
        self.assertEqual(stages, ["select", "refine"])
        self.assertEqual(details["parameter_mode"], "rules_complete")
        self.assertEqual(details["rule_missing_parameters"], [])

    def test_incomplete_rule_values_still_use_model_and_keep_question_grounding(self):
        item = template("nativeId")
        question = '查询ECS“opaque-z9”的原生标识和名称'
        old, _, _ = self.match(item, question, {"nativeId": "opaque-z9"}, 0)
        new, details, stages = self.match(item, question, {"nativeId": "opaque-z9"}, 1)
        self.assertEqual(old, new)
        self.assertIsNotNone(new)
        self.assertEqual(details["parameter_mode"], "llm")
        self.assertEqual(details["rule_missing_parameters"], ["nativeId"])
        self.assertEqual(stages, ["select", "fill", "refine"])

    def test_optional_condition_is_not_silently_dropped_to_skip_model(self):
        item = template("logicalRegionName", "status")
        item["optional_params"] = ["status"]
        question = "查询区域region_lab9下 ACTIVE 状态的ECS名称"
        old, _, _ = self.match(item, question, {"status": "active"}, 0)
        new, details, stages = self.match(item, question, {"status": "active"}, 1)
        self.assertEqual(old, new)
        self.assertIsNotNone(new)
        self.assertEqual(len(new["api_call"]["condition"]["constraint"]), 2)
        self.assertIn("status", details["rule_missing_parameters"])
        self.assertEqual(stages, ["select", "fill", "refine"])

    def test_ambiguous_entities_or_enum_values_fall_back_to_model(self):
        for parameter, question in [("logicalRegionName", "查询区域region_one或region_two下的ECS名称"),
                                    ("status", "查询运行中和异常ECS的名称")]:
            with self.subTest(parameter=parameter):
                result, details, stages = self.match(template(parameter), question, {}, 1)
                self.assertIsNone(result)
                self.assertEqual(details["parameter_mode"], "llm")
                self.assertEqual(details["rule_missing_parameters"], [parameter])
                self.assertEqual(stages, ["select", "fill"])

    def test_false_and_zero_are_complete_values(self):
        result, details, stages = self.match(template("management"), "查询租户虚拟机的名称", {}, 1)
        self.assertIsNotNone(result)
        value = result["api_call"]["condition"]["constraint"][0]["simple"]["value"]
        self.assertIs(value, False)
        self.assertEqual(stages, ["select", "refine"])
        self.assertEqual(details["parameter_mode"], "rules_complete")

        def explicit_zero(question, values, parameters, item):
            if "port" in parameters:
                values["port"] = 0
        with patch.object(matcher, "_auto_fill_params", side_effect=explicit_zero):
            result, details, stages = self.match(template("port"), "查询ECS参数值0的名称", {}, 1)
        self.assertIsNotNone(result)
        self.assertIs(type(result["api_call"]["condition"]["constraint"][0]["simple"]["value"]), int)
        self.assertEqual(stages, ["select", "refine"])

    def test_unproven_rule_and_sample_default_do_not_enable_shortcut(self):
        item = template("tenantName")
        item["default_params"] = {"tenantName": "sample-tenant"}
        result, details, stages = self.match(item, "查询指定租户的ECS名称", {"tenantName": "sample-tenant"}, 1)
        self.assertIsNone(result)
        self.assertEqual(details["rule_missing_parameters"], ["tenantName"])
        self.assertEqual(stages, ["select", "fill"])

    def test_dependency_placeholders_are_preserved_and_no_parameters_still_refine(self):
        item = template("logicalRegionName")
        item["api_call"] = [item["api_call"], {"url": "/rest/hackthon/db/instances/FLAVOR",
            "condition": {"constraint": [{"simple": {"name": "id", "operator": "in", "value": "{{flavorId from step 1}}"}}]}}]
        result, details, stages = self.match(item, "查询区域region_lab9下ECS的名称", {}, 1)
        self.assertIsNotNone(result)
        self.assertEqual(result["api_call"][1]["condition"]["constraint"][0]["simple"]["value"], "{{flavorId from step 1}}")
        self.assertEqual(stages, ["select", "refine"])
        result, details, stages = self.match(template(), "查询ECS名称", {}, 1)
        self.assertIsNotNone(result)
        self.assertEqual(details["parameter_mode"], "none")
        self.assertEqual(stages, ["select", "refine"])


@unittest.skipUnless(os.environ.get("RUNBOOK_TEST_LOCAL_API") == "1", "需启动本地数据服务")
class LocalRuleFillTests(unittest.TestCase):
    def test_original_three_case_entry_preserves_score_with_six_mock_requests(self):
        matcher._warm_schema_cache()
        cases = json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"][:3]
        retriever = system_module.RunbookRetriever(system_module.RUNBOOK_ITEMS)
        answers = []
        for case in cases:
            item = next(item for item in system_module.RUNBOOK_ITEMS if case["question"] in item.get("examples", []))
            candidates = retriever.retrieve(case["question"])
            index = next(i + 1 for i, candidate in enumerate(candidates) if candidate.id == item["id"])
            placeholders = matcher._get_placeholders(item)
            rules = {}
            matcher._auto_fill_params(case["question"], rules, placeholders, item)
            rules = matcher._ground_params(case["question"], rules, item)
            self.assertTrue(all(p in rules for p in placeholders))
            answers.extend([str(index), case["sql"]])
        responses = iter(answers)
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=completion(next(responses)))

        captured = io.StringIO()
        old_logging = logging.root.manager.disable
        try:
            with OpenAI(api_key="local-test-only", base_url="https://local-test.invalid/v1", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client, \
                 patch.object(matcher, "_llm_client", client), patch.object(matcher, "_llm_events", []), \
                 patch.dict(os.environ, {"DEEPSEEK_API_KEY": "local-test-only", "RUNBOOK_MAX_LLM_CALLS": "6",
                                         "RUNBOOK_RULE_ONLY_FILL": "1", "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0",
                                         "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "0"}), redirect_stdout(captured):
                status = quick_eval.main(["3"])
                stages = [event["stage"] for event in matcher.get_llm_events()]
        finally:
            logging.disable(old_logging)
        self.assertEqual(status, 0)
        self.assertIn("score=15/15", captured.getvalue())
        self.assertEqual(len(requests), 6)
        self.assertEqual(stages, ["select", "refine"] * 3)


if __name__ == "__main__":
    unittest.main()
