"""Bounded pure-local profile: largest volume-capacity VDC -> referenced storage pools.
No question routing, defaults, network, official runtime, or arbitrary ranking DSL.
"""
from copy import deepcopy
import hashlib
import json
import re
import sqlite3
from urllib.parse import urlencode

FAMILY_ID='A_NEXT_VOLUME_CAPACITY_VDC_POOLS'
SCALE=10**6
MAX_SCALED_TOTAL=2**63-1
WS=''.join(chr(x) for x in (9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288))
RESOURCES=('VOLUME','STORAGE_POOL')
SCHEMA={
 'VOLUME':['id','logicalRegionName','vdcId','vdcName','size','attachBackendId'],
 'STORAGE_POOL':['id','logicalRegionName','poolName','totalCapacityGB','freeCapacityGB','allocatedCapacityGB','provisionedCapacityGB'],
}
PREPARED={**SCHEMA,'VOLUME':SCHEMA['VOLUME']+['size_scaled']}
REQUIRED=('logicalRegionName','tie_policy','unknown_owner_policy','unknown_size_policy')
PARAMETER_SCHEMA={'type':'object','additionalProperties':False,'required':list(REQUIRED),'properties':{
 'logicalRegionName':{'type':'string','minLength':1},'tie_policy':{'enum':['all_ties']},
 'unknown_owner_policy':{'enum':['reject','known_only']},'unknown_size_policy':{'enum':['reject','known_only']}}}
OUTPUT_COLUMNS=['logical_region_name','vdc_id','vdc_name','volume_count','known_volume_size_source_units','unknown_size_volume_count',
 'total_volume_size_if_complete_source_units','unknown_backend_volume_count','referenced_pool_id','pool_id','pool_name','pool_state',
 'pool_total_capacity_raw','pool_free_capacity_raw','pool_allocated_capacity_raw','pool_provisioned_capacity_raw']


