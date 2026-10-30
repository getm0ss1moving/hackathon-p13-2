"""仅合成CI与SQLite，验证完整名称域、守恒及拒绝边界；禁止真实网络。"""

from contextlib import ExitStack, closing
import copy
import json
import sqlite3
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runbook_tenant_resources as t
import runbook_executor as executor


QUESTION = "查询区域region_synthetic7下各租户的ECS实例数量、云硬盘数量、云硬盘总容量和ECS规格分布"
REGION = "region_synthetic7"


def call(ci, field=None, value=None):
    result = {"method": "GET", "url": "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=10000"}
    if field:
        result["condition"] = {"constraint": [{"simple": {"name": field, "value": value, "operator": "equal"}}]}
    return result


def item(dependent=False):
    vm = call("VM_NOVA", "logicalRegionName", "{{logicalRegionName}}")
    flavor = call("FLAVOR", "id", "{{flavorId from step 1}}") if dependent else call("FLAVOR")
    flavor["autoPagination"] = True
    return {"id": "synthetic_template", "sql": "SELECT tenantName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY tenantName",
            "api_call": [vm, flavor, call("VOLUME")] if dependent else [vm, call("VOLUME"), flavor]}


def fixture():
    vms = [
        {"id": "vm1", "tenantName": "alpha", "flavorId": "f1"},
        {"id": "vm2", "tenantName": "alpha", "flavorId": "missing-flavor"},
        {"id": "vm3", "tenantName": None, "flavorId": None},
        {"id": "vm4", "tenantName": ""},
        {"id": "vm5", "flavorId": "f2"},
    ]
    volumes = [{"id": "d1", "tenantName": "alpha", "size": "10"},
               {"id": "d2", "tenantName": "alpha", "size": "20"},
               {"id": "d3", "tenantName": "only-volume", "size": "7"},
               {"id": "d4", "tenantName": "", "size": "3"},
               {"id": "d5", "tenantName": None, "size": "5"}]
    for row in vms + volumes:
        row["logicalRegionName"] = REGION
    flavors = [{"id": "f1", "name": "small", "vcpuSize": "2", "ramSize": "2048", "diskSize": "20"},
               {"id": "f2", "name": "large", "vcpuSize": "8", "ramSize": "8192", "diskSize": "80"},
               {"id": "unused", "name": "global-unused", "vcpuSize": "4", "ramSize": "4096", "diskSize": "40"}]
    return {"VM_NOVA": vms, "VOLUME": volumes, "FLAVOR": flavors}


def filled(plan):
    result = copy.deepcopy(plan["item"])
    for api in result["api_call"]:
        for entry in api.get("condition", {}).get("constraint", []):
            if entry["simple"]["value"] == "{{logicalRegionName}}":
                entry["simple"]["value"] = REGION
    return result


class TenantResourcesTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for owner, method in [(requests.Session, "request"), (httpx.Client, "send")]:
            self.stack.enter_context(patch.object(owner, method, side_effect=AssertionError("禁止真实网络")))
        self.stack.enter_context(patch.object(t.m, "_schema_columns", copy.deepcopy(t._FIELDS)))
        self.stack.enter_context(patch.object(t.m, "JOIN_RELATIONS", "CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id"))

    def plan(self, source=None):
        plan = t.plan_tenants(QUESTION, source or item())
        self.assertIsNotNone(plan)
        return plan

    def validate(self, plan=None, data=None, supplied=None):
        plan = plan or self.plan()
        data = copy.deepcopy(data if data is not None else fixture())
        calls = []

        def lookup(api, previous=None):
            ci = t._endpoint(api)
            calls.append(ci)
            records = data[ci]
            if ci == "FLAVOR" and t._constraints(api):
                allowed = {row.get("flavorId") for row in previous if row.get("flavorId")}
                records = [row for row in records if row["id"] in allowed]
            return records, t._TABLES[ci]

        with patch.object(t.m, "_execute_lookup_api", side_effect=lookup):
            result = t.validate_tenants(QUESTION, supplied or filled(plan), plan)
        return result, calls

    def execute(self, sql, data):
        tables = {t._TABLES[ci]: rows for ci, rows in data.items()}
        with closing(executor.load_into_sqlite(tables)) as connection:
            cursor = connection.execute(sql)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    def test_plan_adds_only_proven_volume_scope_and_preserves_base(self):
        source = item()
        saved = copy.deepcopy(source)
        plan = self.plan(source)
        self.assertEqual(source, saved)
        self.assertTrue(plan["volume_scope_added"])
        self.assertEqual(plan["item"]["sql"], saved["sql"])
        self.assertEqual(plan["item"]["api_call"][0], saved["api_call"][0])
        self.assertEqual(plan["item"]["api_call"][2], saved["api_call"][2])
        self.assertEqual(t._constraints(plan["item"]["api_call"][1]), [("logicalRegionName", "{{logicalRegionName}}", "equal")])
        self.assertNotIn("R_VOLUME_MOUNTON_VM", plan["preview_sql"])
        source["api_call"][1] = call("VOLUME", "logicalRegionName", REGION)
        plan = self.plan(source)
        self.assertFalse(plan["volume_scope_added"])
        self.assertEqual(plan["item"]["api_call"], source["api_call"])

    def test_full_domain_null_empty_unknown_and_count_capacity_conservation(self):
        plan, data = self.plan(), fixture()
        proof, calls = self.validate(plan, data)
        self.assertTrue(proof["valid"], proof)
        self.assertEqual(calls, ["VM_NOVA", "VOLUME", "FLAVOR"])
        self.assertEqual((proof["vm_count"], proof["volume_count"], proof["tenant_domain_count"]), (5, 5, 4))
        self.assertEqual((proof["missing_flavor_field_rows"], proof["dangling_flavor_rows"], proof["unresolved_flavor_vm_count"]), (1, 1, 3))
        rows = self.execute(t.compose_tenants(plan["base_sql"], plan), data)
        extra = [obj for row in rows if row['volume_only_tenants_json'] is not None
                 for obj in json.loads(row['volume_only_tenants_json'])]
        self.assertEqual(len(rows),3);self.assertEqual(len(extra),1)
        self.assertEqual(extra[0]['tenantName'],'only-volume')
        keyed = {row["tenantName"]: row for row in rows + extra}
        self.assertEqual(set(keyed), {"alpha", "only-volume", None, ""})
        self.assertEqual((keyed[None]["ecs_count"], keyed[""]["ecs_count"]), (2, 1))
        self.assertEqual((keyed["only-volume"]["ecs_count"], keyed["only-volume"]["volume_count"]), (0, 1))
        self.assertEqual(keyed["only-volume"]["flavor_distribution"], [])
        self.assertEqual((keyed["alpha"]["ecs_count"], keyed["alpha"]["volume_count"], keyed["alpha"]["total_volume_size"]), (2, 2, 30))
        self.assertEqual(sum(row["ecs_count"] for row in rows + extra), 5)
        self.assertEqual(sum(row["volume_count"] for row in rows + extra), 5)
        self.assertEqual(sum(row["total_volume_size"] for row in rows + extra), 45)
        distribution = [value for row in rows for value in json.loads(row["flavor_distribution"])]
        self.assertEqual(sum(value["ecs_count"] for value in distribution), 5)
        self.assertEqual(sum(value["ecs_count"] for value in distribution if value["resolved"] == 0), 3)
        self.assertEqual(sum(row["unresolved_flavor_vm_count"] for row in rows), 3)
        self.assertTrue(any(value["flavor_id"] == "missing-flavor" and value["flavor_name"] is None for value in distribution))

    def test_typed_zero_vm_input_keeps_volume_only_tenants_without_fake_vm_group(self):
        plan=self.plan();data=fixture();data['VM_NOVA']=[]
        with closing(sqlite3.connect(':memory:')) as connection:
            for ci,fields in t._FIELDS.items():
                connection.execute('CREATE TABLE '+t._TABLES[ci]+' ('+','.join(fields)+')')
                connection.executemany('INSERT INTO '+t._TABLES[ci]+' VALUES ('+','.join('?' for _ in fields)+')',
                    [tuple(row.get(field) for field in fields) for row in data[ci]])
            cursor=connection.execute(t.compose_tenants(plan['base_sql'],plan));columns=[c[0] for c in cursor.description]
            rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['row_kind'],'summary_only')
            self.assertIsNone(rows[0]['ecs_count'])
            extra=json.loads(rows[0]['volume_only_tenants_json'])
            self.assertEqual({row['tenantName'] for row in extra},{'alpha','only-volume',None,''})
            self.assertTrue(all(row['ecs_count']==0 for row in extra))
            self.assertEqual(sum(row['volume_count'] for row in extra),5)
            self.assertEqual(sum(row['total_volume_size'] for row in extra),45)
            for table in t._TABLES.values():connection.execute('DELETE FROM '+table)
            self.assertEqual(connection.execute(plan['preview_sql']).fetchall(),[])

    def test_original_count_alias_is_preserved_and_refinement_cannot_change_contract(self):
        source = item()
        source["sql"] = "SELECT v.tenantName,COUNT(*) AS original_total FROM CLOUD_VM_NOVA AS v GROUP BY v.tenantName"
        plan = self.plan(source)
        rows = self.execute(t.compose_tenants(source["sql"], plan), fixture())
        self.assertIn("original_total", rows[0])
        for candidate in [source["sql"].replace("original_total", "ecs_count"),
                          source["sql"].replace("COUNT(*)", "COUNT(DISTINCT v.id)"),
                          source["sql"].replace("COUNT(*)", "COUNT(1)"),
                          source["sql"].replace("v.tenantName", "v.id"),
                          source["sql"] + " ORDER BY original_total", source["sql"] + "; SELECT 1"]:
            with self.subTest(candidate=candidate):
                self.assertIsNone(t.compose_tenants(candidate, plan))
        self.assertIsNotNone(t.compose_tenants(source["sql"].replace(" AS v", " AS x").replace("v.", "x."), plan))

    def test_only_whole_list_region_prefix_and_exact_supported_intent(self):
        for question in [QUESTION.replace("区域region_synthetic7下", ""),
                         QUESTION.replace("区域region_synthetic7下", "区域region_synthetic7和region_other下"),
                         QUESTION.replace("下各租户", "下租户tenant_x"),
                         QUESTION + "且运行中", QUESTION.replace("数量", "数量和IP", 1),
                         QUESTION.replace("规格分布", "实例列表"), QUESTION.replace("ECS实例数量", "VDC实例数量"),
                         QUESTION.replace("云硬盘数量、", ""), QUESTION.replace("云硬盘总容量", "平均容量")]:
            with self.subTest(question=question):
                self.assertIsNone(t.plan_tenants(question, item()))

    def test_unknown_extra_duplicate_ci_or_filter_are_rejected(self):
        mutations = [
            lambda source: source["api_call"].append(call("VM_NOVA")),
            lambda source: source["api_call"].__setitem__(1, call("VM_NOVA")),
            lambda source: source["api_call"].__setitem__(1, call("ROUTER")),
            lambda source: source["api_call"][0].update(method="POST"),
            lambda source: source["api_call"][0].update(url="https://example.invalid/rest/hackthon/db/instances/VM_NOVA"),
            lambda source: source["api_call"][0].update(url="/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageNo=1"),
            lambda source: source["api_call"][1].update(condition={"constraint": [{"simple": {"name": "status", "value": "available"}}]}),
            lambda source: source["api_call"][0]["condition"]["constraint"].append({"simple": {"name": "tenantName", "value": "x"}}),
            lambda source: source["api_call"][0]["condition"]["constraint"][0]["simple"].update(value="region_wrong"),
            lambda source: source["api_call"][2].update(condition={"constraint": [{"simple": {"name": "logicalRegionName", "value": REGION}}]}),
            lambda source: source["api_call"][2].update(totalNum=123),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                source = item()
                mutation(source)
                self.assertIsNone(t.plan_tenants(QUESTION, source))

    def test_adjacent_known_flavor_dependency_only(self):
        plan = self.plan(item(True))
        proof, calls = self.validate(plan)
        self.assertTrue(proof["valid"], proof)
        self.assertEqual(calls, ["VM_NOVA", "FLAVOR", "VOLUME"])
        self.assertEqual(proof["dangling_flavor_rows"], 1)
        for source in [item(), item(True)]:
            if source["api_call"][1]["url"].split("?")[0].endswith("FLAVOR"):
                source["api_call"][1]["condition"]["constraint"][0]["simple"]["value"] = "{{flavorId from step 2}}"
            else:
                source["api_call"][2]["condition"] = {"constraint": [{"simple": {"name": "id", "value": "{{flavorId from step 1}}"}}]}
            self.assertIsNone(t.plan_tenants(QUESTION, source))

    def test_empty_dependency_stops_before_flavor_lookup(self):
        plan, data = self.plan(item(True)), fixture()
        for row in data["VM_NOVA"]:
            row["flavorId"] = None
        proof, calls = self.validate(plan, data)
        self.assertFalse(proof["valid"])
        self.assertEqual(proof["reason"], "empty_tenant_flavor_dependency")
        self.assertEqual(calls, ["VM_NOVA"])

    def test_bad_numeric_size_empty_ci_and_duplicate_identity_fail_closed(self):
        for bad in [None, "", "NaN", "Infinity", "1x", True, [], -1, "-2"]:
            data = fixture()
            data["VOLUME"][0]["size"] = bad
            with self.subTest(size=bad):
                proof, _ = self.validate(data=data)
                self.assertFalse(proof["valid"])
                self.assertEqual(proof["reason"], "invalid_volume_size")
        for ci in t._TABLES:
            for mode in ["empty", "duplicate"]:
                with self.subTest(ci=ci, mode=mode):
                    data = fixture()
                    data[ci] = [] if mode == "empty" else data[ci] + [copy.deepcopy(data[ci][0])]
                    proof, _ = self.validate(data=data)
                    self.assertFalse(proof["valid"])

    def test_missing_sqlite_union_column_and_scope_type_mismatch_rejected(self):
        data = fixture()
        for row in data["VM_NOVA"]:
            row.pop("flavorId", None)
        proof, calls = self.validate(data=data)
        self.assertFalse(proof["valid"])
        self.assertEqual((proof["reason"], calls), ("tenant_loader_column_absent", ["VM_NOVA"]))
        for ci, field, value in [("VM_NOVA", "logicalRegionName", "region_other"),
                                 ("VOLUME", "logicalRegionName", "region_other"),
                                 ("VM_NOVA", "tenantName", 42), ("VM_NOVA", "flavorId", ["f1"]),
                                 ("FLAVOR", "ramSize", "NaN"), ("FLAVOR", "name", None)]:
            with self.subTest(ci=ci, field=field):
                data = fixture()
                data[ci][0][field] = value
                proof, _ = self.validate(data=data)
                self.assertFalse(proof["valid"])

    def test_schema_or_join_proof_and_api_drift_stop_before_get(self):
        with patch.object(t.m, "JOIN_RELATIONS", ""):
            self.assertIsNone(t.plan_tenants(QUESTION, item()))
        for ci, fields in t._FIELDS.items():
            schema = copy.deepcopy(t._FIELDS)
            schema[ci] = fields[:-1]
            with self.subTest(ci=ci), patch.object(t.m, "_schema_columns", schema):
                self.assertIsNone(t.plan_tenants(QUESTION, item()))
        plan = self.plan()
        supplied = filled(plan)
        supplied["api_call"][1]["condition"]["constraint"][0]["simple"]["value"] = "region_other"
        proof, calls = self.validate(plan, supplied=supplied)
        self.assertFalse(proof["valid"])
        self.assertEqual(calls, [])

    def test_api_exception_and_wrong_table_do_not_become_empty_answers(self):
        plan = self.plan()
        with patch.object(t.m, "_execute_lookup_api", side_effect=RuntimeError("synthetic transport")):
            proof = t.validate_tenants(QUESTION, filled(plan), plan)
        self.assertFalse(proof["valid"])
        self.assertEqual(proof["reason"], "tenant_resource_lookup_failed")
        with patch.object(t.m, "_execute_lookup_api", return_value=(fixture()["VM_NOVA"], "OTHER_TABLE")):
            proof = t.validate_tenants(QUESTION, filled(plan), plan)
        self.assertFalse(proof["valid"])
        self.assertEqual(proof["reason"], "tenant_resource_mismatch")


if __name__ == "__main__":
    unittest.main()
