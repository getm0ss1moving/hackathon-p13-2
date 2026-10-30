"""Closed cluster ranking + host vCPU + active-VM list candidate. Pure local only."""
from copy import deepcopy
import hashlib
import json
import math
import sqlite3
from urllib.parse import urlencode

PROFILE='cluster_max_vm_host_running_details'
RESOURCES=('VM_NOVA','CLUSTER','M_ClusterContainsPhyHost','HOST')
SCHEMA={'VM_NOVA':['id','name','logicalRegionName','azoneName','clusterId','hostId','status'],
 'CLUSTER':['id','name','logicalRegionName'],
 'M_ClusterContainsPhyHost':['id','source_Instance_Id','target_Instance_Id'],
 'HOST':['id','name','logicalRegionName','totalVcpuCores']}
OPTIONAL_VALUES={'VM_NOVA':{'azoneName','clusterId','hostId','status'},'HOST':{'totalVcpuCores'},'M_ClusterContainsPhyHost':{'source_Instance_Id','target_Instance_Id'},'CLUSTER':set()}
PREPARED={**SCHEMA,'VM_NOVA':SCHEMA['VM_NOVA']+['rank_eligible','rank_cluster_id','is_running','status_known'],
 'CLUSTER':SCHEMA['CLUSTER']+['host_graph_complete'],'HOST':SCHEMA['HOST']+['vcpu_known']}
MAX_CPU=2**63-1
WS=''.join(chr(n) for n in (9,10,11,12,13,28,29,30,31,32,133,160,5760,*range(8192,8203),8232,8233,8239,8287,12288))
# Exact documented nonactive status tokens; unknown/other/uppercase are uncertain.
NONACTIVE={'building','error','resize','deleted','hibernating','hibernated','stopped','create_failed','create_success','starting','stopping','migrating','shutting_down','fault_resuming','pause','recycling','removed','reboot','shutoff','suspended','verify_resize','live_volume_migrating','storage_migrating','live_volume_migrating_fail'}
POPULATIONS=('all_hosts_all_active_VMs','winner-cluster-only_active_VMs')
OUTPUT_COLUMNS=['cluster_id','cluster_name','cluster_logical_region_name','rank_vm_count','reference_host_id','host_id','host_name','host_vcpu_raw','known_cluster_host_vcpu','unknown_host_vcpu_count','complete_cluster_host_vcpu','running_vm_id','running_vm_name','running_vm_status','host_link_status']

def utf8(x):
 if not isinstance(x,str):return False
 try:x.encode('utf-8');return True
 except UnicodeEncodeError:return False

def receipt_ok(x):
 if not isinstance(x,dict) or x.get('ok') is not True or x.get('error') or ('success' in x and x['success'] is not True):return False
 keys=('http_status','httpStatus','status_code','statusCode','http_status_code','httpStatusCode')
 for k in keys:
  if k in x and (type(x[k]) is not int or not 200<=x[k]<300):return False
 if 'status' in x and type(x['status']) is int and not 200<=x['status']<300:return False
 return True

def blank(x):return x is None or (isinstance(x,str) and not x.strip(WS))
def compact(x):return len(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode())
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def block(reason,**kw):return {'status':'blocked','reason':reason,**kw}
def lit(x):return "'"+x.replace("'","''")+"'"

def validate_params(p):
 keys={'profile','filters','tie_policy','unknown_rank_policy','details_population'}
 if not isinstance(p,dict) or set(p)!=keys or p['profile']!=PROFILE:raise ValueError('closed profile with explicit filters/policies required')
 if not isinstance(p['filters'],dict) or set(p['filters'])-{'logicalRegionName','azoneName'}:raise ValueError('global{} or explicit region/AZ filters only')
 for value in p['filters'].values():
  if not utf8(value) or blank(value) or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('nonblank control-free filter value required')
 if p['tie_policy']!='all_ties' or p['unknown_rank_policy'] not in ('reject','known_only_with_diagnostic') or p['details_population'] not in POPULATIONS:raise ValueError('unsupported explicit policy')

