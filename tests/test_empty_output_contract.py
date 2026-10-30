"""Output-only fixtures; no real language/model recognition is claimed."""
import ast
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

IMPL = Path(__file__).resolve().parents[1] / 'implementation'
sys.path.insert(0, str(IMPL))
import runbook_system as system_module
from evaluator import evaluate_case
from runbook_executor import execute


def reference(answer, sql='SELECT 1 AS value'):
    return {'case_id': 'SYNTHETIC-OUTPUT', 'question': '合成接口验证',
            'api_call': [], 'sql': sql, 'answer': answer}


class EmptyOutputTests(unittest.TestCase):
    def setUp(self):
        self.system = system_module.RunbookQuerySystem.__new__(system_module.RunbookQuerySystem)
        self.system.items, self.system.retriever = [], None

    def test_unsupported_fixtures_are_null_with_internal_reason(self):
        for question, reason in [('查询各项目下一季度预测成本', 'no_candidates'),
                                 ('列出实例名称以及未来预测成本', 'partial_unsupported'),
                                 ('查询那个项目的资源', 'ambiguous_scope')]:
            def unsupported(question, items, retriever, diagnostics, **kwargs):
                diagnostics['rejection'] = {'reason': reason}
                return None
            details = {}
            with self.subTest(reason=reason), patch.object(system_module, 'match_runbook', side_effect=unsupported):
                output = self.system.query(question, diagnostics=details)
                self.assertEqual({k: output[k] for k in ['matched_runbook', 'sql', 'result', 'error']},
                                 dict.fromkeys(['matched_runbook', 'sql', 'result', 'error']))
                self.assertIs(output['diagnostics'], details)
                self.assertEqual(details['rejection']['reason'], reason)
                self.assertIsNone(json.loads(json.dumps(output))['result'])
                self.assertEqual(evaluate_case(reference({'rows': [], 'row_count': 0}), output, .1)['score'], 0)

    def test_successful_zero_rows_is_not_unsupported(self):
        item = {'name': 'synthetic', 'api_call': [], 'sql': 'SELECT 1 AS value WHERE 0'}
        with patch.object(system_module, 'match_runbook', return_value=copy.deepcopy(item)), \
                patch.dict(os.environ, {'RUNBOOK_BOUNDED_API': '0'}):
            output = self.system.query('合成成功零行')
        self.assertEqual(output['result'], {'columns': ['value'], 'rows': [], 'row_count': 0})
        self.assertEqual(output['matched_runbook'], 'synthetic')
        self.assertIsNone(output['error'])
        self.assertEqual(evaluate_case(reference(output['result'], item['sql']), output, .1)['score'], 5)

    def test_positive_and_execution_error_are_not_reclassified(self):
        for sql, expected_error in [('SELECT 1 AS value', False), ('SELECT (', True)]:
            item = {'name': 'synthetic', 'api_call': [], 'sql': sql}
            with self.subTest(sql=sql), patch.object(system_module, 'match_runbook', return_value=item), \
                    patch.dict(os.environ, {'RUNBOOK_BOUNDED_API': '0'}):
                output = self.system.query('合成查询')
            self.assertEqual(output['matched_runbook'], 'synthetic')
            self.assertEqual(bool(output['error']), expected_error)
            if not expected_error:
                self.assertEqual(output['result']['rows'], [{'value': 1}])

    def test_bounded_unsupported_plan_is_null_and_stays_zero_score(self):
        item = {'name': 'synthetic', 'api_call': [], 'sql': 'DELETE FROM unavailable'}
        details = {}
        with patch.object(system_module, 'match_runbook', return_value=item), \
                patch.dict(os.environ, {'RUNBOOK_BOUNDED_API': '1'}):
            output = self.system.query('合成不支持计划', diagnostics=details)
        self.assertIsNone(output['matched_runbook'])
        self.assertIsNone(output['result'])
        self.assertIsNone(output['error'])
        self.assertEqual(details['bounded_api']['refusal_reason'], 'unsupported_or_unfilled_sql')
        self.assertEqual(evaluate_case(reference({'rows': [], 'row_count': 0}), output, .1)['score'], 0)

    def test_cli_unsupported_stdout_is_empty(self):
        source = ast.parse((IMPL / 'runbook_system.py').read_text())
        node = next(n for n in source.body if isinstance(n, ast.If) and
                    isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name)
                    and n.test.left.id == '__name__')
        code = compile(ast.Module(body=[node], type_ignores=[]), '<synthetic-cli>', 'exec')
        class FixtureSystem:
            items = []
            def query(self, question):
                return {'matched_runbook': None, 'result': None, 'error': None}
        stream = io.StringIO()
        with patch.object(sys, 'argv', ['runbook_system.py', '合成问题']), contextlib.redirect_stdout(stream):
            with self.assertRaises(SystemExit) as status:
                exec(code, {'__name__': '__main__', 'RunbookQuerySystem': FixtureSystem, 'sys': sys, 'json': json})
        self.assertEqual(status.exception.code, 0)
        self.assertEqual(stream.getvalue(), '')

    def test_null_result_alone_cannot_represent_unsupported(self):
        empty = execute({'api_call': [], 'sql': 'SELECT 1 AS value WHERE 0'})
        unsupported = {'matched_runbook': None, 'result': None, 'error': None}
        misleading = {'matched_runbook': 'synthetic', 'api_call': [], 'result': None, 'error': None}
        case = reference(empty['result'])
        self.assertEqual(evaluate_case(case, unsupported, .1)['score'], 0)
        # Document the fixed evaluator's behavior; never exploit it as an improvement.
        self.assertEqual(evaluate_case(case, misleading, .1)['score'], 5)


if __name__ == '__main__':
    unittest.main()
