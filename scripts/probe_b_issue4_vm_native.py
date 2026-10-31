"""真实consumer/provider租户VM/EIP捕获和B typed验收；不调用模型或评分。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
import runbook_issue4 as shared
import runbook_issue4_vm_links as links
from runbook_issue3 import NativeReader,execute_plan
from check_official_integrity import require_official_files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    params=links.parameters(args.question)
    if params is None:parser.error('完整原文不属于已绑定合同')
    a,_,_=links.layout(params);execution={};reader=NativeReader(execution,raw_duplicate_resources={'PORT'})
    report={'model_requests':0,'scoring_executed':False,'default_profile_enabled':False,'parameters':params,
        'official_integrity':require_official_files(ROOT),'A_sources':shared.sources()[1]}
    try:
        for ci in a['resources']:reader.schema(ci)
        plan=links.prepare(args.question,{'id':'declarative_native_probe','name':'native contract','resources':['VM_NOVA','FLOATING_IPS','HOST']},reader.schemas)
        if plan is None:raise ValueError('native_schema_cannot_bind_question')
        (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
        result=execute_plan(plan,[],execution,reader=reader)
        with gzip.open(out/'result.json.gz','wt',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False)
        report.update(status='native_passed',result_rows=result['result']['row_count'],
            A_detail_rows=execution['A_detail_rows'],relation_states=execution['relation_state_counts'],core_utf8_bytes=execution['core_utf8_bytes'])
    except Exception as error:report.update(status='blocked',reason=str(error),error_type=type(error).__name__)
    finally:
        reader.close();report['execution']=execution
        report['B_runtime_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['implementation/runbook_issue4.py','implementation/runbook_issue4_vm_links.py','implementation/runbook_issue3.py']}
        with gzip.open(out/'raw_snapshots.json.gz','wt',encoding='utf-8') as stream:json.dump(reader.cache,stream,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'official_integrity','A_sources','execution'}},ensure_ascii=False))
    return 0 if report['status']=='native_passed' else 1


if __name__=='__main__':raise SystemExit(main())