def request(ci,page=1,page_size=1000):
 endpoint='relations' if ci.startswith('M_') else 'instances'
 return {'method':'GET','url':'/rest/hackthon/db/'+endpoint+'/'+ci+'?'+urlencode({'pageNo':page,'pageSize':page_size})}

def _render(p):
 # Filters are materialized into the validated rank_eligible column; explicit SQL
 # predicate keeps their role inspectable and prevents accidental AZ detail filtering.
 predicate=' AND '.join('v.'+k+'='+lit(v) for k,v in sorted(p['filters'].items())) or '1=1'
 restriction=' AND v.clusterId=w.cid' if p['details_population']=='winner-cluster-only_active_VMs' else ''
 sql=f'''WITH r AS(SELECT v.rank_cluster_id cid,COUNT(DISTINCT v.id) n FROM CLOUD_VM_NOVA v
 WHERE v.rank_eligible=1 AND v.rank_cluster_id IS NOT NULL AND {predicate} GROUP BY v.rank_cluster_id),
w AS(SELECT c.id cid,c.name cn,c.logicalRegionName rg,c.host_graph_complete gc,r.n FROM r JOIN CLOUD_CLUSTER c ON c.id=r.cid WHERE r.n=(SELECT MAX(n) FROM r)),
e AS(SELECT DISTINCT x.source_Instance_Id cid,x.target_Instance_Id hid FROM M_ClusterContainsPhyHost x JOIN w ON w.cid=x.source_Instance_Id),
h AS(SELECT e.cid,e.hid,h.id id,h.name hn,h.totalVcpuCores raw,h.vcpu_known cpu FROM e JOIN w ON w.cid=e.cid LEFT JOIN CLOUD_HOST h ON h.id=e.hid AND h.logicalRegionName=w.rg),
s AS(SELECT cid,SUM(COALESCE(cpu,0)) k,SUM(cpu IS NULL) u FROM h GROUP BY cid)
SELECT w.cid AS cluster_id,w.cn AS cluster_name,w.rg AS cluster_logical_region_name,w.n AS rank_vm_count,
h.hid AS reference_host_id,h.id AS host_id,h.hn AS host_name,h.raw AS host_vcpu_raw,
COALESCE(s.k,0) AS known_cluster_host_vcpu,COALESCE(s.u,0) AS unknown_host_vcpu_count,
CASE WHEN w.gc=1 AND COALESCE(s.u,0)=0 THEN COALESCE(s.k,0) END AS complete_cluster_host_vcpu,
v.id AS running_vm_id,v.name AS running_vm_name,v.status AS running_vm_status,
CASE WHEN h.cid IS NULL THEN 'no_host_reference' WHEN h.hid IS NULL THEN 'unknown_host_reference' WHEN h.id IS NULL THEN 'unresolved_host' ELSE 'resolved' END AS host_link_status
FROM w LEFT JOIN h ON h.cid=w.cid LEFT JOIN s ON s.cid=w.cid
LEFT JOIN CLOUD_VM_NOVA v ON v.hostId=h.hid AND v.logicalRegionName=w.rg AND v.is_running=1{restriction}
ORDER BY w.rg,w.cid,h.hid,v.id'''
 return {'api_call':[request(ci) for ci in RESOURCES],'sql':sql}

def build(params):
 validate_params(params);core=_render(params);n=compact(core)
 static=deepcopy(params);static['filters']={k:'{{'+k+'}}' for k in params['filters']}
 out={'id':'A_NEXT_CLUSTER_RANKED_HOSTS','profile':PROFILE,'params':deepcopy(params),'resources':list(RESOURCES),**core,
 'status':'blocked_transport_budget' if n>4096 else 'isolated_candidate_policy_conditional',
 'blocked_reason':{'boundary':'expanded_api_call+sql','measured_bytes':n,'limit_bytes':4096,'reason':'utf8_json_budget_exceeded'} if n>4096 else None,
 'output_columns':list(OUTPUT_COLUMNS),'required_schema':deepcopy(SCHEMA),'prepared_schema':deepcopy(PREPARED),
 'requires_validated_projection':True,'projection_contract':'cluster-ranked-hosts-v1','native_running_literal':'active',
 'byte_boundaries':{'static_placeholder_core_bytes':compact(_render(static)),'expanded_wire_bytes':n,'expanded_wire_limit_bytes':4096,'full_plan_bytes':0,'full_plan_limit_bytes':None,'final_B_envelope':'measure actual wrapper separately','depth4':'pending official algorithm; not passed'},
 'gates':['native870 unknown cluster refs;34 unresolved host endpoints and32 missing nativeCPU remain partial','C ranking/detail/unknown policies','B truthful global context receipts and typed projection loading','actual final wire/depth limits']}
 for _ in range(4):out['byte_boundaries']['full_plan_bytes']=compact(out)
 return out

