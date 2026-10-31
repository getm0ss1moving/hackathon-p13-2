"""原样A容量排名合同的可信原生捕获与两种未知政策对照；不注册或评分。"""
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
from runbook_issue3 import NativeReader,_local_readonly_identity
from check_official_integrity import require_official_files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',required=True)
    parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    package=ROOT/'experiments/issue3_next_capabilities_20261030';manifest=json.loads((package/'MANIFEST.json').read_text())
    for name,h in manifest['files'].items():assert hashlib.sha256((package/name).read_bytes()).hexdigest()==h,name
    path=package/'modules/ranked_vdc_pool_http_r2/candidate.py'
    spec=importlib.util.spec_from_file_location('_B_capacity_native_probe',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    params={'logicalRegionName':args.region,'tie_policy':'all_ties','unknown_owner_policy':'reject','unknown_size_policy':'reject'}
    plan=mod.build(params);(out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    execution={};reader=NativeReader(execution,max_http=128,seconds=90);snapshots={}
    report={'mode':'isolated_A_native_preflight_SQL_not_B_model_score','model_requests':0,'production_enabled':False,
        'official_integrity':require_official_files(ROOT),'A_candidate_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'parameters':params,'byte_boundaries':plan['byte_boundaries']}
    try:
        before=_local_readonly_identity(reader.base)
        for ci,call in zip(mod.RESOURCES,plan['api_call']):
            snap=reader.fetch(call);pages=[]
            report.setdefault('native_field_audit',{})[ci]={'rows':len(snap['rows']),
                'missing_schema':sorted(set(mod.SCHEMA[ci])-set(snap['columns'])),
                'absent_fields':{f:sum(f not in row for row in snap['rows']) for f in mod.SCHEMA[ci]
                                 if any(f not in row for row in snap['rows'])}}
            for i,page in enumerate(snap['native_pages'],1):
                pages.append(dict(copy.deepcopy(page),ok=True,http_status=200,request=mod.request(ci,args.region,i,page['pageSize'])))
            snapshots[ci]={'ok':True,'http_status':200,'schema_source':snap['schema_source'],'columns':snap['columns'],'pages':pages}
        assert _local_readonly_identity(reader.base)==before,'native service changed'
        report['native_capture_complete']=True;report['policy_results']={}
        for policy in ['reject','known_only']:
            p=dict(params,unknown_owner_policy=policy,unknown_size_policy=policy);prepared=mod.preflight(p,snapshots)
            with gzip.open(out/(policy+'_prepared.json.gz'),'wt',encoding='utf-8') as stream:json.dump(prepared,stream,ensure_ascii=False)
            if prepared['status']=='ready_for_typed_sql':
                result=mod.execute_prepared(p,prepared)
                (out/(policy+'_result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
                report['policy_results'][policy]={'status':result['status'],'row_count':len(result.get('rows',[])),
                    'winners':sorted({r['vdc_id'] for r in result.get('rows',[])}),'diagnostics':result.get('diagnostics')}
            else:report['policy_results'][policy]=prepared
        report['status']='native_policy_comparison_completed'
    except Exception as error:report.update(status='blocked_during_capture',error_type=type(error).__name__,reason=str(error))
    finally:
        reader.close();report['execution']=execution
        with gzip.open(out/'raw_snapshots.json.gz','wt',encoding='utf-8') as stream:json.dump(snapshots,stream,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'official_integrity','execution','policy_results'}},ensure_ascii=False))
    if report.get('policy_results'):
        print(json.dumps({k:{a:b for a,b in v.items() if a!='diagnostics'} for k,v in report['policy_results'].items()},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
