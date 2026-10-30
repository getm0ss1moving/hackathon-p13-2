"""逐VPC的已解析/被引用/未解析子网统计；仅合成API与内存SQLite。"""

import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m
import runbook_vpc_subnets as v


QUESTION = "查询区域region_demo下各VDC的VPC名称和子网数量"
SQL = "SELECT vdcName,name AS vpc_name FROM CLOUD_ROUTER"
RELATIONS = "\n".join(left + " = " + right for left, right in v._EDGES)


def source(duplicate=True):
    call = {"method": "GET", "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
            "condition": {"constraint": [{"simple": {"name": "logicalRegionName", "value": "{{logicalRegionName}}", "operator": "equal"}}]}}
    return {"api_call": [call, copy.deepcopy(call)] if duplicate else call, "sql": SQL}


def data():
    return {"ROUTER": [{"id": "v-a", "nativeId": "n-a", "logicalRegionName": "region_demo", "vdcName": "owner", "name": "same"},
                       {"id": "v-b", "nativeId": "n-b", "logicalRegionName": "region_demo", "vdcName": "owner", "name": "same"},
                       {"id": "v-c", "nativeId": "n-c", "logicalRegionName": "region_demo", "vdcName": None, "name": "no-ports"}],
            "PORT": [{"id": "p-a", "devNativeId": "n-a"}, {"id": "p-b", "devNativeId": "n-a"},
                     {"id": "p-c", "devNativeId": "n-b"}, {"id": "p-null", "devNativeId": None},
                     {"id": "p-empty", "devNativeId": ""}],
            "R_PORT_IN_SUBNET": [{"portId": "p-a", "subnetId": "s-a"}, {"portId": "p-a", "subnetId": "s-a"},
                                 {"portId": "p-b", "subnetId": "s-a"}, {"portId": "p-b", "subnetId": "s-b"},
                                 {"portId": "p-b", "subnetId": "missing-a"}, {"portId": "p-c", "subnetId": "s-b"},
                                 {"portId": "p-c", "subnetId": "missing-b"}, {"portId": "p-a", "subnetId": None},
                                 {"portId": "p-a", "subnetId": ""}, {"portId": None, "subnetId": "s-a"},
                                 {"portId": "", "subnetId": "s-b"}, {"portId": "missing-port", "subnetId": "s-a"}],
            "SUBNET": [{"id": "s-a"}, {"id": "s-b"}]}


