"""原样A租户排名合同的完整原生捕获和两种未知政策验收；不评分或调用模型。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
from runbook_issue3 import NativeReader,_local_readonly_identity,module,source_files,execute_plan
from check_official_integrity import require_official_files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',required=True)
    parser.add_argument('--metric',required=True,choices=['vm_count','volume_count'])
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--b-replay',action='store_true',help='同一可信读取内核验B执行层，仍不调用模型或评分')
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    mod=module('tenant');params={'logicalRegionName':args.region,'metric':args.metric,
        'tie_policy':'all_ties','unknown_tenant_policy':'exclude_with_diagnostic'}
    plan=mod.build(params);(out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    report={'mode':'original_A_native_contract_not_model_score','model_requests':0,'production_enabled':False,
        'parameters':params,'source_sha256':source_files(),'official_integrity':require_official_files(ROOT)}
    execution={};reader=NativeReader(execution);snapshots={}
    try:
        before=_local_readonly_identity(reader.base)
        for ci,call in zip(plan['resources'],plan['api_call']):
            snap=reader.fetch(call);snapshots[ci]=snap
            report.setdefault('field_audit',{})[ci]={'rows':len(snap['rows']),
                'schema_missing':sorted(set(mod.SCHEMAS[ci])-set(snap['columns'])),
                'row_missing':{key:sum(key not in row for row in snap['rows']) for key in mod.SCHEMAS[ci]
                    if any(key not in row for row in snap['rows'])}}
        if before!=_local_readonly_identity(reader.base):raise ValueError('native_source_drift')
        report.update(native_capture_complete=True,source_snapshot=before,policies={})
        for policy in ['reject','exclude_with_diagnostic']:
            p=dict(params,unknown_tenant_policy=policy)
            prepared=mod.preflight(p,{ci:snap['pages'] for ci,snap in snapshots.items()})
            if prepared['status']=='ready_for_typed_sql':
                result=mod.execute_prepared(p,prepared)
                (out/(policy+'_result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
                report['policies'][policy]={'status':result['status'],'rows':len(result.get('rows',[])),
                    'diagnostics':result.get('diagnostics'),'leaders':sorted({r['tenant_id'] for r in result.get('rows',[])})}
            else:report['policies'][policy]=prepared
        if args.b_replay:
            kind='tenant_volume_rank' if args.metric=='volume_count' else 'tenant_vm_rank'
            b_plan=dict(plan,_issue3={'kind':kind,'parameters':params},_expected_result_columns=plan['output_columns'])
            b_diagnostics={};b_result=execute_plan(b_plan,[],b_diagnostics,reader=reader)
            (out/'B_result.json').write_text(json.dumps(b_result,ensure_ascii=False,indent=2)+'\n')
            report['B_execution']=b_diagnostics
            report['B_result']={'row_count':b_result['result']['row_count'],'bounds':b_diagnostics.get('tenant_ranking_bounds')}
            report['B_runtime_sha256']=hashlib.sha256((ROOT/'implementation/runbook_issue3.py').read_bytes()).hexdigest()
        if before!=_local_readonly_identity(reader.base):raise ValueError('native_source_drift_after_execution')
        report['status']='native_comparison_complete'
    except Exception as error:
        report.update(status='blocked',error_type=type(error).__name__,reason=str(error))
    finally:
        reader.close();report['execution']=execution
        with gzip.open(out/'raw_snapshots.json.gz','wt',encoding='utf-8') as stream:
            json.dump(snapshots,stream,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key not in {'source_sha256','official_integrity','source_snapshot','execution','B_execution'}},ensure_ascii=False))
    return 0 if report['status']=='native_comparison_complete' else 1


if __name__=='__main__':raise SystemExit(main())
