"""Offline evidence and budget contracts; no real model/network access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bench = module(REPO / 'C/benchmark.py', 'c_benchmark_test')
entry = module(REPO / 'C/implementation/quick_eval.py', 'c_entry_budget_test')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPO / 'C/reports')
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        blocked = patch('socket.socket.connect', side_effect=AssertionError('network disabled'))
        blocked.start()
        self.addCleanup(blocked.stop)

    def fixture(self, name, scores=(5, -1), ids=None, model='fixture-model', complete=True, request_mismatch=False):
        ids = ids or [f'fixture-{i}' for i in range(len(scores))]
        plan = {'type': 'plan', 'case_count': len(scores), 'dataset_sha256': 'fixture-data',
                'source_sha256': {'evaluator.py': 'fixture-scorer'}, 'model': model,
                'base_url': 'https://fixture.invalid', 'max_output_tokens': 1024, 'sdk_max_retries': 0,
                'thinking': 'provider default', 'temperature': 'provider default',
                'template_count': 200, 'cache_policy': 'fixture-cache'}
        rows = [{'type': 'case', 'case_id': cid, 'score': score, 'elapsed': .1,
                 'reason': '答案正确' if score == 5 else '答案错误'} for cid, score in zip(ids, scores)]
        summary = {'type': 'summary', 'status': 'complete' if complete else 'incomplete',
                   'completed_cases': len(scores), 'planned_cases': len(scores), 'total_score': sum(scores),
                   'generation_requests': 1 if request_mismatch else 0}
        path = self.dir / (name + '.jsonl')
        path.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in [plan, *rows, summary]), encoding='utf-8')
        return path

    def test_existing_full_run_is_verified_without_model_calls(self):
        run = bench.load_run(REPO / 'B/experiments/whitebox_20261029_full.jsonl')
        result = bench.summarize(run)
        self.assertEqual(result['integrity_issues'], [])
        self.assertEqual((result['completed_cases'], result['score'], result['untimed_score']), (200, 448.9, 614.9))
        self.assertEqual((result['requests'], result['time_penalty_points']), (514, 166))
        self.assertEqual(result['answer_reason_counts']['correct'], 116)
        self.assertIsNone(result['official_total'])

    def test_existing_root20_keeps_its_own_identity(self):
        run = bench.load_run(REPO / 'experiments/round3/model20.json')
        result = bench.summarize(run)
        self.assertEqual(result['score'], 75.5)
        self.assertEqual(result['requests'], 53)
        self.assertEqual(result['model_config']['model'], 'deepseek-chat')

    def test_same_question_set_produces_paired_deltas(self):
        a = self.fixture('a', (5, -1))
        b = self.fixture('b', (5, 5))
        result = bench.compare(a, b)
        self.assertEqual(result['score_delta'], 6)
        self.assertEqual(result['improved'], 1)
        self.assertFalse(result['causal_speedup_claim'])

    def test_subset_requires_explicit_scope(self):
        a = self.fixture('a', (5, -1))
        b = self.fixture('b', (5,), ['fixture-1'])
        with self.assertRaises(ValueError):
            bench.compare(a, b)
        self.assertEqual(bench.compare(a, b, subset=True)['count'], 1)
        c = self.fixture('c', (5,), ['unseen'])
        with self.assertRaises(ValueError):
            bench.compare(a, c, subset=True)

    def test_changed_model_is_not_a_controlled_comparison(self):
        a = self.fixture('a')
        b = self.fixture('b', model='other-model')
        with self.assertRaises(ValueError):
            bench.compare(a, b)
        result = bench.compare(a, b, descriptive=True)
        self.assertIn('model', result['different_config'])
        self.assertFalse(result['official_improvement_claim'])

    def test_incomplete_run_cannot_enter_acceptance(self):
        a, b = self.fixture('a'), self.fixture('b', complete=False)
        self.assertIn('incomplete_run', bench.load_run(b)['issues'])
        with self.assertRaises(ValueError):
            bench.compare(a, b)

    def test_duplicate_case_is_rejected(self):
        a = self.fixture('a', ids=['duplicate', 'duplicate'])
        with self.assertRaises(ValueError):
            bench.load_run(a)

    def test_score_tampering_is_detected(self):
        a = self.fixture('a')
        rows = [json.loads(x) for x in a.read_text(encoding='utf-8').splitlines()]
        rows[-1]['total_score'] = 999
        a.write_text('\n'.join(json.dumps(x) for x in rows), encoding='utf-8')
        self.assertIn('declared_score_mismatch', bench.load_run(a)['issues'])

    def test_deleted_request_events_are_detected(self):
        path = self.fixture('missing_events', request_mismatch=True)
        self.assertIn('request_count_mismatch', bench.load_run(path)['issues'])

    def test_time_regression_of_a_correct_control_is_reported(self):
        a = self.fixture('a', (5,))
        b = self.fixture('b', (5,))
        lines = [json.loads(x) for x in b.read_text(encoding='utf-8').splitlines()]
        lines[1].update(score=4, score_without_time_penalty=5, elapsed=4.1, reason='答案正确 [超时>4s, -1]')
        lines[-1]['total_score'] = 4
        b.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in lines), encoding='utf-8')
        result = bench.compare(a, b)
        self.assertEqual(result['control_regressions'], ['fixture-0'])
        self.assertEqual(result['answer_control_regressions'], [])

    def test_missing_token_evidence_is_unknown_not_zero(self):
        a = self.fixture('a')
        result = bench.summarize(bench.load_run(a))
        self.assertIsNone(result['prompt_tokens'])
        self.assertEqual(result['requests'], 0)  # Explicit zero in the fixture summary, not an inferred zero.

    def test_trigger_is_not_automatically_root_cause(self):
        row = bench.row_record({'case_id': 'fixture', 'score': 0, 'reason': '不回答（未命中runbook）',
            'diagnostics': {'matching': {'reason': 'resource_mismatch', 'candidate_ids': ['rb_1']}}})
        category, owner, strength, _ = bench.classify(row)
        self.assertEqual((category, owner, strength), ('resource_gate', 'B/C', 'observed_trigger'))

    def test_frozen_profiles_preserve_group_boundaries(self):
        result = bench.build(self.dir / 'profiles')
        self.assertEqual((result['white_cases'], result['development'], result['regression']), (200, 166, 34))
        dev = bench.read(self.dir / 'profiles/development.json')['case_ids']
        reg = bench.read(self.dir / 'profiles/regression.json')['case_ids']
        self.assertFalse(set(dev) & set(reg))
        self.assertEqual(result['generalization_cases'], 16)
        derived = bench.read(self.dir / 'profiles/generalization.json')['cases']
        self.assertTrue(all('parent_case_id' in case and 'group_id' in case for case in derived))

    def test_aggregate_refuses_missing_or_reused_blackbox(self):
        a = self.fixture('a')
        with self.assertRaises(ValueError):
            bench.aggregate([a, a], [a, a], 200)
        with self.assertRaises(ValueError):
            bench.aggregate([a], [], 200)

    def test_aggregate_formula_uses_raw_scores_and_two_independent_rounds(self):
        paths = []
        for label, count in [('white', 200), ('black', 100)]:
            for round_index in (1, 2):
                p = self.fixture(label+str(round_index), (5,)*count,
                                 [f'{label}-{i}' for i in range(count)])
                rows = [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()]
                rows[0].update(dataset_sha256=label+'-data', round_index=round_index)
                p.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
                paths.append(p)
        result = bench.aggregate(paths[:2], paths[2:], 200)
        self.assertEqual(result['white_mean_score'], 1000)
        self.assertEqual(result['black_mean_score'], 500)
        self.assertEqual(result['formula_reference'], 600)
        self.assertFalse(result['official_score_claim'])


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.client = types.SimpleNamespace(_client=types.SimpleNamespace(event_hooks={}))
        self.guard = entry.RequestGuard(self.client, 'https://fixture.invalid', 2)
        self.addCleanup(self.guard.detach)

    def request(self, url='https://fixture.invalid/chat/completions'):
        return types.SimpleNamespace(url=url, method='POST', content=b'{"model":"fixture","max_tokens":12}')

    def test_every_http_attempt_including_retry_consumes_quota(self):
        self.guard.before(self.request())
        self.guard.before(self.request())
        with self.assertRaises(entry.ModelRequestStop):
            self.guard.before(self.request())
        self.assertEqual(len(self.guard.events), 2)
        self.assertNotIsInstance(entry.ModelRequestStop(), Exception)

    def test_unexpected_destination_stops_before_counting_or_transmission(self):
        with self.assertRaises(entry.ModelRequestStop):
            self.guard.before(self.request('https://other.invalid/chat/completions'))
        self.assertEqual(self.guard.events, [])

    def test_usage_capture_does_not_persist_model_text(self):
        self.guard.before(self.request())
        payload = {'model': 'returned-model', 'usage': {'prompt_tokens': 3, 'completion_tokens': 2},
                   'choices': [{'message': {'content': 'must not persist'}}]}
        response = types.SimpleNamespace(status_code=200, read=lambda: None, json=lambda: payload)
        self.guard.after(response)
        self.assertEqual(self.guard.events[0]['usage']['prompt_tokens'], 3)
        self.assertNotIn('must not persist', json.dumps(self.guard.events))


if __name__ == '__main__':
    unittest.main()
