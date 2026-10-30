"""完整VM/卷明细的合成覆盖、身份和原生API边界测试，不访问网络或题库。"""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_vm_volume_details as d
import runbook_executor as executor


TENANT = "tenant_synthetic"
REGION = "region_synthetic8"
QUESTION = "查询租户" + TENANT + "在区域" + REGION + "中的ECS实例及规格、云硬盘列表及容量"


def call(ci, conditions=()):
    result = {"method": "GET", "url": "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=10000"}
    if conditions:
        result["condition"] = {"constraint": [{"simple": {"name": field, "value": value, "operator": "equal"}}
                                               for field, value in conditions]}
    return result


def item(dependent=True):
    scopes = [("tenantName", "{{tenantName}}"), ("logicalRegionName", "{{logicalRegionName}}")]
    vm, volume = call("VM_NOVA", scopes), call("VOLUME", scopes)
    flavor = call("FLAVOR", [("id", "{{flavorId from step 1}}")]) if dependent else call("FLAVOR")
    flavor["autoPagination"] = True
    return {"id": "synthetic_template", "sql": "SELECT name AS volume_name,size AS volume_size,status AS volume_status FROM CLOUD_VOLUME",
            "api_call": [vm, flavor, volume] if dependent else [vm, volume, flavor]}


def fixture():
    vms = [{"id": "v1", "name": "same-name", "flavorId": "f1"},
           {"id": "v2", "name": "same-name", "flavorId": "missing-flavor"},
           {"id": "v3", "name": "unmounted"},
           {"id": "v4", "name": "outside-volume", "flavorId": "f1"},
           {"id": "v5", "name": "dangling-volume", "flavorId": "f2"}]
    volumes = [{"id": "d1", "name": "same-volume", "size": "10", "status": "in-use"},
               {"id": "d2", "name": "same-volume", "size": "10", "status": "in-use"},
               {"id": "d3", "name": "no-scoped-vm", "size": "5", "status": "available"}]
    for row in vms + volumes:
        row.update(tenantName=TENANT, logicalRegionName=REGION)
    flavors = [{"id": "f1", "name": "small", "vcpuSize": "2", "ramSize": "2048", "diskSize": "20"},
               {"id": "f2", "name": "large", "vcpuSize": "8", "ramSize": "8192", "diskSize": "80"},
               {"id": "unused-global", "name": "global", "vcpuSize": "1", "ramSize": "1024", "diskSize": "0"}]
    pairs = [("v1", "d1"), ("v2", "d1"), ("v1", "d1"), ("v1", "d2"),
             ("v4", "outside-scope-volume"), ("v5", "missing-volume"), ("unresolved-vm", "d3")]
    relations = [{"vmId": vm, "volumeId": volume} for vm, volume in pairs]
    return {"VM_NOVA": vms, "VOLUME": volumes, "FLAVOR": flavors, "R_VOLUME_MOUNTON_VM": relations}


def filled(plan):
    result = copy.deepcopy(plan["item"])
    for api in result["api_call"]:
        for entry in api.get("condition", {}).get("constraint", []):
            simple = entry["simple"]
            if simple["name"] in plan["scope_values"] and simple["value"] == "{{" + simple["name"] + "}}":
                simple["value"] = plan["scope_values"][simple["name"]]
    return result


class VMVolumeDetailsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for owner, name in [(requests.Session, "request"), (httpx.Client, "send")]:
            self.stack.enter_context(patch.object(owner, name, side_effect=AssertionError("禁止真实网络")))
        self.stack.enter_context(patch.object(d.m, "_schema_columns", copy.deepcopy(d._FIELDS)))
        self.stack.enter_context(patch.object(d.m, "JOIN_RELATIONS", "\n".join(left + "=" + right for left, right in d._EDGES)))

    def plan(self, source=None, question=QUESTION):
        proposed = d.plan(question, source or item())
        self.assertIsNotNone(proposed)
        return proposed

    def validate(self, proposed=None, data=None, supplied=None):
        proposed, data = proposed or self.plan(), copy.deepcopy(data if data is not None else fixture())
        calls = []

        def lookup(api, previous=None):
            ci = d._endpoint(api)
            calls.append(copy.deepcopy(api))
            rows = data[ci]
            if ci == "FLAVOR" and d._constraints(api):
                allowed = {row.get("flavorId") for row in previous if row.get("flavorId")}
                rows = [row for row in rows if row["id"] in allowed]
            return rows, d._TABLES[ci]

        with patch.object(d.m, "_execute_lookup_api", side_effect=lookup):
            proof = d.validate(QUESTION, supplied or filled(proposed), proposed)
        return proof, calls

    def execute(self, sql, data):
        with closing(executor.load_into_sqlite({d._TABLES[ci]: rows for ci, rows in data.items()})) as connection:
            cursor = connection.execute(sql)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def test_plan_preserves_original_prefix_and_adds_global_relation_only(self):
        source, saved = item(), item()
        proposed = self.plan(source)
        self.assertEqual(source, saved)
        self.assertEqual(proposed["item"]["sql"], source["sql"])
        self.assertEqual(proposed["item"]["api_call"][:3], source["api_call"])
        relation = proposed["item"]["api_call"][3]
        self.assertEqual(d._endpoint(relation), "R_VOLUME_MOUNTON_VM")
        self.assertEqual(d._constraints(relation), [])
        proof, calls = self.validate(proposed)
        self.assertTrue(proof["valid"], proof)
        self.assertEqual(d._constraints(calls[-1]), [])
        self.assertNotIn("from step", json.dumps(calls[-1]))

    def test_many_to_many_duplicate_names_unknown_flavor_and_orphans_all_preserved(self):
        proposed, data = self.plan(), fixture()
        proof, _ = self.validate(proposed, data)
        self.assertTrue(proof["valid"], proof)
        self.assertEqual((proof["vm_count"], proof["volume_count"], proof["mounted_vm_count"]), (5, 3, 2))
        self.assertEqual((proof["vm_without_scoped_volume_count"], proof["expected_output_rows"]), (3, 3))
        self.assertEqual(proof["duplicate_mount_pairs"], 1)
        self.assertEqual(proof["unresolved_or_out_of_scope_volume_references"], 2)
        self.assertEqual(proof["unresolved_or_out_of_scope_vm_references"], 1)
        rows = self.execute(d.compose(proposed["base_sql"], proposed), data)
        self.assertEqual(len(rows), 3)
        volume_rows = [row for row in rows if row["detail_kind"] == "volume"]
        orphan_objects=[obj for row in rows if row['vms_without_scoped_volume_json'] is not None
                        for obj in json.loads(row['vms_without_scoped_volume_json'])]
        self.assertEqual({row["volume_id"] for row in volume_rows}, {"d1", "d2", "d3"})
        self.assertEqual(len(volume_rows), 3)
        self.assertEqual(sum(float(row["volume_size"]) for row in volume_rows), 25)
        attached = {row["volume_id"]: json.loads(row["vm_attachments"]) for row in volume_rows}
        self.assertEqual({obj["vm_id"] for obj in attached["d1"]}, {"v1", "v2"})
        self.assertEqual(len(attached["d1"]), 2)
        self.assertEqual(attached["d3"], [])
        self.assertEqual({obj['vm_id'] for obj in orphan_objects}, {"v3", "v4", "v5"})
        self.assertEqual(len(orphan_objects),3)
        objects = [obj for row in rows for obj in json.loads(row["vm_attachments"])] + orphan_objects
        self.assertEqual({obj["vm_id"] for obj in objects}, {"v1", "v2", "v3", "v4", "v5"})
        unknown = {obj["vm_id"]: obj for obj in objects if obj["flavor_resolved"] == 0}
        self.assertEqual(set(unknown), {"v2", "v3"})
        self.assertEqual(unknown["v2"]["flavor_id"], "missing-flavor")
        self.assertIsNone(unknown["v2"]["flavor_name"])
        self.assertIsNone(unknown["v3"]["flavor_id"])
        self.assertEqual(sum(row['vms_without_scoped_volume_json'] is not None for row in rows),1)

    def test_global_relation_without_any_scoped_mount_keeps_every_vm_and_volume(self):
        data = fixture()
        data["R_VOLUME_MOUNTON_VM"] = [{"vmId": "other-vm", "volumeId": "other-volume"}]
        proposed = self.plan()
        proof, _ = self.validate(proposed, data)
        self.assertTrue(proof["valid"])
        rows = self.execute(d.compose(proposed["base_sql"], proposed), data)
        self.assertEqual((len(rows), proof["expected_output_rows"]), (3, 3))
        self.assertEqual(sum(row["detail_kind"] == "volume" for row in rows), 3)
        orphans=[obj for row in rows if row['vms_without_scoped_volume_json'] is not None
                 for obj in json.loads(row['vms_without_scoped_volume_json'])]
        self.assertEqual({obj['vm_id'] for obj in orphans},{'v1','v2','v3','v4','v5'})
        self.assertEqual(len(orphans),5)

    def test_typed_zero_volume_input_keeps_vm_list_on_labeled_carrier(self):
        proposed=self.plan();data=fixture();data['VOLUME']=[]
        with closing(sqlite3.connect(':memory:')) as connection:
            for ci,fields in d._FIELDS.items():
                connection.execute('CREATE TABLE '+d._TABLES[ci]+' ('+','.join(fields)+')')
                connection.executemany('INSERT INTO '+d._TABLES[ci]+' VALUES ('+','.join('?' for _ in fields)+')',
                    [tuple(row.get(field) for field in fields) for row in data[ci]])
            cursor=connection.execute(d.compose(proposed['base_sql'],proposed));columns=[c[0] for c in cursor.description]
            rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['detail_kind'],'summary_only')
            self.assertIsNone(rows[0]['volume_id']);self.assertIsNone(rows[0]['volume_size'])
            orphans=json.loads(rows[0]['vms_without_scoped_volume_json'])
            self.assertEqual({obj['vm_id'] for obj in orphans},{'v1','v2','v3','v4','v5'})
            for table in d._TABLES.values():connection.execute('DELETE FROM '+table)
            self.assertEqual(connection.execute(proposed['preview_sql']).fetchall(),[])

    def test_alias_projection_or_base_semantics_change_returns_none(self):
        proposed = self.plan()
        source = proposed["base_sql"]
        for changed in [source.replace("volume_name", "name"), source.replace("size AS", "SUM(size) AS"),
                        source.replace("status AS volume_status", "name AS volume_status"),
                        source + " WHERE status='available'", source + " GROUP BY name", source + " LIMIT 5",
                        source + "; SELECT 1", source.replace("CLOUD_VOLUME", "CLOUD_VM_NOVA")]:
            with self.subTest(changed=changed):
                self.assertIsNone(d.compose(changed, proposed))
        qualified = "SELECT x.name AS volume_name,x.size AS volume_size,x.status AS volume_status FROM CLOUD_VOLUME x"
        self.assertIsNotNone(d.compose(qualified, proposed))
        source_item = item()
        source_item["sql"] = source_item["sql"].replace("volume_name", "original_name")
        alternate = self.plan(source_item)
        rows = self.execute(d.compose(source_item["sql"], alternate), fixture())
        self.assertIn("original_name", rows[0])

    def test_scope_prefix_is_explicit_and_covers_whole_list(self):
        for question in [QUESTION.replace("在区域" + REGION + "中", ""), QUESTION.replace("租户" + TENANT, ""),
                         QUESTION + "且运行中", QUESTION.replace("云硬盘列表及容量", "VPC列表"),
                         QUESTION.replace("及规格", "及IP"), QUESTION.replace(REGION, REGION + "和region_other"),
                         QUESTION.replace("中的", "中各租户的")]:
            with self.subTest(question=question):
                self.assertIsNone(d.plan(question, item()))
        reordered = "查询区域" + REGION + "下租户" + TENANT + "的ECS实例及配置、云硬盘列表及容量"
        self.assertIsNotNone(d.plan(reordered, item()))

    def test_missing_extra_or_different_scope_filter_and_duplicate_resource_rejected(self):
        mutations = [lambda src: src["api_call"][2].pop("condition"),
                     lambda src: src["api_call"].append(copy.deepcopy(src["api_call"][0])),
                     lambda src: src["api_call"].__setitem__(2, call("ROUTER")),
                     lambda src: src["api_call"][0].update(method="POST"),
                     lambda src: src["api_call"][0].update(url="https://example.invalid/rest/hackthon/db/instances/VM_NOVA"),
                     lambda src: src["api_call"][2]["condition"]["constraint"].append({"simple": {"name": "status", "value": "available"}}),
                     lambda src: src["api_call"][2]["condition"]["constraint"][0]["simple"].update(value="other-tenant"),
                     lambda src: src["api_call"][0].update(totalNum=320)]
        for mutation in mutations:
            source = item()
            mutation(source)
            with self.subTest(mutation=mutation):
                self.assertIsNone(d.plan(QUESTION, source))

    def test_global_flavor_and_only_adjacent_original_flavor_dependency_allowed(self):
        proposed = self.plan(item(False))
        proof, calls = self.validate(proposed)
        self.assertTrue(proof["valid"])
        self.assertEqual([d._endpoint(api) for api in calls], ["VM_NOVA", "VOLUME", "FLAVOR", "R_VOLUME_MOUNTON_VM"])
        bad = item(False)
        bad["api_call"][2]["condition"] = {"constraint": [{"simple": {"name": "id", "value": "{{flavorId from step 1}}"}}]}
        self.assertIsNone(d.plan(QUESTION, bad))
        bad = item()
        bad["api_call"][1]["condition"]["constraint"][0]["simple"]["value"] = "{{flavorId from step 2}}"
        self.assertIsNone(d.plan(QUESTION, bad))

    def test_empty_or_long_original_flavor_dependency_stops_before_flavor_request(self):
        for long in [False, True]:
            data = fixture()
            if long:
                data["VM_NOVA"] = [{"id": "vm-" + str(index), "name": "vm", "tenantName": TENANT,
                                     "logicalRegionName": REGION, "flavorId": str(index) + "x" * 240} for index in range(300)]
            else:
                for row in data["VM_NOVA"]:
                    row["flavorId"] = None
            proof, calls = self.validate(data=data)
            self.assertFalse(proof["valid"])
            self.assertEqual(proof["reason"], "empty_or_oversized_vm_flavor_dependency")
            self.assertEqual([d._endpoint(api) for api in calls], ["VM_NOVA"])

    def test_numeric_identity_empty_ci_and_relation_keys_fail_closed(self):
        for bad in [None, "", "NaN", "Infinity", "x3", -1, True, {}]:
            data = fixture()
            data["VOLUME"][0]["size"] = bad
            with self.subTest(size=bad):
                proof, _ = self.validate(data=data)
                self.assertFalse(proof["valid"])
        for ci in d._TABLES:
            data = fixture()
            data[ci] = []
            with self.subTest(empty=ci):
                self.assertFalse(self.validate(data=data)[0]["valid"])
        for ci in ["VM_NOVA", "VOLUME", "FLAVOR"]:
            data = fixture()
            data[ci].append(copy.deepcopy(data[ci][0]))
            with self.subTest(duplicate=ci):
                self.assertFalse(self.validate(data=data)[0]["valid"])
        for ci, field, value in [("VM_NOVA", "logicalRegionName", "region_other"),
                                 ("VOLUME", "tenantName", "other"), ("VM_NOVA", "flavorId", ["f1"]),
                                 ("FLAVOR", "ramSize", "NaN"), ("R_VOLUME_MOUNTON_VM", "vmId", None)]:
            data = fixture()
            data[ci][0][field] = value
            with self.subTest(ci=ci, field=field):
                self.assertFalse(self.validate(data=data)[0]["valid"])

    def test_sparse_flavor_column_all_absent_rejected_for_native_loader(self):
        data = fixture()
        for row in data["VM_NOVA"]:
            row.pop("flavorId", None)
        proof, calls = self.validate(data=data)
        self.assertEqual(proof["reason"], "vm_volume_loader_column_absent")
        self.assertEqual(len(calls), 1)

    def test_schema_relation_api_drift_and_transport_fail_before_further_reads(self):
        with patch.object(d.m, "JOIN_RELATIONS", ""):
            self.assertIsNone(d.plan(QUESTION, item()))
        schema = copy.deepcopy(d._FIELDS)
        schema["R_VOLUME_MOUNTON_VM"] = ["vmId"]
        with patch.object(d.m, "_schema_columns", schema):
            self.assertIsNone(d.plan(QUESTION, item()))
        proposed = self.plan()
        supplied = filled(proposed)
        supplied["api_call"][-1]["condition"] = {"constraint": [{"simple": {"name": "vmId", "value": "{{id from step 3}}"}}]}
        proof, calls = self.validate(proposed, supplied=supplied)
        self.assertFalse(proof["valid"])
        self.assertEqual(calls, [])
        with patch.object(d.m, "_execute_lookup_api", side_effect=RuntimeError("synthetic GET error")):
            proof = d.validate(QUESTION, filled(proposed), proposed)
        self.assertEqual(proof["reason"], "vm_volume_lookup_failed")


if __name__ == "__main__":
    unittest.main()
