"""具名VM网卡与子网CIDR补全：只用合成API和内存SQLite，不读取真实用例。"""

import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m
import runbook_network_details as n


QUESTION = "虚拟机vm-demo有几块网卡，分别关联的子网CIDR是什么"
SQL = "SELECT COUNT(*) AS port_count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_PORT ON CLOUD_VM_NOVA.resId=CLOUD_PORT.devId"
RELATIONS = "\n".join(left + " = " + right for left, right in n._EDGES)


def source(two_steps=False):
    calls = [{"method": "GET", "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
              "condition": {"constraint": [{"simple": {"name": "name", "value": "{{name}}", "operator": "equal"}}]}}]
    if two_steps:
        calls.append(n._call("PORT", "devId", "{{resId from step 1}}", "equal"))
    return {"api_call": calls if two_steps else calls[0],
            "sql": "SELECT COUNT(*) AS port_count FROM CLOUD_PORT" if two_steps else SQL}


def data():
    return {"VM_NOVA": [{"name": "vm-demo", "resId": "vm-res"}],
            "PORT": [{"id": "p-a", "devId": "vm-res"}, {"id": "p-b", "devId": "vm-res"}],
            "R_PORT_IN_SUBNET": [{"portId": "p-a", "subnetId": "s-a"},
                                 {"portId": "p-a", "subnetId": "s-b"},
                                 {"portId": "p-b", "subnetId": "s-b"}],
            "SUBNET": [{"id": "s-a", "cidr": "10.0.0.0/24"}, {"id": "s-b", "cidr": "10.0.1.0/24"}]}


