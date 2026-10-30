"""核验已完成的固定50验证及空结果/未作答；不重跑模型或重算预览分数。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_of(answer):
    if isinstance(answer, list):
        return [r for part in answer for r in rows_of(part)]
    if isinstance(answer, dict):
        return [r for r in answer.get('rows', []) if isinstance(r, dict)]
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.run_dir.resolve()
    destination = out/'analysis.json'
    if destination.exists(): parser.error('不能覆盖已有验证分析')
    plan = json.loads((out/'plan.json').read_text())
    manifest = json.loads((ROOT/'datasets/whitebox_150_50_v1/manifest.json').read_text())
    path = ROOT/'datasets/whitebox_150_50_v1/sealed_test.json'
    assert plan['scope'] == 'sealed50_validation' and plan['holdout_evaluated'] is True
    assert sha(path) == plan['evaluation_sha256'] == manifest['sealed_test_sha256']
    cases = json.loads(path.read_text())['cases']
    expected = {r['case_id']: r for r in cases}
    assert len(expected) == 50 and plan['case_ids'] == [r['case_id'] for r in cases]
    trace = [json.loads(line) for line in (out/'live.jsonl').read_text().splitlines()]
    assert trace[0]['type'] == 'validation_plan'
    assert all(trace[0].get(k) == v for k, v in plan.items() if k not in {'created_at', 'authorization'})
    records = [r for r in trace if r['type'] == 'case']
    requests = [r for r in trace if r['type'] == 'request']
    summary = trace[-1]
    assert summary['type'] == 'summary' and summary['status'] == 'complete'
    assert [r['case_id'] for r in records] == plan['case_ids'] and len(records) == 50
    assert all(r['question'] == expected[r['case_id']]['question'] for r in records)
    assert len(requests) == summary['generation_requests'] <= plan['max_requests'] <= 150
    assert all(r['requested_model'] == r['response_model'] == 'deepseek-flash' for r in requests)
    assert plan['thinking_mode'] == 'disabled' and plan['sdk_max_retries'] == 0
    assert plan['max_output_tokens'] == 1024
    with zipfile.ZipFile(out/'source.zip') as archive:
        assert all(hashlib.sha256(archive.read('runtime/'+name)).hexdigest() == value
                   for name, value in plan['source_sha256'].items())
    assert round(sum(r['score_without_time_penalty'] for r in records), 1) == summary['untimed_score']
    assert round(sum(r['score'] for r in records), 1) == summary['total_score']
    missing, empty_answers = [], []
    reference_empty = {cid for cid, c in expected.items() if not rows_of(c.get('answer'))}
    for r in records:
        d = r.get('diagnostics') or {}
        if r.get('matched_runbook') is None:
            execution_refusal = next((value['refusal_reason'] for value in d.values()
                                      if isinstance(value, dict) and value.get('refusal_reason')), None)
            rejection = d.get('rejection') or {}
            missing.append({'case_id': r['case_id'], 'question': r['question'],
                            'reason': rejection.get('reason') or execution_refusal or d.get('reason') or 'unknown',
                            'stage': rejection.get('stage'), 'selected_template': d.get('selected_template'),
                            'family_error': d.get('family_error'),
                            'missing_filter': d.get('missing_api_filter'),
                            'missing_resources': (d.get('resource_coverage') or {}).get('unsupported'),
                            'unfilled': (d.get('parameters') or {}).get('unfilled'),
                            'reference_empty': r['case_id'] in reference_empty})
        elif isinstance(r.get('result'), dict) and r['result'].get('row_count') == 0:
            empty_answers.append({'case_id': r['case_id'], 'score': r['score_without_time_penalty'],
                                  'reference_empty': r['case_id'] in reference_empty,
                                  'columns': r['result'].get('columns')})
    report = {'scope': 'sealed50_validation', 'status': 'complete', 'cases': 50,
              'runtime_abstentions': len(missing), 'answered_cases': 50-len(missing),
              'scorer_zero_without_time_penalty': sum(r['score_without_time_penalty'] == 0 for r in records),
              'timed_score': summary['total_score'], 'untimed_score': summary['untimed_score'], 'max_score': 250,
              'full_quality_answers': sum(r['score_without_time_penalty'] == 5 for r in records),
              'failed_requests': summary['failed_requests'], 'generation_requests': len(requests),
              'reason_counts': dict(Counter(r['reason'] for r in missing)),
              'reference_stored_empty_count': len(reference_empty),
              'abstentions_with_reference_empty': sum(r['reference_empty'] for r in missing),
              'abstentions_with_reference_nonempty': sum(not r['reference_empty'] for r in missing),
              'executed_empty_answers': empty_answers, 'abstention_details': missing,
              'runtime_sha256': plan['source_sha256']['implementation/runbook_matcher.py'],
              'evaluator_sha256': plan['source_sha256']['implementation/evaluator.py'],
              'trace_sha256': sha(out/'live.jsonl'), 'source_zip_sha256': sha(out/'source.zip'),
              'after_exposure_use': 'validation; not untouched holdout generalization',
              'not_a_combined200_score': True, 'analysis_script_sha256': sha(Path(__file__))}
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'abstention_details','executed_empty_answers'}}, ensure_ascii=False))


if __name__ == '__main__': main()
