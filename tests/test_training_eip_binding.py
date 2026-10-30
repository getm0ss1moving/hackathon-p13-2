"""已关联EIP的状态槽必须有原生字段及原SQL关系；纯合成实体。"""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m


def item():
    return {"api_call": [{"url": "/rest/hackthon/db/instances/FLOATING_IPS",
                         "condition": {"constraint": [{"simple": {"name": "status", "value": "{{status}}", "operator": "equal"}}]}}],
            "sql": "SELECT CLOUD_VM_NOVA.name FROM CLOUD_FLOATING_IPS INNER JOIN CLOUD_VM_NOVA ON CLOUD_FLOATING_IPS.fixedIpAddress=CLOUD_VM_NOVA.privateIps"}


class EipBindingTests(unittest.TestCase):
    def setUp(self):
        for context in [patch.object(m, "_schema_columns", {"FLOATING_IPS": ["status", "fixedIpAddress"], "VM_NOVA": ["privateIps"]}),
                        patch.object(m, "_schema_values", {"FLOATING_IPS": {"status": ["ACTIVE", "DOWN"]}})]:
            context.start(); self.addCleanup(context.stop)

    def test_explicit_association_and_replaced_entities(self):
        for region in ["region_demo", "region_2027", "region_other"]:
            for phrase in ["关联了弹性IP", "已关联EIP", "已关联弹性 IP"]:
                question = f"区域{region}下{phrase}的ECS实例名和固定IP"
                values = {}; m._auto_fill_params(question, values, ["logicalRegionName", "status"], item())
                self.assertEqual(values, {"logicalRegionName": region, "status": "ACTIVE"})

    def test_negative_disjunction_and_missing_intent_do_not_infer_active(self):
        for question in ["未关联了弹性IP的ECS", "没有已关联EIP的ECS", "非关联了弹性IP的ECS", "关联了弹性IP或未关联EIP的ECS",
                         "关联了弹性IP的ECS，不包括停止的ECS", "ECS和弹性IP列表", "弹性IP固定IP非空", "ECS关联弹性IP的数量",
                         "查询名称“已关联EIP”的ECS", "关联了弹性IP的ECSvm_beta", "关联了弹性IP的运行中ECS", "已关联EIP的ECS OR 未绑定EIP"]:
            with self.subTest(question=question):
                self.assertEqual(m._eip_association_status(question, item()), [])
                self.assertNotIn("ACTIVE", m._semantic_values(question, item(), "status"))

    def test_native_role_schema_and_relation_are_required(self):
        for change in ["owner", "join", "extra_table", "missing_schema", "operator", "wrong_field"]:
            source = item()
            schema = copy.deepcopy(m._schema_columns)
            if change == "owner": source["api_call"][0]["url"] = "/rest/hackthon/db/instances/VM_NOVA"
            if change == "join": source["sql"] = source["sql"].replace("CLOUD_VM_NOVA.privateIps", "CLOUD_VM_NOVA.id")
            if change == "extra_table": source["sql"] += " JOIN CLOUD_ROUTER ON CLOUD_ROUTER.id=CLOUD_FLOATING_IPS.routerId"
            if change == "missing_schema": schema["FLOATING_IPS"].remove("fixedIpAddress")
            if change == "operator": source["api_call"][0]["condition"]["constraint"][0]["simple"]["operator"] = "not_equal"
            if change == "wrong_field": source["api_call"][0]["condition"]["constraint"][0]["simple"]["name"] = "name"
            with patch.object(m, "_schema_columns", schema), self.subTest(change=change):
                self.assertEqual(m._eip_association_status("已关联EIP的ECS", source), [])

    def test_reverse_join_and_enum_case_follow_schema(self):
        source = item()
        source["sql"] = source["sql"].replace("CLOUD_FLOATING_IPS.fixedIpAddress=CLOUD_VM_NOVA.privateIps", "CLOUD_VM_NOVA.privateIps = CLOUD_FLOATING_IPS.fixedIpAddress")
        with patch.object(m, "_schema_values", {"FLOATING_IPS": {"status": ["active", "down"]}}):
            self.assertEqual(m._semantic_values("已关联EIP的ECS", source, "status"), ["active"])

    def test_grounding_and_fill_preserve_the_existing_contract(self):
        source = item(); before = copy.deepcopy(source)
        question = "区域region_demo下关联了弹性IP的ECS实例名和固定IP"
        values = {}; m._auto_fill_params(question, values, ["status"], source)
        with patch.dict(os.environ, {"RUNBOOK_GROUND_ENUM_LABELS": "1"}):
            self.assertEqual(m._ground_params(question, {"status": "ACTIVE"}, source), values)
            self.assertEqual(m._ground_params(question.replace("关联了", "未关联"), {"status": "ACTIVE"}, source), {})
        self.assertEqual(source, before)
        self.assertTrue(m._fill_params(source, values, question))
        self.assertEqual(source["sql"], before["sql"])
        self.assertEqual(source["api_call"][0]["condition"]["constraint"][0]["simple"]["value"], "ACTIVE")


if __name__ == "__main__": unittest.main()
