"""核验同候选连续分批精确覆盖200题后合计原始分数；不重新评分或调用模型。"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from analyze_full_whitebox import group,reason,sha
from training_raw_output import RAW_OUTPUT_POLICY, verify_raw_output


def require(condition,message):
    if not condition:raise ValueError(message)


def read_batch(directory):
    directory=Path(directory).resolve()
    load=lambda name:json.loads((directory/name).read_text())
    plan=load('plan.json');summary=load('summary.json');budget=load('budget.json')
    trace=[json.loads(line) for line in (directory/'live.jsonl').read_text().splitlines()]
    rows=[r for r in trace if r.get('type')=='case'];requests=[r for r in trace if r.get('type')=='request']
    require(plan['scope']=='whitebox200_batch' and plan['holdout_evaluated'] is True,'not an explicit whitebox batch')
    require(summary['status']=='complete' and len(rows)==plan['case_count']==summary['completed_cases']==summary['planned_cases'],'batch incomplete')
    require(rows==load('case_results.json') and trace[-1]==summary,'case/summary trace mismatch')
    require(all(trace[0].get(k)==v for k,v in plan.items() if k not in {'created_at','authorization'}),'plan trace mismatch')
    require(0<=len(requests)==summary['generation_requests']==budget['used']<=plan['max_requests']<=450,'request ledger mismatch')
    require(budget['maximum']==summary['max_requests']==plan['max_requests'],'budget maximum mismatch')
    require(budget['child_exit_code']==0 and budget['failed']==summary['failed_requests']==sum(r['status']!='ok' for r in requests),'closed budget mismatch')
    require(plan['model']=='deepseek-flash' and plan['thinking_mode']=='disabled' and plan['sdk_max_retries']==0,'model/options mismatch')
    require(all(r['requested_model']==plan['model'] and (r['status']!='ok' or r.get('response_model')==plan['model']) for r in requests),'response model mismatch')
    with zipfile.ZipFile(directory/'source.zip') as archive:
        require(all(hashlib.sha256(archive.read('runtime/'+f)).hexdigest()==h for f,h in plan['source_sha256'].items()),'source archive drift')
        dataset=json.loads(archive.read('runtime/CMDB用例集-白盒200.json'))['cases']
    require(len(dataset)==200 and len({c['case_id'] for c in dataset})==200,'dataset is not unique200')
    first,last=plan['whitebox_range'];expected=dataset[first-1:last]
    require(1<=first<=last<=200 and last-first+1<=150,'invalid batch interval')
    require([r['case_id'] for r in rows]==plan['case_ids']==[r['case_id'] for r in expected],'identity/order mismatch')
    require([r['case_index'] for r in rows]==list(range(first,last+1)),'original index mismatch')
    require(all(r['question']==c['question'] for r,c in zip(rows,expected)),'question text mismatch')
    if plan.get('raw_output_policy') is not None:
        require(plan['raw_output_policy']==RAW_OUTPUT_POLICY,'unsupported raw output policy')
        for row in rows:
            verify_raw_output(directory,row)
    measured=group(rows)
    require(measured['timed_score']==summary['total_score'] and measured['untimed_score']==summary['untimed_score'],'score summary mismatch')
    return {'directory':str(directory),'plan':plan,'dataset':dataset,'rows':rows,'requests':requests,
            'summary':summary,'budget':budget,'trace_sha256':sha(directory/'live.jsonl'),'source_zip_sha256':sha(directory/'source.zip')}


def combine_batches(directories, expected_count=200):
    require(type(expected_count) is int and 1<=expected_count<=200,'invalid expected case count')
    batches=[read_batch(path) for path in directories]
    require(len(batches)>=1,'need original-order bounded batches')
    reference=batches[0];end=0;rows=[];requests=[]
    same=['source_sha256','feature_flags','template_count','model','base_url','thinking_mode',
          'thinking_extra_body','max_output_tokens','sdk_max_retries','scoring_revision','evaluation_sha256']
    for batch in batches:
        plan=batch['plan'];first,last=plan['whitebox_range']
        require(first==end+1,'overlap, gap or reordering between batches')
        require(batch['dataset']==reference['dataset'] and all(plan[k]==reference['plan'][k] for k in same),'query source/dataset/options changed between batches')
        require(plan.get('raw_output_policy')==reference['plan'].get('raw_output_policy'),'raw output policy changed between batches')
        rows+=batch['rows'];requests+=batch['requests'];end=last
    require(end==len(rows)==expected_count and [r['case_id'] for r in rows]==[c['case_id'] for c in reference['dataset'][:expected_count]],'requested coverage not proven')
    failures=[{'case_id':r['case_id'],'case_index':r['case_index'],'question':r['question'],
               'score':r['score'],'untimed_score':r['score_without_time_penalty'],'scorer_reason':r['reason'],
               'cause':reason(r),'selected_template':(r.get('diagnostics') or {}).get('selected_template'),
               'empty_guess':bool((r.get('diagnostics') or {}).get('empty_answer_fallback')),
               'api_call':r.get('api_call'),'sql':r.get('sql'),'result':r.get('result')}
              for r in rows if r['score_without_time_penalty']!=5]
    report={'scope':('whitebox200_all_development' if expected_count==200 else 'whitebox200_prefix_development'),'status':'complete','run_mode':'same frozen candidate, consecutive batches; fresh process/cache per batch',
            'single_process_round':False,'full_coverage_verified':expected_count==200,'requested_coverage_verified':True,'case_count':expected_count,'source_rows_rescored':False,
            'template_count':reference['plan']['template_count'],'overall':group(rows),
            'first170':group(rows[:170]),'last30':group(rows[170:]),
            'original_train150_members':group([r for r in rows if r.get('training_case_index') is not None]),
            'original_validation50_members':group([r for r in rows if r.get('training_case_index') is None]),
            'generation_requests':len(requests),'failed_requests':sum(r['status']!='ok' for r in requests),
            'raw_output_policy':reference['plan'].get('raw_output_policy'),
            'source_sha256':reference['plan']['source_sha256'],'feature_flags':reference['plan']['feature_flags'],
            'batches':[{k:b[k] for k in ['directory','summary','budget','trace_sha256','source_zip_sha256']} for b in batches],
            'limitation':'all200 exposed development questions; not unseen holdout or official weighted score; interrupted150 run excluded',
            'failure_details':failures}
    return report,rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,action='append',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    report,rows=combine_batches(args.batch)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    for name,value in [('analysis.json',report),('case_results.json',rows),('failures.json',report['failure_details'])]:
        (args.output_dir/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'source_sha256','feature_flags','batches','failure_details'}},ensure_ascii=False))


if __name__=='__main__':main()
