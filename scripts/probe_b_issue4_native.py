"""B新网络合同完整原生捕获、typed与结果守恒验收；不调用模型或评分。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
import runbook_issue4 as network
from runbook_issue3 import NativeReader,execute_plan
from check_official_integrity import require_official_files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    parsed=network.parameters(args.question)
    if parsed is None:parser.error('完整原文不属于已绑定网络合同')
    family,params=parsed;adapter=network.module();plan=adapter.build(family,params)
    execution={};reader=NativeReader(execution,raw_duplicate_resources={'PORT'})
    report={'model_requests':0,'scoring_executed':False,'default_profile_enabled':False,
        'family':family,'parameters':params,'official_integrity':require_official_files(ROOT),
        'A_sources':network.sources()[1]}
    try:
        for ci in plan['resources']:reader.schema(ci)
        selected={'id':'declarative_native_probe','name':'native contract','resources':['ROUTER','FLOATING_IPS']}
        bound=network.prepare(args.question,selected,reader.schemas)
        if bound is None:raise ValueError('actual_schema_cannot_bind_complete_question')
        (out/'plan.json').write_text(json.dumps(bound,ensure_ascii=False,indent=2)+'\n')
        result=execute_plan(bound,[],execution,reader=reader)
        with gzip.open(out/'result.json.gz','wt',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False)
        first=result['result']['rows'][0]
        report.update(status='native_passed',result_rows=result['result']['row_count'],
            summary_values={k:v for k,v in first.items() if not k.endswith('_json')},
            A_detail_rows=execution['A_detail_rows'],core_utf8_bytes=execution['core_utf8_bytes'])
    except Exception as error:report.update(status='blocked',reason=str(error),error_type=type(error).__name__)
    finally:
        reader.close();report['execution']=execution
        report['B_runtime_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['implementation/runbook_issue4.py','implementation/runbook_issue3.py']}
        with gzip.open(out/'raw_snapshots.json.gz','wt',encoding='utf-8') as stream:json.dump(reader.cache,stream,ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'official_integrity','A_sources','execution'}},ensure_ascii=False))
    return 0 if report['status']=='native_passed' else 1


if __name__=='__main__':raise SystemExit(main())
