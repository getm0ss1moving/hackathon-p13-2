"""180接入的合成合同与真实SDK内存传输检查；不读取题目或访问网络。"""
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))
sys.path.insert(0, str(ROOT / "scripts"))
import runbook_matcher as m
import runbook_system as system_module
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import RunbookRetriever, Candidate
import train_live

FAMILIES = {item["family_id"]: item for item in json.loads(
    (ROOT / "experiments/a_family_candidate_20261030/family_candidates.json").read_text())}


def params(**axes):
    return {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"},
            "required_filters": ["logicalRegionName"], **axes}


class A180Tests(unittest.TestCase):
    def setUp(self):
        for target in [(httpx.Client, "send"), (m._schema_session, "get")]:
            context = patch.object(*target, side_effect=AssertionError("免费测试禁止网络"))
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(m, "_get_table_schemas", return_value="")
        context.start()
        self.addCleanup(context.stop)

    def match(self, family, question, parameters, refine=None):
        item = FAMILIES[family]
        retriever = SimpleNamespace(retrieve=lambda *a, **k: [Candidate(id=item["id"], score=1, tier="strong", coverage=1)])
        diagnostics = {}
        with patch.object(m, "llm_ask", side_effect=["1", json.dumps(parameters)]), \
                patch.object(m, "_refine_sql", side_effect=lambda q, sql, *a, **k: refine or sql):
            result = m.match_runbook(question, list(FAMILIES.values()), retriever, diagnostics)
        return result, diagnostics

    def test_runtime_count_and_imports(self):
        if not any(item.get("family_id") for item in RUNBOOK_ITEMS):
            self.skipTest("仅在已展开的私有180验证快照检查活动数量")
        self.assertEqual(len(RUNBOOK_ITEMS), 180)
        self.assertEqual(len({item["id"] for item in RUNBOOK_ITEMS}), 180)
        self.assertEqual(set(FAMILIES), {"F01", "F08", "F14", "F18", "F20", "F21"})
        self.assertEqual(RunbookRetriever(RUNBOOK_ITEMS)._doc_count, 400)
        modules = {name: sys.modules[name] for name in ("runbook_matcher", "runbook_system", "runbook_items")}
        self.assertEqual(len(train_live.runtime_source_paths(modules)), 3)
        with self.assertRaises(ValueError):
            train_live.runtime_source_paths({"runbook_items": SimpleNamespace(__file__="/tmp/old/runbook_items.py")})

    def test_six_families_materialize_ordinary_queries(self):
        rows = [
            ("F01", "region_demo下ECS按状态统计数量", params(group="status", metrics="count"), "GROUP BY status"),
            ("F08", "region_demo下宿主机按虚拟化类型统计数量", params(group="hypervisorType"), "GROUP BY hypervisorType"),
            ("F14", "region_demo下各VDC云硬盘数量与总容量", params(metrics="count_sum"), "SUM(size) AS total_size"),
            ("F18", "region_demo下GaussDB按引擎版本统计数量", params(group="engineVersion", metrics="count"), "GROUP BY engineVersion"),
            ("F20", "region_demo下非共享网络的数量", params(view="count", count_alias="total",
                filters={"logicalRegionName": "region_demo", "shared": False}, required_filters=["logicalRegionName", "shared"]), "COUNT(*) AS total"),
            ("F21", "region_demo下弹性IP按租户和状态统计数量", params(group="tenantName_status"), "GROUP BY tenantName, status"),
        ]
        for family, question, parameters, fragment in rows:
            with self.subTest(family=family):
                result, details = self.match(family, question, parameters)
                self.assertIsNotNone(result, details)
                self.assertNotIn("family_id", result)
                self.assertIsInstance(result["api_call"], dict)
                self.assertIn(fragment, result["sql"])
                self.assertEqual(details["parameters"]["llm_extracted"], parameters)

    def test_rejects_dropped_wrong_role_or_unsupported_conditions(self):
        p = params(group="status", metrics="count")
        rows = [
            ("region_demo下租户tenant_demo的ECS按状态统计数量", p),
            ("区域alpha的ECS按状态统计数量", params(group="status", metrics="count", filters={"tenantName":"alpha"}, required_filters=["tenantName"])),
            ("region_demo或region_other下ECS按状态统计数量", p),
            ("排除region_demo的ECS按状态统计数量", p),
            ("region_demo下ECS按状态和租户统计数量", p),
            ("region_demo下ECS与云硬盘的数量", params(group="none", metrics="count", count_alias="total")),
            ("region_demo下ECS、云硬盘和VPC的数量", params(group="none", metrics="count", count_alias="total")),
            ("region_demo下ECS、云硬盘、VPC和子网的数量", params(group="none", metrics="count", count_alias="total")),
            ("region_demo下ECS按状态统计数量和CPU总核数", p),
            ("region_demo下ECS按状态统计数量", params(group="status", metrics="count", required_filters=[])),
            ("ECS按状态统计数量", {"scope":"global", "filters":{}, "required_filters":[], "group":"status", "metrics":"count"}),
        ]
        for question, parameters in rows:
            with self.subTest(question=question):
                result, details = self.match("F01", question, parameters)
                self.assertIsNone(result, details)
                self.assertIn("rejection", details)

    def test_boolean_false_preserved_and_numeric_bool_rejected(self):
        p = params(view="count", count_alias="count", filters={"shared":False}, required_filters=["shared"])
        result, details = self.match("F20", "统计非共享网络数量", p)
        self.assertIsNotNone(result, details)
        self.assertIs(result["api_call"]["condition"]["constraint"][0]["simple"]["value"], False)
        for value in [0, "false", None, True]:
            with self.subTest(value=value):
                invalid = copy.deepcopy(p)
                invalid["filters"]["shared"] = value
                self.assertIsNone(self.match("F20", "统计非共享网络数量", invalid)[0])

    def test_boolean_wire_values_follow_native_schema_without_changing_semantics(self):
        for samples, expected in [(["true", "false"], "false"), (["TRUE", "FALSE"], "FALSE"), ([True, False], False)]:
            with self.subTest(samples=samples), patch.object(m, "_schema_values", {"NETWORK":{"shared":samples}}):
                p = params(view="rows", filters={"shared":False}, required_filters=["shared"])
                result = m._materialize_family(FAMILIES["F20"], p)
                actual = result["api_call"]["condition"]["constraint"][0]["simple"]["value"]
                self.assertEqual(actual, expected)
                self.assertIs(type(actual), type(expected))
                self.assertIs(p["filters"]["shared"], False)

    def test_entity_and_role_perturbations(self):
        for region,tenant in [("area-q9","org-z8"),("区域甲","租户乙"),("0","CPU")]:
            p = params(group="none", metrics="count", count_alias="total",
                filters={"logicalRegionName":region,"tenantName":tenant},required_filters=["logicalRegionName","tenantName"])
            question = '区域"'+region+'"中租户"'+tenant+'"的ECS有多少台'
            result, details = self.match("F01", question, p)
            self.assertIsNotNone(result, details)
            swapped = copy.deepcopy(p)
            swapped["filters"] = {"logicalRegionName":tenant,"tenantName":region}
            self.assertIsNone(self.match("F01", question, swapped)[0])

    def test_refinement_cannot_change_family_contract(self):
        result, details = self.match("F01", "region_demo下ECS按状态统计数量", params(group="status", metrics="count"),
                                     "SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA")
        self.assertIn("GROUP BY status", result["sql"])
        self.assertFalse(details["family_refinement_kept"])
        self.assertEqual(details["sql_after_refine"], result["sql"])

    def test_total_active_distinguishes_resource_count_from_status_bucket(self):
        p = params(group="vdcName", metrics="total_active")
        result, details = self.match("F01", "region_demo下各VDC的ECS数量和运行中ECS数量", p)
        self.assertIsNotNone(result, details)
        self.assertIn("active_count", result["sql"])
        for question in ["region_demo下各VDC的ECS数量和运行中ECS数量以及paused数量",
                         "region_demo下各VDC的ECS数量"]:
            self.assertIsNone(self.match("F01", question, p)[0])

    def test_unsupported_returns_null_without_execution(self):
        instance = system_module.RunbookQuerySystem.__new__(system_module.RunbookQuerySystem)
        item = FAMILIES["F01"]
        instance.items = RUNBOOK_ITEMS
        instance.retriever = SimpleNamespace(retrieve=lambda *a, **k: [Candidate(id=item["id"], score=1, tier="strong", coverage=1)])
        with patch.object(m, "llm_ask", side_effect=["1", "{}"]), \
                patch.object(system_module, "execute", side_effect=AssertionError("未支持不能执行")):
            output = instance.query("region_demo下ECS和云硬盘数量")
        self.assertIsNone(output["matched_runbook"])
        self.assertIsNone(output["result"])
        self.assertIsNone(output["error"])


