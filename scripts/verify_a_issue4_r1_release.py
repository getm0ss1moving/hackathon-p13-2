"""Verify this disabled public closure and replay synthetic controls, offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'experiments/a_issue4_r1_20261031'
MANIFEST=PACKAGE/'PUBLIC_MANIFEST.json'

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def verify():
 m=json.loads(MANIFEST.read_text());assert sha(canonical(m['files']))==m['closure_sha256'],'closure array changed'
 names=set()
 for f in m['files']:
  rel=Path(f['path']);assert not rel.is_absolute() and '..' not in rel.parts
  p=ROOT/rel;assert not p.is_symlink() and p.resolve().is_relative_to(ROOT)
  raw=p.read_bytes();assert sha(raw)==f['sha256'] and len(raw)==f['bytes'],f['path']
  assert f['path'] not in names;names.add(f['path'])
 actual=set()
 for directory in m['inventory_roots']:
  for p in (ROOT/directory).rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:actual.add(str(p.relative_to(ROOT)))
 actual|=set(m['external_files']);actual.discard(str(MANIFEST.relative_to(ROOT)))
 assert actual==names,'unexpected/missing public files: '+repr(actual^names)
 p=json.loads((PACKAGE/'consumer/PROVIDER_LOCK.json').read_text());provider=(PACKAGE/'consumer'/p['provider_root']).resolve()
 assert provider==PACKAGE/'provider' and sha((provider/'shared_policy.py').read_bytes())==p['source_sha256']
 assert p['source_sha256']=='ae861eebdd59a6b0bcb7b3e17156ffe0718411288e18b7d9a819aab295cbd609'
 binding=json.loads((PACKAGE/'management/BINDING.json').read_text())
 assert binding['default_enabled'] is False and binding['actual_runtime_N_delta']==0
 for record in binding['assets'].values():assert sha((PACKAGE/'management'/record['path']).read_bytes())==record['sha256']
 provenance=json.loads((PACKAGE/'PROVENANCE.json').read_text())
 for f in provenance['files']:assert sha((ROOT/f['published_path']).read_bytes())==f['published_sha256'],f['published_path']
 return {'status':'PASS','files':len(names),'closure_sha256':m['closure_sha256'],'manifest_sha256':sha(MANIFEST.read_bytes()),'default_enabled':False,'runtime_N_delta':0}

BOOTSTRAP="""import runpy,sys
from pathlib import Path
script=Path(sys.argv[1]).resolve();sys.argv=sys.argv[1:];sys.dont_write_bytecode=True
sys.path.insert(0,str(script.parent))
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):
  raise RuntimeError('offline replay forbids '+event)
sys.addaudithook(audit)
runpy.run_path(str(script),run_name='__main__')
"""

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--verify-only',action='store_true');ap.add_argument('--output',type=Path);ap.add_argument('--legacy-source-root',type=Path);a=ap.parse_args()
 integrity=verify()
 if a.verify_only:print(json.dumps(integrity));return
 if a.output is None:ap.error('--output is required for replay')
 out=a.output.resolve();assert not out.exists() and out!=ROOT and ROOT not in out.parents,'fresh external output directory required'
 out.mkdir(parents=True)
 jobs=[
  ('main115',['scripts/a_issue4_r1/validate_main.py','--output',str(out/'main115.json')]),
  ('volume33',['experiments/a_issue4_r1_20261031/main/volume_types.py','--self-test',str(out/'volume33.json')]),
  ('provider',['scripts/a_issue4_r1/test_provider.py','--output',str(out/'provider.json')]),
  ('consumer43',['scripts/a_issue4_r1/test_consumer.py']),
  ('paired14',['scripts/a_issue4_r1/paired_smoke.py','--output-dir',str(out/'paired14')]),
  ('address23',['scripts/a_issue4_r1/test_address.py']),
  ('address8',['scripts/a_issue4_r1/test_address_boundaries.py']),
  ('capacity25',['scripts/a_issue4_r1/test_capacity.py',str(out/'capacity25.json')]),
  ('capacity_nullable',['scripts/a_issue4_r1/test_capacity_nullable.py','--output',str(out/'capacity_nullable.json')])]
 if a.legacy_source_root is not None:jobs.append(('management50',['scripts/a_issue4_r1/test_management.py','--legacy-source-root',str(a.legacy_source_root.resolve()),'--output-dir',str(out/'management')]))
 records=[]
 for name,args in jobs:
  r=subprocess.run([sys.executable,'-B','-c',BOOTSTRAP,*args],cwd=ROOT,capture_output=True)
  raw=r.stdout+r.stderr;(out/(name+'.log')).write_bytes(raw)
  records.append({'name':name,'exit_code':r.returncode,'log_sha256':sha(raw),'passed':r.returncode==0})
  if r.returncode:print(raw.decode(errors='replace'));break
 result={'status':'PASS'if all(r['passed']for r in records)and len(records)==len(jobs)else'FAIL','integrity':integrity,'replays':records,'management_replay':a.legacy_source_root is not None,'model_calls':0,'business_API_calls':0,'native_SQL_runs':0,'official_evaluation_runs':0,'not_business_or_score_certification':True}
 (out/'REPLAY_SUMMARY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
 assert verify()==integrity,'source changed during replay'
 raise SystemExit(result['status']!='PASS')

if __name__=='__main__':main()
