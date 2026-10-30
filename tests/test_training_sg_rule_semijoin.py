"""依赖读取、真实条件账本及原SQL等价性；仅合成内存传输。"""

import copy
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system
from runbook_sg_rule_semijoin import plan_security_group_rule_semijoin
from runbook_retriever import RunbookRetriever
from test_bounded_api import MemorySession, book, call

SCHEMA = {"SECURITY_GROUP": ["id", "name"], "SECURITY_GROUP_RULE": ["id", "securityGroupId"]}
G1, G2, G3 = "a" * 32, "b" * 32, "c" * 32
R1, R2, R3 = "d" * 32, "f" * 32, "ab" * 16
SQL = ("SELECT g.name AS sg_name,g.id AS sg_id,COUNT(r.id) AS rule_count "
       "FROM CLOUD_SECURITY_GROUP g LEFT JOIN CLOUD_SECURITY_GROUP_RULE r "
       "ON g.id=r.securityGroupId GROUP BY g.name,g.id")


def fixture(sql=SQL):
    item = book(call("SECURITY_GROUP"), sql=sql)
    item.update(id="synthetic_group_counts", name="所有安全组列表及规则数量", resources=["CLOUD_SECURITY_GROUP"],
                examples=["查询所有安全组列表及规则数量"])
    return item


class SecurityGroupSemijoinRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.database = {"SECURITY_GROUP": [{"id": G1, "name": "one"}, {"id": G2, "name": "two"}, {"id": G3, "name": "empty"}],
                         "SECURITY_GROUP_RULE": [{"id": R1, "securityGroupId": G1}, {"id": R2, "securityGroupId": G1},
                                                 {"id": R3, "securityGroupId": G2}]}
        for target, name, replacement in [(matcher, "_schema_columns", SCHEMA)]:
            context = patch.object(target, name, replacement);context.start();self.addCleanup(context.stop)
        context = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        context.start();self.addCleanup(context.stop)
        context = patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden"))
        context.start();self.addCleanup(context.stop)

    def prepared(self, item=None):
        decision = plan_security_group_rule_semijoin(item or fixture(), schema_columns=SCHEMA, ci_name_map=executor.CI_NAME_MAP)
        self.assertTrue(decision["eligible"], decision)
        return decision["item"]

    def bounded(self, item=None, database=None, **options):
        transport = MemorySession(self.database if database is None else database)
        diagnostics = {}
        result = system._execute_bounded_api(self.prepared(item), diagnostics, session=transport,
                                            sg_rule_semijoin=True, **options)
        return result, diagnostics, transport

    def test_partitioned_rule_reads_preserve_left_join_zero_counts_and_original_sql(self):
        item = fixture();before = copy.deepcopy(item)
        result, details, transport = self.bounded(item, max_values=1, page_size=1)
        self.assertEqual(item, before)
        self.assertEqual(result["sql"], SQL)
        self.assertEqual({row["sg_name"]: row["rule_count"] for row in result["result"]["rows"]},
                         {"one": 2, "two": 1, "empty": 0})
        self.assertEqual(details["steps"][1]["rows"], 3)
        self.assertEqual(details["steps"][1]["batches"], 3)
        self.assertEqual(len(details["bound_api_calls"]), len(transport.requests))
        for bound, sent in zip(details["bound_api_calls"], transport.requests):
            self.assertEqual(bound.get("condition", {}).get("constraint", []), sent["constraints"])
            self.assertIn(sent["url"].split("?", 1)[1].split("&condition", 1)[0], bound["url"])
        self.assertNotIn("{{", json.dumps(details["bound_api_calls"]))

    def test_complete_domain_matches_original_executor_with_unrelated_orphan_rule(self):
        self.database["SECURITY_GROUP_RULE"].append({"id": "ca" * 16, "securityGroupId": "db" * 16})
        item = fixture()
        with patch.object(executor, "_query_server", side_effect=lambda ci, conditions=None: copy.deepcopy(self.database[ci])):
            control = executor.execute(item)
        optimized, _, _ = self.bounded(item, max_values=1)
        self.assertEqual(optimized["result"], control["result"])

    def test_empty_parent_executes_typed_left_join_without_child_request(self):
        database = {"SECURITY_GROUP": [], "SECURITY_GROUP_RULE": self.database["SECURITY_GROUP_RULE"]}
        output, details, transport = self.bounded(database=database)
        self.assertEqual(output["result"]["columns"], ["sg_name", "sg_id", "rule_count"])
        self.assertEqual(output["result"]["rows"], [])
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(details["short_circuit"], "empty_verified_semijoin_root")

    def test_empty_parent_global_count_stays_one_zero_row(self):
        item = fixture("SELECT COUNT(*) AS total FROM CLOUD_SECURITY_GROUP g LEFT JOIN CLOUD_SECURITY_GROUP_RULE r ON g.id=r.securityGroupId")
        output, _, transport = self.bounded(item, {"SECURITY_GROUP": [], "SECURITY_GROUP_RULE": []})
        self.assertEqual(output["result"]["rows"], [{"total": 0}])
        self.assertEqual(len(transport.requests), 1)

    def test_unsupported_numeric_or_short_parent_key_defers_before_child(self):
        for value in ["01", 1, False, None, [], "short-key", "1e" + "0" * 30]:
            with self.subTest(value=value):
                output, details, transport = self.bounded(database={"SECURITY_GROUP": [{"id": value, "name": "one"}],
                                                                   "SECURITY_GROUP_RULE": []})
                self.assertIsNone(output)
                self.assertFalse(details["sql_executed"])
                self.assertEqual(len(transport.requests), 1)
                self.assertIn("defer_to_original", details["semijoin_outcome"])

    def test_unsupported_child_key_defers_without_executing_partial_sql(self):
        self.database["SECURITY_GROUP_RULE"][0]["id"] = 1
        output, details, _ = self.bounded()
        self.assertIsNone(output)
        self.assertFalse(details["sql_executed"])

    def test_root_partitioning_defers_before_generic_union_can_remove_duplicate_rows(self):
        item = fixture();item["api_call"] = [call("SECURITY_GROUP", ("id", "in", [G1, G2]))]
        self.database["SECURITY_GROUP"].append(copy.deepcopy(self.database["SECURITY_GROUP"][0]))
        result, details, transport = self.bounded(item, max_values=1)
        self.assertIsNone(result)
        self.assertEqual(transport.requests, [])
        self.assertFalse(details["sql_executed"])
        self.assertEqual(details["semijoin_outcome"], "unsupported_root_batches_defer_to_original_executor")

    def test_duplicate_identical_child_key_is_rejected_even_with_single_batch(self):
        self.database["SECURITY_GROUP_RULE"].append(copy.deepcopy(self.database["SECURITY_GROUP_RULE"][0]))
        for maximum in [1, 500]:
            with self.subTest(max_values=maximum), self.assertRaisesRegex(system._APIPlanRefusal, "duplicate_semijoin_child_key"):
                self.bounded(max_values=maximum)

    def test_wrong_batch_foreign_key_cannot_be_accepted_as_complete(self):
        def responder(session, ci, query):
            if ci == "SECURITY_GROUP_RULE":
                payload = {"objList": [{"id": R1, "securityGroupId": [G1]}], "totalNum": 1,
                           "pageSize": 10000, "totalPageNo": 1, "currentPage": 1}
                return SimpleNamespace(status_code=200, json=lambda: payload)
        with self.assertRaisesRegex(system._APIPlanRefusal, "semijoin_child_outside_requested_parent_ids"):
            system._execute_bounded_api(self.prepared(), {}, session=MemorySession(self.database, responder), sg_rule_semijoin=True)

    def test_mode_cannot_bypass_proof_with_right_join_or_unprepared_calls(self):
        for item in [fixture(), {**self.prepared(), "sql": SQL.replace("LEFT JOIN", "RIGHT JOIN")}]:
            transport = MemorySession(self.database)
            with self.assertRaisesRegex(system._APIPlanRefusal, "unverified_semijoin_plan"):
                system._execute_bounded_api(item, {}, session=transport, sg_rule_semijoin=True)
            self.assertEqual(transport.requests, [])

    def test_query_records_actual_bound_calls_after_bm25_select_and_refine(self):
        item = fixture()
        unrelated = [{"id": f"synthetic_background_{i}", "name": f"unrelated_resource_{i}",
                      "examples": [f"background_only_{i}"], "sql": "SELECT id FROM CLOUD_HOST"} for i in range(9)]
        items = [item, *unrelated];retriever = RunbookRetriever(items)
        question = "查询所有安全组列表及规则数量"
        retrieved = [candidate.id for candidate in retriever.retrieve(question)]
        self.assertIn(item["id"], retrieved)
        stages = []
        def model(prompt, stage):
            stages.append(stage)
            return str(retrieved.index(item["id"]) + 1) if stage == "select" else item["sql"]
        instance = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        instance.items, instance.retriever = items, retriever
        transport = MemorySession(self.database);original = system._execute_bounded_api
        flags = {"RUNBOOK_SG_RULE_SEMIJOIN": "1", "RUNBOOK_BOUNDED_API": "0", "RUNBOOK_VERIFIED_EMPTY_ROOT": "0"}
        with patch.dict(os.environ, flags), patch.object(matcher, "llm_ask", side_effect=model), \
                patch.object(matcher, "_get_table_schemas", return_value="synthetic schema"), \
                patch.object(system, "_execute_bounded_api", side_effect=lambda selected, diag, **kw:
                             original(selected, diag, session=transport, max_values=1, **kw)), \
                patch.object(system, "execute", side_effect=AssertionError("must use proved dependent plan")):
            output = instance.query(question)
        self.assertEqual(stages, ["select", "refine"])
        self.assertEqual(output["sql"], item["sql"])
        self.assertEqual(output["api_call"], output["diagnostics"]["sg_rule_semijoin"]["bound_api_calls"])
        self.assertEqual(len(output["api_call"]), len(transport.requests))
        self.assertNotIn("{{", json.dumps(output["api_call"]))

    def test_unsupported_key_query_uses_original_plan_and_reports_no_unexecuted_conditions(self):
        item = fixture();self.database["SECURITY_GROUP"][0]["id"] = "short-key"
        instance = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        instance.items, instance.retriever = [], None
        original = system._execute_bounded_api
        expected = {"sql": SQL, "result": {"columns": ["sg_name"], "rows": [], "row_count": 0}, "error": None}
        with patch.dict(os.environ, {"RUNBOOK_SG_RULE_SEMIJOIN": "1", "RUNBOOK_BOUNDED_API": "0"}), \
                patch.object(system, "match_runbook", return_value=item), \
                patch.object(system, "_execute_bounded_api", side_effect=lambda selected, diag, **kw:
                             original(selected, diag, session=MemorySession(self.database), **kw)), \
                patch.object(system, "execute", return_value=expected) as native:
            output = instance.query("synthetic")
        native.assert_called_once_with(item)
        self.assertEqual(output["api_call"], item["api_call"])

    def test_disabled_flag_keeps_original_executor_and_api(self):
        item = fixture();instance = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        instance.items, instance.retriever = [], None
        expected = {"sql": SQL, "result": {"columns": ["sg_name"], "rows": [], "row_count": 0}, "error": None}
        with patch.dict(os.environ, {"RUNBOOK_SG_RULE_SEMIJOIN": "0", "RUNBOOK_BOUNDED_API": "0", "RUNBOOK_VERIFIED_EMPTY_ROOT": "0"}), \
                patch.object(system, "match_runbook", return_value=item), \
                patch.object(system, "execute", return_value=expected) as native, \
                patch.object(system, "_execute_bounded_api", side_effect=AssertionError("must not optimize")):
            output = instance.query("synthetic")
        native.assert_called_once_with(item)
        self.assertEqual(output["api_call"], item["api_call"])


if __name__ == "__main__":
    unittest.main()
