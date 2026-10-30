"""核对单轮完整白盒记录，区分计分0、原流程失败与猜空；不调用或重算模型。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classification(rows, key):
    result = Counter('correct' if row[key] == 5 else 'wrong' if row[key] < 0
                     else 'zero' if row[key] == 0 else 'partial' for row in rows)
    return {k: result[k] for k in ['correct', 'partial', 'wrong', 'zero']}


def reason(row):
    d = row.get('diagnostics') or {}
    rejection = d.get('rejection') or {}
    execution = next((v['refusal_reason'] for v in d.values()
                      if isinstance(v, dict) and v.get('refusal_reason')), None)
    if rejection.get('reason') or execution:
        return rejection.get('reason') or execution
    if (d.get('empty_answer_fallback') or {}).get('original_error'):
        return 'explicit_execution_error'
    return d.get('reason') or (d.get('matching') or {}).get('reason') or 'unclassified'


def group(rows):
    guesses = [r for r in rows if (r.get('diagnostics') or {}).get('empty_answer_fallback')]
    return {'cases': len(rows), 'timed_counts': classification(rows, 'score'),
            'untimed_counts': classification(rows, 'score_without_time_penalty'),
            'timed_score': round(sum(r['score'] for r in rows), 1),
            'untimed_score': round(sum(r['score_without_time_penalty'] for r in rows), 1),
            'runtime_abstentions': sum(r.get('matched_runbook') is None for r in rows),
            'empty_answer_guesses': len(guesses),
            'guess_reasons': dict(Counter(reason(r) for r in guesses)),
            'guess_untimed_counts': classification(guesses, 'score_without_time_penalty'),
            'api_gate_zero': sum('API条件不合规' in r['reason'] for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    if (directory/'analysis.json').exists(): parser.error('不覆盖既有分析')
    plan = json.loads((directory/'plan.json').read_text())
    trace = [json.loads(line) for line in (directory/'live.jsonl').read_text().splitlines()]
    rows = [r for r in trace if r.get('type') == 'case']
    requests = [r for r in trace if r.get('type') == 'request']
    summary = trace[-1]
    assert plan['scope'] == 'whitebox200_explicit' and plan['case_count'] == 200
    assert trace[0]['type'] == 'validation_plan' and plan['holdout_evaluated'] is True
    assert all(trace[0].get(k) == v for k, v in plan.items() if k not in {'created_at', 'authorization'})
    assert [r['case_id'] for r in rows] == plan['case_ids'][:len(rows)]
    assert len(requests) == summary['generation_requests'] <= plan['max_requests'] <= 450
    assert summary['type'] == 'summary' and len(rows) == summary['completed_cases']
    assert json.loads((directory/'case_results.json').read_text()) == rows
    assert all(r['requested_model'] == plan['model'] for r in requests)
    assert all(r.get('response_model') == plan['model'] for r in requests if r['status'] == 'ok')
    assert plan['thinking_mode'] == 'disabled' and plan['sdk_max_retries'] == 0
    with zipfile.ZipFile(directory/'source.zip') as archive:
        assert all(hashlib.sha256(archive.read('runtime/'+f)).hexdigest() == h
                   for f, h in plan['source_sha256'].items())
        dataset = json.loads(archive.read('runtime/CMDB用例集-白盒200.json'))['cases']
    assert [r['case_id'] for r in dataset] == plan['case_ids']
    assert all(r['question'] == dataset[i]['question'] for i, r in enumerate(rows))
    overall = group(rows)
    assert overall['timed_score'] == summary['total_score']
    assert overall['untimed_score'] == summary['untimed_score']
    if summary['status'] == 'complete': assert len(rows) == 200
    failures = []
    for row in rows:
        d = row.get('diagnostics') or {}
        if row['score_without_time_penalty'] == 5 and not d.get('empty_answer_fallback'):
            continue
        failures.append({'case_id': row['case_id'], 'case_index': row['case_index'],
                         'question': row['question'], 'score': row['score'],
                         'untimed_score': row['score_without_time_penalty'],
                         'reason': reason(row), 'scorer_reason': row['reason'],
                         'empty_guess': bool(d.get('empty_answer_fallback')),
                         'selected_template': d.get('selected_template'),
                         'missing_resources': (d.get('resource_coverage') or {}).get('unsupported'),
                         'missing_filter': d.get('missing_api_filter'), 'family_error': d.get('family_error'),
                         'result': row.get('result'), 'sql': row.get('sql')})
    report = {'scope': plan['scope'], 'status': summary['status'], 'template_count': plan['template_count'],
              'model': plan['model'], 'thinking_mode': plan['thinking_mode'], 'overall': overall,
              'first170': group([r for r in rows if r['case_index'] <= 170]),
              'last30': group([r for r in rows if r['case_index'] > 170]),
              'training150_members': group([r for r in rows if r.get('training_case_index') is not None]),
              'validation50_members': group([r for r in rows if r.get('training_case_index') is None]),
              'generation_requests': len(requests),
              'failed_requests': sum(r['status'] != 'ok' for r in requests),
              'budget': json.loads((directory/'budget.json').read_text()),
              'source_sha256': plan['source_sha256'], 'trace_sha256': sha(directory/'live.jsonl'),
              'source_zip_sha256': sha(directory/'source.zip'), 'analysis_script_sha256': sha(Path(__file__)),
              'source_rows_rescored': False, 'official_weighted_score': False,
              'failure_details': failures,
              'limitation': '同一冻结版本单轮本地评分；50已曝光为验证集，不代表独立未见题泛化。'}
    (directory/'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (directory/'failures.json').write_text(json.dumps(failures, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'source_sha256', 'failure_details'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
