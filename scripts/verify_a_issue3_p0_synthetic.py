"""Public19-case synthetic replay for the disabled P0 R2 source-contract closure.

The two historical zero-page fixtures are replaced with fresh synthetic literals.
Original-prepare equality uses pinned synthetic plan hashes, not old runtime modules.
94 boundary subcases remain nested. vdc_counts is hash-checked but not executed.
"""
from pathlib import Path
from copy import deepcopy
import argparse,ast,hashlib,importlib.util,json,sys,traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'experiments/issue3_p0_compositions_20261030'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
for relative,expected in manifest['files'].items():assert sha(PACKAGE/relative)==expected,relative
for relative,expected in manifest['tools'].items():assert sha(ROOT/relative)==expected,relative
minimum=json.loads((PACKAGE/'MINIMAL_B_HANDOFF.json').read_text())
assert minimum['source_contract_file_count']==len(minimum['files'])==6
source_before={entry['path']:sha(PACKAGE/entry['path']) for entry in minimum['files']}
for entry in minimum['files']:assert source_before[entry['path']]==entry['sha256']
# Hash/parse the unchanged count profile only; do not import or retest it.
for entry in minimum['files']:
 if entry['path'].endswith('.py'):ast.parse((PACKAGE/entry['path']).read_text())
 elif entry['path'].endswith('.json'):json.loads((PACKAGE/entry['path']).read_text())
