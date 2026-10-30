"""模板输出契约候选的边界和开关回归；不调用模型。"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m


class ProjectionContractTests(unittest.TestCase):
    def setUp(self):
        context = patch.object(m, "_schema_columns", {"VM_NOVA": ["name", "createdAt", "status", "tenantName"]})
        context.start()
        self.addCleanup(context.stop)

    def test_missing_identity_column_is_protected_only_when_enabled(self):
        original = "SELECT name,createdAt FROM CLOUD_VM_NOVA"
        refined = "SELECT createdAt FROM CLOUD_VM_NOVA"
        for flag, expected in [("0", refined), ("1", original)]:
            with self.subTest(flag=flag), patch.dict(os.environ, {"RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": flag}):
                self.assertEqual(m._validated_refinement(refined, original, "查询创建时间"), expected)

    def test_adding_columns_is_allowed(self):
        decision = m._projection_contract("SELECT name FROM CLOUD_VM_NOVA",
                                          "SELECT name,status FROM CLOUD_VM_NOVA")
        self.assertFalse(decision["reject"])

    def test_explicit_grouping_change_is_not_forced_back(self):
        decision = m._projection_contract("SELECT status,COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY status",
                                          "SELECT tenantName,COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY tenantName")
        self.assertFalse(decision["reject"])
        self.assertEqual(decision["reason"], "query_structure_changed")

    def test_unknown_original_projection_is_not_guessed(self):
        decision = m._projection_contract("SELECT missing_column FROM CLOUD_VM_NOVA",
                                          "SELECT name FROM CLOUD_VM_NOVA")
        self.assertFalse(decision["reject"])
        self.assertEqual(decision["reason"], "projection_unknown")
