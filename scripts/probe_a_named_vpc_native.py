"""完整原生目录交给原样A合同验收；重复记录不清洗，仅诊断，不注册生产。"""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
from runbook_issue3 import NativeReader,_local_readonly_identity
from check_official_integrity import require_official_files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True);parser.add_argument('--region')
    parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    package=ROOT/'experiments/issue3_named_vpc_20261030';manifest=json.loads((package/'MANIFEST.json').read_text())
    for name,h in manifest['files'].items():
        assert hashlib.sha256((package/name).read_bytes()).hexdigest()==h, name
    spec=importlib.util.spec_from_file_location('_B_named_probe',package/'candidate.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    filters={'name':args.name}
    if args.region:filters['logicalRegionName']=args.region
    params={'profile':mod.PROFILE,'filters':filters,'required_filters':list(filters),'same_name_policy':'all_matching_parent_ids'}
    plan=mod.build(params);receipts={};execution={};reader=NativeReader(execution,max_http=128,seconds=90);diagnostics={}
    report={'mode':'isolated_native_A_validation_not_model_or_score','model_requests':0,'production_enabled':False,
        'official_integrity':require_official_files(ROOT),'parameters':params,
        'A_candidate_sha256':hashlib.sha256((package/'candidate.py').read_bytes()).hexdigest()}
    (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    try:
        before=_local_readonly_identity(reader.base)
        for call in plan['api_call']:
            parsed=urlsplit(call['url']);ci=parsed.path.rsplit('/',1)[-1];columns=reader.schema(ci)
            page=1;pages=[];population=[];expected=None
            while True:
                query={'pageNo':page,'pageSize':1000}
                if call.get('condition'):query['condition']=json.dumps(call['condition'],ensure_ascii=False,separators=(',',':'))
                body=reader.get(reader.base+parsed.path,query)
                total,n,current,size=(body.get(k) for k in ['totalNum','totalPageNo','currentPage','pageSize']);rows=body.get('objList')
                if (any(type(x)is not int for x in [total,n,current,size]) or total<0 or size!=1000 or current!=page
                    or n!=(total+999)//1000 or not isinstance(rows,list) or len(rows)!=min(1000,max(0,total-(page-1)*1000))):raise ValueError('invalid_native_page:'+ci)
                if expected is not None and expected!=(total,n):raise ValueError('native_total_drift:'+ci)
                expected=(total,n);population.extend(rows);pages.append(dict(copy.deepcopy(body),ok=True,pageNo=page))
                if page>=max(1,n):break
                page+=1
            counts=Counter(r.get('id') for r in population);duplicates={k:v for k,v in counts.items() if v>1}
            diagnostics[ci]={'raw_rows':len(population),'schema':columns,'duplicate_key_count':len(duplicates),
                'duplicate_extra_rows':sum(n-1 for n in duplicates.values()),'raw_pages':len(pages)}
            receipts[ci]={'ok':True,'request':call,'schema':columns,'schema_verified':True,'pages':pages}
        assert _local_readonly_identity(reader.base)==before,'native service changed'
        report['transport_capture_complete']=True
        prepared=mod.prepare(params,receipts);answer=mod.execute_prepared(prepared)
        report.update(status='native_A_prepare_and_SQL_passed',A_diagnostics=answer.get('diagnostics'),row_count=len(answer['rows']))
        (out/'result.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
    except Exception as error:
        report.update(status='blocked',reason=str(error),error_type=type(error).__name__)
    finally:
        reader.close();report.update(resources=diagnostics,execution=execution)
        with gzip.open(out/'raw_receipts.json.gz','wt',encoding='utf-8') as f:json.dump(receipts,f,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'official_integrity','execution','resources'}},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