def envelope_budget(payload,boundary='B_final_envelope',limit=4096):
 n=compact(payload);return {'status':'blocked' if n>limit else 'within_local_byte_budget','boundary':boundary,'measured_bytes':n,'limit_bytes':limit,'reason':'utf8_json_budget_exceeded' if n>limit else None}

def _graph(params,tables):
 clusters={c['id']:c for c in tables['CLUSTER']};hosts={h['id']:h for h in tables['HOST']};vms=tables['VM_NOVA'];rels=tables['M_ClusterContainsPhyHost']
 unknown_scope=0;unknown_cluster=0
 for v in vms:
  v['is_running']=int(v['status']=='active');v['status_known']=int(v['status']=='active' or v['status'] in NONACTIVE)
  region_match='logicalRegionName' not in params['filters'] or v['logicalRegionName']==params['filters']['logicalRegionName']
  scope_uncertain=region_match and 'azoneName' in params['filters'] and blank(v['azoneName'])
  eligible=region_match and not scope_uncertain and all(v[k]==value for k,value in params['filters'].items())
  c=clusters.get(v['clusterId']);known=c is not None and c['logicalRegionName']==v['logicalRegionName']
  unknown_scope+=int(scope_uncertain);unknown_cluster+=int(eligible and not known)
  v['rank_eligible']=int(eligible);v['rank_cluster_id']=v['clusterId'] if known else None
 for h in hosts.values():
  val=h['totalVcpuCores']
  if type(val) is int and abs(val)>MAX_CPU:raise ValueError('native_host_cpu_range_exceeded')
  h['vcpu_known']=val if type(val) is int and 0<=val<=MAX_CPU else None
 unknown_source=sum(x['source_Instance_Id'] not in clusters for x in rels)
 summaries={}
 for cid,c in clusters.items():
  edges=[x for x in rels if x['source_Instance_Id']==cid];refs={x['target_Instance_Id'] for x in edges};knownrefs={x for x in refs if x is not None}
  unresolved=[x for x in knownrefs if x not in hosts or hosts[x]['logicalRegionName']!=c['logicalRegionName']]
  owned=[v for v in vms if v['clusterId']==cid and v['logicalRegionName']==c['logicalRegionName']]
  missing_members=[v for v in owned if v['hostId'] is None or v['hostId'] not in knownrefs]
  onrefs=[v for v in vms if v['hostId'] in knownrefs and v['logicalRegionName']==c['logicalRegionName']]
  selected=onrefs if params['details_population']=='all_hosts_all_active_VMs' else [v for v in onrefs if v['clusterId']==cid]
  unknown_status=sum(not v['status_known'] for v in selected)
  potential_unplaced=sum(v['hostId'] is None and (v['is_running'] or not v['status_known']) and v['logicalRegionName']==c['logicalRegionName'] and (params['details_population']=='all_hosts_all_active_VMs' or v['clusterId']==cid or v['rank_cluster_id'] is None) for v in vms)
  cross_region_onrefs=sum(v['hostId'] in knownrefs and v['logicalRegionName']!=c['logicalRegionName'] for v in vms)
  unknown_detail_cluster=sum(v['rank_cluster_id'] is None for v in onrefs) if params['details_population']=='winner-cluster-only_active_VMs' else 0
  c['host_graph_complete']=int(not unknown_source and None not in refs and not unresolved and not missing_members)
  cpu=sum(hosts[x]['vcpu_known'] or 0 for x in knownrefs if x in hosts and hosts[x]['logicalRegionName']==c['logicalRegionName'])
  if cpu>MAX_CPU:raise ValueError('host_cpu_sum_range_exceeded')
  unplaced=[{k:v[k] for k in ('id','name','status','hostId','clusterId')} for v in missing_members if v['is_running']]
  summaries[cid]={'unknown_relation_source_count':unknown_source,'blank_host_reference_rows':sum(x['target_Instance_Id'] is None for x in edges),
   'unresolved_host_reference_ids':sorted(unresolved),'unknown_status_vm_count':unknown_status,'potentially_active_unplaced_context_vm_count':potential_unplaced,'cross_region_vm_host_reference_count':cross_region_onrefs,'unknown_detail_cluster_vm_count':unknown_detail_cluster,
   'known_cluster_vm_missing_host_membership_count':len(missing_members),'unplaced_known_active_vm_rows':unplaced,
   'host_graph_complete':bool(c['host_graph_complete']),'running_vm_list_complete':bool(c['host_graph_complete']) and not unknown_status and not unknown_detail_cluster and not unplaced and not potential_unplaced and not cross_region_onrefs}
 return {'unknown_rank_scope_vm_count':unknown_scope,'unknown_rank_cluster_vm_count':unknown_cluster,'unknown_rank_vm_count':unknown_scope+unknown_cluster,
  'scope_max_certified':not unknown_scope and not unknown_cluster,'ranking_population':'clusters referenced by scoped VMs; no zero-VM cluster-catalog maximum is claimed',
  'business_policy_accepted':False,'cluster_details':summaries}

