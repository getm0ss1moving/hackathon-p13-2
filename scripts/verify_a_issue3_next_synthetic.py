"""Public adapted19-case replay of the default-disabled next capability closure.

Fresh synthetic HTTP failure inputs replace historical fixtures. Prepared relabel
checks use a current projection stripped of source evidence, not a legacy module.
Network prior18/18 is referenced only. No model, HTTP, B or official runtime calls.
"""
from pathlib import Path
from copy import deepcopy
import argparse,ast,hashlib,importlib.util,json,sys,traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'experiments/issue3_next_capabilities_20261030'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
for path,expected in manifest['files'].items():assert sha(PACKAGE/path)==expected,path
for path,expected in manifest['tools'].items():assert sha(ROOT/path)==expected,path
for path,expected in manifest['external_files'].items():assert sha(ROOT/path)==expected,path
closure=json.loads((PACKAGE/'SOURCE_CLOSURE.json').read_text())
assert closure['source_contract_files']==len(closure['files'])==8
for record in closure['files']:assert sha(PACKAGE/record['path'])==record['published_sha256']
for record in closure['files']:
 if record['path'].endswith('.py'):ast.parse((PACKAGE/record['path']).read_text())
 else:json.loads((PACKAGE/record['path']).read_text())
source_before={x['path']:sha(PACKAGE/x['path']) for x in closure['files']}
out=args.output.resolve()
assert out!=ROOT and ROOT not in out.parents,'output must be outside repository'
out.mkdir(parents=True,exist_ok=False)
def load(group):
 path=PACKAGE/'modules'/group/'candidate.py'
 spec=importlib.util.spec_from_file_location('public_next_'+group,path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
P=load('ranked_vdc_pool_http_r2');C=load('cluster_ranked_hosts');V=load('vm_eip_host')
cases=[]
def eq(a,b):
 assert a==b,'expected '+repr(b)+'; got '+repr(a)
 return a
def test(name,fn):
 try:cases.append({'id':name,'status':'PASS','detail':fn()})
 except Exception as e:cases.append({'id':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
def block(value):eq(value['status'],'blocked');return value.get('reason')
def ranked_fixture():
 region='fresh-rank-region'
 params={'logicalRegionName':region,'tie_policy':'all_ties','unknown_owner_policy':'reject','unknown_size_policy':'reject'}
 rows={'VOLUME':[{'id':identity,'logicalRegionName':region,'vdcId':owner,'vdcName':owner,'size':size,'attachBackendId':pool} for identity,owner,size,pool in [('fresh-v1','fresh-owner-A','4','fresh-p1'),('fresh-v2','fresh-owner-A','6','fresh-p2'),('fresh-v3','fresh-owner-B','10','fresh-p2')]],
       'STORAGE_POOL':[{'id':pool,'logicalRegionName':region,'poolName':pool,'totalCapacityGB':'100','freeCapacityGB':'50','allocatedCapacityGB':'40','provisionedCapacityGB':'60'} for pool in ['fresh-p1','fresh-p2']]}
 snapshots={}
 for ci in P.RESOURCES:
  data=rows[ci];size=2
  pages=[{'ok':True,'http_status':200,'currentPage':i//size+1,'pageSize':size,'totalNum':len(data),'totalPageNo':(len(data)+size-1)//size,'request':P.request(ci,region,i//size+1,size),'objList':deepcopy(data[i:i+size])} for i in range(0,len(data),size)]
  snapshots[ci]={'ok':True,'schema_source':'public owned synthetic fixture; not production provenance','columns':list(P.SCHEMA[ci]),'pages':pages}
 return {'params':params,'snapshots':snapshots}
old={}
for name in ['HTTP_envelope','HTTP_page']:
 fixture=ranked_fixture()
 if name=='HTTP_envelope':fixture['snapshots']['VOLUME']['http_status']=503
 else:fixture['snapshots']['VOLUME']['pages'][0]['http_status']=503
 old[name]=fixture
 def failed_receipt(name=name):
  f=old[name];o=P.execute(f['params'],f['snapshots']);block(o);return o
 test('HTTP_fresh_'+name+'_rejected',failed_receipt)
def state_matrix():
 n=0
 for alias in ['http_status','httpStatus','status_code']:
  for value,valid in [(200,True),(204,True),(299,True),(199,False),(300,False),(503,False),(True,False),(None,False),('200',False)]:
   eq(P.receipt_state({'ok':True,alias:value}),valid);n+=1
 for error,valid in [(None,True),(False,True),('',True),(0,False),([],False),({},False),('timeout',False)]:
  eq(P.receipt_state({'ok':True,'error':error}),valid);n+=1
 for success,valid in [(True,True),(False,False),(None,False),(1,False)]:
  eq(P.receipt_state({'ok':True,'success':success}),valid);n+=1
 return {'matrix_subcases_not_added':n}
test('HTTP_exact_state_matrix',state_matrix)
def good_p():
 f=deepcopy(old['HTTP_envelope'])
 for snap in f['snapshots'].values():
  snap.pop('http_status',None);snap['http_status']=200
  for page in snap['pages']:page['http_status']=200
 return f
def fresh_p():
 f=good_p();o=P.execute(f['params'],f['snapshots']);eq(o['status'],'local_sql_ok_policy_conditional');return {'rows':len(o['rows']),'full_answer_certified':o['diagnostics']['full_answer_certified']}
test('HTTP_valid_positive_not_all_reject',fresh_p)
def prepared_relabel(with_evidence):
 healthy=good_p();x=P.preflight(healthy['params'],healthy['snapshots']);eq(x['status'],'ready_for_typed_sql')
 # Simulate a source-free prepared object relabelled to the new contract.
 x.pop('input_evidence',None);x.pop('input_evidence_sha256',None)
 x['projection_contract']=P.build(healthy['params'])['projection_contract']
 if with_evidence:
  failed=old['HTTP_envelope']
  x['input_evidence']={'params':deepcopy(failed['params']),'snapshots':deepcopy(failed['snapshots'])}
  x['input_evidence_sha256']=P.fingerprint(x['input_evidence'])
 o=P.execute_prepared(healthy['params'],x);block(o);return o
test('HTTP_old_prepared_tag_alone_not_accepted',lambda:prepared_relabel(False))
test('HTTP_relabel_plus_failed_source_evidence_rejected',lambda:prepared_relabel(True))
def p_attribute():
 f=good_p();pool=f['snapshots']['STORAGE_POOL']['pages'][0]['objList'][0];pool['poolName']=None
 o=P.execute(f['params'],f['snapshots']);eq(o['status'],'local_sql_ok_policy_conditional');eq(o['diagnostics']['pool_link_complete'],True);eq(o['diagnostics']['attribute_values_complete'],False);return eq(o['diagnostics']['full_answer_certified'],False)
test('HTTP_pool_link_and_NULL_attribute_flags_split',p_attribute)
CP={'profile':C.PROFILE,'filters':{'azoneName':'rankAZ'},'tie_policy':'all_ties','unknown_rank_policy':'reject','details_population':'all_hosts_all_active_VMs'}
def cv(id,cluster,host,status='active',az='rankAZ'):
 return {'id':id,'name':id,'logicalRegionName':'r','azoneName':az,'clusterId':cluster,'hostId':host,'status':status}
cd={'CLUSTER':[{'id':i,'name':'same-name','logicalRegionName':'r'} for i in ['A','B','X']],
'HOST':[{'id':'h1','name':'h1','logicalRegionName':'r','totalVcpuCores':4},{'id':'h2','name':'h2','logicalRegionName':'r','totalVcpuCores':8},{'id':'h3','name':'h3','logicalRegionName':'r','totalVcpuCores':16}],
'M_ClusterContainsPhyHost':[{'id':'e'+str(i),'source_Instance_Id':c,'target_Instance_Id':h} for i,(c,h) in enumerate([('A','h1'),('A','h1'),('A','h2'),('B','h3'),('X','h1')])],
'VM_NOVA':[cv('a1','A','h1'),cv('a2','A','h2'),cv('a-outside','A','h2',az='otherAZ'),cv('b1','B','h3','stopped'),cv('b2','B','h3','stopped'),cv('external','X','h1',az='otherAZ')]}
def cr(data):
 out={}
 for ci in C.RESOURCES:
  rows=data.get(ci,[]);size=2;pages=[]
  for i in range(0,len(rows),size):
   pages.append({'ok':True,'currentPage':i//size+1,'pageSize':size,'totalNum':len(rows),'totalPageNo':max(1,(len(rows)+size-1)//size),'request':C.request(ci,i//size+1,size),'objList':deepcopy(rows[i:i+size])})
  if not pages:pages=[{'ok':True,'currentPage':1,'pageSize':size,'totalNum':0,'totalPageNo':0,'request':C.request(ci,1,size),'objList':[]}]
  out[ci]={'ok':True,'columns':list(C.SCHEMA[ci]),'schema_source':'independent owned synthetic fixture','pages':pages}
 return out
def cluster(data=cd,params=CP):return C.execute_local(params,cr(data))
def rank_tie():
 o=cluster();eq(o['status'],'local_sql_ok_policy_conditional');eq({r['cluster_id'] for r in o['rows']},{'A','B'});eq({r['rank_vm_count'] for r in o['rows']},{2});return 'ranking before details; all tied identities retained'
test('CLUSTER_rank_population_and_all_ties',rank_tie)
def no_cpu_fanout():
 o=cluster();a=[r for r in o['rows'] if r['cluster_id']=='A'];eq({r['known_cluster_host_vcpu'] for r in a},{12});eq({r['complete_cluster_host_vcpu'] for r in a},{12});eq({r['running_vm_id'] for r in a},{'a1','a2','a-outside','external'})
 b=[r for r in o['rows'] if r['cluster_id']=='B'];eq(len(b),1);eq(b[0]['running_vm_id'],None);return 'duplicate business edge and active VM fanout do not multiply4+8; idle host retained'
test('CLUSTER_host_CPU_independent_and_active_list',no_cpu_fanout)
def details_population():
 p={**CP,'details_population':'winner-cluster-only_active_VMs'};o=cluster(params=p);eq({r['running_vm_id'] for r in o['rows'] if r['cluster_id']=='A'},{'a1','a2','a-outside'})
 assert all('condition' not in c for c in C.build(CP)['api_call']);return 'rankAZ does not filter host detail population or inherit region'
test('CLUSTER_explicit_detail_population_AZ_boundary',details_population)
def cluster_unknown():
 d=deepcopy(cd);d['VM_NOVA'].append(cv('u',None,'h1'));block(cluster(d))
 p={**CP,'unknown_rank_policy':'known_only_with_diagnostic'};o=cluster(d,p);eq(o['diagnostics']['scope_max_certified'],False);return eq(o['diagnostics']['winner_claim'],'known_cluster_leaders_only')
test('CLUSTER_unknown_rank_changes_certification',cluster_unknown)
def cluster_missing_host_cpu():
 d=deepcopy(cd);d['HOST'][1]['totalVcpuCores']=None;o=cluster(d);a=[r for r in o['rows'] if r['cluster_id']=='A'];eq({r['complete_cluster_host_vcpu'] for r in a},{None});eq({r['unknown_host_vcpu_count'] for r in a},{1})
 d=deepcopy(cd);d['HOST']=[h for h in d['HOST'] if h['id']!='h2'];o=cluster(d);assert any(r['reference_host_id']=='h2' and r['host_id'] is None and r['running_vm_id']=='a2' for r in o['rows']);return eq(o['diagnostics']['selected_cluster_details']['A']['running_vm_list_complete'],False)
test('CLUSTER_missing_CPU_host_not_dropped_or_complete',cluster_missing_host_cpu)
def cluster_unknown_status():
 d=deepcopy(cd);d['VM_NOVA'][0]['status']='ACTIVE';o=cluster(d);return eq(o['diagnostics']['selected_cluster_details']['A']['running_vm_list_complete'],False)
test('CLUSTER_unproven_running_token_not_known_nonactive',cluster_unknown_status)
VP={'view':'known_port_eip_host_rows','tenantName':'tenant'}
vd={'VM_NOVA':[{'id':i,'name':i,'tenantName':'tenant','logicalRegionName':'r','privateIps':'192.0.2.10,192.0.2.11','floatingIp':'198.51.100.1;198.51.100.2','hostId':host,'resId':res} for i,host,res in [('vm1','host','res1'),('vm2',None,'res2')]],
'HOST':[{'id':'host','name':'host','ipAddress':'192.0.2.1','logicalRegionName':'r'}],
'PORT':[{'id':'port1','devId':'res1','logicalRegionName':'r'},{'id':'port2','devId':'res2','logicalRegionName':'r'}],
'FLOATING_IPS':[{'id':'e'+str(i),'portId':'port1','floatingIpAddress':'203.0.113.'+str(i),'isInternal':i==1,'logicalRegionName':'r'} for i in [1,2]]}
def vr(p,data):
 plan=V.build(p);schema=V.schema_for(p['view']);out={}
 for ci,call in zip(schema,plan['api_call']):
  rows=data.get(ci,[]);size=2;pages=[{'ok':True,'pageNo':i//size+1,'pageSize':size,'totalNum':len(rows),'totalPageNo':max(1,(len(rows)+size-1)//size),'objList':deepcopy(rows[i:i+size])} for i in range(0,len(rows),size)] or [{'ok':True,'pageNo':1,'pageSize':size,'totalNum':0,'totalPageNo':0,'objList':[]}]
  out[ci]={'ok':True,'request':deepcopy(call),'schema_verified':True,'schema':list(schema[ci]),'pages':pages}
 return out
def vm(data=vd,p=VP):return V.execute_local(p,vr(p,data))
def ip_multivalue():
 o=vm();eq(len([r for r in o['rows'] if r['vm_id']=='vm1']),2);eq(len([r for r in o['rows'] if r['vm_id']=='vm2']),1);eq({r['private_ips_raw'] for r in o['rows']},{'192.0.2.10,192.0.2.11'});eq({r['native_floating_ip_raw'] for r in o['rows']},{'198.51.100.1;198.51.100.2'});eq({r['eip_internal_role_raw'] for r in o['rows'] if r['eip_id'] is not None},{'true','false'});return 'multi-valued raw strings preserved, shared IP text does not join vm2 to vm1 EIPs'
test('VM_multiIP_raw_and_multiEIP_identity_boundary',ip_multivalue)
def missing_host_authority():
 o=vm();r=next(r for r in o['rows'] if r['vm_id']=='vm2');eq(r['host_link_status'],'unknown_host_reference');eq(r['host_id'],None);eq(o['diagnostics']['full_eip_objects_binding_complete'],False);return eq(o['diagnostics']['business_complete'],False)
test('VM_unknown_host_parent_and_EIP_authority_retained',missing_host_authority)
def native_no_port():
 p={'view':'native_ip_host_rows','tenantName':'tenant'};o=vm(p=p);eq(len(o['rows']),2);eq(V.build(p)['resources'],['VM_NOVA','HOST']);assert all('logicalRegionName' not in json.dumps(c.get('condition',{})) for c in V.build(p)['api_call']);return 'native attribute/host view needs no PORT and no implicit region'
test('VM_native_view_no_PORT_or_region_default',native_no_port)
def unknown_port():
 d=deepcopy(vd);d['FLOATING_IPS'].append({'id':'dangling','portId':'missing','floatingIpAddress':None,'isInternal':None,'logicalRegionName':'r'});o=vm(d);eq(o['diagnostics']['eips_missing_or_dangling_port_count'],1);return eq(o['diagnostics']['declared_view_values_complete'],False)
test('VM_unresolved_EIP_not_no_EIP_complete',unknown_port)
def reject_vm(fn):
 try:fn()
 except V.Unsupported:return 'rejected'
 raise AssertionError('bad VM source accepted')
def vm_cross_duplicate():
 d=deepcopy(vd);d['HOST'][0]['logicalRegionName']='other';reject_vm(lambda:vm(d))
 d=deepcopy(vd);d['PORT'].append(deepcopy(d['PORT'][0]));reject_vm(lambda:vm(d))
 d=deepcopy(vd);d['VM_NOVA'][1]['resId']='res1';return reject_vm(lambda:vm(d))
test('VM_crossregion_duplicate_PORT_ambiguous_resId_rejected',vm_cross_duplicate)
def health_neighbors():
 r=vr(VP,vd);r['HOST']['pages'][0]['http_status']=503;reject_vm(lambda:V.execute_local(VP,r))
 r=cr(cd);r['HOST']['pages'][0]['http_status']=503;block(C.execute_local(CP,r))
 r=cr(cd);r['HOST']['columns']=[];block(C.execute_local(CP,r));return 'new groups HTTP failure and missing schema rejected'
test('NEW_groups_failed_or_schema_unknown_not_empty',health_neighbors)

assert source_before=={x['path']:sha(PACKAGE/x['path']) for x in closure['files']}
summary={'scope':'public adapted19-case synthetic replay; no full owner/archive/native acceptance',
 'checks':len(cases),'passed':sum(x['status']=='PASS' for x in cases),'failed':sum(x['status']=='FAIL' for x in cases),
 'HTTP_matrix_subcases_not_added':38,'eight_source_contract_hashes_verified':True,'source_files_unchanged':True,
 'network_prior18_not_retested_or_added':True,'actual_runtime_N_delta':0,'runtime_enablement_approved':False,
 'model_calls':0,'service_calls':0,'B_runtime_calls':0,'official_executor_or_scorer_calls':0,
 'not_merged':['192 dual-count increment','057 increment'],
 'remaining':['trusted real source/request/schema/pages','typed-empty and numeric projected loading','all original obligations/unknown propagation','B/C policy and actual final envelope/official depth']}
(out/'RESULTS.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert summary['checks']==19 and summary['passed']==19 and summary['failed']==0,'public next replay failed'