out=args.output.resolve()
assert out!=ROOT and ROOT not in out.parents,'output must be outside repository'
out.mkdir(parents=True,exist_ok=False)
def load(group):
 spec=importlib.util.spec_from_file_location('public_p0_'+group,PACKAGE/'modules'/group/'candidate.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
T=load('tenant_lists');N=load('vdc_network')
prepare_references=json.loads((PACKAGE/'evidence/SYNTHETIC_PREPARE_REFERENCES.json').read_text())
results=[]
def eq(a,b):
 assert a==b,'expected '+repr(b)+'; got '+repr(a)
 return a
def case(name,fn):
 try:results.append({'id':name,'status':'PASS','detail':fn()})
 except Exception as e:results.append({'id':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
def reject(module,params,receipts):
 try:module.execute_local(params,receipts)
 except module.Unsupported as e:return str(e)
 raise AssertionError('invalid neighboring input accepted')
TEN="fresh-zero-tenant_'x";V='fresh-zero-vdc';R='fresh-zero-region'
TP={'profile':'tenant_parallel_lists','resource_set':['VM_NOVA','SECURITY_GROUP','VOLUME'],'filters':{'tenantName':TEN},'required_filters':['tenantName'],'output_columns':['resource_type','resource_id','resource_name']}
NP={'profile':'vdc_network_inventory','filters':{'vdcName':V,'logicalRegionName':R},'required_filters':['vdcName','logicalRegionName']}
def pages(rows,page_count='auto',size=2):
 p=[{'ok':True,'pageNo':i//size+1,'pageSize':size,'totalNum':len(rows),'totalPageNo':max(1,(len(rows)+size-1)//size),'objList':deepcopy(rows[i:i+size])} for i in range(0,len(rows),size)] or [{'ok':True,'pageNo':1,'pageSize':size,'totalNum':0,'totalPageNo':0,'objList':[]}]
 if page_count!='auto':
  for r in p:
   if page_count=='omit':r.pop('totalPageNo')
   else:r['totalPageNo']=page_count
 return p
tdata={ci:[{'id':ci+'-new','name':'name-'+ci,'tenantName':TEN}] for ci in T.RESOURCES}
ndata={'ROUTER':[{'id':'new-v','name':'VPC','vdcName':V,'logicalRegionName':R}],'SUBNET':[{'id':'new-s','cidr':'192.0.2.0/24','vdcName':V,'logicalRegionName':R}],'FLOATING_IPS':[{'id':'new-e'+str(i),'vdcName':V,'logicalRegionName':R} for i in range(2)]}
def receipts(m,data,page_count='auto'):return {ci:pages(data.get(ci,[]),page_count) for ci in m.RESOURCES}
for group,m,params in [('tenant_lists',T,TP),('vdc_network',N,NP)]:
 def synthetic_zero(m=m,p=params,group=group):
  raw=receipts(m,{},0);before=deepcopy(raw);o=m.execute_local(p,raw)
  if group=='tenant_lists':eq(o['rows'],[])
  else:eq(o['rows'],[{'resource_type':'EIP_COUNT','resource_id':None,'resource_name':None,'cidr':None,'resource_count':0}])
  eq(raw,before)
  return {'synthetic_fresh_params':True,'correct_empty_shape':True,'input_unmodified':True}
 case(group+'_fresh_zero_pagecount_closed',synthetic_zero)
for label,m,params,data in [('T',T,TP,tdata),('N',N,NP,ndata)]:
 def zero_forms(m=m,p=params):
  outputs=[]
  for form in [0,1,'omit']:
   o=m.execute_local(p,receipts(m,{},form));outputs.append(o['rows'])
  eq(outputs[0],outputs[1]);eq(outputs[0],outputs[2]);return {'subcases':3,'equivalent_zero_outputs':outputs[0]}
 case(label+'_zero_0_1_omitted_same_result',zero_forms)
 def one_branch_empty(m=m,p=params,data=data,label=label):
  for ci in m.RESOURCES:
   d=deepcopy(data);d[ci]=[];o=m.execute_local(p,receipts(m,d,0 if False else 'auto'))
   if label=='T':eq(len(o['rows']),2)
   else:
    eq([r['resource_count'] for r in o['rows'] if r['resource_type']=='EIP_COUNT'],[0 if ci=='FLOATING_IPS' else 2])
    eq(len([r for r in o['rows'] if r['resource_type']=='VPC']),0 if ci=='ROUTER' else 1)
    eq(len([r for r in o['rows'] if r['resource_type']=='SUBNET']),0 if ci=='SUBNET' else 1)
  return {'subcases':3,'other_independent_branches_retained':True}
 case(label+'_one_branch_native_zero_keeps_others',one_branch_empty)
 def empty_bad_counts(m=m,p=params):
  evidence=[]
  for bad in [False,True,-1,2,0.0,'0',None]:
   r=receipts(m,{},0);r[m.RESOURCES[0]][0]['totalPageNo']=bad;evidence.append(reject(m,p,r))
  return {'subcases':len(evidence),'all_rejected':True}
 case(label+'_zero_total_invalid_pagecounts_rejected',empty_bad_counts)
 def zero_neighbor_failure(m=m,p=params):
  kinds=['missing_ok','numeric_ok','success_false','error','missing_objList','null_objList','total_nonzero','negative_total','boolean_total','wrong_first_page','nonpositive_size','extra_empty_page']
  for kind in kinds:
   r=receipts(m,{},0);ci=m.RESOURCES[0];page=r[ci][0]
   if kind=='missing_ok':page.pop('ok')
   elif kind=='numeric_ok':page['ok']=1
   elif kind=='success_false':page['success']=False
   elif kind=='error':page['error']='HTTP503'
   elif kind=='missing_objList':page.pop('objList')
   elif kind=='null_objList':page['objList']=None
   elif kind=='total_nonzero':page['totalNum']=1
   elif kind=='negative_total':page['totalNum']=-1
   elif kind=='boolean_total':page['totalNum']=False
   elif kind=='wrong_first_page':page['pageNo']=2
   elif kind=='nonpositive_size':page['pageSize']=0
   elif kind=='extra_empty_page':
    r[ci].append(deepcopy(page));r[ci][1]['pageNo']=2
   reject(m,p,r)
  r=receipts(m,{},0);r.pop(m.RESOURCES[-1]);reject(m,p,r)
  return {'subcases':len(kinds)+1,'all_rejected':True}
 case(label+'_failure_incomplete_or_missing_source_not_empty',zero_neighbor_failure)
 def nonempty_boundary(m=m,p=params,data=data):
  # One CI becomes a legitimate three-row/two-page source; other CIs unchanged.
  d=deepcopy(data);ci=m.RESOURCES[0];row=d[ci][0];d[ci]=[{**row,'id':'fresh-three-'+str(i)} for i in range(3)]
  r=receipts(m,d);o=m.execute_local(p,r)
  for bad in [0,1,3,True]:
   mutated=deepcopy(r)
   for page in mutated[ci]:page['totalPageNo']=bad
   reject(m,p,mutated)
  truncated=deepcopy(r);truncated[ci].pop();reject(m,p,truncated)
  changed=deepcopy(r);changed[ci][1]['totalNum']=4;reject(m,p,changed)
  repeated=deepcopy(r);repeated[ci][1]['objList'][0]=deepcopy(repeated[ci][0]['objList'][0]);reject(m,p,repeated)
  return {'subcases':8,'valid_nonempty_rows':len(o['rows']),'wrong_ceil_and_partial_rejected':True}
 case(label+'_nonempty_exact_ceil_and_pagination_remain_strict',nonempty_boundary)
 def schema_neighbors(m=m,p=params,data=data,label=label):
  count=0
  for ci in m.RESOURCES:
   for key in (['id','name','tenantName'] if label=='T' else {'ROUTER':['id','name','vdcName','logicalRegionName'],'SUBNET':['id','cidr','vdcName','logicalRegionName'],'FLOATING_IPS':['id','vdcName','logicalRegionName']}[ci]):
    d=deepcopy(data);d[ci][0].pop(key);reject(m,p,receipts(m,d));count+=1
   d=deepcopy(data);d[ci]=[{'_empty':''}];reject(m,p,receipts(m,d));count+=1
  return {'subcases':count,'nonempty_missing_schema_and_placeholder_rejected':True,'empty_schema_source_authentication':'not represented by local receipt; B host must supply independently'}
 case(label+'_nonempty_missing_schema_and_sentinel_rejected',schema_neighbors)
 def zero_with_nonempty_rows(m=m,p=params,data=data):
  r=receipts(m,{},0);r[m.RESOURCES[0]][0]['objList']=[deepcopy(data[m.RESOURCES[0]][0])]
  return reject(m,p,r)
 case(label+'_zero_total_nonempty_objList_rejected',zero_with_nonempty_rows)
 def prepare_unchanged(m=m,p=params,label=label):
  group='tenant_lists' if label=='T' else 'vdc_network'
  reference=prepare_references[group]
  eq(p,reference['params'])
  digest=hashlib.sha256(json.dumps(m.prepare(p),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  eq(digest,reference['canonical_plan_sha256'])
  return 'complete plan matches unchanged original materializer fingerprint on fresh synthetic params'
 case(label+'_new_legal_entities_prepare_matches_old',prepare_unchanged)
def tenant_no_region():
 plan=T.prepare(TP);assert 'logicalRegionName' not in plan['sql']
 for c in plan['api_call']:eq([x['simple']['name'] for x in c['condition']['constraint']],['tenantName'])
 eq(len(T.execute_local(TP,receipts(T,tdata))['rows']),3);return 'no inherited/default region'
case('T_tenant_only_stays_region_free',tenant_no_region)

assert source_before=={entry['path']:sha(PACKAGE/entry['path']) for entry in minimum['files']}
summary={'scope':'Public adapted19-case R2 synthetic replay, not an owner archive/full business acceptance',
 'checks':len(results),'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results),
 'boundary_subcases_not_added':sum(x.get('detail',{}).get('subcases',0) for x in results if isinstance(x.get('detail'),dict)),
 'source_contract_files_verified':6,'sources_unchanged':True,'vdc_counts_imported_or_retested':False,
 'original_35_count_passes_not_added':True,'runtime_N_delta':0,'production_enabled':False,
 'model_requests':0,'service_requests':0,'B_runtime_calls':0,'official_executor_or_scorer_calls':0,
 'real_empty_schema_provenance_certified':False,'actual_final_envelope_or_official_depth_certified':False}
(out/'RESULTS.json').write_text(json.dumps({'summary':summary,'cases':results},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert summary['checks']==19 and summary['passed']==19 and summary['failed']==0,'public P0 replay failed'
assert summary['boundary_subcases_not_added']==94