def preflight(params,snapshots):
 plan=build(params)
 if plan['status']=='blocked_transport_budget':return block('transport_budget',blocked_reason=plan['blocked_reason'])
 if not isinstance(snapshots,dict) or set(snapshots)!=set(RESOURCES):return block('missing_or_extra_resource')
 tables={};missing_optional={}
 for ci in RESOURCES:
  snap=snapshots[ci]
  if not receipt_ok(snap):return block('request_failed_or_unconfirmed',resource=ci)
  if not utf8(snap.get('schema_source')) or blank(snap['schema_source']):return block('schema_provenance_required',resource=ci)
  if not isinstance(snap.get('columns'),list) or not all(utf8(c) for c in snap['columns']) or not set(SCHEMA[ci])<=set(snap['columns']):return block('missing_schema',resource=ci)
  pages=snap.get('pages')
  if not isinstance(pages,list) or not pages:return block('missing_pages',resource=ci)
  rows=[];seen=set();meta=None
  for i,page in enumerate(pages,1):
   if not receipt_ok(page):return block('page_failed_or_unconfirmed',resource=ci)
   vals=[page.get(k) for k in ('totalNum','totalPageNo','pageSize','currentPage')]
   if any(type(v) is not int for v in vals):return block('invalid_pagination',resource=ci)
   total,np,ps,no=vals;expected=max(1,(total+ps-1)//ps) if ps>0 else -1
   if total<0 or not 1<=ps<=1000 or no!=i or len(pages)!=expected or (np!=expected and not(total==0 and np==0 and len(pages)==1)):return block('incomplete_or_unstable_pages',resource=ci)
   if meta is None:meta=vals[:3]
   elif meta!=vals[:3]:return block('unstable_pagination',resource=ci)
   if page.get('request')!=request(ci,i,ps):return block('request_binding_mismatch',resource=ci)
   batch=page.get('objList')
   if not isinstance(batch,list) or len(batch)!=min(ps,max(0,total-(i-1)*ps)):return block('truncated_page',resource=ci)
   for raw in batch:
    if not isinstance(raw,dict) or any(k not in raw for k in set(SCHEMA[ci])-OPTIONAL_VALUES[ci]):return block('missing_row_schema',resource=ci)
    if not isinstance(raw['id'],str) or blank(raw['id']) or raw['id'] in seen:return block('invalid_or_duplicate_identity',resource=ci)
    seen.add(raw['id']);row={k:deepcopy(raw.get(k)) for k in SCHEMA[ci]}
    for key in OPTIONAL_VALUES[ci]:
     if key not in raw:missing_optional[ci+'.'+key]=missing_optional.get(ci+'.'+key,0)+1
    if ci!='M_ClusterContainsPhyHost' and (not isinstance(row['logicalRegionName'],str) or blank(row['logicalRegionName'])):return block('unknown_region_context',resource=ci)
    for key,value in row.items():
     if isinstance(value,str) and not utf8(value):return block('invalid_utf8_business_text',resource=ci)
     if key=='totalVcpuCores':
      if value is not None and type(value) not in (str,int,float):return block('invalid_cpu_field_type')
      if type(value) is float and not math.isfinite(value):return block('invalid_nonfinite_native_cpu')
     elif value is not None and not isinstance(value,str):return block('invalid_text_field',resource=ci)
    for key in ('clusterId','hostId','source_Instance_Id','target_Instance_Id'):
     if key in row and blank(row[key]):row[key]=None
    rows.append(row)
  tables[ci]=rows
 try:diagnostics=_graph(params,tables)
 except ValueError as err:return block(str(err))
 diagnostics['missing_nullable_business_fields']=missing_optional
 if diagnostics['unknown_rank_vm_count'] and params['unknown_rank_policy']=='reject':return block('unknown_rank_population',diagnostics=diagnostics)
 return {'status':'ready_for_typed_sql','tables':tables,'diagnostics':diagnostics,'projection_contract':plan['projection_contract'],'params_sha256':digest(params),'projection_sha256':digest(tables)}

prepare=preflight

def execute_prepared(params,prepared):
 plan=build(params)
 if plan['status']=='blocked_transport_budget':return block('transport_budget',blocked_reason=plan['blocked_reason'])
 if not isinstance(prepared,dict) or prepared.get('status')!='ready_for_typed_sql' or prepared.get('projection_contract')!=plan['projection_contract'] or prepared.get('params_sha256')!=digest(params):return block('validated_projection_required')
 tables=deepcopy(prepared.get('tables'))
 if not isinstance(tables,dict) or set(tables)!=set(RESOURCES) or prepared.get('projection_sha256')!=digest(tables):return block('projection_changed')
 if any(not isinstance(row,dict) or set(row)!=set(PREPARED[ci]) for ci in RESOURCES for row in tables[ci]):return block('invalid_projection_schema')
 # Recompute every derived value and truth flag; never trust caller-mutated markers.
 before=digest(tables)
 try:diagnostics=_graph(params,tables)
 except ValueError as err:return block(str(err))
 if digest(tables)!=before:return block('derived_projection_changed')
 if diagnostics['unknown_rank_vm_count'] and params['unknown_rank_policy']=='reject':return block('unknown_rank_population',diagnostics=diagnostics)
 conn=sqlite3.connect(':memory:')
 try:
  for ci in RESOURCES:
   cols=PREPARED[ci];integer={'rank_eligible','is_running','status_known','host_graph_complete','vcpu_known'}
   def typ(k):return 'INTEGER' if k in integer else 'BLOB' if k=='totalVcpuCores' else 'TEXT'
   name=ci if ci.startswith('M_') else 'CLOUD_'+ci
   conn.execute('CREATE TABLE '+name+' ('+','.join('"'+k+'" '+typ(k) for k in cols)+')')
   conn.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in cols)+')',[[r[k] for k in cols] for r in tables[ci]])
  cur=conn.execute(plan['sql']);rows=[dict(zip([c[0] for c in cur.description],r)) for r in cur.fetchall()]
 finally:conn.close()
 winners={r['cluster_id'] for r in rows};diagnostics['selected_cluster_details']={k:v for k,v in diagnostics.pop('cluster_details').items() if k in winners}
 diagnostics['winner_claim']='all_maxima_among_observed_scoped_VM_owners' if diagnostics['scope_max_certified'] else 'known_cluster_leaders_only'
 diagnostics['full_answer_certified']=False
 return {'status':'local_sql_ok_policy_conditional','columns':list(OUTPUT_COLUMNS),'rows':rows,'diagnostics':diagnostics,'byte_boundaries':plan['byte_boundaries']}

def execute_local(params,snapshots):
 checked=preflight(params,snapshots)
 return execute_prepared(params,checked) if checked['status']=='ready_for_typed_sql' else checked
execute=execute_local
