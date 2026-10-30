"""新提示词仍经过原SQL合同；合成SQL，不验证模型语义能力。"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m


class RefineContractPromptTests(unittest.TestCase):
    def setUp(self):
        context = patch.object(m, "_schema_columns", {"VM_NOVA": ["id", "name", "tenantName", "status"]})
        context.start()
        self.addCleanup(context.stop)
        context = patch.dict(os.environ, {"RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1",
                "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1", "RUNBOOK_PRESERVE_AGGREGATE_GRAIN": "1",
                "RUNBOOK_PRESERVE_LITERAL_LABELS": "1"})
        context.start()
        self.addCleanup(context.stop)

    def test_default_dispatch_keeps_original_prompt(self):
        sql = "SELECT id,name FROM CLOUD_VM_NOVA"
        with patch.dict(os.environ, {}, clear=True), patch.object(m, "llm_ask", return_value=sql) as ask:
            details = {}
            self.assertEqual(m._refine_sql("实例列表", sql, "known schema", details), sql)
        ask.assert_called_once_with(m.REFINE_SQL_PROMPT.format(question="实例列表", sql=sql,
                                    schemas="known schema", join_relations=m.JOIN_RELATIONS), stage="refine")
        self.assertEqual(details["refine_prompt_policy"], "original")

    def test_candidate_keeps_inputs_and_existing_projection_fallback(self):
        sql = "SELECT id,name FROM CLOUD_VM_NOVA"
        with patch.dict(os.environ, {"RUNBOOK_REFINE_CONTRACT_PROMPT": "1"}), \
                patch.object(m, "llm_ask", return_value="SELECT name FROM CLOUD_VM_NOVA") as ask:
            details = {}
            self.assertEqual(m._refine_sql("实例列表", sql, "known schema", details), sql)
        ask.assert_called_once_with(m.REFINE_SQL_CONTRACT_PROMPT.format(question="实例列表", sql=sql,
                                    schemas="known schema", join_relations=m.JOIN_RELATIONS), stage="refine")
        self.assertTrue(details["projection_contract"]["reject"])
        self.assertEqual(details["refine_prompt_policy"], "preserve_output_contract")

    def test_candidate_allows_valid_new_statistics(self):
        before = "SELECT COUNT(*) AS n FROM CLOUD_VM_NOVA"
        after = "SELECT COUNT(*) AS n,COUNT(DISTINCT tenantName) AS tenants FROM CLOUD_VM_NOVA"
        with patch.dict(os.environ, {"RUNBOOK_REFINE_CONTRACT_PROMPT": "1"}), \
                patch.object(m, "llm_ask", return_value=after):
            self.assertEqual(m._refine_sql("统计实例总数及租户数", before), after)

    def test_candidate_cannot_bypass_where_guard(self):
        sql = "SELECT id,name FROM CLOUD_VM_NOVA"
        with patch.dict(os.environ, {"RUNBOOK_REFINE_CONTRACT_PROMPT": "1"}), \
                patch.object(m, "llm_ask", return_value=sql+" WHERE status='active'"):
            self.assertEqual(m._refine_sql("实例列表", sql), sql)


if __name__ == "__main__":
    unittest.main()
