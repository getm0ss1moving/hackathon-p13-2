"""验收A租户VM原生属性/宿主视图，原始稀疏行保留，不注册生产。"""
import argparse
from collections import Counter
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
    parser.add_argument('--tenant',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    package=ROOT/'experiments/issue3_next_capabilities_20261030';manifest=json.loads((package/'MANIFEST.json').read_text())
    for name,h in manifest['files'].items():assert hashlib.sha256((package/name).read_bytes()).hexdigest()==h,name
    path=package/'modules/vm_eip_host/candidate.py';spec=importlib.util.spec_from_file_location('_B_vm_native_probe',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    params={'view':'native_ip_host_rows','tenantName':args.tenant};plan=mod.build(params)
    (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    execution={};reader=NativeReader(execution);receipts={};audit={}
    report={'mode':'isolated_A_native_preflight_not_B_query_or_model_score','model_requests':0,'production_enabled':False,
        'official_integrity':require_official_files(ROOT),'parameters':params,
        'A_candidate_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        before=_local_readonly_identity(reader.base)
        for call in plan['api_call']:
            snap=reader.fetch(call);ci=snap['ci'];fields=mod.schema_for(params['view'])[ci]
            audit[ci]={'rows':len(snap['rows']),'schema_missing':sorted(set(fields)-set(snap['columns'])),
                'absent_fields':{f:sum(f not in r for r in snap['rows']) for f in fields if any(f not in r for r in snap['rows'])},
                'null_fields':{f:sum(r.get(f)is None for r in snap['rows']) for f in fields}}
            receipts[ci]={'ok':True,'http_status':200,'request':copy.deepcopy(call),'schema':snap['columns'],
                'schema_verified':True,'pages':snap['pages']}
        assert _local_readonly_identity(reader.base)==before,'native source changed'
        report['native_capture_complete']=True;report['source_snapshot']=before
        result=mod.execute_local(params,receipts)
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        report.update(status='native_A_SQL_passed',row_count=len(result['rows']),A_diagnostics=result['diagnostics'])
    except Exception as error:report.update(status='blocked',reason=str(error),error_type=type(error).__name__)
    finally:
        reader.close();report.update(execution=execution,field_audit=audit)
        with gzip.open(out/'raw_receipts.json.gz','wt',encoding='utf-8') as stream:json.dump(receipts,stream,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'official_integrity','execution','source_snapshot'}},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
