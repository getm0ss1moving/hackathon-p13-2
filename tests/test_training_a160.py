"""160接入的合成合同控制；不加载训练答案，不调用模型或真实网络。"""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runbook_matcher as matcher
import runbook_system as system
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import Candidate
from a160_fixtures import family_item


REGION = {"logicalRegionName": "region_alpha"}
FIXTURES = [
    ("F10", "区域region_alpha下vCPU分配率最高的前7台宿主机",
     {"metric": "vcpu_allocation_rate", "direction": "desc", "top_k": 7,
      "filters": REGION, "required_filters": ["logicalRegionName"]}),
    ("F17_SAFE", "区域region_alpha下各可用区的存储池容量使用情况",
     {"view": "az_usage", "filters": REGION, "required_filters": ["logicalRegionName"]}),
    ("F11_CORE", "型号model_alpha的物理服务器各区域数量",
     {"view": "region_count", "filters": {"productName": "model_alpha"}, "required_filters": ["productName"]}),
    ("F16", "查询存储池pool_alpha的容量详情",
     {"view": "capacity_detail", "filters": {"name": "pool_alpha"}, "required_filters": ["name"]}),
    ("F26", "区域region_alpha下各VDC的虚拟防火墙数量",
     {"view": "count", "filters": REGION, "required_filters": ["logicalRegionName"]}),
    ("NEXT_N28", "区域region_alpha下ECS、云硬盘和VPC数量",
     {"resource_set": ["VM_NOVA", "VOLUME", "ROUTER"], "group": "none", "layout": "labeled_rows",
      "metric": "count_rows", "filters": REGION, "required_filters": ["logicalRegionName"]}),
]


class A160IntegrationTests(unittest.TestCase):
    def item(self, family):
        return family_item(family)

    def fill(self, family, question, parameters, refine="SELECT 999 AS broken"):
        details = {}
        with patch.object(matcher, "llm_ask", return_value=json.dumps(parameters)), \
                patch.object(matcher, "_get_table_schemas", return_value="synthetic"), \
                patch.object(matcher, "_refine_sql", return_value=refine) as refinement:
            ordinary = matcher._match_a160_candidate(question, self.item(family), details)
        return ordinary, details, refinement.call_count

    def test_all_six_namespaces_materialize_and_keep_refinement_stage(self):
        for family, question, parameters in FIXTURES:
            with self.subTest(family=family):
                ordinary, details, calls = self.fill(family, question, parameters)
                self.assertIsNotNone(ordinary, details)
                self.assertEqual(calls, 1)
                self.assertEqual(details["family_status"], "materialized")
                self.assertFalse(details["family_refinement_kept"])
                self.assertNotIn("broken", ordinary["sql"])
                self.assertTrue(ordinary["_expected_result_columns"])
                self.assertNotIn("{{", json.dumps(ordinary["api_call"]))

    def test_no_optional_filter_is_invented_or_declared_condition_dropped(self):
        for family, question, parameters in FIXTURES:
            with self.subTest(family=family):
                wrong = copy.deepcopy(parameters)
                wrong["filters"][next(iter(wrong["filters"]))] = "different_entity"
                ordinary, _, calls = self.fill(family, question, wrong)
                self.assertIsNone(ordinary)
                self.assertEqual(calls, 0)

    def test_extra_obligation_or_projection_is_never_silently_discarded(self):
        for family, question, parameters in FIXTURES:
            for tail in ["，并返回未知字段secretMetric", "，或者区域region_beta"]:
                with self.subTest(family=family, tail=tail):
                    ordinary, _, calls = self.fill(family, question + tail, parameters)
                    self.assertIsNone(ordinary)
                    self.assertEqual(calls, 0)

    def test_real_matcher_keeps_retrieval_select_fill_refine_path(self):
        family, question, parameters = FIXTURES[0]
        item = self.item(family)
        retriever = SimpleNamespace(retrieve=lambda query: [Candidate(item["id"], "strong", 10, 1)])
        stages = []
        def response(prompt, stage):
            stages.append(stage)
            return "1" if stage == "select" else json.dumps(parameters)
        with patch.object(matcher, "llm_ask", side_effect=response), \
                patch.object(matcher, "_get_table_schemas", return_value="synthetic"), \
                patch.object(matcher, "_refine_sql", return_value="SELECT 1") as refine:
            result = matcher.match_runbook(question, [item], retriever, {})
        self.assertIsNotNone(result)
        self.assertEqual(stages, ["select", "family_fill"])
        self.assertEqual(refine.call_count, 1)

    def test_boolean_topk_and_missing_required_parameters_refuse(self):
        family, question, parameters = FIXTURES[0]
        for wrong in [dict(parameters, top_k=True), dict(parameters, top_k=0), dict(parameters, filters={}),
                      dict(parameters, required_filters=[]), None]:
            with self.subTest(wrong=wrong):
                result, _, calls = self.fill(family, question, wrong)
                self.assertIsNone(result)
                self.assertEqual(calls, 0)

    def test_r2_continuous_ascii_names_are_not_split_by_region_or_HOST_words(self):
        family, question, parameters = FIXTURES[0]
        wrong = copy.deepcopy(parameters)
        wrong["filters"]["logicalRegionName"] = "r_region_HOST_core"
        ordinary, details, _ = self.fill(family, question.replace("region_alpha", "r_region_HOST_core"), wrong)
        self.assertIsNotNone(ordinary, details)
        self.assertEqual(ordinary["api_call"]["condition"]["constraint"][0]["simple"]["value"], "r_region_HOST_core")

    def test_explicit_same_family_two_views_are_not_collapsed_to_one(self):
        family, question, parameters = FIXTURES[0]
        result, _, _ = self.fill(family, question + "以及剩余内存最高的前2台宿主机", parameters)
        self.assertIsNone(result)

    def test_model_distribution_view_is_repaired_only_when_original_request_proves_it(self):
        parameters = {"view": "manufacturer_count", "filters": {"productName": "model_alpha"},
                      "required_filters": ["productName"]}
        question = "查询型号为model_alpha的服务器数量及分布情况"
        result, detail, calls = self.fill("F11_CORE", question, parameters)
        self.assertIsNotNone(result, detail)
        self.assertEqual(calls, 1)
        self.assertEqual(detail["view_repair"]["to"], "region_count")
        self.assertIn("GROUP BY logicalRegionName", result["sql"])
        self.assertEqual(result["api_call"]["condition"]["constraint"][0]["simple"]["value"], "model_alpha")
        for tail in ["，但只输出厂商", "，并且状态active", "或者区域region_other"]:
            with self.subTest(tail=tail):
                rejected, _, refined = self.fill("F11_CORE", question + tail, parameters)
                self.assertIsNone(rejected)
                self.assertEqual(refined, 0)


