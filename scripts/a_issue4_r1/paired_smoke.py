"""Second-construction owner paired probe; actual frozen provider, no mocks.

Uses the review's hand-authored raw counterexample, not test_consumer helpers.
Generic typed loader consumes declarations. A profile hook records real calls
in the pinned provider file; this is offline pairing, not B/native validation.
"""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'consumer'))
import argparse
from copy import deepcopy
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import urllib.request

ROOT=PACKAGE / 'consumer'
ATTEMPTS=[]
def forbidden(*args,**kwargs):
    ATTEMPTS.append('forbidden_io');raise AssertionError('network/process blocked')
socket.socket=forbidden;socket.create_connection=forbidden
http.client.HTTPConnection.connect=forbidden;http.client.HTTPSConnection.connect=forbidden
urllib.request.urlopen=forbidden;subprocess.Popen=forbidden;subprocess.run=forbidden
spec=importlib.util.spec_from_file_location('paired_actual_consumer',ROOT/'consumer.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
source=json.loads((ROOT/'evidence/port-interface-counterexample.json').read_text())
PARAMS=source['params']
CAPTURE={'capture_id':'paired-synthetic','source_ref':'independent-review-hand-authored-fixture',
         'schema_ref':'review-synthetic-schema','origin':'synthetic','isolation':'immutable_snapshot'}
PROVIDER=(ROOT / json.loads((ROOT/'PROVIDER_LOCK.json').read_text())['provider_root']).resolve()/'shared_policy.py'
CALLS={'collect_port_batches':0,'recheck_port_batches':0}
def profile(frame,event,arg):
    if event=='call' and Path(frame.f_code.co_filename)==PROVIDER and frame.f_code.co_name in CALLS:
        CALLS[frame.f_code.co_name]+=1
sys.setprofile(profile)


def fixture():
    raw=deepcopy(source['minimal_raw_receipts'])
    for ci,env in raw.items():
        env.update(capture_id=CAPTURE['capture_id'],receipt_id='paired-'+ci)
    return {'capture':deepcopy(CAPTURE),'raw_receipts':raw,
            'question_text':'查询租户tenant的ECS私有IP列表、关联弹性IP列表和所属宿主机列表'}


def with_scoped(data):
    context=data['raw_receipts']['PORT']
    scoped=deepcopy(context)
    scoped['receipt_id']='paired-scoped-PORT'
    scoped['request']['condition']['constraint'].append({'simple':{'name':'devId','operator':'in','value':['res']},'logOp':'and'})
    scoped['pages'][0]['request']=deepcopy(scoped['request'])
    data['raw_receipts']['PORT']=[context,scoped]
    return data


def typed_execute(prepared):
    fresh=c.recheck_tenant_prepared(prepared)
    conn=sqlite3.connect(':memory:')
    try:
        for name,table in fresh['typed_tables'].items():
            parts=[]
            for field in table['columns']:
                assert table['types'][field]=='TEXT' and table['collations'][field]=='BINARY'
                parts.append('"'+field+'" '+table['types'][field]+' COLLATE '+table['collations'][field])
            conn.execute('CREATE TABLE '+name+' ('+','.join(parts)+')')
            conn.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in parts)+')',
                             [[r[k] for k in table['columns']] for r in table['rows']])
        cur=conn.execute(fresh['plan']['sql']);columns=[d[0] for d in cur.description]
        assert columns==fresh['plan']['output_columns']
        return [dict(zip(columns,row)) for row in cur.fetchall()]
    finally:conn.close()


