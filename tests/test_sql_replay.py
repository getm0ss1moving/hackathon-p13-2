"""回放用原完整问题，拒绝重复题号、错文本及缺少 SQL 依据的记录。"""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_sql import source_cases


class SQLReplayInputTests(unittest.TestCase):
    def setUp(self):
        self.question = "查询" + "完整条件" * 20
        self.cases = {"fixture-a": {"case_id": "fixture-a", "question": self.question},
                      "fixture-b": {"case_id": "fixture-b", "question": "无匹配能力"}}
        self.rows = [
            {"type": "case", "case_id": "fixture-a", "question": self.question[:60],
             "matched_runbook": "fixture", "sql": "SELECT name FROM CLOUD_VM_NOVA",
             "diagnostics": {"matching": {"sql_before_refine": "SELECT name,status FROM CLOUD_VM_NOVA"}}},
            {"type": "case", "case_id": "fixture-b", "question": "无匹配能力", "matched_runbook": None, "sql": None},
        ]

    def test_scorer_prefix_is_validated_but_complete_question_is_recovered(self):
        original = copy.deepcopy(self.rows)
        selected = source_cases(self.rows, self.cases, True)
        self.assertEqual(selected[0]["question"], self.question)
        self.assertEqual(len(selected), 2)
        self.assertEqual(self.rows, original)

    def test_partial_scopes_and_duplicate_or_unknown_ids_never_become_full_runs(self):
        for rows in [self.rows[:1], [self.rows[0], self.rows[0]],
                     [{"type": "case", "case_id": "unknown", "question": "未知"}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                source_cases(rows, self.cases, True)

    def test_wrong_text_or_missing_before_sql_is_rejected(self):
        for mutation in ["text", "sql"]:
            rows = copy.deepcopy(self.rows)
            if mutation == "text": rows[0]["question"] = self.question[:59]
            else: rows[0]["diagnostics"]["matching"].pop("sql_before_refine")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                source_cases(rows, self.cases, True)

    def test_legacy_changed_sql_scope_excludes_refusals(self):
        selected = source_cases(self.rows, self.cases, False)
        self.assertEqual([row["case_id"] for row in selected], ["fixture-a"])


if __name__ == "__main__":
    unittest.main()
