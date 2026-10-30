"""同scope三份独立列表的合成守恒与拒绝边界；禁止网络、模型和真实题库。"""

from contextlib import ExitStack, closing
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_parallel_resource_lists as p
import runbook_executor as executor


TENANT = "tenant_synthetic"
REGION = "region_synthetic9"
BODY = "ECS实例名和IP、云硬盘名称和容量、VPC名称列表"
QUESTION = "查询租户" + TENANT + "的" + BODY
REGION_QUESTION = "查询租户" + TENANT + "在区域" + REGION + "中的" + BODY


def item(region=False):
    calls = []
    for ci in ["VM_NOVA", "VOLUME", "ROUTER"]:
        fields = ["tenantName", "logicalRegionName"] if region else ["tenantName"]
        calls.append({"method": "GET", "url": "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=10000",
                      "condition": {"constraint": [{"simple": {"name": field, "value": "{{" + field + "}}", "operator": "equal"}}
                                                    for field in fields]}})
    return {"id": "synthetic_template", "api_call": calls,
            "sql": "SELECT name AS volume_name,size AS volume_size,status AS volume_status FROM CLOUD_VOLUME"}


def fixture():
    data = {"VOLUME": [{"id": "same-id", "name": "same-volume", "size": "10", "status": "available"},
                       {"id": "d2", "name": "same-volume", "size": "20", "status": "in-use"}],
            "VM_NOVA": [{"id": "same-id", "name": "same-vm", "privateIps": "opaque-ip-A"},
                        {"id": "vm2", "name": "same-vm", "privateIps": "opaque-ip-B"},
                        {"id": "vm3", "name": "unmounted-vm", "privateIps": "opaque-ip-C"}],
            "ROUTER": [{"id": "vpc1", "name": "same-vpc"}, {"id": "vpc2", "name": "same-vpc"}]}
    for rows in data.values():
        for row in rows:
            row.update(tenantName=TENANT, logicalRegionName=REGION)
    return data


def filled(plan):
    result = copy.deepcopy(plan["item"])
    for call in result["api_call"]:
        for entry in call["condition"]["constraint"]:
            field = entry["simple"]["name"]
            if entry["simple"]["value"] == "{{" + field + "}}":
                entry["simple"]["value"] = plan["scope_values"][field]
    return result


class ParallelResourceListTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for owner, method in [(requests.Session, "request"), (httpx.Client, "send")]:
            self.stack.enter_context(patch.object(owner, method, side_effect=AssertionError("禁止真实网络")))
        self.stack.enter_context(patch.object(p.m, "_schema_columns", p._schema({"logicalRegionName": REGION})))
        self.stack.enter_context(patch.object(p.m, "JOIN_RELATIONS", ""))

    def plan(self, region=False, source=None):
        plan = p.plan(REGION_QUESTION if region else QUESTION, source or item(region))
        self.assertIsNotNone(plan)
        return plan

    def validate(self, plan=None, data=None, supplied=None):
        plan, data = plan or self.plan(), copy.deepcopy(data if data is not None else fixture())
        calls = []

        def lookup(call):
            ci = p._endpoint(call)
            calls.append(ci)
            return data[ci], p._TABLES[ci]

        question = REGION_QUESTION if "logicalRegionName" in plan["scope_values"] else QUESTION
        with patch.object(p.m, "_execute_lookup_api", side_effect=lookup):
            proof = p.validate(question, supplied or filled(plan), plan)
        return proof, calls

    def execute(self, sql, data):
        with closing(executor.load_into_sqlite({p._TABLES[ci]: rows for ci, rows in data.items()})) as connection:
            cursor = connection.execute(sql)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def test_plan_keeps_apis_base_and_infers_no_resource_relationship(self):
        source = item()
        saved = copy.deepcopy(source)
        proposed = self.plan(source=source)
        self.assertEqual(source, saved)
        self.assertEqual(proposed["item"], saved)
        self.assertNotIn("JOIN", proposed["preview_sql"].upper())
        self.assertNotIn("R_VOLUME", proposed["preview_sql"])
        self.assertEqual(proposed["preview_sql"].upper().count("UNION ALL"), 2)

    def test_complete_all_resource_ids_with_duplicate_names_and_unmounted_vm(self):
        proposed, data = self.plan(), fixture()
        proof, calls = self.validate(proposed, data)
        self.assertTrue(proof["valid"], proof)
        self.assertEqual(calls, ["VM_NOVA", "VOLUME", "ROUTER"])
        self.assertEqual(proof["resource_counts"], {"ECS": 3, "Volume": 2, "VPC": 2})
        self.assertEqual(proof["expected_output_rows"], 7)
        rows = self.execute(p.compose(proposed["base_sql"], proposed), data)
        self.assertEqual(len(rows), 7)
        self.assertEqual(len({(row["resource_type"], row["resource_id"]) for row in rows}), 7)
        self.assertIn(("Volume", "same-id"), {(row["resource_type"], row["resource_id"]) for row in rows})
        self.assertIn(("ECS", "same-id"), {(row["resource_type"], row["resource_id"]) for row in rows})
        self.assertEqual(sum(float(row["volume_size"]) for row in rows if row["resource_type"] == "Volume"), 30)
        self.assertTrue(any(row["vm_name"] == "unmounted-vm" for row in rows))
        self.assertEqual(sum(row["vpc_name"] == "same-vpc" for row in rows), 2)

    def test_null_values_are_only_non_applicable_fields(self):
        proposed = self.plan()
        rows = self.execute(p.compose(proposed["base_sql"], proposed), fixture())
        for row in rows:
            self.assertIsNotNone(row["resource_type"])
            self.assertIsNotNone(row["resource_id"])
            if row["resource_type"] == "Volume":
                self.assertTrue(all(row[field] is not None for field in ["volume_name", "volume_size", "volume_status"]))
                self.assertTrue(all(row[field] is None for field in ["vm_name", "vm_ip", "vpc_name"]))
            elif row["resource_type"] == "ECS":
                self.assertTrue(all(row[field] is None for field in ["volume_name", "volume_size", "volume_status", "vpc_name"]))
                self.assertTrue(all(row[field] is not None for field in ["vm_name", "vm_ip"]))
            else:
                self.assertTrue(all(row[field] is None for field in ["volume_name", "volume_size", "volume_status", "vm_name", "vm_ip"]))
                self.assertIsNotNone(row["vpc_name"])

    def test_optional_region_requires_same_explicit_filter_on_all_three_calls(self):
        proposed = self.plan(True)
        proof, _ = self.validate(proposed)
        self.assertTrue(proof["valid"])
        bad = item(True)
        bad["api_call"][2]["condition"]["constraint"].pop()
        self.assertIsNone(p.plan(REGION_QUESTION, bad))
        self.assertIsNone(p.plan(QUESTION, item(True)))
        data = fixture()
        data["VM_NOVA"][0]["logicalRegionName"] = "region_other"
        self.assertFalse(self.validate(proposed, data)[0]["valid"])
        # 无区域限定时不擅自缩小同租户的列表。
        self.assertTrue(self.validate(self.plan(), data)[0]["valid"])

    def test_projection_alias_expression_or_base_shape_change_rejected(self):
        proposed = self.plan()
        source = proposed["base_sql"]
        for changed in [source.replace("volume_name", "other"), source.replace("size AS", "SUM(size) AS"),
                        source.replace("status AS", "nativeId AS"), source + " LIMIT 3", source + " WHERE name='x'",
                        source.replace("CLOUD_VOLUME", "CLOUD_ROUTER"), source + ";SELECT 1"]:
            with self.subTest(changed=changed):
                self.assertIsNone(p.compose(changed, proposed))
        qualified = "SELECT x.name AS volume_name,x.size AS volume_size,x.status AS volume_status FROM CLOUD_VOLUME x"
        self.assertIsNotNone(p.compose(qualified, proposed))

    def test_non_parallel_related_missing_scope_or_extra_request_rejected(self):
        for question in [QUESTION.replace("租户" + TENANT + "的", ""),
                         QUESTION.replace("ECS实例名和IP", "VPC关联的ECS实例名和IP"),
                         QUESTION.replace("云硬盘名称和容量", "挂载云硬盘名称和容量"),
                         QUESTION.replace("VPC名称列表", "ECS所属VPC名称列表"),
                         QUESTION + "且运行中", QUESTION.replace("ECS实例名和IP", "ECS实例数量"),
                         QUESTION.replace("、VPC名称列表", ""),
                         QUESTION.replace("VPC名称列表", "安全组名称列表")]:
            with self.subTest(question=question):
                self.assertIsNone(p.plan(question, item()))
        for question in ["查询区域" + REGION + "下租户" + TENANT + "的" + BODY,
                         QUESTION.replace("ECS实例名和IP", "ECS实例名和IP列表").replace("云硬盘名称和容量", "云硬盘名称和容量列表")]:
            source = item("区域" in question)
            self.assertIsNotNone(p.plan(question, source))

    def test_extra_unknown_duplicate_resource_filter_or_dependency_rejected(self):
        mutations = [lambda source: source["api_call"].append(copy.deepcopy(source["api_call"][0])),
                     lambda source: source["api_call"].__setitem__(2, copy.deepcopy(source["api_call"][0])),
                     lambda source: source["api_call"][2].update(url="/rest/hackthon/db/instances/FLAVOR"),
                     lambda source: source["api_call"][0].update(method="POST"),
                     lambda source: source["api_call"][0].update(url="https://example.invalid/rest/hackthon/db/instances/VM_NOVA"),
                     lambda source: source["api_call"][1]["condition"]["constraint"].append({"simple": {"name": "status", "value": "available"}}),
                     lambda source: source["api_call"][2]["condition"]["constraint"][0]["simple"].update(value="{{tenantName from step 2}}"),
                     lambda source: source["api_call"][0].pop("condition")]
        for mutation in mutations:
            source = item()
            mutation(source)
            with self.subTest(mutation=mutation):
                self.assertIsNone(p.plan(QUESTION, source))

    def test_empty_ci_duplicate_identity_wrong_scope_and_unknown_requested_values_rejected(self):
        for ci in p._TABLES:
            for mode in ["empty", "duplicate", "scope"]:
                data = fixture()
                if mode == "empty":
                    data[ci] = []
                elif mode == "duplicate":
                    data[ci].append(copy.deepcopy(data[ci][0]))
                else:
                    data[ci][0]["tenantName"] = "other_tenant"
                with self.subTest(ci=ci, mode=mode):
                    self.assertFalse(self.validate(data=data)[0]["valid"])
        for ci, field, value in [("VM_NOVA", "privateIps", None), ("VM_NOVA", "privateIps", ""),
                                 ("VOLUME", "status", None), ("VOLUME", "size", "NaN"),
                                 ("VOLUME", "size", True), ("ROUTER", "name", []), ("ROUTER", "id", None)]:
            data = fixture()
            data[ci][0][field] = value
            with self.subTest(ci=ci, field=field, value=value):
                self.assertFalse(self.validate(data=data)[0]["valid"])

    def test_schema_api_drift_and_transport_error_fail_closed(self):
        schema = p._schema({"logicalRegionName": REGION})
        schema["VM_NOVA"].remove("privateIps")
        with patch.object(p.m, "_schema_columns", schema):
            self.assertIsNone(p.plan(QUESTION, item()))
        proposed = self.plan()
        supplied = filled(proposed)
        supplied["api_call"][2]["condition"]["constraint"][0]["simple"]["value"] = "other"
        proof, calls = self.validate(proposed, supplied=supplied)
        self.assertFalse(proof["valid"])
        self.assertEqual(calls, [])
        with patch.object(p.m, "_execute_lookup_api", side_effect=RuntimeError("synthetic GET failure")):
            proof = p.validate(QUESTION, filled(proposed), proposed)
        self.assertFalse(proof["valid"])
        self.assertEqual(proof["reason"], "parallel_lookup_failed")


if __name__ == "__main__":
    unittest.main()
