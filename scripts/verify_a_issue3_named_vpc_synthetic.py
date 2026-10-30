"""Public15-case named-VPC synthetic replay; no owner suites or native inputs.

Source audit covers the published source/contract/doc, not the full owner archive.
No model, HTTP, B, official executor or scorer calls. Output is outside Git.
"""
from pathlib import Path
from copy import deepcopy
import argparse,ast,hashlib,importlib.util,json,sys,traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'experiments/issue3_named_vpc_20261030'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
for relative,expected in manifest['files'].items():assert sha(PACKAGE/relative)==expected,relative
for relative,expected in (manifest['tools']|manifest['external_files']).items():assert sha(ROOT/relative)==expected,relative
closure=json.loads((PACKAGE/'SOURCE_CLOSURE.json').read_text())
assert closure['source_contract_file_count']==len(closure['files'])==2
for entry in closure['files']:assert sha(PACKAGE/entry['path'])==entry['sha256']
source_before={entry['path']:sha(PACKAGE/entry['path']) for entry in closure['files']}
ast.parse((PACKAGE/'candidate.py').read_text());json.loads((PACKAGE/'CONTRACT.json').read_text())
out=args.output.resolve()
assert out!=ROOT and ROOT not in out.parents,'output must be outside repository'
out.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('public_named_vpc',PACKAGE/'candidate.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
P={'profile':'named_vpc_subnet_eip_counts','filters':{'name':"exact_'VPC中"},'required_filters':['name'],'same_name_policy':'all_matching_parent_ids'}
d={'ROUTER':[{'id':i,'name':P['filters']['name'],'nativeId':native,'logicalRegionName':region} for i,native,region in [('A','native-shared','r1'),('B','native-shared','r2'),('zero','native-zero','r1')]],
'PORT':[{'id':i,'devNativeId':'native-shared','logicalRegionName':region} for i,region in [('p1','r1'),('p2','r1'),('pB','r2')]],
'R_PORT_IN_SUBNET':[{'id':'edge'+str(i),'portId':p,'subnetId':s} for i,(p,s) in enumerate([('p1','s1'),('p2','s1'),('p2','s2'),('pB','sB')])],
'SUBNET':[{'id':s,'logicalRegionName':region} for s,region in [('s1','r1'),('s2','r1'),('sB','r2')]],
'FLOATING_IPS':[{'id':'e'+str(i),'routerId':'A','logicalRegionName':'r1'} for i in range(3)]+[{'id':'eB','routerId':'B','logicalRegionName':'r2'}]}
def pages(rows,size=2):
 return [{'ok':True,'pageNo':i//size+1,'pageSize':size,'totalNum':len(rows),'totalPageNo':max(1,(len(rows)+size-1)//size),'objList':deepcopy(rows[i:i+size])} for i in range(0,len(rows),size)] or [{'ok':True,'pageNo':1,'pageSize':size,'totalNum':0,'totalPageNo':0,'objList':[]}]
def receipts(data=d,p=P):
 plan=N.build(p);return {ci:{'ok':True,'request':deepcopy(plan['api_call'][i]),'schema_verified':True,'schema':list(N.SCHEMA[ci]),'pages':pages(data.get(ci,[]))} for i,ci in enumerate(N.RESOURCES)}
def run(data=d,p=P):return N.execute_local(p,receipts(data,p))
def eq(a,b):assert a==b,'expected '+repr(b)+'; observed '+repr(a);return a
def reject(fn):
 try:fn()
 except N.Unsupported as e:return str(e)
 raise AssertionError('invalid or unsupported input accepted')
cases=[]
def case(name,fn):
 try:cases.append({'id':name,'status':'PASS','detail':fn()})
 except Exception as e:cases.append({'id':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
def independent_counts():
 o=run();a=next(r for r in o['rows'] if r['vpc_id']=='A');eq([a[k] for k in ['resolved_subnet_count','referenced_subnet_count','unresolved_subnet_count','known_eip_count']],[2,2,0,3]);eq(len(o['rows']),3);return eq(o['diagnostics']['known_local_graph_complete'],True)
case('N01_subnets_and_EIPs_independent_no_fanout',independent_counts)
def no_region_all_names():
 plan=N.build(P);assert all('condition' not in c for c in plan['api_call']);eq({r['vpc_id'] for r in run()['rows']},{'A','B','zero'});return 'cross-region same nativeId allowed, all exact-name identities retained, no region default'
case('N02_name_only_no_region_all_identities',no_region_all_names)
def ambiguity():
 reject(lambda:run(p={**P,'same_name_policy':'reject_multiple_parent_ids'}))
 p=deepcopy(P);p['filters']['logicalRegionName']='r2';p['required_filters']=['logicalRegionName','name'];p['same_name_policy']='reject_multiple_parent_ids'
 # A full global relation table remains global. Outside-region links cannot be silently certified away.
 data={ci:([r for r in rows if r.get('logicalRegionName')=='r2'] if ci!='R_PORT_IN_SUBNET' else rows) for ci,rows in d.items()}
 o=run(data,p);eq([r['vpc_id'] for r in o['rows']],['B']);eq(o['rows'][0]['known_eip_count'],1);eq(o['diagnostics']['known_local_graph_complete'],False)
 return 'region disambiguates parent; unrelated unresolved global relation evidence remains conservative partial'
case('N03_reject_multiple_and_explicit_region',ambiguity)
def zero_parent_selection():
 o=run();z=next(r for r in o['rows'] if r['vpc_id']=='zero');eq([z[k] for k in ['resolved_subnet_count','referenced_subnet_count','unresolved_subnet_count','known_eip_count']],[0,0,0,0])
 p=deepcopy(P);p['filters']['name']='absent';o=run(p=p);eq(o['rows'],[]);eq(o['diagnostics']['selected_parent_count'],0);return eq(run({})['rows'],[])
case('N04_zero_children_zero_match_and_true_empty_separate',zero_parent_selection)
def unknown_and_unresolved():
 data=deepcopy(d);data['FLOATING_IPS'].append({'id':'missing-owner','logicalRegionName':'r1'});data['R_PORT_IN_SUBNET'].extend([{'id':'unknown-subnet','portId':'p1','subnetId':'\t'},{'id':'dangling-subnet','portId':'p1','subnetId':'ghost'}])
 o=run(data);a=next(r for r in o['rows'] if r['vpc_id']=='A');eq(a['known_eip_count'],3);eq(a['unresolved_subnet_count'],1);eq(a['referenced_subnet_count'],3);eq(o['diagnostics']['unknown_eip_parent_count'],1);eq(o['diagnostics']['selected_unknown_subnet_reference_count'],1);return eq(o['diagnostics']['known_local_graph_complete'],False)
case('N05_missing_EIP_FK_and_unknown_subnet_never_complete',unknown_and_unresolved)
def wrong_role():
 data=deepcopy(d);data['FLOATING_IPS'][0]['routerId']='native-shared';o=run(data);eq(o['diagnostics']['unresolved_eip_parent_count'],1);return eq(o['diagnostics']['known_local_graph_complete'],False)
case('N06_EIP_routerId_not_nativeId_role',wrong_role)
def cross_region():
 data=deepcopy(d);data['FLOATING_IPS'][0]['routerId']='B';reject(lambda:run(data))
 data=deepcopy(d);data['R_PORT_IN_SUBNET'][0]['subnetId']='sB';return reject(lambda:run(data))
case('N07_known_cross_region_edges_rejected',cross_region)
def scope_and_collision():
 p=deepcopy(P);p['filters']['logicalRegionName']='r1';p['required_filters'].append('logicalRegionName');reject(lambda:run(d,p))
 data=deepcopy(d);data['ROUTER'][2]['nativeId']='native-shared';return reject(lambda:run(data))
case('N08_wrong_region_response_and_parent_native_ambiguity',scope_and_collision)
def duplicate_port():
 data=deepcopy(d);data['PORT'].append(deepcopy(data['PORT'][0]));return reject(lambda:run(data))
case('N09_duplicate_PORT_even_identical_not_folded',duplicate_port)
def health_matrix():
 count=0
 for at in ['resource','page']:
  for alias in ['http_status','httpStatus','status_code']:
   for bad in [503,True,None,'200']:
    r=receipts();target=r['ROUTER'] if at=='resource' else r['ROUTER']['pages'][0];target[alias]=bad;reject(lambda:N.execute_local(P,r));count+=1
 r=receipts({});r['ROUTER']['schema_verified']=False;reject(lambda:N.execute_local(P,r))
 r=receipts();r['FLOATING_IPS']['pages'].pop();reject(lambda:N.execute_local(P,r))
 return {'matrix_subcases_not_added':count+2}
case('N10_HTTP_contradictions_schema_and_pages_fail_closed',health_matrix)
def request_and_cross_step():
 plan=N.build(P);eq(len(plan['api_call']),5);assert all('from-step' not in json.dumps(c) for c in plan['api_call'])
 r=receipts();r['ROUTER']['request']['method']='POST';reject(lambda:N.execute_local(P,r))
 r=receipts();r.pop('PORT');reject(lambda:N.execute_local(P,r))
 r=receipts();r['ROUTER']['request']['condition']={'constraint':[{'simple':{'name':'name','value':P['filters']['name'],'operator':'equal'}}]};return reject(lambda:N.execute_local(P,r))
case('N11_full_catalog_binding_no_implicit_cross_step_substitution',request_and_cross_step)
def prepared_checks():
 x=N.prepare(P,receipts());x.pop('input_evidence');reject(lambda:N.execute_prepared(x))
 x=N.prepare(P,receipts());x['tables']['CLOUD_ROUTER'][0]['name']='tampered';reject(lambda:N.execute_prepared(x))
 x=N.prepare(P,receipts());x['input_evidence']['receipts']['ROUTER']['pages'][0]['http_status']=503;x['evidence_sha256']=hashlib.sha256(N.encoded(x['input_evidence'])).hexdigest();return reject(lambda:N.execute_prepared(x))
case('N12_prepared_marker_projection_or_failed_evidence_no_bypass',prepared_checks)
def new_entities():
 data=deepcopy(d);p=deepcopy(P);p['filters']['name']="brand-new_'identifier"
 for ci,rows in data.items():
  for row in rows:
   for k in ['id','nativeId','devNativeId','portId','subnetId','routerId']:
    if k in row:row[k]='fresh-'+row[k]
   if ci=='ROUTER':row['name']=p['filters']['name']
 o=run(data,p);eq({r['vpc_id'] for r in o['rows']},{'fresh-A','fresh-B','fresh-zero'});return eq(o['diagnostics']['known_local_graph_complete'],True)
case('N13_new_quoted_entities_no_old_data_whitelist',new_entities)
def extra_obligations():
 p=deepcopy(P);p['filters']['logicalRegionName']='r1';reject(lambda:N.build(p))
 p=deepcopy(P);p['filters']['vdcName']='other';reject(lambda:N.build(p))
 p=deepcopy(P);p['view']='with_VM';return reject(lambda:N.build(p))
case('N14_missing_required_filter_or_extra_obligation_rejected',extra_obligations)
def encoding_limit():
 p=deepcopy(P);p['filters']['name']='x'*6000;o=N.build(p);eq(o['transport_diagnostic']['status'],'blocked_core_length');assert len(p['filters']['name'])==6000 and p['filters']['name'] in o['sql'];return o['transport_diagnostic']
case('N15_long_legal_name_reports_bound_no_truncation',encoding_limit)

assert source_before=={entry['path']:sha(PACKAGE/entry['path']) for entry in closure['files']}
summary={'scope':'public15-case synthetic replay; published closure audit, no full owner/native acceptance',
 'checks':len(cases),'passed':sum(c['status']=='PASS' for c in cases),'failed':sum(c['status']=='FAIL' for c in cases),
 'matrix_subcases_not_added':sum(c.get('detail',{}).get('matrix_subcases_not_added',0) for c in cases if isinstance(c.get('detail'),dict)),
 'source_contract_files_verified':2,'source_files_unchanged':True,'owner27_suite_run':False,
 'actual_runtime_N_delta':0,'production_enabled':False,'model_calls':0,'service_calls':0,'B_runtime_calls':0,
 'official_executor_or_scorer_calls':0,'057_or_other_capabilities_included':False,
 'remaining':['native duplicate PORT canonical path absent','unknown relationships/conservative global diagnostics','B trusted real request/schema/pages and typed-empty projection','full obligations/business authority','actual final envelope/official depth']}
(out/'RESULTS.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert summary['checks']==summary['passed']==15 and summary['failed']==0 and summary['matrix_subcases_not_added']==26,'public named-VPC replay failed'
