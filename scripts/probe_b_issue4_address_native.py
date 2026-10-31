"""地址成员合同的完整原生验收；显式题文，无模型、无评分、无生产开关变更。"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
import runbook_issue4 as shared
import runbook_issue4_address as address
import runbook_matcher as matcher
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import RunbookRetriever
from runbook_issue3 import NativeReader,execute_plan
from check_official_integrity import require_official_files


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--question',required=True);p.add_argument('--output-dir',required=True,type=Path)
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ['RUNBOOK_JSON_COPY_MODE']='fast'
    a=address.module();files=dict(shared.sources()[1])
    for name in ['implementation/runbook_issue3.py','implementation/runbook_issue4.py',
                 'implementation/runbook_issue4_address.py','implementation/runbook_matcher.py',
                 'implementation/runbook_items.py','implementation/runbook_retriever.py',
                 'scripts/probe_b_issue4_address_native.py']:
        files[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    with zipfile.ZipFile(out/'source.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in files:z.write(ROOT/name,'runtime/'+name)
    execution={};reader=NativeReader(execution,max_http=1024,contain_fields={('VM_NOVA','privateIps')})
    report={'model_requests':0,'scoring_executed':False,'default_profile_enabled':False,
            'question':args.question,'official_integrity':require_official_files(ROOT),'source_sha256':files}
    started=time.perf_counter()
    try:
        for ci in a.SCHEMA:
            reader.schema(ci)
            body=reader.get(reader.base+'/rest/hackthon/db/schema/'+ci)
            matcher._remember_schema_values(ci,body.get('sample_data',[]),body['columns'])
        by_id={x['id']:x for x in RUNBOOK_ITEMS};plans=[]
        for candidate in RunbookRetriever(RUNBOOK_ITEMS).retrieve(args.question):
            plan=address.prepare(args.question,by_id[candidate.id],reader.schemas)
            if plan is not None:plans.append(plan)
        if len(plans)!=1:raise ValueError('native_unique_retrieved_address_contract_required')
        plan=plans[0];(out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
        result=execute_plan(plan,[],execution,reader=reader)
        with gzip.open(out/'result.json.gz','wt',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False)
        report.update(status='native_passed',output_rows=result['result']['row_count'],A_diagnostics=execution['A_diagnostics'])
    except Exception as error:
        report.update(status='blocked',reason=str(error),error_type=type(error).__name__)
    finally:
        reader.close();report.update(execution=execution,seconds=time.perf_counter()-started)
        with gzip.open(out/'raw_snapshots.json.gz','wt',encoding='utf-8') as f:json.dump(reader.cache,f,ensure_ascii=False)
    if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h for name,h in files.items()):
        report.update(status='blocked',reason='runtime_source_changed_during_native_capture')
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'source_sha256','official_integrity','execution','A_diagnostics'}},ensure_ascii=False))
    return 0 if report['status']=='native_passed' else 1


if __name__=='__main__':raise SystemExit(main())