class VpcSubnetTests(unittest.TestCase):
    def setUp(self):
        context = patch.object(m, "_schema_columns", copy.deepcopy(v._FIELDS), create=True)
        context.start(); self.addCleanup(context.stop)
        context = patch.object(m, "JOIN_RELATIONS", RELATIONS, create=True)
        context.start(); self.addCleanup(context.stop)

    def plan(self, item=None):
        plan = v.plan_vpc(QUESTION, item or source())
        self.assertIsNotNone(plan)
        return plan

    def filled(self, plan):
        item = copy.deepcopy(plan["item"])
        item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "region_demo"
        return item

    def lookup(self, rows):
        def execute(call, previous=None):
            ci = v._endpoint(call)
            return copy.deepcopy(rows[ci]), v._TABLES[ci]
        return execute

    def query(self, plan, rows, base_sql=None):
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            for ci, fields in v._FIELDS.items():
                connection.execute("CREATE TABLE " + v._TABLES[ci] + "(" + ','.join(field + " TEXT" for field in fields) + ")")
                connection.executemany("INSERT INTO " + v._TABLES[ci] + " VALUES (" + ','.join('?' for _ in fields) + ")",
                                       [tuple(row.get(field) for field in fields) for row in rows[ci]])
            sql = v.compose_vpc(base_sql or plan["base_sql"], plan)
            self.assertIsNotNone(sql)
            return [dict(row) for row in connection.execute(sql)]

    def test_flat_detail_shape_kept_and_identical_root_api_deduplicated(self):
        item = source(); before = copy.deepcopy(item); plan = self.plan(item)
        self.assertEqual(item, before)
        self.assertEqual(plan["deduplicated_root_calls"], 1)
        self.assertEqual([v._endpoint(call) for call in plan["item"]["api_call"]], list(v._TABLES))
        self.assertTrue(all("condition" not in call for call in plan["item"]["api_call"][1:]))
        self.assertEqual(plan["item"]["api_call"][0], item["api_call"][0])
        self.assertEqual(v._shape(plan["item"]["sql"], True)["output_columns"], ["vdcname", "vpc_name", "vpc_id", "vpc_native_id"])
        for calls in [source(False)["api_call"], [source(False)["api_call"]]]:
            other = self.plan(dict(source(), api_call=calls))
            self.assertEqual(other["deduplicated_root_calls"], 0)

    def test_counts_distinguish_real_objects_references_and_dangling_without_product(self):
        plan = self.plan(); rows = self.query(plan, data()); by_id = {row["vpc_id"]: row for row in rows}
        self.assertEqual(len(rows), 3)
        self.assertEqual([by_id["v-a"][key] for key in v._COUNTS], [2, 3, 1])
        self.assertEqual([by_id["v-b"][key] for key in v._COUNTS], [1, 2, 1])
        self.assertEqual([by_id["v-c"][key] for key in v._COUNTS], [0, 0, 0])
        self.assertEqual(by_id["v-a"]["vpc_name"], by_id["v-b"]["vpc_name"])
        self.assertIsNone(by_id["v-c"]["vdcName"])
        self.assertEqual(set(rows[0]), {"vdcName", "vpc_name", "vpc_id", "vpc_native_id", *v._COUNTS})

    def test_multiple_unresolved_references_are_not_reported_as_existing_subnets(self):
        plan = self.plan(); rows = data()
        rows["R_PORT_IN_SUBNET"] = [{"portId": "p-a", "subnetId": "unknown-" + str(i)} for i in range(4)]
        by_id = {row["vpc_id"]: row for row in self.query(plan, rows)}
        self.assertEqual([by_id["v-a"][key] for key in v._COUNTS], [0, 4, 4])
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
            result = v.validate_vpc(QUESTION, self.filled(plan), plan)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["data_quality"]["max_unresolved_per_vpc"], 4)

    def test_null_and_empty_references_do_not_create_matches(self):
        plan = self.plan(); rows = data()
        rows["R_PORT_IN_SUBNET"] = [{"portId": "p-a", "subnetId": None}, {"portId": "p-a", "subnetId": ""},
                                   {"portId": None, "subnetId": "s-a"}, {"portId": "", "subnetId": "s-a"}]
        self.assertTrue(all(all(row[key] == 0 for key in v._COUNTS) for row in self.query(plan, rows)))
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
            result = v.validate_vpc(QUESTION, self.filled(plan), plan)
        self.assertTrue(result["valid"], result)
        quality = result["data_quality"]
        self.assertEqual(quality["blank_relation_port_keys"], 2)
        self.assertEqual(quality["blank_relation_subnet_keys"], 2)
        self.assertEqual(quality["vpcs_with_unresolved_subnets"], 0)

    def test_validation_reports_dangling_references_and_uses_independent_gets(self):
        plan = self.plan()
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(data()), create=True) as lookup:
            result = v.validate_vpc(QUESTION, self.filled(plan), plan)
        self.assertTrue(result["valid"], result)
        self.assertEqual(lookup.call_count, 4)
        self.assertTrue(all(len(call.args) == 1 for call in lookup.call_args_list))
        self.assertEqual(result["data_quality"]["scoped_vpcs"], 3)
        self.assertEqual(result["data_quality"]["scoped_unresolved_reference_count"], 2)
        self.assertEqual(result["data_quality"]["orphan_relation_port_ids"], 1)
        self.assertEqual(result["data_quality"]["blank_port_device_keys"], 2)
        self.assertEqual({entry["vpc_id"] for entry in result["data_quality"]["sample_unresolved_references"]}, {"v-a", "v-b"})

    def test_simple_table_aliases_and_region_variants_are_supported(self):
        item = source(); item["sql"] = "SELECT r.vdcName,r.name AS vpc_name FROM CLOUD_ROUTER AS r;"
        plan = self.plan(item)
        alternative = "SELECT x.vdcName,x.name AS vpc_name,x.id AS vpc_id,x.nativeId AS vpc_native_id FROM CLOUD_ROUTER x"
        self.assertEqual(self.query(plan, data()), self.query(plan, data(), alternative))
        for question in ["查询区域region_demo下各VPC的子网数量", "查询区域region_other下各VDC的VPC名称和子网总数"]:
            self.assertIsNotNone(v.plan_vpc(question, source()))

    def test_changed_field_shape_or_alias_returns_none_for_parent_fallback(self):
        plan = self.plan(); sql = plan["base_sql"]
        for changed in [sql.replace("vpc_name", "router_name"), sql.replace("vpc_id", "router_id"),
                        sql.replace("nativeId", "networkId"), sql.replace("vdcName", "tenantName"),
                        sql + " GROUP BY vdcName", sql + " ORDER BY name", sql + " LIMIT 1", SQL,
                        sql.replace("CLOUD_ROUTER", "CLOUD_SUBNET")]:
            with self.subTest(sql=changed): self.assertIsNone(v.compose_vpc(changed, plan))
        for changed in ["SELECT COUNT(*) AS vpc_count FROM CLOUD_ROUTER", SQL + " GROUP BY vdcName",
                        SQL + " WHERE status='active'", SQL.replace("vpc_name", "router_name")]:
            with self.subTest(sql=changed): self.assertIsNone(v.plan_vpc(QUESTION, dict(source(), sql=changed)))

    def test_question_rejects_unknown_scope_or_extra_requested_resources(self):
        for question in [QUESTION.replace("region_demo", "region_demo和region_other"), QUESTION + "且租户owner",
                         QUESTION + "且VDCowner", QUESTION + "且可用区az0.dc0", QUESTION + "及安全组数量",
                         QUESTION + "按最多排序前5", QUESTION.replace("子网数量", "子网CIDR"),
                         "查询区域region_demo下VPC名称和子网数量", "查询各VPC子网数量", QUESTION + "且VPC名为router-a",
                         QUESTION + "且nativeId=n-a"]:
            with self.subTest(question=question): self.assertIsNone(v.plan_vpc(question, source()))

    def test_root_call_duplicates_must_be_exact_and_no_extra_filters_are_allowed(self):
        for change in ["different_scope", "extra_filter", "method", "url_filter", "third_call", "lookup_in_source"]:
            item = source()
            if change == "different_scope": item["api_call"][1]["condition"]["constraint"][0]["simple"]["value"] = "region_other"
            elif change == "extra_filter":
                for call in item["api_call"]: call["condition"]["constraint"].append({"simple": {"name": "status", "value": "active"}})
            elif change == "method":
                for call in item["api_call"]: call["method"] = "POST"
            elif change == "url_filter":
                for call in item["api_call"]: call["url"] += "&condition=unknown"
            elif change == "third_call": item["api_call"].append(copy.deepcopy(item["api_call"][0]))
            else: item["api_call"][1] = v._lookup("SUBNET")
            with self.subTest(change=change): self.assertIsNone(v.plan_vpc(QUESTION, item))

    def test_schema_relationship_and_compilation_are_required_before_planning(self):
        for ci, fields in v._FIELDS.items():
            for field in fields:
                schema = copy.deepcopy(v._FIELDS); schema[ci].remove(field)
                with self.subTest(ci=ci, field=field), patch.object(m, "_schema_columns", schema):
                    self.assertIsNone(v.plan_vpc(QUESTION, source()))
        with patch.object(m, "JOIN_RELATIONS", RELATIONS.splitlines()[0]):
            self.assertIsNone(v.plan_vpc(QUESTION, source()))
        with patch.object(v.sqlite3, "connect", side_effect=sqlite3.OperationalError("compile failure")):
            self.assertIsNone(v.plan_vpc(QUESTION, source()))

    def test_changed_filled_scope_or_lookup_filters_make_no_get(self):
        plan = self.plan()
        for change in ["unresolved", "region", "filter", "shape", "lookup"]:
            item = self.filled(plan)
            if change == "unresolved": item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "{{logicalRegionName}}"
            elif change == "region": item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "region_other"
            elif change == "filter": item["api_call"][1]["condition"] = {"constraint": [{"simple": {"name": "id", "value": "one"}}]}
            elif change == "shape": item["sql"] = SQL
            else: item["api_call"].append(copy.deepcopy(item["api_call"][1]))
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api", create=True) as lookup:
                self.assertFalse(v.validate_vpc(QUESTION, item, plan)["valid"])
                lookup.assert_not_called()

    def test_empty_resources_stop_before_later_native_gets(self):
        plan = self.plan()
        for step, ci in enumerate(v._TABLES, 1):
            rows = data(); rows[ci] = []
            with self.subTest(ci=ci), patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True) as lookup:
                result = v.validate_vpc(QUESTION, self.filled(plan), plan)
                self.assertFalse(result["valid"], result)
                self.assertEqual(result["reason"], "empty_vpc_resource")
                self.assertEqual(lookup.call_count, step)

    def test_missing_fields_are_rejected_even_when_other_rows_have_them(self):
        plan = self.plan()
        for step, (ci, fields) in enumerate(v._FIELDS.items(), 1):
            for field in fields:
                rows = data(); rows[ci][0].pop(field)
                with self.subTest(ci=ci, field=field), patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True) as lookup:
                    self.assertFalse(v.validate_vpc(QUESTION, self.filled(plan), plan)["valid"])
                    self.assertEqual(lookup.call_count, step)

    def test_empty_or_duplicate_identities_cannot_form_empty_key_products(self):
        plan = self.plan()
        for ci, fields in [("ROUTER", ["id", "nativeId"]), ("PORT", ["id"]), ("SUBNET", ["id"])]:
            for field in fields:
                for value in [None, "", " "] + (["duplicate"] if ci == "ROUTER" else []):
                    rows = data()
                    if value == "duplicate": rows[ci][1][field] = rows[ci][0][field]
                    else: rows[ci][0][field] = value
                    with self.subTest(ci=ci, field=field, value=value), \
                            patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
                        self.assertFalse(v.validate_vpc(QUESTION, self.filled(plan), plan)["valid"])

    def test_duplicate_lookup_rows_are_counted_once_but_conflicting_port_owners_are_rejected(self):
        plan = self.plan(); rows = data()
        rows["PORT"].append(copy.deepcopy(rows["PORT"][0]))
        rows["SUBNET"].append(copy.deepcopy(rows["SUBNET"][0]))
        self.assertEqual(self.query(plan, rows), self.query(plan, data()))
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
            result = v.validate_vpc(QUESTION, self.filled(plan), plan)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["data_quality"]["duplicate_port_rows"], 1)
        self.assertEqual(result["data_quality"]["duplicate_subnet_rows"], 1)
        rows["PORT"][-1]["devNativeId"] = "n-b"
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
            result = v.validate_vpc(QUESTION, self.filled(plan), plan)
        self.assertFalse(result["valid"], result)
        self.assertEqual(result["reason"], "conflicting_port_device_identity")

    def test_root_region_and_field_types_are_verified_from_native_results(self):
        plan = self.plan()
        for change in ["region", "router_type", "port_type", "relation_type", "subnet_type"]:
            rows = data()
            if change == "region": rows["ROUTER"][0]["logicalRegionName"] = "region_other"
            elif change == "router_type": rows["ROUTER"][0]["nativeId"] = 1
            elif change == "port_type": rows["PORT"][0]["devNativeId"] = []
            elif change == "relation_type": rows["R_PORT_IN_SUBNET"][0]["subnetId"] = {}
            else: rows["SUBNET"][0]["id"] = False
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
                self.assertFalse(v.validate_vpc(QUESTION, self.filled(plan), plan)["valid"])


if __name__ == "__main__":
    unittest.main()
