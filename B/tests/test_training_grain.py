"""合成同名不同ID数据证明聚合粒度，完全不读取用例文件。"""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m


class AggregateGrainTests(unittest.TestCase):
    def setUp(self):
        context = patch.object(m, "_schema_columns", {"HOST": ["id", "name", "ipAddress", "status"],
                                                     "VM_NOVA": ["id", "name", "hostId", "status", "tenantName"]})
        context.start()
        self.addCleanup(context.stop)
        context = patch.dict(os.environ, {"RUNBOOK_PRESERVE_AGGREGATE_GRAIN": "1"})
        context.start()
        self.addCleanup(context.stop)

    def test_new_identity_dimension_changes_counts(self):
        before = "SELECT name,COUNT(*) AS n FROM CLOUD_HOST GROUP BY name"
        after = "SELECT name,COUNT(*) AS n FROM CLOUD_HOST GROUP BY id,name"
        self.assertEqual(m._row_semantics_contract(before, after, "主机数量")["reason"], "changed_aggregate_grain_without_request")
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE CLOUD_HOST (id TEXT,name TEXT)")
            connection.executemany("INSERT INTO CLOUD_HOST VALUES (?,?)", [("one", "same"), ("two", "same")])
            self.assertEqual(connection.execute(before).fetchall(), [("same", 2)])
            self.assertEqual(connection.execute(after).fetchall(), [("same", 1), ("same", 1)])

    def test_explicit_regroup_is_allowed(self):
        before = "SELECT status,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY status"
        after = "SELECT tenantName,COUNT(*) AS n FROM CLOUD_VM_NOVA GROUP BY tenantName"
        self.assertFalse(m._row_semantics_contract(before, after, "按租户统计实例数量")["reject"])

    def test_same_identity_attributes_are_allowed(self):
        before = "SELECT id,COUNT(*) AS n FROM CLOUD_HOST GROUP BY id"
        after = "SELECT id,name,COUNT(*) AS n FROM CLOUD_HOST GROUP BY id,name"
        self.assertFalse(m._row_semantics_contract(before, after, "主机列表")["reject"])

    def test_alias_only_change_is_allowed(self):
        before = "SELECT h.name,COUNT(*) AS n FROM CLOUD_HOST h GROUP BY h.name"
        after = "SELECT x.name,COUNT(*) AS n FROM CLOUD_HOST AS x GROUP BY x.name"
        self.assertFalse(m._row_semantics_contract(before, after, "主机分布")["reject"])

    def test_global_count_cannot_silently_split(self):
        before = "SELECT COUNT(*) AS n FROM CLOUD_HOST"
        after = "SELECT status,COUNT(*) AS n FROM CLOUD_HOST GROUP BY status"
        self.assertTrue(m._row_semantics_contract(before, after, "主机总数")["reject"])

    def test_disabled_flag_preserves_previous_policy(self):
        with patch.dict(os.environ, {"RUNBOOK_PRESERVE_AGGREGATE_GRAIN": "0"}):
            self.assertFalse(m._row_semantics_contract("SELECT name,COUNT(*) AS n FROM CLOUD_HOST GROUP BY name",
                                                     "SELECT name,COUNT(*) AS n FROM CLOUD_HOST GROUP BY id,name", "主机数量")["reject"])


if __name__ == "__main__":
    unittest.main()
