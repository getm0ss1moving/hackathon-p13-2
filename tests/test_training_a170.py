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
    def test_view_prompt_schema_closes_array_type_and_all_legal_filter_profiles(self):
        for family, count in [("F02", 7), ("F19", 4)]:
            captured = []
            def ask(prompt, stage):
                captured.append(prompt)
                raise ValueError("offline prompt capture")
            with patch.object(m, "llm_ask", side_effect=ask):
                self.assertIsNone(m._match_closed_view_candidate("合成结构检查", FAMILIES[family], {}))
            line = next(line for line in captured[0].splitlines() if line.startswith("JSON Schema："))
            schema = json.loads(line.removeprefix("JSON Schema："))
            self.assertEqual(schema["properties"]["required_filters"]["type"], "array")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(len(schema["oneOf"]), count)
            actual = {(branch["properties"]["view"]["const"], frozenset(branch["properties"]["filters"]["required"])) for branch in schema["oneOf"]}
            expected = {(view, frozenset(keys)) for view, (owner, columns, order, _) in v.VIEWS.items() if owner == family
                        for keys in v._B3_SPECS[family]["shapes"][tuple(columns)][order]}
            self.assertEqual(actual, expected)

    def test_malformed_model_filter_list_is_rejected_without_repair(self):
        question = "查询ECS实例Demo_name的创建时间"
        retriever = RunbookRetriever(RUNBOOK_ITEMS)
        offered = [candidate.id for candidate in retriever.retrieve(question)]
        response = {"view": "ecs_creation_time", "filters": {"name": "ECSDemo_name"},
                    "required_filters": {"name": "ECSDemo_name"}}
        diagnostic = {}
        with patch.object(m, "llm_ask", side_effect=[str(offered.index(FAMILIES["F02"]["id"]) + 1), json.dumps(response)]), \
                patch.object(m, "_refine_sql") as refine:
            result = m.match_runbook(question, RUNBOOK_ITEMS, retriever, diagnostic)
        self.assertIsNone(result)
        self.assertEqual(diagnostic["family_error"], "explicit_complete_filter_contract_required")
        refine.assert_not_called()

    def test_resource_attachment_and_quoted_real_prefix_have_different_roles(self):
        positives = [
            ("查询ECSDemo_name的创建时间", "Demo_name"),
            ("查询ECSECSDemo_name的创建时间", "ECSDemo_name"),
            ("查询ECS名称为“ECSDemo_name”的创建时间", "ECSDemo_name"),
            ("查询ECS实例“ECSDemo_name”的创建时间", "ECSDemo_name"),
            ("查询ECS名称为“ECS_OR_创建时间”的创建时间", "ECS_OR_创建时间"),
        ]
        for question, name in positives:
            with self.subTest(question=question):
                diagnostic = {}
                ordinary = v.prepare_natural_candidate(question, FAMILIES["F02"], parsed("ecs_creation_time", name=name), v._prepare_batch3_candidate, diagnostic)
                self.assertIsNotNone(ordinary, diagnostic)
                self.assertEqual(ordinary["api_call"]["condition"]["constraint"][0]["simple"]["value"], name)
        for question, name in [("查询ECSDemo_name的创建时间", "ECSDemo_name"),
                               ("查询ECS名称为“ECSDemo_name”的创建时间", "Demo_name")]:
            self.assertIsNone(v.prepare_natural_candidate(question, FAMILIES["F02"], parsed("ecs_creation_time", name=name), v._prepare_batch3_candidate))

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
