"""原执行器与合成安全组数据证明无消费者查找可裁剪，不打开用例文件。"""

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m
import runbook_executor as executor


def fixture():
    return {"id": "synthetic_sg", "name": "synthetic groups", "examples": ["所有安全组"],
            "api_call": [{"method": "GET", "url": "/rest/hackthon/db/instances/ROUTER", "condition": {
                "constraint": [{"simple": {"name": "name", "value": "{{name}}", "operator": "equal"}}]}},
                {"method": "GET", "url": "/rest/hackthon/db/instances/SECURITY_GROUP"}],
            "sql": "SELECT g.id,COUNT(r.id) AS n FROM CLOUD_SECURITY_GROUP g JOIN CLOUD_SECURITY_GROUP_RULE r ON g.id=r.securityGroupId GROUP BY g.id"}


class PruneLookupTests(unittest.TestCase):
    def test_global_scope_removes_only_unconsumed_lookup(self):
        item = fixture()
        evidence = m._prune_unused_lookups(item, "查询所有安全组和规则数量")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["resource"], "ROUTER")
        self.assertEqual(m._get_placeholders(item), [])
        self.assertEqual(len(item["api_call"]), 1)

    def test_native_result_is_independent_of_removed_table(self):
        source = {"ROUTER": [{"id": "router_else"}], "SECURITY_GROUP": [{"id": "g1"}, {"id": "g2"}],
                  "SECURITY_GROUP_RULE": [{"id": "a", "securityGroupId": "g1"}, {"id": "b", "securityGroupId": "g1"},
                                          {"id": "c", "securityGroupId": "g2"}]}
        wire = []

        def query(ci, conditions=None):
            wire.append(ci)
            return source[ci]

        item = fixture()
        m._prune_unused_lookups(item, "所有安全组及规则数量")
        self.assertTrue(m._fill_params(item, {}, "所有安全组及规则数量"))
        with patch.object(executor, "_query_server", side_effect=query):
            actual = executor.execute(item)
            self.assertNotIn("ROUTER", wire)
            expected = fixture()
            self.assertTrue(m._fill_params(expected, {"name": "other-router"}))
            control = executor.execute(expected)
        self.assertEqual(actual["result"], control["result"])
        self.assertEqual(actual["result"]["rows"], [{"id": "g1", "n": 2}, {"id": "g2", "n": 1}])

    def test_named_resource_and_absent_global_scope_are_kept(self):
        for question in ["VPCrouter_test中的所有安全组", "查询安全组列表", "查询名称为router_test的全部VPC下安全组"]:
            with self.subTest(question=question):
                item = fixture()
                self.assertFalse(m._prune_unused_lookups(item, question))
                self.assertEqual(len(item["api_call"]), 2)

    def test_consumed_table_is_kept(self):
        item = fixture()
        item["sql"] += " JOIN CLOUD_ROUTER x ON x.id=g.id"
        self.assertFalse(m._prune_unused_lookups(item, "所有安全组"))

    def test_quoted_table_and_nested_sql_are_not_inferred(self):
        for sql in ['SELECT id FROM "CLOUD_ROUTER"', "SELECT id FROM (SELECT id FROM CLOUD_SECURITY_GROUP)"]:
            with self.subTest(sql=sql):
                item = fixture()
                item["sql"] = sql
                self.assertFalse(m._prune_unused_lookups(item, "所有安全组"))

    def test_dependency_and_shared_placeholder_are_kept(self):
        item = fixture()
        item["api_call"][1]["condition"] = {"constraint": [{"simple": {"name": "id", "value": "{{id from step 1}}"}}]}
        self.assertFalse(m._prune_unused_lookups(item, "所有安全组"))
        item = fixture()
        item["params"] = {"condition": [{"name": "name", "value": "{{name}}"}]}
        self.assertFalse(m._prune_unused_lookups(item, "所有安全组"))

    def test_matching_flag_controls_unblocking(self):
        item = fixture()
        retriever = SimpleNamespace(retrieve=lambda question: [SimpleNamespace(id=item["id"])])
        schema = {"SECURITY_GROUP": ["id"], "SECURITY_GROUP_RULE": ["id", "securityGroupId"], "ROUTER": ["id", "name"]}

        def model(prompt, stage="unknown"):
            return "1" if stage == "select" else "{}" if stage == "fill" else item["sql"]

        with patch.object(m, "_schema_columns", schema), patch.object(m, "llm_ask", side_effect=model), \
                patch.object(m, "_get_table_schemas", return_value="synthetic"):
            for flag, expected in [("0", False), ("1", True)]:
                import os
                with self.subTest(flag=flag), patch.dict(os.environ, {"RUNBOOK_PRUNE_UNUSED_LOOKUPS": flag, "RUNBOOK_RULE_ONLY_FILL": "1"}):
                    self.assertEqual(m.match_runbook("所有安全组和规则数量", [copy.deepcopy(item)], retriever) is not None, expected)


if __name__ == "__main__":
    unittest.main()
