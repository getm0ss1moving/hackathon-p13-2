"""选择与SQL精调合同；模拟模型输出，不验证模型的语义准确率。"""

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m
from test_params import template


class MatchingSQLTests(unittest.TestCase):
    def setUp(self):
        self.retriever = Mock()
        self.retriever.retrieve.return_value = [SimpleNamespace(id="fixture", tier="strong")]
        self.schemas = patch.object(m, "_schema_columns", {
            "VM_NOVA": ["name", "status", "privateIps", "logicalRegionName"],
            "VOLUME": ["name", "size"]})
        self.schemas.start()
        self.addCleanup(self.schemas.stop)
        schema_text = patch.object(m, "_get_table_schemas", return_value="本地测试字段")
        schema_text.start()
        self.addCleanup(schema_text.stop)

    def test_explicit_refusal_and_invalid_indices_never_force_top1(self):
        for answer in ["0", "-1", "2", "不确定", "1 或 0"]:
            with self.subTest(answer=answer), patch.object(m, "llm_ask", return_value=answer) as llm:
                details = {}
                self.assertIsNone(m.match_runbook("查询ECS名称", [template()], self.retriever, details))
                self.assertIn(details["reason"], ["selector_refused", "invalid_selection"])
                self.assertEqual(llm.call_count, 1)

    def test_zero_placeholder_template_still_refines_sql(self):
        sql = "SELECT name, status FROM CLOUD_VM_NOVA"
        with patch.object(m, "llm_ask", side_effect=["1", sql]) as llm:
            result = m.match_runbook("查询ECS名称和状态", [template()], self.retriever)
        self.assertEqual(result["sql"], sql)
        self.assertEqual([c.kwargs["stage"] for c in llm.call_args_list], ["select", "refine"])

    def test_ip_output_does_not_require_ip_filter(self):
        item = template("logicalRegionName")
        item["sql"] = "SELECT name, privateIps FROM CLOUD_VM_NOVA"
        with patch.object(m, "llm_ask", side_effect=["1", "logicalRegionName=region_new", item["sql"]]):
            result = m.match_runbook("查询区域region_new下ECS名称和IP地址", [item], self.retriever)
        self.assertIsNotNone(result)

    def test_explicit_region_cannot_be_silently_ignored(self):
        with patch.object(m, "llm_ask", return_value="1") as llm:
            details = {}
            result = m.match_runbook("查询区域region_new下ECS名称", [template()], self.retriever, details)
        self.assertIsNone(result)
        self.assertEqual(details["reason"], "missing_api_filter")
        self.assertEqual(llm.call_count, 1)

    def test_top_n_and_original_count_alias_are_preserved(self):
        for sql, question in [
            ("SELECT name FROM CLOUD_VM_NOVA ORDER BY name LIMIT 3", "查询区域region_new前3台ECS名称"),
            ("SELECT COUNT(*) AS count FROM CLOUD_VM_NOVA", "查询区域region_new的ECS数量"),
        ]:
            with self.subTest(sql=sql):
                item = template("logicalRegionName")
                item["sql"] = sql
                with patch.object(m, "llm_ask", side_effect=["1", "logicalRegionName=region_new", sql]):
                    result = m.match_runbook(question, [item], self.retriever)
                self.assertEqual(result["sql"], sql)

    def test_invalid_sql_falls_back_before_executor(self):
        original = "SELECT name FROM CLOUD_VM_NOVA"
        invalid = [
            "SELECT name FROM CLOUD_VM_NOVA; DELETE FROM CLOUD_VM_NOVA",
            "SELECT imaginary_field FROM CLOUD_VM_NOVA",
            "SELECT name FROM CLOUD_VOLUME",
            "SELECT name FROM CLOUD_VM_NOVA WHERE status='active'",
            "SELECT name FROM CLOUD_VM_NOVA LIMIT 1",
            "这是SQL：SELECT name FROM CLOUD_VM_NOVA",
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                self.assertEqual(m._validated_refinement(candidate, original, "查询ECS名称"), original)

    def test_sql_literals_and_comments_are_not_treated_as_commands(self):
        original = "SELECT name FROM CLOUD_VM_NOVA"
        candidate = "SELECT name, '; DELETE FROM example' AS note FROM CLOUD_VM_NOVA; -- harmless"
        self.assertEqual(m._validated_refinement(candidate, original, "查询ECS名称"), candidate)

    def test_existing_union_template_is_preserved(self):
        sql = "SELECT name FROM CLOUD_VM_NOVA UNION ALL SELECT name FROM CLOUD_VOLUME"
        item = template()
        item["resources"] = ["VM_NOVA", "VOLUME"]
        item["sql"] = sql
        item["api_call"] = [item["api_call"], template(resource="VOLUME")["api_call"]]
        with patch.object(m, "llm_ask", side_effect=["1", sql]):
            result = m.match_runbook("查询ECS和云硬盘名称", [item], self.retriever)
        self.assertEqual(result["sql"], sql)

    def test_schema_missing_and_refine_failure_keep_original(self):
        original = "SELECT name FROM CLOUD_VM_NOVA"
        with patch.object(m, "_schema_columns", {}):
            self.assertEqual(m._validated_refinement("SELECT name,status FROM CLOUD_VM_NOVA", original, "查询ECS"), original)
        with patch.object(m, "llm_ask", side_effect=RuntimeError("fixture")):
            self.assertEqual(m._refine_sql("查询ECS", original), original)

    def test_resource_words_inside_entity_name_do_not_trigger_mismatch(self):
        item = template("name")
        question = '查询ECS“exporter-host-42”的名称'
        with patch.object(m, "llm_ask", side_effect=["1", "name=exporter-host-42", item["sql"]]):
            self.assertIsNotNone(m.match_runbook(question, [item], self.retriever))

    def test_truncated_model_output_refuses_only_current_query(self):
        for answers, item, reason in [
            ([m.ModelOutputError("truncated")], template(), "invalid_model_output_select"),
            (["1", m.ModelOutputError("truncated")], template("name"), "invalid_model_output_fill"),
        ]:
            with self.subTest(reason=reason), patch.object(m, "llm_ask", side_effect=answers):
                details = {}
                self.assertIsNone(m.match_runbook("查询ECS new-vm 的名称", [item], self.retriever, details))
                self.assertEqual(details["reason"], reason)

    def test_transport_and_budget_failures_still_propagate(self):
        for error in [TimeoutError("network"), RuntimeError("budget")]:
            with self.subTest(error=type(error).__name__), patch.object(m, "llm_ask", side_effect=error):
                with self.assertRaises(type(error)):
                    m.match_runbook("查询ECS名称", [template()], self.retriever)


if __name__ == "__main__":
    unittest.main()
