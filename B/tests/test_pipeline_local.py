"""本地流水线联调：真实数据 API/执行器/评分器，模型响应由内存 transport 模拟。"""

import json
import io
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

import httpx
from openai import OpenAI

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
import runbook_system as system_module
from evaluator import evaluate_case
import quick_eval
from test_llm_runtime import completion


@unittest.skipUnless(os.environ.get("RUNBOOK_TEST_LOCAL_API") == "1", "需先启动本地数据服务")
class LocalPipelineTests(unittest.TestCase):
    def test_select_fill_refine_execute_and_score(self):
        template = {
            "id": "local-smoke", "name": "区域内虚拟机状态统计",
            "description": "按区域查询ECS实例的状态分布", "resources": ["VM_NOVA"],
            "examples": ["查询区域下所有ECS实例按状态的分布情况"],
            "api_call": {"method": "GET",
                         "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
                         "condition": {"constraint": [{"simple": {
                             "name": "logicalRegionName", "value": "{{logicalRegionName}}", "operator": "equal"}}]}},
            "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY status",
        }
        # 测试夹具中的参考实体只用于本地联调，不进入查询实现或模板库。
        cases = json.loads((HERE / "CMDB用例集-白盒200.json").read_text(encoding="utf-8"))["cases"]
        case = next(c for c in cases if c["case_id"] == "CMDB-004")
        region = case["api_call"]["condition"]["constraint"][0]["simple"]["value"]
        responses = iter(["1", f"logicalRegionName={region}", template["sql"]])
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=completion(next(responses)))

        with OpenAI(api_key="local-test-only", base_url="https://local-test.invalid/v1", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
            with patch.object(system_module, "RUNBOOK_ITEMS", [template]), \
                 patch.object(matcher, "_llm_client", client), \
                 patch.object(matcher, "_llm_events", []), \
                 patch.dict(os.environ, {"RUNBOOK_MAX_LLM_CALLS": "3"}):
                output = system_module.RunbookQuerySystem().query(case["question"])
        self.assertIsNone(output["error"])
        self.assertEqual(evaluate_case(case, output, 0)["score"], 5)
        self.assertEqual(len(calls), 3)
        self.assertEqual([e["stage"] for e in output["diagnostics"]["llm_calls"]], ["select", "fill", "refine"])
        self.assertIn("{{logicalRegionName}}", json.dumps(template))

    def test_original_quick_eval_entry_with_mock_model_three_cases(self):
        cases = json.loads((HERE / "CMDB用例集-白盒200.json").read_text(encoding="utf-8"))["cases"][:3]
        responses = []
        retriever = system_module.RunbookRetriever(system_module.RUNBOOK_ITEMS)
        for case in cases:
            # 选择结果是测试夹具，不能用于报告模型准确率。
            target = next(item for item in system_module.RUNBOOK_ITEMS if item["sql"] == case["sql"]
                          and bool(item["api_call"].get("condition")) == bool(case["api_call"].get("condition")))
            candidates = retriever.retrieve(case["question"])
            index = next(i + 1 for i, candidate in enumerate(candidates) if candidate.id == target["id"])
            responses.append(str(index))
            if matcher._get_placeholders(target):
                values = {c["simple"]["name"]: c["simple"]["value"]
                          for c in case["api_call"]["condition"]["constraint"]}
                responses.append(json.dumps(values))
            responses.append(case["sql"])
        answers = iter(responses)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=completion(next(answers)))

        captured = io.StringIO()
        old_logging = logging.root.manager.disable
        try:
            with OpenAI(api_key="local-test-only", base_url="https://local-test.invalid/v1", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
                with patch.object(matcher, "_llm_client", client), \
                     patch.object(matcher, "_llm_events", []), \
                     patch.dict(os.environ, {"RUNBOOK_MAX_LLM_CALLS": "9", "DEEPSEEK_API_KEY": "local-test-only"}), \
                     redirect_stdout(captured):
                    status = quick_eval.main(["3"])
        finally:
            logging.disable(old_logging)
        self.assertEqual(status, 0)
        self.assertIn("score=15/15", captured.getvalue())
        self.assertEqual(len(calls), 8)


if __name__ == "__main__":
    unittest.main()
