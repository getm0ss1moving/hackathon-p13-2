"""核对相同冻结候选的固定150/50各一次覆盖；明确分进程，不拼不同源码。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

from analyze_full_whitebox import group, reason

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_run(path, count, scope, *, incomplete_prefix=False):
    path = path.resolve()
    plan = json.loads((path/'plan.json').read_text())
    trace = [json.loads(line) for line in (path/'live.jsonl').read_text().splitlines()]
    rows = [r for r in trace if r.get('type') == 'case']
    requests = [r for r in trace if r.get('type') == 'request']
    summary = trace[-1]
    assert plan['scope'] == scope and plan['case_count'] == count
    completed = len(rows)
    if incomplete_prefix:
        assert summary['status'] == 'incomplete' and 0 < completed < count
        assert [r.get('error_type') for r in trace if r.get('type') == 'run_error'] == ['FileNotFoundError']
    else:
        assert summary['status'] == 'complete' and completed == count
    assert summary['completed_cases'] == completed
    assert [r['case_id'] for r in rows] == plan['case_ids'][:completed]
    assert all(trace[0].get(k) == v for k, v in plan.items() if k not in {'created_at', 'authorization'})
    assert json.loads((path/'case_results.json').read_text()) == rows
    assert len(requests) == summary['generation_requests'] <= plan['max_requests'] <= 450
    assert sum(len((r.get('diagnostics') or {}).get('llm_calls', [])) for r in rows) == len(requests)
    assert all(r['requested_model'] == plan['model'] for r in requests)
    assert all(r.get('response_model') == plan['model'] for r in requests if r['status'] == 'ok')
    assert plan['thinking_mode'] == 'disabled' and plan['sdk_max_retries'] == 0 and plan['max_output_tokens'] == 1024
    budget = json.loads((path/'budget.json').read_text())
    assert budget['status'] == 'closed' and budget['used'] == len(requests)
    assert budget['plan_sha256'] == sha(path/'plan.json') and budget['trace_sha256'] == sha(path/'live.jsonl')
    assert all(r['case_id'] in {row['case_id'] for row in rows} for r in requests)
    with zipfile.ZipFile(path/'source.zip') as archive:
        assert all(hashlib.sha256(archive.read('runtime/'+name)).hexdigest() == value
                   for name, value in plan['source_sha256'].items())
    counts = group(rows)
    assert counts['timed_score'] == summary['total_score']
    assert counts['untimed_score'] == summary['untimed_score']
    return plan, rows, {'source': str(path), 'scores': counts, 'generation_requests': len(requests),
                        'failed_requests': summary['failed_requests'], 'trace_sha256': sha(path/'live.jsonl'),
                        'source_zip_sha256': sha(path/'source.zip'),
                        'budget': budget, 'completed_cases': completed, 'original_planned_cases': count}


def same_query_sources(left, right):
    shared = set(left['source_sha256']) & set(right['source_sha256'])
    recorder_only = {'scripts/train_live.py', 'scripts/run_saved_training.py'}
    differing = {name: [left['source_sha256'][name], right['source_sha256'][name]] for name in shared
                 if left['source_sha256'][name] != right['source_sha256'][name]}
    assert set(differing) <= recorder_only, differing
    for prefix in ['implementation/', 'experiments/a_family_candidate_132_v2_r4_20261030/']:
        assert {n: h for n, h in left['source_sha256'].items() if n.startswith(prefix)} == {
            n: h for n, h in right['source_sha256'].items() if n.startswith(prefix)}
    assert left['feature_flags'] == right['feature_flags']
    for key in ['model', 'thinking_mode', 'sdk_max_retries', 'max_output_tokens', 'template_count', 'template_revision', 'base_url']:
        assert left[key] == right[key]
    return shared, differing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-run', type=Path, required=True)
    parser.add_argument('--validation-run', type=Path, required=True, action='append',
                        help='完整50目录，或依次传入中断前缀目录及未请求后缀目录')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    left, train, train_summary = load_run(args.train_run, 150, 'train_only')
    assert 1 <= len(args.validation_run) <= 2
    right, validation, prefix_summary = load_run(args.validation_run[0], 50, 'sealed50_validation',
                                               incomplete_prefix=len(args.validation_run) == 2)
    shared, recorder_differences = same_query_sources(left, right)
    segments = [prefix_summary]
    if len(args.validation_run) == 2:
        suffix, suffix_rows, suffix_summary = load_run(args.validation_run[1], 50-len(validation), 'sealed50_resume')
        _, recorder_differences = same_query_sources(left, suffix)
        same_query_sources(right, suffix)
        parent = suffix['resume_parent']
        assert parent['completed_prefix'] == len(validation) and parent['manual_retry'] is False
        assert (ROOT/parent['path']).resolve() == args.validation_run[0].resolve()
        assert suffix['case_ids'] == right['case_ids'][len(validation):]
        assert all(sha(ROOT/name) == digest for name, digest in parent['files_sha256'].items())
        validation += suffix_rows
        segments.append(suffix_summary)
    validation_summary = {'source_segments': segments, 'scores': group(validation),
                          'generation_requests': sum(r['generation_requests'] for r in segments),
                          'failed_requests': sum(r['failed_requests'] for r in segments),
                          'one_continuous_process': len(segments) == 1}
    manifest = json.loads((ROOT/'datasets/whitebox_150_50_v1/manifest.json').read_text())
    dataset_path = ROOT/'CMDB用例集-白盒200.json'
    assert sha(dataset_path) == manifest['source_dataset_sha256']
    dataset = json.loads(dataset_path.read_text())['cases']
    expected = {r['case_id']: (i + 1, r['question']) for i, r in enumerate(dataset)}
    assert len(train) == 150 and len(validation) == 50
    assert not {r['case_id'] for r in train} & {r['case_id'] for r in validation}
    assert {r['case_id'] for r in train + validation} == set(expected) and len(expected) == 200
    rows = []
    for row in train + validation:
        position, question = expected[row['case_id']]
        assert question == row['question']
        rows.append(dict(row, partition_case_index=row['case_index'], case_index=position))
    rows.sort(key=lambda row: row['case_index'])
    failures = []
    for row in rows:
        d = row.get('diagnostics') or {}
        if row['score_without_time_penalty'] == 5 and not d.get('empty_answer_fallback'): continue
        failures.append({'case_id': row['case_id'], 'position': row['case_index'], 'question': row['question'],
                         'score': row['score'], 'untimed_score': row['score_without_time_penalty'],
                         'reason': reason(row), 'scorer_reason': row['reason'],
                         'guess': bool(d.get('empty_answer_fallback')), 'family_error': d.get('family_error'),
                         'selected_template': d.get('selected_template'),
                         'missing_resources': (d.get('resource_coverage') or {}).get('unsupported'),
                         'missing_filter': d.get('missing_api_filter'), 'obligations': d.get('obligations')})
    report = {'type': 'same_candidate_two_partition_coverage', 'status': 'complete',
              'one_continuous_process': False, 'cache_policy': 'fresh process per run segment; no case repeated',
              'template_count': left['template_count'], 'template_revision': left['template_revision'],
              'overall': group(rows), 'first170': group(rows[:170]), 'last30': group(rows[170:]),
              'training150': train_summary, 'validation50': validation_summary,
              'shared_source_sha256': {name: left['source_sha256'][name] for name in sorted(shared-recorder_differences.keys())},
              'recorder_only_differences': recorder_differences,
              'failure_reasons': dict(Counter(row['reason'] for row in failures)),
              'dataset_sha256': sha(dataset_path), 'analysis_script_sha256': sha(Path(__file__)),
              'validation_status': 'previously_exposed; not untouched holdout',
              'limits': 'single sample per case; no model stability or official weighted-score claim'}
    if args.baseline:
        base_plan = json.loads((args.baseline/'plan.json').read_text())
        baseline = json.loads((args.baseline/'case_results.json').read_text())
        by_id = {row['case_id']: row for row in baseline}
        assert set(by_id) == set(expected)
        changed = [{'case_id': row['case_id'], 'before': by_id[row['case_id']]['score_without_time_penalty'],
                    'after': row['score_without_time_penalty']}
                   for row in rows if row['score_without_time_penalty'] != by_id[row['case_id']]['score_without_time_penalty']]
        report['baseline_observation'] = {'source': str(args.baseline), 'template_count': base_plan['template_count'],
            'scores': group(baseline), 'changed_cases': changed,
            'interpretation': 'library plus B integration; source/order/cache differ, descriptive comparison only'}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir/'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (args.output_dir/'failures.json').write_text(json.dumps(failures, ensure_ascii=False, indent=2)+'\n')
    (args.output_dir/'case_results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'shared_source_sha256', 'baseline_observation'}}, ensure_ascii=False))


if __name__ == '__main__': main()
