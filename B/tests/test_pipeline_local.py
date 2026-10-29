"""本地流水线联调：真实数据 API/执行器/评分器，模型响应由内存 transport 模拟。"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import OpenAI

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
import runbook_system as system_module
from evaluator import evaluate_case
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


if __name__ == "__main__":
    unittest.main()
