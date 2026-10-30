"""Public17 management-VM synthetic checks; owner92/bootable/native audit excluded.

Source integrity covers the published source/contract/doc. Address fixtures use
documentation ranges and preserve raw multivalue semantics. No production wiring.
"""
from pathlib import Path
from copy import deepcopy
import argparse,ast,hashlib,importlib.util,json,sys,traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'experiments/issue3_management_vm_20261030'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((SRC/'MANIFEST.json').read_text())
for rel,expected in manifest['files'].items():assert sha(SRC/rel)==expected,rel
for rel,expected in (manifest['tools']|manifest['external_files']).items():assert sha(ROOT/rel)==expected,rel
closure=json.loads((SRC/'SOURCE_CLOSURE.json').read_text())
assert closure['source_contract_file_count']==len(closure['files'])==2
for entry in closure['files']:assert sha(SRC/entry['path'])==entry['sha256']
source_before={entry['path']:sha(SRC/entry['path']) for entry in closure['files']}
ast.parse((SRC/'candidate.py').read_text());json.loads((SRC/'CONTRACT.json').read_text())
out=args.output.resolve()
assert out!=ROOT and ROOT not in out.parents,'output must be outside repository'
out.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('public_management_vm',SRC/'candidate.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
P={'view':M.VIEW,'logicalRegionName':"new-region_'x",'ip_role':'both_raw','capacity_mode':'per_volume_raw_and_numeric_summary'}
def vm(id,vdc,flavor='f'):
 return {'id':id,'name':id,'logicalRegionName':P['logicalRegionName'],'management':True,'vdcId':vdc,'vdcName':'VDC-'+vdc,'privateIps':'192.0.2.10,192.0.2.11','ipAddress':'203.0.113.1;203.0.113.2','flavorId':flavor}
data={'VM_NOVA':[vm('vmA','A'),vm('vmB','B')],
'FLAVOR':[{'id':'f','name':'flavor','logicalRegionName':P['logicalRegionName'],'vcpuSize':'4','ramSize':'8','diskSize':'20'}],
'VOLUME':[{'id':'w1','name':'same-volume-name','logicalRegionName':P['logicalRegionName'],'size':'10'},{'id':'w2','name':'same-volume-name','logicalRegionName':P['logicalRegionName'],'size':'10'}],
'R_VOLUME_MOUNTON_VM':[{'id':'m'+str(i),'vmId':v,'volumeId':w} for i,(v,w) in enumerate([('vmA','w1'),('vmA','w2'),('vmA','w1'),('vmB','w1')])],
'S_DeployNode':[{'id':'nA','vmId':'vmA','hostClass':'VM'},{'id':'nB','vmId':'vmB','hostClass':'VM'}],
'S_DeployInstance':[{'id':'i'+str(i),'deployNodeId':node,'deployComponentId':comp} for i,(node,comp) in enumerate([('nA','c1'),('nA','c2'),('nA','c3'),('nA','c1'),('nB','c1')])],
'S_DeployComponent':[{'id':'c'+str(i),'serviceId':'s'+str(i)} for i in [1,2,3]],
'S_Service':[{'id':'s'+str(i),'cloudServiceId':'cloud'+str(i)} for i in [1,2,3]],
'S_CloudService':[{'id':'cloud'+str(i),'name':'same-service-name' if i<3 else 'other-service'} for i in [1,2,3]]}
def pages(rows):
 return [{'ok':True,'pageNo':i//1000+1,'pageSize':1000,'totalNum':len(rows),'totalPageNo':max(1,(len(rows)+999)//1000),'objList':deepcopy(rows[i:i+1000])} for i in range(0,len(rows),1000)] or [{'ok':True,'pageNo':1,'pageSize':1000,'totalNum':0,'totalPageNo':0,'objList':[]}]
def receipts(d=data,p=P):
 plan=M.build(p);return {ci:{'ok':True,'request':deepcopy(call),'schema_verified':True,'schema':list(M.SCHEMA[ci]),'pages':pages(d.get(ci,[]))} for ci,call in zip(M.SCHEMA,plan['api_call'])}
def run(d=data,p=P):return M.execute_local(p,receipts(d,p))
def eq(a,b):assert a==b,'expected '+repr(b)+'; got '+repr(a);return a
def rejected(fn):
 try:fn()
 except M.Unsupported as e:return str(e)
 raise AssertionError('unsupported/incomplete source accepted')
cases=[];counterexamples={}
def case(name,fn):
 try:cases.append({'id':name,'status':'PASS','detail':fn()})
 except Exception as e:cases.append({'id':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
def fanout():
 o=run();eq(len(o['rows']),2);a=next(r for r in o['rows'] if r['vm_id']=='vmA');b=next(r for r in o['rows'] if r['vm_id']=='vmB')
 eq(len(json.loads(a['services_json'])),3);eq(len(json.loads(a['mounted_volumes_json'])),2);eq(a['known_size_sum_native_numbers'],'20');eq(a['complete_size_sum_native_numbers'],'20');eq(b['known_size_sum_native_numbers'],'10');eq(a['declared_values_complete'],1);return eq(o['diagnostics']['full_answer_certified'],False)
case('M01_services_times_volumes_do_not_multiply_same_size_sum',fanout)
def bool_binding():
 plan=M.build(P);calls=plan['api_call'];eq(len(calls),9);eq(calls[0]['condition']['constraint'][1]['simple']['value'],True);assert type(calls[0]['condition']['constraint'][1]['simple']['value']) is bool
 assert all('condition' not in c for c in calls[1:])
 for value in [False,'true',1,None]:
  d=deepcopy(data);d['VM_NOVA'][0]['management']=value;rejected(lambda:run(d))
 r=receipts({});r['VM_NOVA']['request']['condition']['constraint'][1]['simple']['value']='true';rejected(lambda:M.execute_local(P,r))
 return {'boolean_values_tested':4,'string_management_request_rejected':True,'service_CIs_not_given_fake_region':True}
case('M02_native_bool_and_typed_API_binding',bool_binding)
def missing_vdc_flavor():
 d=deepcopy(data)
 for k in ['vdcId','vdcName','flavorId']:d['VM_NOVA'][1].pop(k)
 o=run(d);eq(len(o['rows']),2);b=next(r for r in o['rows'] if r['vm_id']=='vmB');eq(b['vdc_status'],'unknown_source_VDC');eq(b['flavor_status'],'unknown_reference');eq(b['declared_values_complete'],0);return b
case('M03_missing_VDC_flavor_retains_parent',missing_vdc_flavor)
def unresolved_flavor():
 d=deepcopy(data);d['VM_NOVA'][0]['flavorId']='missing-f';a=next(r for r in run(d)['rows'] if r['vm_id']=='vmA');eq(a['flavor_reference_id'],'missing-f');eq(a['flavor_id'],None);return eq(a['declared_values_complete'],0)
case('M04_unresolved_flavor_not_inner_dropped',unresolved_flavor)
def broken_service():
 d=deepcopy(data);d['S_DeployComponent'][1]['serviceId']='missing-service';a=next(r for r in run(d)['rows'] if r['vm_id']=='vmA');eq(len(json.loads(a['services_json'])),2);eq(a['unknown_service_link_count'],1);eq(a['service_status'],'known_services_incomplete');return eq(a['declared_values_complete'],0)
case('M05_broken_deployment_chain_keeps_known_services_and_unknown',broken_service)
def no_service():
 d=deepcopy(data);d['S_DeployInstance']=[];o=run(d);eq(len(o['rows']),2);eq({r['service_status'] for r in o['rows']},{'no_known_service'});return eq({r['declared_values_complete'] for r in o['rows']},{0})
case('M06_no_service_is_not_certified_none',no_service)
def missing_volume():
 d=deepcopy(data);d['VOLUME']=d['VOLUME'][:1];a=next(r for r in run(d)['rows'] if r['vm_id']=='vmA')
 eq(a['known_size_sum_native_numbers'],'10');eq(a['complete_size_sum_native_numbers'],None);eq(a['unknown_size_reference_count'],1)
 row=next(v for v in json.loads(a['mounted_volumes_json']) if v['volume_reference_id']=='w2');eq(row['volume_id'],None);eq(row['status'],'unresolved_reference');return eq(a['declared_values_complete'],0)
case('M07_missing_volume_target_reference_preserved_NULL_total',missing_volume)
def unknown_owner():
 d=deepcopy(data);d['R_VOLUME_MOUNTON_VM'].append({'id':'unknown-owner','vmId':None,'volumeId':'w1'});o=run(d);eq({r['complete_size_sum_native_numbers'] for r in o['rows']},{None});return eq(o['diagnostics']['unknown_global_mount_owners'],1)
case('M08_unknown_mount_owner_prevents_full_capacity',unknown_owner)
def exact_decimal_and_dirty():
 d=deepcopy(data);d['VOLUME'][0]['size']='0.1';d['VOLUME'][1]['size']='0.2';a=next(r for r in run(d)['rows'] if r['vm_id']=='vmA');eq(a['complete_size_sum_native_numbers'],'0.3')
 d['VOLUME'][1]['size']='2GB';a=next(r for r in run(d)['rows'] if r['vm_id']=='vmA');eq(a['known_size_sum_native_numbers'],'0.1');eq(a['complete_size_sum_native_numbers'],None);return eq(a['unknown_size_reference_count'],1)
case('M09_exact_source_numbers_dirty_not_zero_or_rounded',exact_decimal_and_dirty)
def raw_IP_roles():
 o=run();eq({r['private_ips_raw'] for r in o['rows']},{'192.0.2.10,192.0.2.11'});eq({r['vm_ip_address_raw'] for r in o['rows']},{'203.0.113.1;203.0.113.2'})
 d=deepcopy(data);d['VM_NOVA'][0]['privateIps']=None;a=next(r for r in run(d)['rows'] if r['vm_id']=='vmA');eq(a['private_ips_raw'],None);eq(a['vm_ip_address_raw'],'203.0.113.1;203.0.113.2');return eq(a['declared_values_complete'],0)
case('M10_raw_multiIP_no_first_token_or_role_fallback',raw_IP_roles)
def scope_guards():
 d=deepcopy(data);d['VM_NOVA'][0]['logicalRegionName']='wrong';rejected(lambda:run(d))
 d=deepcopy(data);d['FLAVOR'][0]['logicalRegionName']='wrong';rejected(lambda:run(d))
 d=deepcopy(data);d['VOLUME'][0]['logicalRegionName']=None;return rejected(lambda:run(d))
case('M11_resolved_scope_mismatch_or_unknown_not_joined',scope_guards)
def ground_full():
 q='查询区域“'+P['logicalRegionName']+'”下各VDC的管理虚拟机名称、IP、所属云服务、规格和挂载云硬盘容量。';item={'id':M.FAMILY_ID,'family_id':M.FAMILY_ID};eq(M.prepare_candidate(q,item,P)['family_id'],M.FAMILY_ID)
 bad=[q.replace('和挂载云硬盘容量',''),q.replace('管理虚拟机','普通虚拟机'),q+'并按租户统计数量。',q.replace(P['logicalRegionName'],'different')]
 for question in bad:eq(M.prepare_candidate(question,item,P),None)
 eq(M.prepare_candidate(q,item,{**P,'ip_role':'private_ips_raw'}),None)
 p={**P,'ip_role':'private_ips_raw'};q2=q.replace('、IP、','、私网IP、');assert M.prepare_candidate(q2,item,p) is not None
 return {'full_scope_and_five_fields_proven':True,'partial_extra_wrong_scope_or_IP_role_rejected':len(bad)+1}
case('M12_full_question_obligations_not_silently_dropped',ground_full)
def state_and_schema():
 count=0
 for ci in ['VM_NOVA','S_CloudService','R_VOLUME_MOUNTON_VM']:
  for at in ['resource','page']:
   for alias in ['http_status','statusCode','httpStatusCode']:
    r=receipts();target=r[ci] if at=='resource' else r[ci]['pages'][0];target[alias]=503;rejected(lambda:M.execute_local(P,r));count+=1
 r=receipts({});r['FLAVOR']['schema_verified']=False;rejected(lambda:M.execute_local(P,r))
 r=receipts();r['S_Service']['pages'][0].pop('objList');rejected(lambda:M.execute_local(P,r))
 return {'matrix_subcases_not_added':count+2}
case('M13_HTTP_failure_missing_schema_and_payload_not_empty',state_and_schema)
def identity_and_unknown_nodes():
 d=deepcopy(data);d['S_DeployInstance'].append(deepcopy(d['S_DeployInstance'][0]));rejected(lambda:run(d))
 d=deepcopy(data);d['S_DeployNode'].append({'id':'node-unknown','vmId':None,'hostClass':'VM'});o=run(d);eq(o['diagnostics']['unknown_global_service_owner_nodes'],1);return eq({r['declared_values_complete'] for r in o['rows']},{0})
case('M14_duplicate_object_and_unknown_service_owner_not_full',identity_and_unknown_nodes)
def true_empty_no_mount():
 eq(run({})['rows'],[])
 d=deepcopy(data);d['R_VOLUME_MOUNTON_VM']=[];o=run(d);eq({r['complete_size_sum_native_numbers'] for r in o['rows']},{'0'});return eq({r['mount_status'] for r in o['rows']},{'no_recorded_mounts_in_snapshot'})
case('M15_verified_no_recorded_mount_zero_distinct_from_unknown',true_empty_no_mount)
def new_entities():
 d=deepcopy(data);p=deepcopy(P);p['logicalRegionName']='brand-new-region'
 fk={'id','flavorId','vmId','volumeId','deployNodeId','deployComponentId','serviceId','cloudServiceId'}
 for ci,rows in d.items():
  for row in rows:
   for k in list(row):
    if k in fk:row[k]='fresh-'+row[k]
    if k=='logicalRegionName':row[k]=p['logicalRegionName']
 o=run(d,p);eq({r['vm_id'] for r in o['rows']},{'fresh-vmA','fresh-vmB'});return eq(next(r for r in o['rows'] if r['vm_id']=='fresh-vmA')['complete_size_sum_native_numbers'],'20')
case('M16_new_legal_region_entities_not_historical_hash_locked',new_entities)
def length_boundaries():
 p={**P,'logicalRegionName':'Example-R'};o=M.build(p);core={'api_call':o['api_call'],'sql':o['sql']};eq(len(M.compact(core).encode()),1757)
 p={**P,'logicalRegionName':'x'*6000};o=M.build(p);eq(o['transport']['status'],'blocked_core_length');assert p['logicalRegionName'] in o['sql'];return {'normal_expanded_core_bytes':1757,'long_field_not_truncated':True,'official_final_envelope_unverified':True}
case('M17_core_encoding_measurement_and_no_truncation',length_boundaries)

assert source_before=={entry['path']:sha(SRC/entry['path']) for entry in closure['files']}
summary={'scope':'public17 pure synthetic scenarios; delivery-only integrity audit, not full owner/native acceptance',
 'checks':len(cases),'passed':sum(c['status']=='PASS' for c in cases),'failed':sum(c['status']=='FAIL' for c in cases),
 'HTTP_matrix_subcases_not_added':sum(c.get('detail',{}).get('matrix_subcases_not_added',0) for c in cases if isinstance(c.get('detail'),dict)),
 'source_contract_files_verified':2,'source_files_unchanged':True,'owner92_suite_run':False,
 'bootable_imported_or_retested':False,'native_records_read':False,'native_statistics_rederived':False,
 'model_calls':0,'service_calls':0,'B_runtime_calls':0,'official_executor_or_scorer_calls':0,
 'full_answer_certified':False,'production_enabled':False,'actual_runtime_N_delta':0,
 'remaining':['B registry/card/unified_prepare and trusted capture/typed prepared loader','field coverage gaps','IP role/multivalue codec, capacity units and deployment-service meaning','actual final B envelope/official depth']}
(out/'RESULTS.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2,default=lambda x:sorted(x,key=repr) if isinstance(x,set) else repr(x))+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert summary['checks']==summary['passed']==17 and summary['failed']==0 and summary['HTTP_matrix_subcases_not_added']==20,'public management-VM replay failed'
