"""170新增view/OBS的纯合成边界；不读取题目或访问模型/数据服务。"""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))
import runbook_matcher as m
import runbook_family_views as v
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import RunbookRetriever

FAMILIES = {item["family_id"]: item for item in RUNBOOK_ITEMS if item.get("family_id")}


def parsed(view, **filters):
    return {"view": view, "filters": filters, "required_filters": list(filters)}


class A170Tests(unittest.TestCase):
    def test_nine_natural_views_keep_their_complete_outputs(self):
        cases = [
            ("F02", "查询ECS实例Demo_name的创建时间", parsed("ecs_creation_time", name="Demo_name")),
            ("F02", "查询ECS实例Demo_name所属集群和可用区", parsed("ecs_cluster_zone", name="Demo_name")),
            ("F02", "查询区域region_demo可用区az0.dc0下ECS IP和租户", parsed("ecs_ip_tenant", logicalRegionName="region_demo", azoneName="az0.dc0")),
            ("F02", "查询租户tenant_demo区域region_demo下ECS IP列表", parsed("ecs_filtered_list", tenantName="tenant_demo", logicalRegionName="region_demo")),
            ("F02", "查询VDCvdc_demo区域region_demo可用区az0.dc0下各租户的ECS实例名和IP", parsed("ecs_tenant_ordered_ip", vdcName="vdc_demo", logicalRegionName="region_demo", azoneName="az0.dc0")),
            ("F19", "查询区域region_demo下GaussDB实例清单及数据库版本", parsed("db_region_inventory", logicalRegionName="region_demo")),
            ("F19", "查询GaussDB实例db_demo的配置信息", parsed("db_named_config", name="db_demo")),
            ("F19", "查询区域region_demo下GaussDB引擎版本和数据VIP", parsed("db_region_version_vip", logicalRegionName="region_demo")),
            ("F19", "查询GaussDB实例db_demo的高可用模式和数据VIP", parsed("db_named_ha_vip", name="db_demo")),
        ]
        for family, question, parameters in cases:
            with self.subTest(view=parameters["view"]):
                before = copy.deepcopy(parameters); diagnostic = {}
                ordinary = v.prepare_natural_candidate(question, FAMILIES[family], parameters, v._prepare_batch3_candidate, diagnostic)
                self.assertIsNotNone(ordinary, diagnostic)
                self.assertEqual(parameters, before)
                expected = v._materialize_batch3(FAMILIES[family], v.view_parameters(FAMILIES[family], parameters))
                self.assertEqual((ordinary["api_call"], ordinary["sql"]), (expected["api_call"], expected["sql"]))
                self.assertNotIn("family_id", ordinary)

    def test_same_family_multiple_output_obligations_do_not_return_partial_view(self):
        parameters = parsed("ecs_creation_time", name="Demo_name")
        for question in ["查询ECS实例Demo_name的创建时间及所属集群和可用区", "查询ECS实例Demo_name的创建时间并统计数量"]:
            self.assertIsNone(v.prepare_natural_candidate(question, FAMILIES["F02"], parameters, v._prepare_batch3_candidate))

    def test_unknown_field_missing_filter_and_wrong_role_fail_closed(self):
        parameters = parsed("ecs_creation_time", name="Demo_name")
        cases = [("查询ECS租户Demo_name的创建时间", parameters),
                 ("查询ECS实例Demo_name的创建时间", parsed("ecs_creation_time", name=None)),
                 ("查询ECS实例Demo_name的创建时间", dict(parameters, projection=["name", "createdAt"])),
                 ("查询ECS实例Demo_name的创建时间", parsed("db_named_config", name="Demo_name"))]
        for question, parameters in cases:
            self.assertIsNone(v.prepare_natural_candidate(question, FAMILIES["F02"], parameters, v._prepare_batch3_candidate))

    def test_obs_contracts_retain_region_and_reject_extra_clauses(self):
        base = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"}, "required_filters": ["logicalRegionName"]}
        for view, question in [("rows", "查询区域region_demo下OBS桶列表"), ("tenant_count", "统计区域region_demo下各租户的OBS桶数量")]:
            parameters = dict(base, view=view)
            self.assertIsNotNone(m._ground_obs_parameters(question, parameters))
            ordinary = m._materialize_family(FAMILIES["F27"], parameters)
            self.assertNotIn("family_id", ordinary)
        for question in ["查询区域region_demo下OBS桶列表及容量", "查询区域region_demo下OBS桶列表和数量", "查询区域不是region_demo下OBS桶列表"]:
            with self.assertRaises(ValueError):
                m._ground_obs_parameters(question, dict(base, view="rows"))

    def test_default_retriever_and_matcher_materialize_before_executor(self):
        question = "查询ECS实例Demo_name的创建时间"; family = FAMILIES["F02"]
        retriever = RunbookRetriever(RUNBOOK_ITEMS)
        offered = [candidate.id for candidate in retriever.retrieve(question)]
        self.assertIn(family["id"], offered)
        diagnostic = {}
        with patch.object(m, "llm_ask", side_effect=[str(offered.index(family["id"]) + 1), json.dumps(parsed("ecs_creation_time", name="Demo_name"))]), \
                patch.object(m, "_get_table_schemas", return_value=""), patch.object(m, "_refine_sql", side_effect=lambda q, sql, *a, **k: sql):
            ordinary = m.match_runbook(question, RUNBOOK_ITEMS, retriever, diagnostic)
        self.assertIsNotNone(ordinary, diagnostic)
        self.assertNotIn("family_id", ordinary)
        self.assertIsInstance(ordinary["api_call"], dict)
        self.assertNotIn("{{", json.dumps(ordinary["api_call"]))
        self.assertEqual(ordinary["sql"], "SELECT name, createdAt FROM CLOUD_VM_NOVA")


if __name__ == "__main__": unittest.main()