class A160CountExecutionTests(unittest.TestCase):
    def setUp(self):
        import runbook_family_count as helper
        family, question, parameters = FIXTURES[-1]
        item = family_item(family)
        self.ordinary = helper.prepare_count_candidate(question, item, parameters)
        self.schemas = patch.dict(matcher._schema_columns, {
            "VM_NOVA": ["id", "logicalRegionName", "vdcName"],
            "VOLUME": ["id", "logicalRegionName", "vdcName"],
            "ROUTER": ["id", "logicalRegionName", "vdcName"],
        })
        self.schemas.start()
        self.addCleanup(self.schemas.stop)

    def test_independent_real_empty_branches_count_zero_without_dummy_rows(self):
        payload = {"objList": [], "totalNum": 0, "totalPageNo": 0, "currentPage": 1, "pageSize": 10000,
                   "error": None, "success": True}
        calls = []
        def get(url, **options):
            calls.append(url)
            return SimpleNamespace(status_code=200, json=lambda: payload)
        result = system._execute_bounded_api(self.ordinary, {}, session=SimpleNamespace(get=get))
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["result"]["columns"], ["type", "count"])
        self.assertEqual(result["result"]["rows"], [{"type": "ECS", "count": 0},
                                                   {"type": "Volume", "count": 0}, {"type": "VPC", "count": 0}])

    def test_missing_objlist_is_not_normal_empty(self):
        session = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: {"success": True}))
        with self.assertRaises((RuntimeError, system._APIPlanRefusal)):
            system._execute_bounded_api(self.ordinary, {}, session=session)

    def test_failed_branch_is_not_answered_as_partial_or_zero_count(self):
        calls = []
        def get(url, **options):
            calls.append(url)
            payload = {"objList": [], "totalNum": 0, "totalPageNo": 0, "currentPage": 1, "pageSize": 10000}
            if len(calls) == 2:
                payload.update(success=False, error="unavailable")
            return SimpleNamespace(status_code=200, json=lambda: payload)
        with self.assertRaises((RuntimeError, system._APIPlanRefusal)):
            system._execute_bounded_api(self.ordinary, {}, session=SimpleNamespace(get=get))
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