class A180SDKTraceTests(unittest.TestCase):
    def test_actual_response_usage_and_truncation_are_recorded(self):
        for finish in ["stop", "length"]:
            raw = ' {"scope":"global"} '
            payload = {"id":"synthetic", "object":"chat.completion", "created":0, "model":"deepseek-flash",
                       "choices":[{"index":0, "finish_reason":finish, "message":{"role":"assistant", "content":raw}}],
                       "usage":{"prompt_tokens":11, "completion_tokens":5, "total_tokens":16}}
            requests = []
            def handler(request):
                requests.append(json.loads(request.content))
                return httpx.Response(200, json=payload)
            with OpenAI(api_key="synthetic", base_url="https://synthetic.invalid", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client, \
                    patch.object(m, "_llm_client", client), patch.object(m, "_llm_events", []), \
                    patch.dict(os.environ, {"RUNBOOK_MAX_LLM_CALLS":"1", "RUNBOOK_MAX_OUTPUT_TOKENS":"1024", "RUNBOOK_THINKING_MODE":"disabled"}):
                if finish == "length":
                    with self.assertRaises(m.ModelOutputError):
                        m.llm_ask("synthetic prompt", "family_fill")
                else:
                    self.assertEqual(m.llm_ask("synthetic prompt", "family_fill"), raw.strip())
                event = m.get_llm_events()[0]
                self.assertEqual(event["response_text"], raw)
                self.assertEqual((event["prompt_tokens"], event["completion_tokens"]), (11, 5))
                self.assertEqual(event["status"], "ok" if finish == "stop" else "error")
                with self.assertRaises(RuntimeError):
                    m.llm_ask("not sent", "family_fill")
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]["max_tokens"], 1024)


if __name__ == "__main__":
    unittest.main()
