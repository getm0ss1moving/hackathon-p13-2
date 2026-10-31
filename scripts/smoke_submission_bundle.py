"""在无Git的新解压目录验证提交ZIP；显式--run才调用一次真实查询。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]

CHILD='''import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'implementation'))
from runbook_system import RunbookQuerySystem
import runbook_matcher as matcher
q=json.load(sys.stdin)['question']
system=RunbookQuerySystem();client=matcher.get_llm();original=client.chat.completions.create;identities=[]
def create(*args,**kw):
    assert kw['model']=='deepseek-flash' and kw['max_tokens']==1024
    assert kw.get('extra_body')=={'thinking':{'type':'disabled'}} and client.max_retries==0
    response=original(*args,**kw)
    identities.append({'requested':kw['model'],'returned':response.model})
    assert response.model==kw['model']
    return response
client.chat.completions.create=create
t=time.perf_counter();output=system.query(q);elapsed=time.perf_counter()-t
print(json.dumps({'output':output,'elapsed':elapsed,'events':matcher.get_llm_events(),'models':identities},ensure_ascii=False))
client.close()
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--case-id',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--run',action='store_true')
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    case=next(c for c in json.loads((ROOT/'CMDB用例集-白盒200.json').read_text())['cases'] if c['case_id']==a.case_id)
    with zipfile.ZipFile(a.archive) as archive:
        for name in archive.namelist():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe_archive_path')
        archive.extractall(out/'extracted')
    stage=out/'extracted/submission'
    manifest=json.loads((stage/'SUBMISSION_MANIFEST.json').read_text())
    assert all(hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest for name,digest in manifest['files'].items())
    assert not (stage/'.git').exists()
    plan={'case_id':case['case_id'],'question':case['question'],'archive_sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),
        'maximum_requests':3,'model':'deepseek-flash','thinking':'disabled','max_tokens':1024,'SDK_retries':0,
        'no_git_directory':True,'files':manifest['files'],'run':a.run}
    (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.run:print(json.dumps({'status':'preflight','maximum_requests':3}));return 0
    environment=dict(os.environ,PYTHONPATH='',PYTHONNOUSERSITE='1',RUNBOOK_MAX_LLM_CALLS='3',
        RUNBOOK_MAX_OUTPUT_TOKENS='1024',RUNBOOK_THINKING_MODE='disabled',DEEPSEEK_MODEL='deepseek-flash')
    for line in (ROOT/'.env.local').read_text().splitlines():
        key,sep,value=line.partition('=')
        if sep and key in {'DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL'}:environment[key]=value
    process=subprocess.run([sys.executable,'-B','-c',CHILD],cwd=stage,env=environment,
        input=json.dumps({'question':case['question']}),capture_output=True,text=True)
    (out/'stderr.log').write_text(process.stderr)
    if process.returncode:
        (out/'failure.json').write_text(json.dumps({'returncode':process.returncode})+'\n');return process.returncode
    raw=json.loads(process.stdout);assert len(raw['events'])<=3 and raw['models']
    (out/'full_output.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    sys.path.insert(0,str(stage/'implementation'))
    from evaluator import evaluate_case
    timed=evaluate_case(case,raw['output'],raw['elapsed']);quality=evaluate_case(case,raw['output'],0)
    result={'case_id':a.case_id,'quality':quality['score'],'timed_score':timed['score'],
        'elapsed':raw['elapsed'],'requests':len(raw['events']),'failed_requests':sum(e['status']!='ok' for e in raw['events']),
        'models':raw['models'],'archive_sha256':plan['archive_sha256'],'status':'passed' if quality['score']==5 else 'not_full_quality',
        'raw_output_sha256':hashlib.sha256((out/'full_output.json').read_bytes()).hexdigest(),'new_full200_score':None}
    (out/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False));return 0 if quality['score']==5 else 1


if __name__=='__main__':raise SystemExit(main())
