"""冻结收据离线回放和profile：零网络/零模型，结果完整对比，不补造历史live。"""
import argparse
from contextlib import ExitStack
import cProfile
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pstats
import resource
import socket
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'implementation'),str(ROOT/'scripts')]
import runbook_issue3 as issue3
from check_official_integrity import require_official_files


def digest_file(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenReader:
    def __init__(self,cache):
        self.cache=cache;self.base='http://127.0.0.1:8080';self.actual_calls=[];self.fetches=0
        self.schemas={s['ci']:s['columns'] for s in cache.values()}
        self.by_request={issue3.digest(s['request']):s for s in cache.values()}
        if len(self.by_request)!=len(cache):raise ValueError('ambiguous_frozen_requests')

    def fetch(self,call):
        self.fetches+=1
        key=issue3.digest(call)
        if key not in self.by_request:raise ValueError('new_request_not_in_frozen_capture')
        self.actual_calls.append(call)
        return self.by_request[key]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--profile',action='store_true')
    p.add_argument('--copy-mode',choices=['standard','fast'],default='standard')
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    captured=a.capture_dir.resolve();start=time.perf_counter()
    source=json.loads((captured/'summary.json').read_text());plan=json.loads((captured/'plan.json').read_text())
    cache=json.load(gzip.open(captured/'raw_snapshots.json.gz','rt'));expected=json.load(gzip.open(captured/'result.json.gz','rt'))
    os.environ['RUNBOOK_JSON_COPY_MODE']=a.copy_mode
    reader=FrozenReader(cache);before=issue3.digest(cache);loading=time.perf_counter()-start
    identity=source['execution']['source_snapshot'];diagnostics={};attempts=[]
    paths=['implementation/runbook_issue3.py','implementation/runbook_issue4.py','implementation/runbook_issue4_vm_links.py','implementation/runbook_copy.py']
    frozen={name:digest_file(ROOT/name) for name in paths}
    def forbidden(*args,**kwargs):attempts.append(True);raise AssertionError('offline_replay_forbids_network')
    profiler=cProfile.Profile()
    print(json.dumps({'status':'replay_started','kind':plan['_issue3']['kind'],'profile':a.profile,'frozen_fetch_roles':len(cache),'model_requests':0}),flush=True)
    with ExitStack() as stack:
        stack.enter_context(patch.object(issue3,'_local_readonly_identity',return_value=identity))
        for target,name in [(socket.socket,'connect'),(socket.socket,'connect_ex'),(socket,'create_connection')]:
            stack.enter_context(patch.object(target,name,side_effect=forbidden))
        t=time.perf_counter()
        result=(profiler.runcall(issue3.execute_plan,plan,[],diagnostics,reader=reader) if a.profile else
                issue3.execute_plan(plan,[],diagnostics,reader=reader))
        elapsed=time.perf_counter()-t
    strict_sha=lambda value:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    actual_sha,expected_sha=strict_sha(result),strict_sha(expected)
    if actual_sha!=expected_sha:raise ValueError('frozen_replay_full_output_or_JSON_types_changed')
    if issue3.digest(cache)!=before:raise ValueError('original_frozen_receipts_mutated')
    if any(digest_file(ROOT/name)!=h for name,h in frozen.items()):raise ValueError('runtime_changed_during_replay')
    if attempts:raise ValueError('unexpected_network_attempts')
    rows=result['result']['rows'];counts={k:diagnostics.get(k) for k in [
        'A_detail_rows','A_group_rows','all_A_details_retained','all_A_groups_retained','business_complete',
        'full_eip_objects_binding_complete','relation_state_counts','selected_tenant_EIP_catalog_count'] if k in diagnostics}
    summary={'status':'offline_replay_complete_output_equal','kind':plan['_issue3']['kind'],'profile_enabled':a.profile,
        'execution_seconds':elapsed,'capture_load_and_digest_seconds':loading,
        'copy_mode':a.copy_mode,
        'peak_process_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024*1024 if sys.platform=='darwin' else 1024),
        'full_output_equal':True,'raw_receipts_unchanged':True,'output_rows':len(rows),'preserved':counts,
        'strict_output_sha256':actual_sha,'expected_output_sha256':expected_sha,
        'model_requests':0,'HTTP_requests':0,'network_attempts':len(attempts),'fetch_replay_calls':reader.fetches,
        'capture_sha256':{n:digest_file(captured/n) for n in ['raw_snapshots.json.gz','result.json.gz','plan.json','summary.json']},
        'source_sha256':frozen,'official_integrity':require_official_files(),
        'meaning':'new offline replay of independent native snapshot, not reconstructed historical live output or new model score'}
    if a.profile:
        profiler.dump_stats(str(out/'replay.prof'));text=io.StringIO()
        pstats.Stats(profiler,stream=text).strip_dirs().sort_stats('cumulative').print_stats(45)
        (out/'profile.txt').write_text(text.getvalue())
    with gzip.open(out/'replayed_output.json.gz','wt',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,allow_nan=False)
    (out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['capture_sha256','source_sha256','official_integrity']},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
