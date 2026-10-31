"""直接导入评测入口的默认配置与外部环境优先级。"""
import os
import unittest
from unittest.mock import patch

from runbook_defaults import apply_defaults


class SubmissionDefaultsTests(unittest.TestCase):
    def test_direct_entry_loads_verified_features_without_development_budget(self):
        with patch.dict(os.environ,{},clear=True):
            apply_defaults()
            self.assertEqual(os.environ['RUNBOOK_A132_CANDIDATE'],'1')
            self.assertEqual(os.environ['RUNBOOK_ISSUE4_AZ_COUNTS'],'1')
            self.assertEqual(os.environ['RUNBOOK_ISSUE4_NETWORK'],'1')
            self.assertEqual(os.environ['RUNBOOK_THINKING_MODE'],'disabled')
            self.assertEqual(os.environ['RUNBOOK_JSON_COPY_MODE'],'fast')
            self.assertEqual(os.environ['RUNBOOK_ISSUE4_ADDRESS'],'0')
            self.assertNotIn('RUNBOOK_MAX_LLM_CALLS',os.environ)
            self.assertNotIn('DEEPSEEK_API_KEY',os.environ)

    def test_evaluation_machine_model_flags_and_budget_always_win(self):
        supplied={'DEEPSEEK_MODEL':'official_model','RUNBOOK_ISSUE4_AZ_COUNTS':'0','RUNBOOK_MAX_LLM_CALLS':'999','RUNBOOK_JSON_COPY_MODE':'standard'}
        with patch.dict(os.environ,supplied,clear=True):
            apply_defaults()
            for key,value in supplied.items():self.assertEqual(os.environ[key],value)


if __name__=='__main__':unittest.main()
