"""仅对已记录失败做原文填参的纯函数诊断；不改运行时、不执行API/SQL或评分。"""
import argparse
import copy
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'implementation')]
import runbook_matcher as m
from runbook_items import RUNBOOK_ITEMS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('不覆盖已存诊断')
    plan=json.loads((args.run_dir/'plan.json').read_text())
    os.environ.update(plan['feature_flags'])
    items = {item['id']: item for item in RUNBOOK_ITEMS}
    entry = m._a132_module('unified_prepare')
    rows = []
    for line in (args.run_dir/'live.jsonl').read_text().splitlines():
        try: row = json.loads(line)
        except json.JSONDecodeError: continue
        if row.get('type') == 'case': rows.append(row)
    records = []
    attempts = []
    def blocked(*a, **kw):
        attempts.append(True)
        raise AssertionError('纯函数诊断禁止网络')
    with patch.object(socket.socket,'connect',blocked), patch.object(socket.socket,'connect_ex',blocked), \
            patch.object(socket,'create_connection',blocked):
        for row in rows:
            d = row.get('diagnostics') or {}
            item = items.get(d.get('selected_template'))
            if not d.get('empty_answer_fallback') or not entry.handles_item(item): continue
            parsed = (d.get('parameters') or {}).get('llm_extracted')
            question = row['question']
            entry.prepare_candidate(m._a132_prepare_question(question,item,parsed),item,parsed,{})
            recovered=m._recover_a132_parameters(question,item,parsed,entry)
            accepted={}
            for ordinary, proposal, helper in recovered:
                key=json.dumps({'api_call':ordinary['api_call'],'sql':ordinary['sql']},sort_keys=True,ensure_ascii=False)
                accepted[key]={'parameters':proposal,'sql':ordinary['sql'],'prepare_evidence':helper}
            records.append({'case_id':row['case_id'],'selected_template':item['id'],'original_parameters':parsed,
                            'distinct_prepared_plans':len(accepted),
                            'unique_pure_recovery':len(accepted)==1,'accepted':list(accepted.values())})
    report={'scope':'observed_failed_cases_only','recorded_cases_seen':len(rows),'checked_failures':len(records),
            'unique_pure_recoveries':sum(r['unique_pure_recovery'] for r in records),'socket_attempts':len(attempts),
            'model_requests':0,'service_requests':0,'sql_executed':False,'new_scores':None,
            'production_query_executed':False,'matcher_sha256':m.hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
            'note':'候选参数已过原文prepare不等于真实API结果或评分通过；仅复放已记录失败，不执行模型或查询。',
            'records':records}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},ensure_ascii=False))


if __name__=='__main__':main()
