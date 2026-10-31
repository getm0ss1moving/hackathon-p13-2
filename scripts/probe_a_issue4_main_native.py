"""A新主包的独立原生/typed验收；只读，不注册合同、不调用模型或评分。"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'implementation'), str(ROOT/'scripts')]
import runbook_issue4 as shared
from runbook_issue3 import NativeReader, _local_readonly_identity, digest
from check_official_integrity import require_official_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=['tenant','ranked_pool','network','capacity'], required=True)
    parser.add_argument('--parameters', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(); out = args.output_dir; out.mkdir(parents=True, exist_ok=False)
    params = json.loads(args.parameters.read_text()); adapter = shared.module()
    plan = adapter.build(args.family, params)
    (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    execution = {}; reader = NativeReader(execution,raw_duplicate_resources={'PORT'})
    receipts = {}; report = {'model_requests':0,'scoring_executed':False,'production_enabled':False,
        'family':args.family,'parameters':params,'A_sources':shared.sources()[1],
        'official_integrity':require_official_files(ROOT)}
    try:
        before = _local_readonly_identity(reader.base)
        for ci,call in zip(plan['receipt_resources'],plan['api_call']):
            snapshot = reader.fetch(call)
            receipts[ci] = shared.receipt(snapshot,call,adapter.policy)
        raw_digest = adapter.policy.digest(receipts)
        prepared = adapter.prepare_local(args.family,params,receipts)
        if prepared.get('status') != 'ready_for_typed_sql':
            raise ValueError('A_prepare_blocked:'+str(prepared.get('reason')))
        prepared = adapter.recheck_prepared(prepared)
        result = shared.typed_sql(plan['sql'],prepared['typed_tables'])
        expected = adapter.execute_local(args.family,params,receipts)
        if (expected.get('status') == 'blocked' or result['columns']!=expected['columns']
                or Counter(digest(r) for r in result['rows'])!=Counter(digest(r) for r in expected['rows'])):
            raise ValueError('B_typed_result_differs_from_A')
        if adapter.policy.digest(receipts)!=raw_digest:
            raise ValueError('native_receipts_mutated')
        shared.sources()
        if before!=_local_readonly_identity(reader.base):raise ValueError('native_source_drift')
        for filename,value in [('result.json.gz',result),('A_result.json.gz',expected)]:
            with gzip.open(out/filename,'wt',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,allow_nan=False)
        report.update(status='native_and_typed_passed',result_rows=result['row_count'],
            raw_populations={ci:sum(len(p['objList']) for p in r['pages']) for ci,r in receipts.items()},
            diagnostics=expected.get('diagnostics'),canonical_receipts=prepared['canonical_receipts'],
            source_snapshot=before,raw_receipts_sha256=raw_digest,
            API_SQL_core_bytes=plan['expanded_adapter_api_sql_bytes'],business_complete=False,
            final_official_depth_and_envelope='unresolved')
    except Exception as error:
        report.update(status='blocked',reason=str(error),error_type=type(error).__name__)
    finally:
        reader.close(); report['execution']=execution
        report['B_runtime_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ['implementation/runbook_issue4.py','implementation/runbook_issue3.py',str(Path(__file__).relative_to(ROOT))]}
        with gzip.open(out/'raw_snapshots.json.gz','wt',encoding='utf-8') as stream:json.dump(reader.cache,stream,ensure_ascii=False)
        with gzip.open(out/'raw_receipts.json.gz','wt',encoding='utf-8') as stream:json.dump(receipts,stream,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in
        {'A_sources','official_integrity','diagnostics','canonical_receipts','source_snapshot','execution','B_runtime_sha256'}},ensure_ascii=False))
    return 0 if report['status']=='native_and_typed_passed' else 1


if __name__=='__main__':raise SystemExit(main())