def compact(x):return len(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode())
def fingerprint(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def blank(x):return x is None or (isinstance(x,str) and not x.strip(WS))
def blocked(reason,**kw):return {'status':'blocked','reason':reason,**kw}
def literal(x):return "'"+x.replace("'","''")+"'"

def receipt_state(receipt):
 """Same exact success/HTTP rules for resources and every page."""
 if not isinstance(receipt,dict) or receipt.get('ok') is not True:return False
 if 'success' in receipt and receipt['success'] is not True:return False
 if 'error' in receipt:
  error=receipt['error']
  if not (error is None or error is False or (type(error) is str and error=='')):return False
 for key in ('http_status','httpStatus','status_code'):
  if key in receipt and (type(receipt[key]) is not int or not 200<=receipt[key]<=299):return False
 return True

def validate_params(p):
 if not isinstance(p,dict) or set(p)!=set(REQUIRED):raise ValueError('explicit region and all three policies required; no additional scope/obligation supported')
 r=p['logicalRegionName']
 if not isinstance(r,str) or blank(r) or any(ord(c)<32 or ord(c)==127 for c in r):raise ValueError('invalid explicit logicalRegionName')
 if p['tie_policy']!='all_ties':raise ValueError('only explicit all_ties is implemented')
 if any(p[k] not in ('reject','known_only') for k in ('unknown_owner_policy','unknown_size_policy')):raise ValueError('unknown policy must be explicit reject or known_only')

def request(ci,region,page=1,page_size=1000):
 return {'method':'GET','url':'/rest/hackthon/db/instances/'+ci+'?'+urlencode({'pageNo':page,'pageSize':page_size}),
         'condition':{'constraint':[{'simple':{'name':'logicalRegionName','value':region,'operator':'equal'}}]}}

def _exact_text(expr):
 return f"CASE WHEN {expr}%{SCALE}=0 THEN CAST({expr}/{SCALE} AS TEXT) ELSE CAST({expr}/{SCALE} AS TEXT)||'.'||RTRIM(printf('%06d',{expr}%{SCALE}),'0') END"

def _render(p):
 r=literal(p['logicalRegionName']);text=_exact_text('w.k')
 sql=f'''WITH v AS (SELECT * FROM CLOUD_VOLUME WHERE logicalRegionName={r}),
g AS (SELECT logicalRegionName,vdcId,CASE WHEN COUNT(DISTINCT vdcName)=1 THEN MIN(vdcName) END dn,
 COUNT(*) n,SUM(COALESCE(size_scaled,0)) k,SUM(size_scaled IS NULL) u,SUM(attachBackendId IS NULL) b
 FROM v WHERE vdcId IS NOT NULL GROUP BY logicalRegionName,vdcId),
w AS (SELECT * FROM g WHERE k=(SELECT MAX(k) FROM g)),
refs AS (SELECT DISTINCT logicalRegionName,vdcId,attachBackendId FROM v WHERE attachBackendId IS NOT NULL)
SELECT w.logicalRegionName AS logical_region_name,w.vdcId AS vdc_id,w.dn AS vdc_name,w.n AS volume_count,
 {text} AS known_volume_size_source_units,w.u AS unknown_size_volume_count,
 CASE WHEN w.u=0 AND NOT EXISTS(SELECT 1 FROM v WHERE vdcId IS NULL) THEN {text} END AS total_volume_size_if_complete_source_units,
 w.b AS unknown_backend_volume_count,r.attachBackendId AS referenced_pool_id,p.id AS pool_id,p.poolName AS pool_name,
 CASE WHEN r.attachBackendId IS NULL THEN 'no_pool_reference' WHEN p.id IS NULL THEN 'unresolved_pool' ELSE 'resolved' END AS pool_state,
 p.totalCapacityGB AS pool_total_capacity_raw,p.freeCapacityGB AS pool_free_capacity_raw,
 p.allocatedCapacityGB AS pool_allocated_capacity_raw,p.provisionedCapacityGB AS pool_provisioned_capacity_raw
FROM w LEFT JOIN refs r ON r.logicalRegionName=w.logicalRegionName AND r.vdcId=w.vdcId
LEFT JOIN CLOUD_STORAGE_POOL p ON p.id=r.attachBackendId AND p.logicalRegionName=w.logicalRegionName
ORDER BY w.logicalRegionName,w.vdcId,r.attachBackendId'''
 return {'api_call':[request(ci,p['logicalRegionName']) for ci in RESOURCES],'sql':sql}

def envelope_budget(payload,boundary='B_final_envelope',limit=4096):
 n=compact(payload);return {'status':'blocked' if n>limit else 'within_local_byte_budget','reason':'utf8_json_budget_exceeded' if n>limit else None,'boundary':boundary,'measured_bytes':n,'limit_bytes':limit}

def build(params):
 validate_params(params);core=_render(params);n=compact(core)
 static=dict(params);static['logicalRegionName']='{{logicalRegionName}}'
 out={'id':FAMILY_ID,'profile':'volume_capacity_max_vdc_pools','resources':list(RESOURCES),**core,
      'status':'blocked_transport_budget' if n>4096 else 'isolated_candidate_policy_conditional',
      'blocked_reason':{'boundary':'expanded_api_call+sql','measured_bytes':n,'limit_bytes':4096,'reason':'utf8_json_budget_exceeded'} if n>4096 else None,
      'params':dict(params),'parameter_schema':deepcopy(PARAMETER_SCHEMA),'output_columns':list(OUTPUT_COLUMNS),
      'required_schema':deepcopy(SCHEMA),'prepared_schema':deepcopy(PREPARED),
      'requires_validated_projection':True,'projection_contract':'volume-capacity-vdc-pool-v3-source-rechecked',
      'size_scale':SCALE,'size_unit':'source_raw_unconverted','byte_boundaries':{
       'encoding':'UTF8 compact JSON ensure_ascii=False','static_api_sql_template_bytes':compact(_render(static)),
       'expanded_wire_bytes':n,'expanded_wire_limit_bytes':4096,'full_plan_bytes':0,'full_plan_limit_bytes':None,
       'final_B_envelope':'must measure actual outgoing wrapper separately','formal_depth4_gate':'unresolved, not passed'},
      'needs_C':['VDC identity namespace and in-scope volume-owner population','all tied maxima and unknown-owner/size policies','source capacity unit and six-decimal bounded numeric policy','pool detail display semantics; whole-pool capacities are not exclusive VDC allocations']}
 for _ in range(4):out['byte_boundaries']['full_plan_bytes']=compact(out)
 return out

def scaled_size(value):
 if value is None or isinstance(value,bool) or not isinstance(value,(str,int,float)):return None
 text=str(value).strip(WS)
 if re.fullmatch(r'[0-9]+(?:\.[0-9]{1,6})?',text,flags=re.ASCII) is None:return None
 # Exact integer scaling from text avoids Decimal-context rounding and SQLite dirty CAST.
 whole,dot,frac=text.partition('.')
 n=int(whole)*SCALE+int(frac.ljust(6,'0') if dot else '0')
 if n>MAX_SCALED_TOTAL:raise ValueError('numeric_range_exceeded')
 return n

def preflight(params,snapshots):
 plan=build(params)
 if plan['status']=='blocked_transport_budget':return blocked('transport_budget',blocked_reason=plan['blocked_reason'])
 if not isinstance(snapshots,dict) or set(snapshots)!=set(RESOURCES):return blocked('missing_or_extra_resource')
 tables={};region=params['logicalRegionName']
 for ci in RESOURCES:
  snap=snapshots[ci]
  if not receipt_state(snap):return blocked('request_outcome_unconfirmed',resource=ci)
  if not isinstance(snap.get('schema_source'),str) or blank(snap['schema_source']):return blocked('schema_provenance_required',resource=ci)
  if not isinstance(snap.get('columns'),list) or not all(isinstance(c,str) for c in snap['columns']) or not set(SCHEMA[ci])<=set(snap['columns']):return blocked('missing_schema',resource=ci)
  pages=snap.get('pages')
  if not isinstance(pages,list) or not pages:return blocked('missing_pages',resource=ci)
  rows=[];seen=set();meta=None
  for index,page in enumerate(pages,1):
   if not receipt_state(page):return blocked('page_request_failed_or_unconfirmed',resource=ci)
   vals=[page.get(k) for k in ('totalNum','totalPageNo','pageSize','currentPage')]
   if any(type(v) is not int for v in vals):return blocked('invalid_pagination_metadata',resource=ci)
   total,np,ps,no=vals
   expected=max(1,(total+ps-1)//ps) if ps>0 else -1
   if total<0 or not 1<=ps<=1000 or no!=index or (np!=expected and not(total==0 and np==0 and len(pages)==1)) or len(pages)!=expected:return blocked('incomplete_or_out_of_order_pages',resource=ci)
   if page.get('request')!=request(ci,region,index,ps):return blocked('request_binding_mismatch',resource=ci)
   if meta is None:meta=vals[:3]
   elif meta!=vals[:3]:return blocked('unstable_pagination',resource=ci)
   batch=page.get('objList')
   if not isinstance(batch,list) or len(batch)!=min(ps,max(0,total-(index-1)*ps)):return blocked('truncated_page',resource=ci)
   for raw in batch:
    if not isinstance(raw,dict) or any(k not in raw for k in SCHEMA[ci]):return blocked('missing_row_schema',resource=ci)
    if not isinstance(raw['id'],str) or blank(raw['id']):return blocked('missing_identity',resource=ci)
    if raw['id'] in seen:return blocked('duplicate_identity',resource=ci)
    seen.add(raw['id'])
    if raw['logicalRegionName']!=region:return blocked('scope_leak',resource=ci)
    if any(raw[k] is not None and not isinstance(raw[k],str) for k in SCHEMA[ci] if k!='size'):return blocked('invalid_text_field',resource=ci)
    row={k:deepcopy(raw[k]) for k in SCHEMA[ci]}
    if ci=='VOLUME':
     row['vdcId']=None if blank(row['vdcId']) else row['vdcId']
     row['attachBackendId']=None if blank(row['attachBackendId']) else row['attachBackendId']
     try:row['size_scaled']=scaled_size(row['size'])
     except (ValueError,OverflowError):return blocked('numeric_range_exceeded',resource=ci)
     if row['size'] is not None and not isinstance(row['size'],(str,int,float)):return blocked('invalid_size_field_type',resource=ci)
    rows.append(row)
  tables[ci]=rows
 volumes=tables['VOLUME'];unknown_owner=sum(v['vdcId'] is None for v in volumes);unknown_size=sum(v['size_scaled'] is None for v in volumes)
 if unknown_owner and params['unknown_owner_policy']=='reject':return blocked('unknown_vdc_identity',unknown_owner_volume_count=unknown_owner,unknown_size_volume_count=unknown_size)
 if unknown_size and params['unknown_size_policy']=='reject':return blocked('unknown_volume_size',unknown_owner_volume_count=unknown_owner,unknown_size_volume_count=unknown_size)
 if sum(v['size_scaled'] or 0 for v in volumes)>MAX_SCALED_TOTAL:return blocked('numeric_aggregate_range_exceeded')
 pools={v['id'] for v in tables['STORAGE_POOL']}
 unknown_backend=sum(v['attachBackendId'] is None for v in volumes)
 unresolved=sum(v['attachBackendId'] is not None and v['attachBackendId'] not in pools for v in volumes)
 diagnostics={'unknown_owner_volume_count':unknown_owner,'unknown_size_volume_count':unknown_size,
  'unknown_backend_volume_count':unknown_backend,'unresolved_backend_volume_count':unresolved,
  'ranking_basis':'known_size_lower_bound' if unknown_size else 'complete_sizes_within_known_owner_population',
  'population':'known_vdc_ids_owning_in_scope_volumes' if unknown_owner else 'all_observed_vdc_ids_owning_in_scope_volumes',
  'scope_max_certified':unknown_owner==0 and unknown_size==0,'business_policy_accepted':False,
  'input_volume_count':len(volumes),'no_volume_population':not volumes,
  'pool_capacity_meaning':'whole pool capacities, not exclusive VDC allocation'}
 # Retain this invocation's actual supplied receipts, not a verified/strict flag.
 # They stay local and are consumed again before SQL; raw input is never mutated.
 evidence={'params':deepcopy(params),'snapshots':deepcopy(snapshots)}
 return {'status':'ready_for_typed_sql','tables':tables,'input_evidence':evidence,'input_evidence_sha256':fingerprint(evidence),'prepared_schema':deepcopy(PREPARED),'diagnostics':diagnostics,
  'projection_contract':plan['projection_contract'],'params_sha256':fingerprint(params),'projection_sha256':fingerprint(tables),'diagnostics_sha256':fingerprint(diagnostics)}

prepare=preflight

def execute_prepared(params,prepared):
 plan=build(params)
 if plan['status']=='blocked_transport_budget':return blocked('transport_budget',blocked_reason=plan['blocked_reason'])
 if not isinstance(prepared,dict) or prepared.get('status')!='ready_for_typed_sql' or prepared.get('projection_contract')!=plan['projection_contract'] or prepared.get('params_sha256')!=fingerprint(params):return blocked('validated_projection_required')
 tables=prepared.get('tables')
 if not isinstance(tables,dict) or set(tables)!=set(RESOURCES) or prepared.get('projection_sha256')!=fingerprint(tables):return blocked('projection_changed')
 # Revalidate canonical projection and same-source diagnostics before loading.
 for ci in RESOURCES:
  for row in tables[ci]:
   if not isinstance(row,dict) or set(row)!=set(PREPARED[ci]):return blocked('invalid_projection_schema')
   if ci=='VOLUME':
    if (row['vdcId'] is not None and blank(row['vdcId'])) or (row['attachBackendId'] is not None and blank(row['attachBackendId'])):return blocked('uncanonical_identity')
    try:expected=scaled_size(row['size'])
    except (ValueError,OverflowError):return blocked('numeric_range_exceeded')
    if row['size_scaled']!=expected:return blocked('size_projection_changed')
 vols=tables['VOLUME'];d=prepared.get('diagnostics')
 if not isinstance(d,dict) or prepared.get('diagnostics_sha256')!=fingerprint(d):return blocked('diagnostic_projection_mismatch')
 if d.get('unknown_owner_volume_count')!=sum(v['vdcId'] is None for v in vols) or d.get('unknown_size_volume_count')!=sum(v['size_scaled'] is None for v in vols):return blocked('diagnostic_projection_mismatch')
 if any(row['logicalRegionName']!=params['logicalRegionName'] for ci in RESOURCES for row in tables[ci]):return blocked('scope_leak')
 evidence=prepared.get('input_evidence')
 if not isinstance(evidence,dict) or set(evidence)!={'params','snapshots'}:return blocked('input_receipts_required')
 if prepared.get('input_evidence_sha256')!=fingerprint(evidence):return blocked('input_receipts_changed')
 if evidence['params']!=params:return blocked('input_receipt_params_mismatch')
 # A caller changing a version tag or a boolean cannot bypass the actual receipts.
 # Revalidate source state/request/schema/paging and derive the canonical projection.
 rechecked=preflight(params,evidence['snapshots'])
 if rechecked.get('status')!='ready_for_typed_sql':
  return blocked('source_receipts_rejected',source_reason=rechecked.get('reason'),resource=rechecked.get('resource'))
 if (rechecked['projection_sha256']!=prepared.get('projection_sha256')
     or rechecked['diagnostics_sha256']!=prepared.get('diagnostics_sha256')):
  return blocked('source_projection_mismatch')
 conn=sqlite3.connect(':memory:')
 try:
  for ci in RESOURCES:
   cols=PREPARED[ci];conn.execute('CREATE TABLE CLOUD_'+ci+' ('+','.join('"'+k+'" '+('INTEGER' if k=='size_scaled' else 'TEXT') for k in cols)+')')
   conn.executemany('INSERT INTO CLOUD_'+ci+' VALUES ('+','.join('?' for _ in cols)+')',[[r[k] for k in cols] for r in tables[ci]])
  cur=conn.execute(plan['sql']);rows=[dict(zip([c[0] for c in cur.description],r)) for r in cur.fetchall()]
 finally:conn.close()
 winids={r['vdc_id'] for r in rows};winning=[v for v in vols if v['vdcId'] in winids]
 poolids={p['id'] for p in tables['STORAGE_POOL']}
 unknown=sum(v['attachBackendId'] is None for v in winning);unresolved=sum(v['attachBackendId'] is not None and v['attachBackendId'] not in poolids for v in winning)
 # Truth flags derive again from the validated volume projection, not supplied flags.
 owner_unknown=sum(v['vdcId'] is None for v in vols);size_unknown=sum(v['size_scaled'] is None for v in vols)
 scope_certified=owner_unknown==0 and size_unknown==0
 # These are independent presence/link diagnostics, not numeric validity or business acceptance.
 link_complete=unknown==0 and unresolved==0
 referenced={v['attachBackendId'] for v in winning if v['attachBackendId'] is not None}
 selected_pools=[p for p in tables['STORAGE_POOL'] if p['id'] in referenced]
 attributes=('poolName','totalCapacityGB','freeCapacityGB','allocatedCapacityGB','provisionedCapacityGB')
 attributes_complete=link_complete and all(not blank(p[k]) for p in selected_pools for k in attributes)
 diagnostics=deepcopy(d);diagnostics.update({'unknown_owner_volume_count':owner_unknown,'unknown_size_volume_count':size_unknown,
  'scope_max_certified':scope_certified,'business_policy_accepted':False,
  'ranking_basis':'known_size_lower_bound' if size_unknown else 'complete_sizes_within_known_owner_population',
  'population':'known_vdc_ids_owning_in_scope_volumes' if owner_unknown else 'all_observed_vdc_ids_owning_in_scope_volumes',
  'winner_unknown_backend_volume_count':unknown,'winner_unresolved_backend_volume_count':unresolved,
  'pool_link_complete':link_complete,'attribute_values_complete':attributes_complete,
  'complete_winner_pool_details':link_complete,'complete_winner_pool_details_semantics':'deprecated link-coverage alias only; does not assert attribute values present','winner_claim':'all_maxima_among_observed_owner_population' if scope_certified else 'known_lower_bound_leaders_only',
  'full_answer_certified':False})
 return {'status':'local_sql_ok_policy_conditional','columns':list(OUTPUT_COLUMNS),'rows':rows,'diagnostics':diagnostics,'byte_boundaries':plan['byte_boundaries']}

def execute(params,snapshots):
 checked=preflight(params,snapshots)
 return execute_prepared(params,checked) if checked['status']=='ready_for_typed_sql' else checked


execute_local=execute
