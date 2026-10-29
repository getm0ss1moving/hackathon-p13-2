"""实体替换、条件完整性和类型回归；不读取题号或标准答案来驱动查询。"""

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m


def template(*parameters, resource="VM_NOVA"):
    return {
        "id": "fixture", "name": "测试模板", "description": "ECS查询", "examples": [],
        "resources": [resource],
        "api_call": {"url": f"/rest/hackthon/db/instances/{resource}",
                     "condition": {"constraint": [{"simple": {
                         "name": p, "value": "{{" + p + "}}", "operator": "equal"}}
                         for p in parameters]}},
        "sql": f"SELECT name FROM CLOUD_{resource}",
    }


class ParameterTests(unittest.TestCase):
    def test_adjacent_chinese_and_replaced_entities(self):
        for tenant, region, az in [("Tenant_Q7", "region_lab9", "az9.dc8"),
                                   ("NewOrg-42", "region_hidden_3", "az21.dc10")]:
            with self.subTest(tenant=tenant):
                question = f"查询租户{tenant}在区域{region}可用区{az}中的ECS名称和IP"
                values = {}
                m._auto_fill_params(question, values, ["tenantName", "logicalRegionName", "azoneName"])
                self.assertEqual(values, {"tenantName": tenant, "logicalRegionName": region, "azoneName": az})

    def test_preserves_chinese_quoted_and_real_resource_prefix(self):
        for entity in ["ECSProduction-42", "各业务的生产集群", "O'Reilly server"]:
            with self.subTest(entity=entity):
                question = f'查询ECS“{entity}”的名称'
                item = template("name")
                values = {}
                m._auto_fill_params(question, values, ["name"], item)
                self.assertEqual(values, {"name": entity})
                self.assertEqual(m._ground_params(question, values, item), values)

    def test_missing_required_filter_does_not_mutate_or_broaden_query(self):
        item = template("tenantName")
        original = copy.deepcopy(item)
        self.assertFalse(m._fill_params(item, {}))
        self.assertEqual(item, original)

    def test_false_zero_and_in_list_keep_json_types(self):
        item = template("management", "port", "name")
        item["api_call"]["condition"]["constraint"][2]["simple"]["operator"] = "in"
        self.assertTrue(m._fill_params(item, {"management": False, "port": 0, "name": ["a", "b"]}))
        values = [c["simple"]["value"] for c in item["api_call"]["condition"]["constraint"]]
        self.assertEqual(values, [False, 0, ["a", "b"]])
        self.assertIs(type(values[0]), bool)
        self.assertIs(type(values[1]), int)

    def test_sql_escaping_does_not_change_api_entity(self):
        item = template("name")
        item["sql"] = "SELECT name FROM CLOUD_VM_NOVA WHERE name = '{{name}}'"
        self.assertTrue(m._fill_params(item, {"name": "O'Reilly"}))
        self.assertIn("'O''Reilly'", item["sql"])
        self.assertEqual(item["api_call"]["condition"]["constraint"][0]["simple"]["value"], "O'Reilly")

    def test_from_step_dependency_is_preserved_for_fixed_executor(self):
        item = template("name")
        item["api_call"] = [item["api_call"], {
            "url": "/rest/hackthon/db/instances/FLAVOR",
            "condition": {"constraint": [{"simple": {
                "name": "id", "operator": "in", "value": "{{flavorId from step 1}}"}}]}}]
        self.assertTrue(m._fill_params(item, {"name": "new-server"}))
        self.assertEqual(item["api_call"][1]["condition"]["constraint"][0]["simple"]["value"],
                         "{{flavorId from step 1}}")

    def test_no_implicit_default_when_entity_is_missing(self):
        item = template("tenantName")
        item["default_params"] = {"tenantName": "ExampleTenant"}
        retriever = Mock()
        retriever.retrieve.return_value = [SimpleNamespace(id="fixture", tier="strong")]
        with patch.object(m, "llm_ask", side_effect=["1", "tenantName="]):
            result = m.match_runbook("查询指定租户的ECS名称", [item], retriever)
        self.assertIsNone(result)

    def test_hallucinated_entity_rejected(self):
        item = template("tenantName")
        self.assertEqual(m._ground_params("查询指定租户的ECS", {"tenantName": "ExampleTenant"}, item), {})

    def test_enum_values_follow_target_field_samples(self):
        examples = [("NETWORK", "shared", "查询非共享网络", "false"),
                    ("VOLUME", "bootable", "查询可启动云硬盘", "true"),
                    ("VM_NOVA", "management", "查询租户虚拟机", False),
                    ("FLOATING_IPS", "status", "查询未绑定弹性IP", "DOWN"),
                    ("ELB", "status", "查询运行中ELB", "ACTIVE")]
        for resource, parameter, question, expected in examples:
            with self.subTest(resource=resource):
                item = template(parameter, resource=resource)
                with patch.object(m, "_schema_values", {resource: {parameter: [expected]}}):
                    values = {}
                    m._auto_fill_params(question, values, [parameter], item)
                    self.assertEqual(values, {parameter: expected})
                    self.assertEqual(m._ground_params(question, values, item), values)

    def test_conflicting_duplicate_keys_are_rejected(self):
        self.assertIsNone(m._parse_params_response("name=one\nname=two", ["name"]))
        self.assertIsNone(m._parse_params_response('{"name":"one","name":"two"}', ["name"]))
        self.assertEqual(m._parse_params_response('{"name":"new","unknown":"discard"}', ["name"]),
                         {"name": "new"})

    def test_opaque_native_id_keeps_declared_field(self):
        item = template("nativeId", resource="HOST")
        m._fill_params(item, {"nativeId": "short-token"})
        m._fix_native_id_to_name(item, {"nativeId": "short-token"}, "查询原生ID short-token 的宿主机")
        self.assertEqual(item["api_call"]["condition"]["constraint"][0]["simple"]["name"], "nativeId")

    def test_enum_format_can_be_inferred_without_matching_sample_value(self):
        for resource, parameter, question, samples, expected in [
            ("VOLUME", "bootable", "查询不可启动云硬盘", ["true"], "false"),
            ("FLOATING_IPS", "status", "查询已绑定弹性IP", ["DOWN"], "ACTIVE"),
        ]:
            with self.subTest(resource=resource), patch.object(m, "_schema_values", {resource: {parameter: samples}}):
                values = {}
                m._auto_fill_params(question, values, [parameter], template(parameter, resource=resource))
                self.assertEqual(values, {parameter: expected})

    def test_list_requires_in_operator_and_singleton_in_stays_list(self):
        item = template("name")
        self.assertFalse(m._fill_params(item, {"name": ["a", "b"]}))
        item["api_call"]["condition"]["constraint"][0]["simple"]["operator"] = "in"
        self.assertTrue(m._fill_params(item, {"name": "a"}))
        self.assertEqual(item["api_call"]["condition"]["constraint"][0]["simple"]["value"], ["a"])


if __name__ == "__main__":
    unittest.main()