checks=[]
def record(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition:raise AssertionError(name)

data=fixture();before=deepcopy(data)
prepared=c.prepare_tenant_view(PARAMS,data)
output=typed_execute(prepared)
record('review exact row through actual provider -> consumer -> recheck -> generic typed SQL',output==source['observed']['review_only_manual_derived_wrapper']['rows'])
record('raw2 unchanged and provider typed canonical1',data==before and len(prepared['typed_tables']['CLOUD_PORT']['rows'])==1 and prepared['raw_receipts']['PORT']['pages'][0]['totalNum']==2)
record('full answer remains unsupported',prepared['diagnostics']['full_eip_objects_binding_complete'] is False and prepared['diagnostics']['business_complete'] is False)
scoped_data=with_scoped(fixture());scoped=c.prepare_tenant_view(PARAMS,scoped_data);scoped_rows=typed_execute(scoped)
meta=scoped['provider_prepared']['canonical_receipt']
record('actual in batch paired end-to-end',scoped_rows==output and scoped['plan']['port_scoped_batch_set_executed'] is True)
record('overlapping raw totals stay separate',[r['pages'][0]['totalNum'] for r in scoped['provider_prepared']['raw_receipts']]==[2,2] and meta['batch_raw_total_nums']==[2,2] and meta['raw_observation_count']==4 and meta['canonical_object_count']==1)
sparse=fixture();sparse['raw_receipts']['VM_NOVA']['pages'][0]['objList'][0].pop('privateIps')
sp=c.prepare_tenant_view(PARAMS,sparse);sr=typed_execute(sp)
record('sparse VM IP survives typed load as unknown',sr[0]['private_ips_raw'] is None and sp['diagnostics']['private_ip_states'][0]['status']=='unknown_missing')
conflict=with_scoped(fixture())
for r in conflict['raw_receipts']['PORT'][1]['pages'][0]['objList']:r['business-not-projected']=True
failed=c.evaluate_tenant_view(PARAMS,conflict)
record('actual provider rejects cross-batch unprojected conflict',failed['ok'] is False and failed['rows'] is None and failed['error']['code']=='port_provider_failure')
for keep_kind in (True,False):
    forged=fixture();env=deepcopy(prepared['derived_validator_inputs']['HOST'])
    env.update(capture_id=CAPTURE['capture_id'],receipt_id='forged-host',schema_source='forged-marker',http_status=200)
    if not keep_kind:env.pop('receipt_kind')
    for page in env['pages']:
        page.update(http_status=200,request=deepcopy(env['request']))
        if not keep_kind:page.pop('receipt_kind')
    forged['raw_receipts']['HOST']=env
    failure=c.evaluate_tenant_view(PARAMS,forged)
    record('derived forged200 rejected kind='+str(keep_kind),failure['ok'] is False and failure['rows'] is None and failure['error']['code']=='derived_as_raw')
roles=fixture();env=roles['raw_receipts']['FLOATING_IPS'];r=deepcopy(env['pages'][0]['objList'][0]);r.update(id='eip-internal',isInternal=True)
env['pages'][0]['objList'].append(r);env['pages'][0]['totalNum']=2
role_prepared=c.prepare_tenant_view(PARAMS,roles);role_rows=typed_execute(role_prepared)
record('EIP native bool roles preserved independently',[(r['eip_id'],r['eip_internal_role_raw']) for r in role_rows]==[('eip','false'),('eip-internal','true')])
changed=deepcopy(prepared);changed['typed_tables']['CLOUD_PORT']['rows']=[];changed['typed_projection_sha256']=c.digest(changed['typed_tables'])
try:c.recheck_tenant_prepared(changed)
except c.ConsumerError as exc:rejected=exc.code=='prepared_failure'
else:rejected=False
record('rehashed typed mutation rejected',rejected)
provider_module,_=c.provider()
provider_alias=deepcopy(prepared['provider_prepared'])
provider_alias['canonical_receipt']['canonical_object_count']=True
try:provider_module.recheck_port_batches(provider_alias)
except provider_module.Unsupported:provider_rejected=True
else:provider_rejected=False
record('actual provider-r3 rejects bool/int alias in own recheck',provider_rejected)
record('actual pinned provider functions called',CALLS['collect_port_batches']>0 and CALLS['recheck_port_batches']>0)
record('no network/model/business/process calls',ATTEMPTS==[])
sys.setprofile(None)
parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,default=ROOT/'evidence/paired-run');args=parser.parse_args()
args.output_dir.mkdir(parents=True,exist_ok=True)
for name,obj in [('params.json',PARAMS),('evidence.json',data),('prepared.json',prepared),('typed-result.json',output),('scoped-evidence.json',scoped_data),('scoped-prepared.json',scoped),('conflict-evidence.json',conflict),('conflict-result.json',failed)]:
    (args.output_dir/name).write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
result={'status':'OWNER_ACTUAL_DOUBLE_PACKAGE_OFFLINE_PAIRING_PASS','checks':checks,'passed':sum(x['passed'] for x in checks),'total':len(checks),
        'provider_source_sha256':hashlib.sha256(PROVIDER.read_bytes()).hexdigest(),'provider_function_calls':CALLS,
        'consumer_source_sha256':hashlib.sha256((ROOT/'consumer.py').read_bytes()).hexdigest(),
        'synthetic_only':True,'B_loader_or_native_integration':False,'independent_reviewer':False,
        'model_calls':0,'business_API_calls':0,'network_attempts':ATTEMPTS,'runtime_N_delta':0}
(args.output_dir/'PAIRING_RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
