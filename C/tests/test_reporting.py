"""只检查结果采集/中止/对照流程，不把替身查询当模型效果测试。"""
import contextlib
import importlib.util
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'implementation'))
sys.path.insert(0, str(ROOT / 'C'))
from analyze_results import analyze, parse
from eval_report import EvaluationReport


class ReportingTests(unittest.TestCase):
    def test_original_entry_to_report_and_analysis(self):
        spec = importlib.util.spec_from_file_location('root_quick_eval', ROOT / 'implementation/quick_eval.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        cases = json.loads((ROOT / 'CMDB用例集-白盒200.json').read_text(encoding='utf-8'))['cases'][:2]
        answers = iter(cases)
        fake = types.ModuleType('runbook_system')

        class System:
            def query(self, question):
                case = next(answers)
                return {'matched_runbook': 'test-only', 'api_call': case['api_call'],
                        'sql': case['sql'], 'result': case['answer'], 'error': None}

        fake.RunbookQuerySystem = System
        previous_logging = logging.root.manager.disable
        try:
            with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
                path = Path(folder) / 'run.jsonl'
                with patch.dict(sys.modules, {'runbook_system': fake}), \
                        patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-key'}), \
                        patch.object(runner.http.client, 'HTTPConnection') as connection, \
                        patch('socket.socket.connect', side_effect=AssertionError('no network')), \
                        contextlib.redirect_stdout(io.StringIO()):
                    response = connection.return_value.getresponse.return_value
                    response.status = 200
                    response.read.return_value = b'{"ci_name":"VM_NOVA","columns":["status"],"row_count":1}'
                    self.assertEqual(runner.main(['2', '--report', str(path)]), 0)
                result, output = analyze(path, expected=2, baseline=path)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(result['observed_score'], 10)
                self.assertEqual(result['cases'][1]['api_call'], cases[1]['api_call'])
                self.assertEqual(result['comparison']['score_delta'], 0)
                self.assertTrue((output / 'comparison.csv').is_file())
                self.assertTrue((output / 'failures.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
        finally:
            logging.disable(previous_logging)

    def test_interrupted_run_is_not_complete_or_rescored(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
            path = Path(folder) / 'partial.jsonl'
            with EvaluationReport(path, __file__, 2) as report:
                report.record({'case_id': 'test-1', 'question': 'fixture'}, {},
                              {'score': 4, 'reason': '答案正确 [超时>5s, -1]'}, 4.9)
            result, _ = analyze(path)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(result['recorded_cases'], 1)
            self.assertIsNone(result['score_percent'])
            self.assertEqual(result['correct_but_lost_points'], 1)

    def test_old_score_format_and_full_credit_partial_reason(self):
        text = 'test-1: +5.0 (部分正确(100%)) [2.9s]\n=== 1 cases: score=5.0/5 ===\n'
        result = parse(text)
        self.assertEqual(result['score_counts']['full'], 1)
        self.assertEqual(result['score_counts']['partial'], 0)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(parse(text + text)['status'], 'incomplete')

    def test_report_refuses_overwrite_and_redacts_key(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
            path = Path(folder) / 'run.jsonl'
            with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-secret'}):
                with EvaluationReport(path, __file__, 1) as report:
                    report.record({'case_id': 'test-1', 'question': 'fixture-secret'}, {},
                                  {'score': 0, 'reason': '不回答'}, 0.1)
                    report.complete()
            self.assertNotIn('fixture-secret', path.read_text(encoding='utf-8'))
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                with EvaluationReport(path, __file__, 1):
                    pass
            self.assertEqual(before, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