class NetworkDetailsTests(unittest.TestCase):
    def setUp(self):
        context = patch.object(m, "_schema_columns", copy.deepcopy(n._FIELDS), create=True)
        context.start(); self.addCleanup(context.stop)
        context = patch.object(m, "JOIN_RELATIONS", RELATIONS, create=True)
        context.start(); self.addCleanup(context.stop)

    def plan(self, item=None):
        plan = n.plan_network(QUESTION, item or source())
        self.assertIsNotNone(plan)
        return plan

    def filled(self, plan):
        item = copy.deepcopy(plan["item"])
        item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "vm-demo"
        return item

    def lookup(self, rows):
        def execute(call, previous=None):
            ci = n._endpoint(call)
            return copy.deepcopy(rows[ci]), n._TABLES[ci]
        return execute

    def query(self, plan, rows):
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            for ci, fields in n._FIELDS.items():
                connection.execute("CREATE TABLE " + n._TABLES[ci] + "(" + ",".join(field + " TEXT" for field in fields) + ")")
                connection.executemany("INSERT INTO " + n._TABLES[ci] + " VALUES (" + ",".join("?" for _ in fields) + ")",
                                       [tuple(row.get(field) for field in fields) for row in rows[ci]])
            return dict(connection.execute(n.compose_network(plan["base_sql"], plan)).fetchone())

    def test_plan_accepts_native_single_vm_and_known_two_step_prefix(self):
        for item in [source(), dict(source(), api_call=[source()["api_call"]]), source(True)]:
            before = copy.deepcopy(item)
            plan = self.plan(item)
            self.assertEqual(item, before)
            self.assertEqual(plan["item"]["sql"], item["sql"])
            self.assertEqual([n._endpoint(call) for call in plan["item"]["api_call"]], list(n._TABLES))
            self.assertEqual([n._constraint(call)[1] for call in plan["item"]["api_call"]][1:],
                             ["{{resId from step 1}}", "{{id from step 2}}", "{{subnetId from step 3}}"])

    def test_count_remains_two_when_one_port_has_multiple_subnets(self):
        for item in [source(), source(True)]:
            plan = self.plan(item)
            for cidrs in [("10.0.0.0/24", "10.0.1.0/24"), ("a1b2c3d4/20", "e5f6a7b8/28")]:
                rows = data()
                for subnet, cidr in zip(rows["SUBNET"], cidrs):
                    subnet["cidr"] = cidr
                with self.subTest(mode=plan["base_shape"]["mode"], cidrs=cidrs):
                    with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
                        self.assertTrue(n.validate_network(QUESTION, self.filled(plan), plan)["valid"])
                    row = self.query(plan, rows)
                    details = json.loads(row["port_subnet_details"])
                    self.assertEqual(row["port_count"], 2)
                    self.assertEqual(len(details), 3)
                    self.assertEqual({(part["port_id"], part["subnet_id"]) for part in details},
                                     {("p-a", "s-a"), ("p-a", "s-b"), ("p-b", "s-b")})
                    self.assertEqual({part["cidr"] for part in details}, set(cidrs))

    def test_left_join_keeps_port_without_subnet_and_deduplicates_relation_pairs(self):
        plan = self.plan(); rows = data()
        rows["R_PORT_IN_SUBNET"] = [rows["R_PORT_IN_SUBNET"][0]] * 2
        rows["SUBNET"] = [rows["SUBNET"][0]]
        row = self.query(plan, rows)
        details = json.loads(row["port_subnet_details"])
        self.assertEqual(row["port_count"], 2)
        self.assertEqual(details, [{"port_id": "p-a", "subnet_id": "s-a", "cidr": "10.0.0.0/24"},
                                   {"port_id": "p-b", "subnet_id": None, "cidr": None}])
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
            result = n.validate_network(QUESTION, self.filled(plan), plan)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["unmapped_ports"], 1)

    def test_equivalent_simple_aliases_allowed_but_base_shape_changes_rejected(self):
        plan = self.plan()
        equivalent = "SELECT COUNT(*) AS port_count FROM CLOUD_VM_NOVA AS v JOIN CLOUD_PORT p ON p.devId=v.resId"
        self.assertIsNotNone(n.compose_network(equivalent, plan))
        for sql in [SQL.replace("port_count", "new_count"), SQL.replace("COUNT(*)", "COUNT(DISTINCT CLOUD_PORT.id)"),
                    SQL.replace("resId", "id"), SQL + " GROUP BY CLOUD_PORT.id", SQL + " LIMIT 1",
                    SQL.replace("CLOUD_PORT", "CLOUD_SUBNET"), "SELECT COUNT(*) AS port_count FROM CLOUD_PORT"]:
            with self.subTest(sql=sql): self.assertIsNone(n.compose_network(sql, plan))

    def test_question_requires_explicit_name_count_association_and_cidr_only(self):
        for question in [QUESTION.replace("vm-demo", "other-vm") + "且租户tenant-a", QUESTION + "且区域region_other",
                         QUESTION.replace("CIDR", "名称"), QUESTION.replace("有几块网卡", "有哪些网卡"),
                         "所有虚拟机有几块网卡，分别关联的子网CIDR是什么", QUESTION + "及安全组列表"]:
            with self.subTest(question=question): self.assertIsNone(n.plan_network(question, source()))
        item = source(); item["api_call"]["condition"]["constraint"][0]["simple"]["value"] = "vm-other"
        self.assertIsNone(n.plan_network(QUESTION, item))

    def test_scope_filters_methods_duplicate_resources_and_bad_dependencies_rejected(self):
        for change in ["filter", "method", "query_filter", "wrong_relation", "duplicate"]:
            item = source(True)
            if change == "filter":
                item["api_call"][0]["condition"]["constraint"].append({"simple": {"name": "status", "value": "active"}})
            elif change == "method": item["api_call"][0]["method"] = "POST"
            elif change == "query_filter": item["api_call"][0]["url"] += "&condition=unknown"
            elif change == "wrong_relation": item["api_call"][1]["condition"]["constraint"][0]["simple"]["value"] = "{{id from step 1}}"
            else: item["api_call"].append(copy.deepcopy(item["api_call"][1]))
            with self.subTest(change=change): self.assertIsNone(n.plan_network(QUESTION, item))

    def test_missing_schema_relation_or_json_compile_proof_prevents_plan(self):
        for ci, fields in n._FIELDS.items():
            for field in fields:
                schema = copy.deepcopy(n._FIELDS); schema[ci].remove(field)
                with self.subTest(ci=ci, field=field), patch.object(m, "_schema_columns", schema):
                    self.assertIsNone(n.plan_network(QUESTION, source()))
        with patch.object(m, "JOIN_RELATIONS", RELATIONS.splitlines()[0]):
            self.assertIsNone(n.plan_network(QUESTION, source()))
        with patch.object(n.sqlite3, "connect", side_effect=sqlite3.OperationalError("JSON unavailable")):
            self.assertIsNone(n.plan_network(QUESTION, source()))

    def test_validation_uses_four_native_steps_with_previous_records(self):
        plan = self.plan()
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup(data()), create=True) as lookup:
            result = n.validate_network(QUESTION, self.filled(plan), plan)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["port_count"], 2)
        self.assertEqual(lookup.call_count, 4)
        self.assertTrue(all(0 < check["request_line_bytes"] <= 60000 for check in result["tables"]))
        self.assertIsNone(lookup.call_args_list[0].args[1])
        self.assertEqual(lookup.call_args_list[2].args[1], data()["PORT"])

    def test_empty_step_stops_before_any_later_lookup(self):
        plan = self.plan()
        for step, ci in enumerate(n._TABLES, 1):
            rows = data(); rows[ci] = []
            with self.subTest(ci=ci), patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True) as lookup:
                result = n.validate_network(QUESTION, self.filled(plan), plan)
                self.assertFalse(result["valid"], result)
                self.assertEqual(result["reason"], "empty_network_resource")
                self.assertEqual(lookup.call_count, step)

    def test_missing_or_false_required_field_stops_at_source(self):
        plan = self.plan()
        for step, (ci, fields) in enumerate(n._FIELDS.items(), 1):
            for field in fields:
                invalid = [None, "", "x" * 513] if field == "cidr" else [None, "", False, []]
                for value in invalid:
                    rows = data(); rows[ci][0][field] = value
                    with self.subTest(ci=ci, field=field, value=value), \
                            patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True) as lookup:
                        result = n.validate_network(QUESTION, self.filled(plan), plan)
                        self.assertFalse(result["valid"], result)
                        self.assertEqual(lookup.call_count, step)

    def test_no_lookup_for_unresolved_name_mutated_scope_or_invalid_plan(self):
        plan = self.plan()
        for change in ["unresolved", "scope", "extra_filter", "shape"]:
            item = self.filled(plan)
            if change == "unresolved": item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "{{name}}"
            elif change == "scope": item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "vm-other"
            elif change == "extra_filter": item["api_call"][2]["condition"]["constraint"].append({"simple": {"name": "id", "value": "other"}})
            else: item["sql"] = item["sql"].replace("port_count", "changed")
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api", create=True) as lookup:
                self.assertFalse(n.validate_network(QUESTION, item, plan)["valid"])
                lookup.assert_not_called()

    def test_oversized_id_sets_and_long_ids_never_reach_next_request(self):
        plan = self.plan()
        for change, expected_calls in [("vm_id_length", 1), ("port_ids", 2), ("port_id_length", 2), ("subnet_ids", 3)]:
            rows = data()
            if change == "vm_id_length": rows["VM_NOVA"][0]["resId"] = "x" * 257
            elif change == "port_ids": rows["PORT"] = [{"id": "p-" + str(i), "devId": "vm-res"} for i in range(129)]
            elif change == "port_id_length": rows["PORT"][0]["id"] = "x" * 257
            else: rows["R_PORT_IN_SUBNET"] = [{"portId": "p-a", "subnetId": "s-" + str(i)} for i in range(129)]
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True) as lookup:
                self.assertFalse(n.validate_network(QUESTION, self.filled(plan), plan)["valid"])
                self.assertEqual(lookup.call_count, expected_calls)

    def test_foreign_dependency_dangling_subnet_and_duplicate_identity_rejected(self):
        plan = self.plan()
        for change in ["port_target", "relation_target", "subnet_target", "dangling", "duplicate_port", "duplicate_subnet"]:
            rows = data()
            if change == "port_target": rows["PORT"][0]["devId"] = "other-vm"
            elif change == "relation_target": rows["R_PORT_IN_SUBNET"][0]["portId"] = "other-port"
            elif change == "subnet_target": rows["SUBNET"][0]["id"] = "other-subnet"
            elif change == "dangling": rows["SUBNET"].pop()
            elif change == "duplicate_port": rows["PORT"].append(copy.deepcopy(rows["PORT"][0]))
            else: rows["SUBNET"].append(copy.deepcopy(rows["SUBNET"][0]))
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True):
                self.assertFalse(n.validate_network(QUESTION, self.filled(plan), plan)["valid"])

    def test_encoded_url_limit_stops_before_relation_get_even_with_bounded_ids(self):
        plan = self.plan()
        for character in ["%", "汉"]:
            rows = data()
            rows["PORT"] = [{"id": "p-" + str(i).zfill(3) + "-" + character * 250, "devId": "vm-res"}
                            for i in range(128)]
            self.assertEqual(len(rows["PORT"]), 128)
            self.assertTrue(all(len(row["id"]) == 256 for row in rows["PORT"]))
            with self.subTest(character=character), \
                    patch.object(m, "_execute_lookup_api", side_effect=self.lookup(rows), create=True) as lookup:
                result = n.validate_network(QUESTION, self.filled(plan), plan)
                self.assertFalse(result["valid"], result)
                self.assertEqual(result["reason"], "network_request_line_too_large")
                self.assertEqual(result["step"], 3)
                self.assertEqual(lookup.call_count, 2)
                self.assertTrue(all(check["request_line_bytes"] <= 60000 for check in result["tables"][:2]))
                self.assertGreater(result["tables"][2]["request_line_bytes"], 60000)
                self.assertIsNone(result["tables"][2]["rows"])


if __name__ == "__main__":
    unittest.main()
