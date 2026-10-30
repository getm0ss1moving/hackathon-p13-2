"""Replay51 public synthetic R2 cases; excludes4 historical private counterexamples.

Derived from the independent frozen55-case review. The64 whitespace subcases
remain nested. No owner suites, native objects, model, HTTP or B runtime calls.
"""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,importlib.util,json,traceback
from build_a_issue3_contracts import PACKAGE, verify_public, fresh_output
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
verify_public()
out=fresh_output(args.output)
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
N=load(PACKAGE/'modules/network/candidate.py','public_r2_network')
T=load(PACKAGE/'modules/tenant/tenant_details.py','public_r2_tenant')
results=[];fresh_receipt_hashes=[]
def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
def digest(value):return hashlib.sha256(compact(value)).hexdigest()
def eq(a,b):
 assert a==b,'expected '+repr(b)+'; observed '+repr(a)
 return a
def case(name,fn):
 try:results.append({'id':name,'status':'PASS','evidence':fn()})
 except Exception as e:results.append({'id':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
def n_reject(fn,contains=None):
 try:fn()
 except N.Unsupported as e:
  if contains:assert contains in str(e),str(e)
  return {'rejected_as':type(e).__name__,'reason':str(e)}
 raise AssertionError('must reject before SQL')
def t_block(value,reason=None):
 eq(value['status'],'blocked')
 if reason:eq(value['reason'],reason)
 return value
def pages_n(rows,size=2):
 out={}
 for ci in N.RESOURCES:
  batch=rows.get(ci,[]);out[ci]=[{'ok':True,'pageNo':i//size+1,'pageSize':size,'totalNum':len(batch),'objList':deepcopy(batch[i:i+size])} for i in range(0,len(batch),size)] or [{'ok':True,'pageNo':1,'pageSize':size,'totalNum':0,'objList':[]}]
 return out

def network_data(seed):
 region="fresh-r2-"+str(seed)+"_'中";vdc='fresh-vdc-'+str(seed);pre='q'+str(seed)+'_'
 params={'logicalRegionName':region,'vdcName':vdc}
 rows={ci:[] for ci in N.RESOURCES}
 rows['ROUTER']=[{'id':pre+i,'name':'same-name','nativeId':pre+'native-'+i,'logicalRegionName':region,'vdcName':vdc if i!='other' else 'other-vdc'} for i in ['main','zero','other']]
 rows['PORT']=[{'id':pre+'p'+str(i),'devNativeId':pre+'native-main','logicalRegionName':region} for i in range(3)]
 count=seed%3+1
 rows['SUBNET']=[{'id':pre+'s'+str(i),'logicalRegionName':region} for i in range(count)]
 rows['R_PORT_IN_SUBNET']=[{'id':pre+'edge'+str(i),'portId':pre+'p'+str(i%3),'subnetId':pre+'s'+str(i%count)} for i in range(count+3)]
 rows['FLOATING_IPS']=[{'id':pre+'e'+str(i),'routerId':pre+'main','logicalRegionName':region} for i in range(seed%4+1)]+[{'id':pre+'foreign-vdc-e','routerId':pre+'other','logicalRegionName':region}]
 return params,rows

def fresh_network(seed):
 params,rows=network_data(seed);receipts=pages_n(rows,seed%3+1);before=deepcopy(receipts);o=N.execute_local(params,receipts);byid={r['vpc_id']:r for r in o['rows']};pre='q'+str(seed)+'_'
 eq(set(byid),{pre+'main',pre+'zero'});eq(byid[pre+'main']['resolved_subnet_count'],seed%3+1);eq(byid[pre+'main']['known_eip_count'],seed%4+1);eq(byid[pre+'zero']['known_eip_count'],0);eq(byid[pre+'zero']['referenced_subnet_count'],0)
 eq(o['diagnostics']['business_complete'],True);eq(o['diagnostics']['result_status'],'complete_known_local_graph');assert 'no live atomic snapshot' in o['diagnostics']['business_complete_scope'];eq(receipts,before)
 fresh_receipt_hashes.append(digest(receipts));return {'input_sha256':digest(receipts),'parents':len(o['rows']),'subnets':seed%3+1,'eips':seed%4+1}
for seed in range(11,19):case('N_fresh_dynamic_dataset_'+str(seed),lambda s=seed:fresh_network(s))
for ci in ['ROUTER','PORT','SUBNET','FLOATING_IPS']:
 def wrong_region(ci=ci):
  p,d=network_data(12);d[ci][0]['logicalRegionName']='new-other-region';return n_reject(lambda:N.execute_local(p,pages_n(d)),'wrong logical region')
 case('N_wrong_region_'+ci,wrong_region)
for ci in N.RESOURCES:
 for style in ['same_page','cross_page']:
  def duplicate(ci=ci,style=style):
   p,d=network_data(12);a=deepcopy(d[ci][0]);b=deepcopy(a);b['id']=a['id']+'_unique'
   d[ci]=[a,deepcopy(a)] if style=='same_page' else [a,b,deepcopy(a)]
   return n_reject(lambda:N.execute_local(p,pages_n(d,2)),'duplicate object id')
  case('N_duplicate_'+ci+'_'+style,duplicate)
def n_metadata():
 p,d=network_data(12)
 for r in d['R_PORT_IN_SUBNET']:r['logicalRegionName']='not-an-owned-scope';r['unrelated_nested_metadata']={'any':['value']}
 receipts=pages_n(d);tables,_=N.preflight(p,receipts);assert all(set(r)==set(N.COLUMNS['R_PORT_IN_SUBNET']) for r in tables['R_PORT_IN_SUBNET']);return eq(N.execute_local(p,receipts)['diagnostics']['business_complete'],True)
case('N_global_relation_extra_metadata_projected_not_scope',n_metadata)
def n_canonical():
 p,d=network_data(12);d['FLOATING_IPS'][0]['routerId']='\t';d['R_PORT_IN_SUBNET'][0]['subnetId']='\u2003';raw=pages_n(d);before=deepcopy(raw);o=N.execute_local(p,raw);eq(raw,before);eq(o['diagnostics']['unknown_eip_parent_rows'],1);eq(o['diagnostics']['unknown_subnet_reference_rows'],1);return eq(o['diagnostics']['business_complete'],False)
case('N_blank_FK_projection_unknowns_not_false_complete',n_canonical)
def n_collision():
 p,d=network_data(12);d['ROUTER'][2]['nativeId']=d['ROUTER'][0]['nativeId'];return n_reject(lambda:N.execute_local(p,pages_n(d)),'ambiguous region/nativeId')
case('N_other_VDC_collision_still_rejected',n_collision)
def n_failed():
 p,d=network_data(12);r=pages_n(d);r['PORT'][0]['ok']=False;return n_reject(lambda:N.execute_local(p,r),'request failed')
case('N_failed_receipt_not_zero',n_failed)
def n_empty():
 p,_=network_data(12);return eq(N.execute_local(p,pages_n({}))['rows'],[])
case('N_verified_local_empty_zero_rows',n_empty)
def n_changedtotal():
 p,d=network_data(12);r=pages_n(d,1);r['ROUTER'][1]['totalNum']+=1;return n_reject(lambda:N.execute_local(p,r),'changing total')
case('N_pagination_drift_not_complete',n_changedtotal)

TP={'logicalRegionName':"fresh-tenant_'中",'metric':'vm_count','tie_policy':'all_ties','unknown_tenant_policy':'exclude_with_diagnostic'}
def vm(id,tenant,region=None):return {'id':id,'tenantId':tenant,'tenantName':None,'logicalRegionName':region or TP['logicalRegionName'],'name':id,'ipAddress':'synthetic-address','privateIps':'synthetic-address','floatingIp':None}
def vol(id,tenant,region=None):return {'id':id,'tenantId':tenant,'tenantName':None,'logicalRegionName':region or TP['logicalRegionName'],'name':id,'size':'12','status':'ready'}
def tenant_pages(rows,params=TP,size=2):
 out={}
 for ci in T.build(params)['resources']:
  d=rows.get(ci,[]);out[ci]=[{'ok':True,'currentPage':i//size+1,'pageSize':size,'totalNum':len(d),'totalPageNo':max(1,(len(d)+size-1)//size),'objList':deepcopy(d[i:i+size])} for i in range(0,len(d),size)] or [{'ok':True,'currentPage':1,'pageSize':size,'totalNum':0,'totalPageNo':0,'objList':[]}]
 return out

def t_case_data(ident,metric):
 p={**TP,'metric':metric};source='VM_NOVA' if metric=='vm_count' else 'VOLUME';f=vm if metric=='vm_count' else vol
 d={source:[f('fresh-known','tenantK'),f('fresh-u1',ident),f('fresh-u2',ident)]};return p,d,source
# Independent literal codepoints: do not derive expected blank behavior from candidate helper.
WS=[9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288]
for metric in ['vm_count','volume_count']:
 def whitespace_matrix(metric=metric):
  evidence=[]
  for cp in WS+[None,'empty','mixed']:
   ident=None if cp is None else '' if cp=='empty' else '\t\u2003\u00a0\n' if cp=='mixed' else chr(cp)
   p,d,source=t_case_data(ident,metric);raw=tenant_pages(d,p);before=deepcopy(raw);prepared=T.preflight(p,raw);o=T.execute_prepared(p,prepared)
   eq(o['status'],'local_sql_ok_policy_conditional');eq({r['tenant_id'] for r in o['rows']},{'tenantK'});eq(o['diagnostics']['unknown_resource_count'],2);eq(o['diagnostics']['ranking_population'],'known_tenant_ids_only');eq([r['tenantId'] for r in prepared['tables'][source]],[ 'tenantK',None,None]);eq(raw,before)
   evidence.append({'codepoint_or_kind':cp,'unknowns':2,'winners':['tenantK']})
  return {'table_subcases':len(evidence),'cases':evidence}
 case('T_all_versioned_whitespace_'+metric,whitespace_matrix)
 def nonblank_matrix(metric=metric):
  p={**TP,'metric':metric};source='VM_NOVA' if metric=='vm_count' else 'VOLUME';f=vm if metric=='vm_count' else vol
  ids=['A',' A','A ','\tA\t','\u200b','\ufeff',' A ']
  raw=tenant_pages({source:[f('opaque'+str(i),identity) for i,identity in enumerate(ids)]},p);o=T.execute(p,raw);eq(o['status'],'local_sql_ok_policy_conditional');eq({r['tenant_id'] for r in o['rows']},set(ids));eq(o['diagnostics']['unknown_resource_count'],0);return {'opaque_identities_preserved':ids,'winner_count':len(o['rows'])}
 case('T_nonblank_identity_exact_not_trimmed_'+metric,nonblank_matrix)
 def reject_blank(metric=metric):
  p,d,_=t_case_data('\u2003',metric);p['unknown_tenant_policy']='reject';return t_block(T.execute(p,tenant_pages(d,p)),'unknown_tenant_identity')
 case('T_reject_policy_'+metric,reject_blank)
 def fresh_tenant(metric=metric):
  evidence=[]
  for seed in [21,34,55,89]:
   p={**TP,'metric':metric,'logicalRegionName':"brand-new-region_"+str(seed)};source='VM_NOVA' if metric=='vm_count' else 'VOLUME';f=vm if metric=='vm_count' else vol
   d={source:[f('obj-'+str(i),'new-owner-'+str(seed),p['logicalRegionName']) for i in range(seed%5+2)]+[f('runner-up','other',p['logicalRegionName'])]}
   raw=tenant_pages(d,p,seed%3+1);prepared=T.preflight(p,raw);o=T.execute_prepared(p,prepared);eq(o['status'],'local_sql_ok_policy_conditional');eq({r['tenant_id'] for r in o['rows']},{'new-owner-'+str(seed)});eq(len(o['rows']),seed%5+2)
   evidence.append({'receipt_sha256':digest(raw),'projection_sha256':prepared['projection_sha256'],'params_sha256':prepared['params_sha256']})
  eq(len({e['projection_sha256'] for e in evidence}),4);return {'fresh_valid_datasets':len(evidence),'runtime_digests_are_dynamic':evidence}
 case('T_fresh_dynamic_projection_'+metric,fresh_tenant)

def prep_good():
 p=deepcopy(TP);raw=tenant_pages({'VM_NOVA':[vm('only','valid-owner')], 'VOLUME':[vol('w','valid-owner')], 'R_VOLUME_MOUNTON_VM':[{'id':'edge','vmId':'only','volumeId':'w'}]},p);return p,raw,T.preflight(p,raw)
def projected_copy():
 p,raw,prepared=prep_good();f=prepared['projection_sha256'];raw['VM_NOVA'][0]['objList'][0]['tenantId']='new-raw';eq(prepared['projection_sha256'],f);eq(T.execute_prepared(p,prepared)['rows'][0]['tenant_id'],'valid-owner');return 'preflight tables do not alias raw source'
case('T_projected_tables_independent_raw_copy',projected_copy)
def changed_projection():
 p,raw,prepared=prep_good();prepared['tables']['VM_NOVA'][0]['tenantId']='changed';return t_block(T.execute_prepared(p,prepared),'validated_projection_changed')
case('T_projection_drift_rejected',changed_projection)
def param_drift():
 p,raw,prepared=prep_good();return t_block(T.execute_prepared({**p,'logicalRegionName':'new-param'},prepared),'requires_validated_projection')
case('T_prepared_params_drift_rejected',param_drift)
def raw_receipts_not_prepared():
 p,raw,_=prep_good();return t_block(T.execute_prepared(p,raw),'requires_validated_projection')
case('T_raw_receipts_cannot_substitute_prepared_projection',raw_receipts_not_prepared)
def noncanonical_raw():
 p,raw,prepared=prep_good();prepared['tables']['VM_NOVA'][0]['tenantId']='\t';prepared['projection_sha256']=T._fingerprint(prepared['tables']);return t_block(T.execute_prepared(p,prepared),'raw_identity_not_canonical')
case('T_noncanonical_identity_refused_even_if_digest_recomputed',noncanonical_raw)
def unknown_diagnostic():
 p,raw,prepared=prep_good();prepared['unknown_resource_count']=99;return t_block(T.execute_prepared(p,prepared),'projection_diagnostics_mismatch')
case('T_unknown_count_diagnostic_mismatch_rejected',unknown_diagnostic)
def missing_contract():
 p,raw,prepared=prep_good();prepared.pop('projection_contract');return t_block(T.execute_prepared(p,prepared),'requires_validated_projection')
case('T_missing_projection_contract_rejected',missing_contract)
def failure_t():
 p,raw,_=prep_good();raw['VM_NOVA'][0]['ok']=False;return t_block(T.execute(p,raw),'invalid_or_incomplete_input')
case('T_failed_page_cannot_be_zero',failure_t)
def partial_mount():
 p,raw,_=prep_good();raw['VOLUME'][0].update({'totalNum':0,'totalPageNo':0,'objList':[]});o=T.execute(p,raw);eq(o['status'],'local_sql_ok_policy_conditional');eq(o['diagnostics']['unresolved_mount_count'],1);eq(o['diagnostics']['complete_mount_details'],False);eq(o['diagnostics']['business_policy_accepted'],False);return eq(o['rows'][0]['mount_status'],'unresolved_volume')
case('T_missing_mount_stays_partial',partial_mount)
def t_empty():return eq(T.execute(TP,tenant_pages({},TP))['rows'],[])
case('T_true_local_empty_zero_details',t_empty)

def length_network():
 try:N.build({'logicalRegionName':'r'*200,'vdcName':'v'*200})
 except N.LengthBlocked as e:
  eq(e.details['measured_bytes'],4571);eq(e.details['api_call_plus_sql_bytes'],3878);eq(e.details['official_boundary_confirmed'],False);return e.details
 raise AssertionError('provisional full-build limit must explain measured boundary')
case('L_network_conservative_length_not_semantic_invalidity',length_network)
for metric in ['vm_count','volume_count']:
 def length_tenant(metric=metric):
  p={**TP,'metric':metric,'logicalRegionName':'中'*1500};o=T.build(p);eq(o['status'],'blocked_transport_budget');eq(o['blocked_reason']['measured_bytes'],len(compact({k:o[k] for k in ['api_call','sql']})));eq(o['blocked_reason']['boundary'],'expanded_api_call+sql');return t_block(T.execute(p,{}),'transport_budget')
 case('L_tenant_long_UTF8_'+metric,length_tenant)

def within_normal_network():
 p={'logicalRegionName':'r'*40,'vdcName':'v'*40};o=N.build(p);return {'core':len(compact({k:o[k] for k in ['api_call','sql']})),'full':len(compact(o))}
case('L_valid_40_ASCII_network',within_normal_network)
def valid_tenant_envelope():
 p={**TP,'logicalRegionName':'r'*40};o=T.build(p);eq(o['status'],'isolated_candidate_policy_conditional');core={k:o[k] for k in ['api_call','sql']};inside=T.check_envelope_budget(core);eq(inside['status'],'within_local_byte_budget');shell={'actual_payload':core,'other_runtime_metadata':'x'*4096};outside=T.check_envelope_budget(shell,boundary='synthetic_B_shell');eq(outside['status'],'blocked');return {'core':inside,'synthetic_outer_shell':outside,'no_actual_B_envelope_tested':True}
case('L_final_envelope_measured_separately',valid_tenant_envelope)


passed=sum(x['status']=='PASS' for x in results)
summary={'scope':'51 public synthetic cases derived from original55; four historical private fixtures excluded',
 'checks':len(results),'passed':passed,'failed':len(results)-passed,
 'nested_whitespace_subcases_not_added':64,'excluded_historical_fixture_checks':4,
 'model_calls':0,'service_calls':0,'B_runtime_calls':0,'production_enabled':False}
(out/'RESULTS.json').write_text(json.dumps({'summary':summary,'cases':results},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert len(results)==51 and passed==51, 'public synthetic replay failed; inspect external RESULTS.json'
