"""SQL常量标签与原始字段的差别；全部合成SQL。"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m


class LiteralLabelTests(unittest.TestCase):
    def test_replacing_display_type_with_raw_class_is_rejected(self):
        before = "SELECT name,'compute' AS type FROM CLOUD_VM_NOVA"
        after = "SELECT name,class_Name AS type FROM CLOUD_VM_NOVA"
        self.assertTrue(m._literal_label_contract(before, after, "实例类型列表")["reject"])

    def test_union_branch_labels_are_checked(self):
        before = "SELECT 'node' AS type FROM CLOUD_VM_NOVA UNION ALL SELECT 'disk' AS type FROM CLOUD_VOLUME"
        after = before.replace("'disk' AS type", "class_Name AS type")
        decision = m._literal_label_contract(before, after, "所有资源类型")
        self.assertEqual(decision["changed_labels"][0]["arm"], 2)

    def test_keywords_commas_and_escaped_quotes_in_literal_are_preserved(self):
        before = "SELECT 'from,union select O''Brien' AS kind FROM CLOUD_VM_NOVA"
        self.assertFalse(m._literal_label_contract(before, before, "类型")["reject"])
        self.assertTrue(m._literal_label_contract(before, before.replace("'from,union select O''Brien'", "class_Name"), "类型")["reject"])

    def test_explicit_raw_column_request_is_allowed(self):
        self.assertFalse(m._literal_label_contract("SELECT 'display' AS type FROM CLOUD_VM_NOVA",
                                                  "SELECT class_Name AS type FROM CLOUD_VM_NOVA", "请输出class_Name字段")["reject"])

    def test_missing_label_in_changed_output_is_not_inferred(self):
        self.assertFalse(m._literal_label_contract("SELECT 'total' AS type,COUNT(*) AS n FROM CLOUD_VM_NOVA",
                                                  "SELECT SUM(id) AS total FROM CLOUD_VM_NOVA", "输出总量")["reject"])

    def test_nested_scope_is_not_guessed(self):
        sql = "SELECT 'kind' AS type FROM (SELECT name FROM CLOUD_VM_NOVA)"
        self.assertEqual(m._literal_label_contract(sql, sql, "类型")["reason"], "literal_labels_outside_checked_scope")

    def test_validation_flag_controls_fallback(self):
        before = "SELECT name,'display' AS type FROM CLOUD_VM_NOVA"
        after = "SELECT name,class_Name AS type FROM CLOUD_VM_NOVA"
        with patch.object(m, "_schema_columns", {"VM_NOVA": ["name", "class_Name"]}):
            for flag, expected in [("0", after), ("1", before)]:
                with self.subTest(flag=flag), patch.dict(os.environ, {"RUNBOOK_PRESERVE_LITERAL_LABELS": flag,
                        "RUNBOOK_PRESERVE_ROW_SEMANTICS": "0", "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "0"}):
                    self.assertEqual(m._validated_refinement(after, before, "类型列表"), expected)


if __name__ == "__main__":
    unittest.main()
