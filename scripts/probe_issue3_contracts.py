"""仅对既有B_INTEGRATE失败逐题检查A源码闭包、完整意图和物化；不调用模型。"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation')]
import runbook_issue3 as contracts
from runbook_items import RUNBOOK_ITEMS


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native',action='store_true',help='真实读取数据服务、preflight和SQL；仍不调用模型')
    args=p.parse_args()
    if args.output.exists():p.error('不覆盖旧诊断')
    ids={r['id'] for r in json.loads((ROOT/'experiments/a132_error_triage_20261031/CLASSIFICATION.json').read_text())['issues'] if r['group']=='B_INTEGRATE'}
    rows=json.loads((ROOT/'reports/a132_runtime_port_20261030/combined200/case_results.json').read_text())
    items={r['id']:r for r in RUNBOOK_ITEMS};records=[]
    sources=contracts.source_files()
    for row in rows:
        if row['case_id'] not in ids:continue
        d={};execution={};record={'case_id':row['case_id'],'question':row['question'],'baseline_score':row['score_without_time_penalty']}
        try:
            selected=items[row['diagnostics']['selected_template']]
            plan=contracts.prepare_selected(row['question'],selected,RUNBOOK_ITEMS,d)
            if plan is None:raise ValueError('complete_grammar_or_selected_resource_mismatch')
            record.update(status='materialized',profile=d['issue3_contract']['kind'],
                          api_sql_bytes=d['issue3_contract']['api_sql_bytes'],output_columns=plan['_expected_result_columns'])
            if args.native:
                result=contracts.execute_plan(plan,RUNBOOK_ITEMS,execution)
                answer=result.get('result') or {}
                record.update(native_execution=execution,result=answer,result_columns=answer.get('columns'),result_rows=answer.get('row_count'),error=result.get('error'))
        except Exception as exc:
            record.update(status='blocked',error_type=type(exc).__name__,reason=str(exc))
            if args.native and execution:record['native_execution']=execution
        records.append(record)
    report={'cases':len(records),'model_requests':0,'native':args.native,'service_requests':sum(r.get('native_execution',{}).get('http_requests',0) for r in records),
            'SQL_executed':any(r.get('native_execution',{}).get('sql_executed') for r in records),'source_sha256':sources,'records':records}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'source_sha256','records'}},ensure_ascii=False))
    for r in records:print(json.dumps({k:v for k,v in r.items() if k not in {'native_execution','question','result'}},ensure_ascii=False))


if __name__=='__main__':main()
