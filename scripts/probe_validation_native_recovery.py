"""仅失败验证题的原生API/SQL复核；无模型请求，不冒充新模型成绩。"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--case-id', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('不能覆盖原生复核记录')
    plan = json.loads((args.run_dir/'plan.json').read_text())
    summary = json.loads((args.run_dir/'summary.json').read_text())
    assert plan['scope'] == 'sealed50_validation' and summary['status'] == 'complete'
    path = ROOT/'datasets/whitebox_150_50_v1/sealed_test.json'
    assert sha(path) == plan['evaluation_sha256']
    references = {r['case_id']: r for r in json.loads(path.read_text())['cases']}
    saved = {r['case_id']: r for r in json.loads((args.run_dir/'case_results.json').read_text())}
    assert set(args.case_id) <= references.keys() and len(args.case_id) == len(set(args.case_id))
    assert all(saved[cid].get('matched_runbook') is None for cid in args.case_id)
    os.environ.update(plan['feature_flags'])
    candidate_flags = {'RUNBOOK_PRESERVE_SPARSE_NULLS': '1', 'RUNBOOK_BIND_DEPLOY_NODE_REGION': '1'}
    os.environ.update(candidate_flags)
    sys.path.insert(0, str(ROOT/'implementation'))
    import runbook_matcher as matcher
    import runbook_system as system
    from evaluator import evaluate_case
    from check_official_integrity import require_official_files
    require_official_files(ROOT)
    source = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'implementation').glob('*.py')}
    matcher._warm_schema_cache()  # 原原生schema预热；不创建模型客户端。
    records = []
    for cid in args.case_id:
        row = saved[cid];d = row['diagnostics'];evidence = {}
        api = (d.get('parameters') or {}).get('effective_api')
        assert api is not None, '本工具只复核保存了有效API的失败题'
        original = d['template_sql']
        proposal = (d.get('sql') or {}).get('model_proposal')
        sql = matcher._validated_refinement(proposal, original, row['question'], evidence) if proposal else original
        item = {'api_call': copy.deepcopy(api), 'sql': sql}
        requested = {}
        matcher._auto_fill_params(row['question'], requested, ['logicalRegionName'], item)
        binding = matcher._resolve_logical_region_scope(item, requested)
        if binding is not None: assert binding['valid'], binding
        execution = {}
        answer = system._execute_bounded_api(item, execution)
        output = {'matched_runbook': 'native_saved_plan_recovery', 'api_call': item['api_call'],
                  'sql': sql, 'result': answer['result'], 'error': answer['error']}
        record = {'case_id': cid, 'baseline_score': row['score_without_time_penalty'],
                  'native_execution_score': evaluate_case(references[cid], output, 0)['score'],
                  'output': output, 'guard': evidence, 'binding': binding, 'execution': execution}
        records.append(record)
    assert not matcher.get_llm_events()
    assert source == {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'implementation').glob('*.py')}
    report = {'scope': 'failed_validation_native_replay_only', 'model_requests': 0,
              'not_a_fresh_model_or_full50_score': True, 'baseline_matcher_sha256': plan['source_sha256']['implementation/runbook_matcher.py'],
              'post_fix_runtime_sha256': source, 'schema_warmup': 'original warmup; not included in per-query data request counts',
              'candidate_flags': candidate_flags,
              'records': records}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps([{'case_id': r['case_id'], 'native_execution_score': r['native_execution_score'],
                       'row_count': r['output']['result']['row_count'], 'model_requests': 0} for r in records], ensure_ascii=False))


if __name__ == '__main__': main()
