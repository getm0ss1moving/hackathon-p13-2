"""验证诊断不改变原查询结果和模型调用流程；模型/网络均使用替身。"""
import copy
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'implementation'))
sys.path.insert(0, str(ROOT / 'C'))
import runbook_matcher as matcher
from runbook_retriever import Candidate
from runbook_system import RunbookQuerySystem
from eval_report import EvaluationReport
from analyze_results import analyze


def template():
    fields = ['name', 'status', 'logicalRegionName', 'clusterName']
    return {'id': 'fixture', 'name': 'fixture', 'description': 'test only', 'examples': [],
            'api_call': {'method': 'GET', 'url': '/test', 'condition': {'constraint': [
                {'simple': {'name': name, 'value': '{{' + name + '}}'}} for name in fields]}},
            'sql': 'SELECT name FROM CLOUD_INVENTORY', 'default_params': {'clusterName': 'default-cluster'}}


class Retriever:
    def __init__(self, candidates=None):
        self.candidates = candidates if candidates is not None else [Candidate('fixture', 'strong', 3.2, .7)]

    def retrieve(self, question):
        return self.candidates


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        previous_logging = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, previous_logging)
        self.network = patch('socket.socket.connect', side_effect=AssertionError('no network'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.schema = patch.object(matcher, '_get_table_schemas', return_value='')
        self.schema.start()
        self.addCleanup(self.schema.stop)

    def test_diagnostics_preserve_result_prompts_and_parameter_origins(self):
        item = template()
        pristine = copy.deepcopy(item)
        responses = ['1', 'name=VMalpha\nstatus=运行中', 'SELECT name, status FROM CLOUD_INVENTORY LIMIT 2']
        question = '区域 region_lab cluster 的清单'
        with patch.object(matcher, 'llm_ask', side_effect=responses) as plain_llm:
            plain = matcher.match_runbook(question, [item], Retriever())
        diagnostics = {}
        with patch.object(matcher, 'llm_ask', side_effect=responses) as traced_llm:
            traced = matcher.match_runbook(question, [item], Retriever(), diagnostics)
        self.assertEqual(plain, traced)
        self.assertEqual(plain_llm.call_args_list, traced_llm.call_args_list)
        self.assertEqual(item, pristine)
        self.assertEqual(diagnostics['retrieval']['candidates'][0]['score'], 3.2)
        self.assertEqual(diagnostics['selection']['selected_id'], 'fixture')
        parameters = diagnostics['parameters']
        self.assertEqual(parameters['llm_extracted']['name'], 'VMalpha')
        self.assertEqual(parameters['final']['name'], 'alpha')
        self.assertEqual(parameters['sources']['name'], 'llm+normalization')
        self.assertEqual(parameters['sources']['logicalRegionName'], 'question_rule')
        self.assertEqual(parameters['sources']['clusterName'], 'template_default')
        self.assertEqual(diagnostics['sql']['before_refine'], 'SELECT name FROM CLOUD_INVENTORY')
        self.assertIn('LIMIT 2', diagnostics['sql']['model_proposal'])
        self.assertNotIn('LIMIT', diagnostics['sql']['after_refine'])
        self.assertEqual(diagnostics['sql']['final'], traced['sql'])

    def test_rejections_and_strong_fallback_have_explicit_reasons(self):
        cases = [
            ('no_candidates', Retriever([]), '清单', [], template()),
            ('invalid_selector_output', Retriever(), '清单', ['not-an-index'], template()),
            ('selector_declined_or_out_of_range', Retriever([Candidate('fixture', 'weak', .2, .2)]),
             '清单', ['0'], template()),
            ('resource_mismatch', Retriever(), '查询ECS清单', ['1'], template()),
            ('refinement_changed_tables', Retriever(), '清单',
             ['1', 'name=alpha', 'SELECT name FROM DIFFERENT_TABLE'], template()),
        ]
        for reason, retriever, question, responses, item in cases:
            with self.subTest(reason=reason), patch.object(matcher, 'llm_ask', side_effect=responses):
                diagnostics = {'stale': 'must be cleared'}
                self.assertIsNone(matcher.match_runbook(question, [item], retriever, diagnostics))
                self.assertEqual(diagnostics['rejection']['reason'], reason)
                self.assertNotIn('stale', diagnostics)
        item = template()
        item['api_call']['condition']['constraint'] = [
            {'simple': {'name': 'name', 'value': '{{name}}'}}]
        with patch.object(matcher, 'llm_ask', side_effect=['1', 'name=alpha']):
            diagnostics = {}
            self.assertIsNone(matcher.match_runbook('停止的清单', [item], Retriever(), diagnostics))
            self.assertEqual(diagnostics['rejection']['required_condition'], 'status')
        item = template()
        item['api_call'] = {'method': 'GET', 'url': '/test'}
        with patch.object(matcher, 'llm_ask', return_value='0') as llm:
            diagnostics = {}
            self.assertIsNotNone(matcher.match_runbook('清单', [item], Retriever(), diagnostics))
            self.assertEqual(diagnostics['selection']['method'], 'strong_top1_fallback')
            self.assertEqual(diagnostics['sql']['refine_status'], 'skipped_no_placeholders')
            self.assertEqual(llm.call_count, 1)

    def test_refinement_fallback_records_discarded_proposal(self):
        original = 'SELECT name FROM CLOUD_INVENTORY'
        for proposal, status in [('not SQL', 'kept_original_not_select'),
                                 (original + " WHERE name='x'", 'kept_original_where'),
                                 (original + ' UNION ' + original, 'kept_original_union'),
                                 ('SELECT 1', 'kept_original_no_from')]:
            with self.subTest(status=status), patch.object(matcher, 'llm_ask', return_value=proposal):
                diagnostics = {}
                self.assertEqual(matcher._refine_sql('fixture', original, diagnostics=diagnostics), original)
                self.assertEqual(diagnostics['refine_status'], status)
                self.assertEqual(diagnostics['model_proposal'], proposal)
        with patch.object(matcher, 'llm_ask', side_effect=RuntimeError('fixture')):
            diagnostics = {}
            self.assertEqual(matcher._refine_sql('fixture', original, diagnostics=diagnostics), original)
            self.assertEqual(diagnostics['error_type'], 'RuntimeError')

    def test_query_keeps_return_contract_and_persists_diagnostics(self):
        system = RunbookQuerySystem.__new__(RunbookQuerySystem)
        system.items = [template()]
        system.retriever = Retriever()
        responses = ['1', 'name=alpha', 'SELECT name FROM CLOUD_INVENTORY']
        executed = {'sql': 'SELECT name FROM CLOUD_INVENTORY', 'result': {'rows': [], 'columns': ['name']}, 'error': None}
        with patch.object(matcher, 'llm_ask', side_effect=responses), \
                patch('runbook_system.execute', return_value=executed):
            plain = system.query('清单')
        with patch.object(matcher, 'llm_ask', side_effect=responses), \
                patch('runbook_system.execute', return_value=executed):
            diagnostics = {}
            traced = system.query('清单', diagnostics=diagnostics)
        self.assertEqual(plain, traced)
        self.assertNotIn('diagnostics', traced)
        with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
            path = Path(folder) / 'run.jsonl'
            with EvaluationReport(path, __file__, 1) as report:
                report.record({'case_id': 'fixture', 'question': '清单'}, traced,
                              {'score': -1, 'reason': '答案错误'}, 0.1, diagnostics)
                report.complete()
            result, output = analyze(path)
            row = result['cases'][0]
            self.assertEqual(row['selected_id'], 'fixture')
            self.assertEqual(row['sql_before_refine'], template()['sql'])
            self.assertEqual(row['parameter_sources']['name'], 'llm')
            self.assertIn('llm', (output / 'cases.csv').read_text(encoding='utf-8-sig'))
            self.assertIn('sql_before_refine', (output / 'failures.csv').read_text(encoding='utf-8-sig'))

    def test_query_exception_keeps_diagnostics_without_inventing_score(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
            path = Path(folder) / 'error.jsonl'
            with EvaluationReport(path, __file__, 1) as report:
                report.query_error({'case_id': 'fixture', 'question': '清单'}, RuntimeError(),
                                   {'selection': {'selected_id': 'fixture'}})
            result, _ = analyze(path)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(result['recorded_cases'], 0)
            self.assertEqual(result['query_errors'][0]['diagnostics']['selection']['selected_id'], 'fixture')
            self.assertIsNone(result['score_percent'])


if __name__ == '__main__':
    unittest.main()
