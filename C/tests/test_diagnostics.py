"""验证共用B流程与C诊断/报告的集成；合成模板，禁止真实网络和模型。"""
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

QUESTION = '查询region_lab下运行中的ECS名称为alpha，标记blue'
SQL = 'SELECT name FROM CLOUD_VM_NOVA'
PARAMS = 'name=alpha\nstatus=active\ntag=blue'


def template():
    fields = ['name', 'status', 'logicalRegionName', 'tag']
    return {'id': 'fixture', 'name': 'fixture', 'description': 'test only', 'examples': [],
            'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/VM_NOVA',
                         'condition': {'constraint': [
                             {'simple': {'name': name, 'value': '{{' + name + '}}'}} for name in fields]}},
            'sql': SQL, 'default_params': {'name': 'unmentioned-default'}}


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
        for context in [patch('socket.socket.connect', side_effect=AssertionError('no network')),
                        patch.object(matcher, '_get_table_schemas', return_value=''),
                        patch.dict(matcher._schema_columns,
                                   {'VM_NOVA': ['name', 'status', 'logicalRegionName', 'tag']}, clear=True),
                        patch.dict(matcher._schema_values, {}, clear=True),
                        patch.dict('os.environ', {}, clear=True)]:
            context.start()
            self.addCleanup(context.stop)

    def test_diagnostics_preserve_result_prompts_and_parameter_origins(self):
        item = template()
        pristine = copy.deepcopy(item)
        responses = ['1', PARAMS, SQL + ' LIMIT 2']
        with patch.object(matcher, 'llm_ask', side_effect=responses) as plain_llm:
            plain = matcher.match_runbook(QUESTION, [item], Retriever())
        diagnostics = {}
        with patch.object(matcher, 'llm_ask', side_effect=responses) as traced_llm:
            traced = matcher.match_runbook(QUESTION, [item], Retriever(), diagnostics)
        self.assertIsNotNone(traced)
        self.assertEqual(plain, traced)
        self.assertEqual(plain_llm.call_args_list, traced_llm.call_args_list)
        self.assertEqual(item, pristine)
        self.assertEqual(diagnostics['retrieval']['candidates'][0]['score'], 3.2)
        self.assertEqual(diagnostics['selection']['selected_id'], 'fixture')
        parameters = diagnostics['parameters']
        self.assertEqual(parameters['llm_extracted']['name'], 'alpha')
        self.assertEqual(parameters['final']['name'], 'alpha')
        self.assertEqual(parameters['sources']['tag'], 'llm')
        self.assertEqual(parameters['sources']['logicalRegionName'], 'question_rule')
        self.assertNotIn('unmentioned-default', parameters['final'].values())
        self.assertEqual(diagnostics['sql']['before_refine'], SQL)
        self.assertIn('LIMIT 2', diagnostics['sql']['model_proposal'])
        self.assertNotIn('LIMIT', diagnostics['sql']['after_refine'])
        self.assertEqual(diagnostics['sql']['refine_status'], 'contract_fallback')
        self.assertEqual(diagnostics['sql']['final'], traced['sql'])

    def test_rejections_record_current_b_policy_without_strong_fallback(self):
        cases = [
            ('no_candidates', Retriever([]), '清单', []),
            ('invalid_selection', Retriever(), '清单', ['not-an-index']),
            ('selector_refused', Retriever(), '清单', ['0']),
            ('resource_mismatch', Retriever(), '查询云硬盘清单', ['1']),
            ('missing_parameters', Retriever(), '清单', ['1', 'name=unmentioned']),
        ]
        for reason, retriever, question, responses in cases:
            with self.subTest(reason=reason), patch.object(matcher, 'llm_ask', side_effect=responses):
                diagnostics = {'stale': 'must be cleared'}
                self.assertIsNone(matcher.match_runbook(question, [template()], retriever, diagnostics))
                self.assertEqual(diagnostics['rejection']['reason'], reason)
                self.assertNotIn('stale', diagnostics)
        item = template()
        item['api_call'].pop('condition')
        with patch.object(matcher, 'llm_ask', return_value='1'):
            diagnostics = {}
            self.assertIsNone(matcher.match_runbook('查询region_other下的ECS', [item], Retriever(), diagnostics))
            self.assertEqual(diagnostics['rejection']['stage'], 'api_conditions')
            self.assertEqual(diagnostics['missing_api_filter']['field'], 'logicalRegionName')

    def test_refinement_fallback_records_discarded_proposal(self):
        for proposal in ['not SQL', SQL + " WHERE name='x'", SQL + ' UNION ' + SQL,
                         'SELECT name FROM DIFFERENT_TABLE']:
            with self.subTest(proposal=proposal), patch.object(matcher, 'llm_ask', return_value=proposal):
                diagnostics = {}
                self.assertEqual(matcher._refine_sql('fixture', SQL, diagnostics=diagnostics), SQL)
                self.assertEqual(diagnostics['refine_status'], 'contract_fallback')
                self.assertEqual(diagnostics['model_proposal'], proposal)
        with patch.object(matcher, 'llm_ask', side_effect=RuntimeError('fixture')):
            diagnostics = {}
            self.assertEqual(matcher._refine_sql('fixture', SQL, diagnostics=diagnostics), SQL)
            self.assertEqual(diagnostics['error_type'], 'RuntimeError')
            self.assertEqual(diagnostics['refine_status'], 'error_fallback')

    def test_query_supports_external_diagnostics_and_c_report(self):
        system = RunbookQuerySystem.__new__(RunbookQuerySystem)
        system.items = [template()]
        system.retriever = Retriever()
        responses = ['1', PARAMS, SQL]
        executed = {'sql': SQL, 'result': {'rows': [], 'columns': ['name']}, 'error': None}
        with patch.object(matcher, 'llm_ask', side_effect=responses), \
                patch('runbook_system.execute', return_value=executed):
            plain = system.query(QUESTION)
        with patch.object(matcher, 'llm_ask', side_effect=responses), \
                patch('runbook_system.execute', return_value=executed):
            diagnostics = {}
            traced = system.query(QUESTION, diagnostics=diagnostics)
        self.assertEqual({k: v for k, v in plain.items() if k != 'diagnostics'},
                         {k: v for k, v in traced.items() if k != 'diagnostics'})
        self.assertEqual(traced['matched_runbook'], 'fixture')
        self.assertIs(traced['diagnostics'], diagnostics)
        self.assertEqual(diagnostics['selection'], diagnostics['matching']['selection'])
        with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
            path = Path(folder) / 'run.jsonl'
            with EvaluationReport(path, __file__, 1) as report:
                report.record({'case_id': 'fixture', 'question': QUESTION}, traced,
                              {'score': -1, 'reason': '答案错误'}, 0.1, diagnostics)
                report.complete()
            result, output = analyze(path)
            row = result['cases'][0]
            self.assertEqual(row['selected_id'], 'fixture')
            self.assertEqual(row['sql_before_refine'], SQL)
            self.assertEqual(row['parameter_sources']['tag'], 'llm')
            self.assertIn('llm', (output / 'cases.csv').read_text(encoding='utf-8-sig'))
            self.assertIn('sql_before_refine', (output / 'failures.csv').read_text(encoding='utf-8-sig'))

    def test_query_exception_preserves_completed_diagnostics(self):
        system = RunbookQuerySystem.__new__(RunbookQuerySystem)
        system.items, system.retriever = [], Retriever()
        def broken_match(question, items, retriever, details):
            details['selection'] = {'selected_id': 'fixture'}
            raise RuntimeError('synthetic interruption')
        diagnostics = {}
        with patch('runbook_system.match_runbook', side_effect=broken_match), self.assertRaises(RuntimeError):
            system.query('清单', diagnostics=diagnostics)
        with tempfile.TemporaryDirectory(dir=ROOT / 'C/reports') as folder:
            path = Path(folder) / 'error.jsonl'
            with EvaluationReport(path, __file__, 1) as report:
                report.query_error({'case_id': 'fixture', 'question': '清单'}, RuntimeError(), diagnostics)
            result, _ = analyze(path)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(result['recorded_cases'], 0)
            self.assertEqual(result['query_errors'][0]['diagnostics']['selection']['selected_id'], 'fixture')
            self.assertIsNone(result['score_percent'])


if __name__ == '__main__':
    unittest.main()
