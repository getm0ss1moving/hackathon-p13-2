"""合成前缀日志验证：补未请求后缀，不自动重试，不允许查询源码变化。"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from validation_resume import remaining_validation, sha


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.parent = self.root/'reports/partial'
        self.parent.mkdir(parents=True)
        self.cases = [{'case_id': f'SYNTH-{i:02}', 'question': f'合成{i}'} for i in range(50)]
        source = self.root/'implementation/matcher.py'
        source.parent.mkdir()
        source.write_text('original query\n')
        runner = self.root/'scripts/train_live.py'
        runner.parent.mkdir()
        runner.write_text('old recorder\n')
        self.plan = {'scope': 'sealed50_validation', 'case_ids': [r['case_id'] for r in self.cases],
                     'source_sha256': {'implementation/matcher.py': sha(source),
                                       'scripts/train_live.py': sha(runner)},
                     'runtime_source_paths': {'runbook_matcher': str(source)}}
        self.records = [{'type': 'case', 'case_id': r['case_id']} for r in self.cases[:17]]
        self.trace = [*({'type': 'request', 'case_id': r['case_id'], 'status': 'ok'} for r in self.records),
                      *self.records, {'type': 'run_error', 'error_type': 'FileNotFoundError'},
                      {'type': 'summary', 'status': 'incomplete', 'completed_cases': 17}]
        self.write()

    def write(self):
        for name, value in [('plan.json', self.plan), ('case_results.json', self.records),
                            ('summary.json', self.trace[-1])]:
            (self.parent/name).write_text(json.dumps(value))
        (self.parent/'live.jsonl').write_text('\n'.join(json.dumps(r) for r in self.trace)+'\n')
        budget = {'status': 'closed', 'used': sum(r['type'] == 'request' for r in self.trace),
                  'plan_sha256': sha(self.parent/'plan.json'), 'trace_sha256': sha(self.parent/'live.jsonl')}
        (self.parent/'budget.json').write_text(json.dumps(budget))

    def test_returns_only_unrequested_suffix_and_parent_hashes(self):
        remaining, evidence = remaining_validation(self.root, self.parent, self.cases)
        self.assertEqual(remaining, self.cases[17:])
        self.assertEqual((len(remaining), evidence['completed_prefix'], evidence['manual_retry']), (33, 17, False))
        self.assertEqual(evidence['files_sha256']['reports/partial/live.jsonl'], sha(self.parent/'live.jsonl'))

    def test_query_drift_rejected_but_recorder_change_allowed(self):
        (self.root/'scripts/train_live.py').write_text('recorder with resume\n')
        self.assertEqual(len(remaining_validation(self.root, self.parent, self.cases)[0]), 33)
        (self.root/'implementation/matcher.py').write_text('changed query\n')
        with self.assertRaises(ValueError):
            remaining_validation(self.root, self.parent, self.cases)

    def test_inflight_or_failed_model_request_cannot_be_retried(self):
        original = copy.deepcopy(self.trace)
        for request in [{'type': 'request', 'case_id': 'SYNTH-17', 'status': 'ok'},
                        {'type': 'request', 'case_id': 'SYNTH-16', 'status': 'error'}]:
            self.trace = [request, *original]
            self.write()
            with self.assertRaises(ValueError):
                remaining_validation(self.root, self.parent, self.cases)

    def test_missing_prefix_wrong_error_and_budget_tampering_rejected(self):
        self.records.reverse()
        self.write()
        with self.assertRaises(ValueError):
            remaining_validation(self.root, self.parent, self.cases)
        self.records.reverse()
        self.trace[-2]['error_type'] = 'TimeoutError'
        self.write()
        with self.assertRaises(ValueError):
            remaining_validation(self.root, self.parent, self.cases)
        self.trace[-2]['error_type'] = 'FileNotFoundError'
        self.write()
        (self.parent/'live.jsonl').write_text((self.parent/'live.jsonl').read_text()+'\n')
        with self.assertRaises(ValueError):
            remaining_validation(self.root, self.parent, self.cases)


if __name__ == '__main__':
    unittest.main()
