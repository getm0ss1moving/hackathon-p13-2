"""按原白盒题序分组复核已保存结果；各轮分开，不调用模型/服务或重算答案。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(rows, score_key):
    values = Counter('correct' if row[score_key] == 5 else 'wrong' if row[score_key] < 0
                     else 'zero' if row[score_key] == 0 else 'partial' for row in rows)
    return {key: values[key] for key in ['correct', 'partial', 'wrong', 'zero']}


def detail(row, position):
    d = row.get('diagnostics') or {}
    rejection = d.get('rejection') or {}
    m = d.get('matching') or {}
    extra = next((v['refusal_reason'] for v in d.values()
                  if isinstance(v, dict) and v.get('refusal_reason')), None)
    coverage = d.get('resource_coverage') or m.get('resource_coverage') or {}
    return {'position': position, 'case_id': row['case_id'], 'question': row['question'],
            'score': row['score'], 'untimed_score': row['score_without_time_penalty'],
            'runtime_abstained': row.get('matched_runbook') is None,
            'empty_guess': bool(d.get('empty_answer_fallback')),
            'reason': rejection.get('reason') or extra or d.get('reason') or m.get('reason'),
            'stage': rejection.get('stage'),
            'missing_resources': coverage.get('unsupported'),
            'missing_filter': d.get('missing_api_filter') or m.get('missing_api_filter'),
            'family_error': d.get('family_error') or m.get('family_error')}


def group(rows):
    abstentions = sum(row.get('matched_runbook') is None for row in rows)
    return {'cases': len(rows), 'runtime_abstentions': abstentions,
            'abstention_percent': round(100 * abstentions / len(rows), 4) if rows else None,
            'timed_score_counts': counts(rows, 'score'),
            'untimed_score_counts': counts(rows, 'score_without_time_penalty'),
            'empty_guesses': sum(bool((r.get('diagnostics') or {}).get('empty_answer_fallback')) for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, action='append', required=True)
    parser.add_argument('--tail-size', type=int, default=30)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = ROOT / 'CMDB用例集-白盒200.json'
    ids = [case['case_id'] for case in json.loads(source.read_text())['cases']]
    if len(ids) != len(set(ids)) or not 1 <= args.tail_size < len(ids):
        parser.error('原始题序或尾段大小无效')
    positions = {cid: index + 1 for index, cid in enumerate(ids)}
    tail = set(ids[-args.tail_size:])
    runs = []
    for directory in args.run_dir:
        directory = (ROOT / directory).resolve()
        plan = json.loads((directory / 'plan.json').read_text())
        summary = json.loads((directory / 'summary.json').read_text())
        rows = json.loads((directory / 'case_results.json').read_text())
        if (summary['status'] != 'complete' or len(rows) != summary['completed_cases']
                or len({r['case_id'] for r in rows}) != len(rows)
                or [r['case_id'] for r in rows] != plan['case_ids']
                or any(r['case_id'] not in positions for r in rows)):
            parser.error('仅分析题数完整、成员与计划一致的单轮结果')
        before = [row for row in rows if row['case_id'] not in tail]
        after = [row for row in rows if row['case_id'] in tail]
        left, right = group(before), group(after)
        runs.append({'source': str(directory), 'scope': plan['scope'],
                     'source_sha256': plan['source_sha256'],
                     'input_sha256': {name: sha(directory / name)
                                      for name in ['plan.json', 'summary.json', 'case_results.json']},
                     'before_tail': left, 'tail': right,
                     'abstention_delta_percentage_points': round(right['abstention_percent'] - left['abstention_percent'], 4)
                         if before and after else None,
                     'tail_details': sorted([detail(r, positions[r['case_id']]) for r in after], key=lambda r: r['position']),
                     'repeats': plan['repeats'], 'generation_requests': summary['generation_requests'],
                     'failed_requests': summary['failed_requests']})
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = {'type': 'descriptive_original_order_tail_analysis', 'dataset_sha256': sha(source),
              'tail_size': args.tail_size, 'tail_ids': ids[-args.tail_size:], 'runs': runs,
              'same_source_across_runs': all(r['source_sha256'] == runs[0]['source_sha256'] for r in runs),
              'combined200_result': None, 'new_model_requests': 0, 'new_service_requests': 0,
              'command': [sys.executable, *sys.argv], 'analysis_script_sha256': sha(Path(__file__))}
    (args.output_dir / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(args.output_dir), 'runs': [
        {'source': r['source'], 'before_tail': r['before_tail'], 'tail': r['tail'],
         'abstention_delta_percentage_points': r['abstention_delta_percentage_points']} for r in runs],
        'new_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
