"""精调行语义合同；使用合成列和重复数据验证，不调用模型。"""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m


class RowSemanticsTests(unittest.TestCase):
    def setUp(self):
        context = patch.object(m, "_schema_columns", {
            "VM_NOVA": ["id", "name", "status", "tenantName", "flavorId"],
            "FLAVOR": ["id", "name", "vcpuSize", "ramSize", "diskSize"],
        })
        context.start()
        self.addCleanup(context.stop)

    def policy(self, original, candidate, question="查询实例列表"):
        return m._row_semantics_contract(original, candidate, question)

    def test_removed_distinct_is_protected_only_when_enabled(self):
        original = "SELECT DISTINCT name,status FROM CLOUD_VM_NOVA"
        candidate = "SELECT name,status FROM CLOUD_VM_NOVA"
        for flag, expected in [("0", candidate), ("1", original)]:
            details = {}
            with self.subTest(flag=flag), patch.dict(os.environ, {"RUNBOOK_PRESERVE_ROW_SEMANTICS": flag,
                                                                "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "0"}):
                self.assertEqual(m._validated_refinement(candidate, original, "查询实例列表", details), expected)
                if flag == "1":
                    self.assertEqual(details["row_semantics_contract"]["reason"], "removed_template_distinct")

    def test_explicit_duplicate_request_can_remove_distinct(self):
        for question in ["查询实例名称，保留重复", "实例名不要去重", "列出实例，不去重"]:
            with self.subTest(question=question):
                self.assertFalse(self.policy("SELECT DISTINCT name FROM CLOUD_VM_NOVA",
                                             "SELECT name FROM CLOUD_VM_NOVA", question)["reject"])

    def test_count_distinct_change_requires_explicit_contract(self):
        original = "SELECT name,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY name"
        candidate = "SELECT name,COUNT(DISTINCT id) AS n FROM CLOUD_VM_NOVA GROUP BY name,id"
        self.assertEqual(self.policy(original, candidate)["reason"], "changed_count_distinct_contract")
        self.assertFalse(self.policy(original, candidate, "按名称和ID统计唯一实例ID数量")["reject"])
        self.assertTrue(self.policy(candidate, original)["reject"])

    def test_added_grouping_cannot_collapse_ungrouped_details(self):
        original = "SELECT tenantName,name,status FROM CLOUD_VM_NOVA"
        candidate = original + " GROUP BY tenantName"
        result = self.policy(original, candidate, "按租户分组展示实例名称和状态")
        self.assertEqual(result["reason"], "introduced_ungrouped_detail_columns")
        self.assertEqual(result["columns"], ["cloud_vm_nova.name", "cloud_vm_nova.status"])

    def test_alias_changes_and_group_aliases_are_equivalent(self):
        original = "SELECT v.tenantName,COUNT(*) AS n FROM CLOUD_VM_NOVA v GROUP BY v.tenantName"
        candidate = "SELECT x.tenantName AS tenant,COUNT(1) AS n FROM CLOUD_VM_NOVA AS x GROUP BY tenant"
        self.assertFalse(self.policy(original, candidate)["reject"])

    def test_explicit_new_group_dimension_preserves_refinement(self):
        original = "SELECT status,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY status"
        candidate = "SELECT tenantName,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY tenantName"
        self.assertFalse(self.policy(original, candidate, "按租户统计实例数量")["reject"])

    def test_new_count_distinct_output_is_not_an_existing_count_change(self):
        original = "SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA"
        candidate = "SELECT COUNT(*) AS total,COUNT(DISTINCT tenantName) AS tenants FROM CLOUD_VM_NOVA"
        self.assertFalse(self.policy(original, candidate, "实例总数和租户数量")["reject"])

    def test_coarser_grouping_cannot_silently_drop_configuration_columns(self):
        original = ("SELECT name,vcpuSize,ramSize,COUNT(*) AS n FROM CLOUD_FLAVOR "
                    "GROUP BY name,vcpuSize,ramSize ORDER BY n DESC LIMIT 3")
        candidate = "SELECT name,COUNT(*) AS n FROM CLOUD_FLAVOR GROUP BY name ORDER BY n DESC LIMIT 3"
        self.assertEqual(self.policy(original, candidate, "使用最多的前3种规格")["reason"],
                         "coarser_grouping_lost_output_columns")
        self.assertFalse(self.policy(original, candidate, "按名称汇总规格数量，返回前3种")["reject"])

    def test_legacy_bare_columns_do_not_become_new_regressions(self):
        original = "SELECT name,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY tenantName"
        self.assertFalse(self.policy(original, original)["reject"])

    def test_nested_union_window_and_ordinal_grouping_are_not_guessed(self):
        for sql in ["SELECT name FROM (SELECT name FROM CLOUD_VM_NOVA)",
                    "SELECT name FROM CLOUD_VM_NOVA UNION ALL SELECT name FROM CLOUD_FLAVOR",
                    "SELECT name,COUNT(*) OVER() FROM CLOUD_VM_NOVA",
                    "SELECT name,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY 1"]:
            with self.subTest(sql=sql):
                self.assertFalse(self.policy(sql, sql)["reject"])
                self.assertIsNone(m._flat_grouping(sql))

    def test_constants_and_literals_do_not_become_ungrouped_columns(self):
        before = "SELECT status,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY status"
        for literal in ["NULL", "0", "'fixed'", "TRUE"]:
            candidate = f"SELECT status,{literal} AS constant,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY status"
            with self.subTest(literal=literal):
                self.assertFalse(self.policy(before, candidate)["reject"])

    def test_join_correction_with_same_output_is_allowed(self):
        original = ("SELECT DISTINCT v.name FROM CLOUD_VM_NOVA v JOIN CLOUD_FLAVOR f ON v.flavorId=f.id")
        candidate = original.replace("v.flavorId=f.id", "v.flavorId=f.name")
        self.assertFalse(self.policy(original, candidate)["reject"])

    def test_repeated_data_proves_distinct_and_group_collapse_change_rows(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE CLOUD_VM_NOVA (name TEXT,status TEXT,tenantName TEXT)")
            connection.executemany("INSERT INTO CLOUD_VM_NOVA VALUES (?,?,?)",
                                   [("a", "up", "t"), ("a", "up", "t"), ("b", "down", "t")])
            distinct = "SELECT DISTINCT name,status FROM CLOUD_VM_NOVA"
            duplicate = "SELECT name,status FROM CLOUD_VM_NOVA"
            collapsed = duplicate + " GROUP BY tenantName"
            self.assertEqual([len(connection.execute(sql).fetchall()) for sql in [distinct, duplicate, collapsed]], [2, 3, 1])
            self.assertTrue(self.policy(distinct, duplicate)["reject"])
            self.assertTrue(self.policy(duplicate, collapsed)["reject"])


if __name__ == "__main__":
    unittest.main()
