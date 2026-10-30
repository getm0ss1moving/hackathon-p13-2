"""Closed global/named VPC hierarchy candidates; no service/model calls."""
from __future__ import annotations
import json
import sqlite3
from collections import defaultdict

RESOURCES=('ROUTER','PORT','R_PORT_IN_SUBNET','SUBNET','VM_NOVA')
SCHEMA={
 'ROUTER':('id','name','nativeId','logicalRegionName'),
 'PORT':('id','devNativeId','devId','logicalRegionName'),
 'R_PORT_IN_SUBNET':('id','portId','subnetId'),
 'SUBNET':('id','name','cidr','logicalRegionName'),
 'VM_NOVA':('id','resId','name','logicalRegionName'),
}
TABLES={r:r if r.startswith('R_') else 'CLOUD_'+r for r in RESOURCES}
HIERARCHY_COLUMNS=('catalog_vpc_count','selected_vpc_count','row_kind','vpc_id','vpc_name','region_name','subnet_reference_id','subnet_id','subnet_name','subnet_cidr','subnet_link_status','vm_port_reference_id','vm_reference_res_id','vm_id','vm_name','vm_link_status')
COUNT_COLUMNS=('catalog_vpc_count','selected_vpc_count','row_kind','vpc_id','vpc_name','region_name','referenced_subnet_count','resolved_subnet_count','unresolved_subnet_count','has_unknown_subnet_link','known_vm_count','unknown_vm_endpoint_count')

class Unsupported(ValueError):pass

def blank(v):return v is None or (isinstance(v,str) and not v.strip())
def literal(v):return "'"+v.replace("'","''")+"'"
def params_checked(params):
 if not isinstance(params,dict) or 'view' not in params or set(params)-{'view','vpcName','logicalRegionName'}:raise Unsupported('closed parameters: view, optional exact vpcName, optional logicalRegionName')
 if params['view'] not in ('hierarchy_rows','parent_counts'):raise Unsupported('unknown view')
 for k in ('vpcName','logicalRegionName'):
  if k in params and (not isinstance(params[k],str) or blank(params[k]) or any(ord(c)<32 for c in params[k])):raise Unsupported(k+' must be a nonblank exact string without control characters; no default scope')
 for value in params.values():
  try:value.encode('utf-8')
  except UnicodeEncodeError:raise Unsupported('surrogate text is not valid UTF-8')
 return dict(params)

def build(params):
 p=params_checked(params);where=[]
 if 'vpcName' in p:where.append('name='+literal(p['vpcName']))
 if 'logicalRegionName' in p:where.append('logicalRegionName='+literal(p['logicalRegionName']))
 parent_filter=' AND '.join(where) or '1=1'
 cte=f"""WITH p AS (SELECT * FROM CLOUD_ROUTER WHERE {parent_filter}),
 vr AS (SELECT DISTINCT p.id AS vpc_id,router_relation.subnetId AS subnet_ref FROM p
 JOIN CLOUD_PORT router_port ON router_port.devNativeId=p.nativeId AND router_port.logicalRegionName=p.logicalRegionName
 LEFT JOIN R_PORT_IN_SUBNET router_relation ON router_relation.portId=router_port.id),
 vl AS (SELECT DISTINCT vm_relation.subnetId AS subnet_ref,vm_relation.id AS link_id,vm_relation.portId AS port_ref,vm_port.id AS port_id,
 vm_port.devId AS vm_ref,vm_port.logicalRegionName AS region,v.id AS vm_id,v.name AS vm_name
 FROM R_PORT_IN_SUBNET vm_relation LEFT JOIN CLOUD_PORT vm_port ON vm_port.id=vm_relation.portId
 LEFT JOIN CLOUD_VM_NOVA v ON v.resId=vm_port.devId AND v.logicalRegionName=vm_port.logicalRegionName
 WHERE NOT EXISTS (SELECT 1 FROM CLOUD_ROUTER q WHERE q.nativeId=vm_port.devNativeId AND q.logicalRegionName=vm_port.logicalRegionName)),
 h AS (SELECT DISTINCT p.id AS vpc_id,p.name AS vpc_name,p.logicalRegionName AS region_name,
 vr.subnet_ref AS subnet_reference_id,s.id AS subnet_id,s.name AS subnet_name,s.cidr AS subnet_cidr,
 CASE WHEN p.nativeId IS NULL THEN 'unknown_vpc_native' WHEN vr.vpc_id IS NULL THEN 'no_known_subnet' WHEN vr.subnet_ref IS NULL THEN 'unknown_subnet_reference' WHEN s.id IS NULL THEN 'unresolved_subnet' ELSE 'resolved' END AS subnet_link_status,
 CASE WHEN vl.vm_id IS NULL THEN vl.port_ref ELSE NULL END AS vm_port_reference_id,
 vl.vm_ref AS vm_reference_res_id,vl.vm_id,vl.vm_name,
 CASE WHEN vr.subnet_ref IS NULL THEN 'not_evaluable' WHEN vl.link_id IS NULL THEN 'no_known_vm' WHEN vl.port_id IS NULL THEN 'unresolved_port' WHEN vl.vm_ref IS NULL THEN 'unknown_vm_reference' WHEN vl.vm_id IS NULL THEN 'unresolved_vm' ELSE 'resolved' END AS vm_link_status
 FROM p LEFT JOIN vr ON vr.vpc_id=p.id LEFT JOIN CLOUD_SUBNET s ON s.id=vr.subnet_ref AND s.logicalRegionName=p.logicalRegionName
 LEFT JOIN vl ON vl.subnet_ref=vr.subnet_ref AND (vl.region=p.logicalRegionName OR vl.region IS NULL))"""
 total='(SELECT COUNT(*) FROM CLOUD_ROUTER)'
 selected='(SELECT COUNT(*) FROM p)'
 if p['view']=='hierarchy_rows':
  cols=HIERARCHY_COLUMNS
  select=f"SELECT {total} AS catalog_vpc_count,{selected} AS selected_vpc_count,'hierarchy' AS row_kind,"+','.join(cols[3:])+" FROM h"
 else:
  cols=COUNT_COLUMNS
  select=f"""SELECT {total} AS catalog_vpc_count,{selected} AS selected_vpc_count,'parent_count' AS row_kind,vpc_id,vpc_name,region_name,
 COUNT(DISTINCT subnet_reference_id) AS referenced_subnet_count,COUNT(DISTINCT subnet_id) AS resolved_subnet_count,
 COUNT(DISTINCT CASE WHEN subnet_id IS NULL THEN subnet_reference_id END) AS unresolved_subnet_count,
 MAX(CASE WHEN subnet_link_status IN ('unknown_subnet_reference','unknown_vpc_native') THEN 1 ELSE 0 END) AS has_unknown_subnet_link,
 COUNT(DISTINCT vm_id) AS known_vm_count,
 SUM(CASE WHEN vm_link_status IN ('unresolved_port','unknown_vm_reference','unresolved_vm') THEN 1 ELSE 0 END) AS unknown_vm_endpoint_count
 FROM h GROUP BY vpc_id,vpc_name,region_name"""
 sentinel=f"SELECT {total},{selected},'summary_only',"+','.join('NULL' for _ in cols[3:])+" WHERE NOT EXISTS (SELECT 1 FROM p)"
 sql=cte+' '+select+' UNION ALL '+sentinel
 calls=[]
 for resource in RESOURCES:
  endpoint='relations' if resource.startswith('R_') else 'instances'
  call={'method':'GET','url':f'/rest/hackthon/db/{endpoint}/{resource}?pageNo=1&pageSize=1000','autoPagination':True}
  if 'logicalRegionName' in p and resource!='R_PORT_IN_SUBNET':call['condition']={'constraint':[{'simple':{'name':'logicalRegionName','value':p['logicalRegionName'],'operator':'equal'}}]}
  calls.append(call)
 core_bytes=len(json.dumps({'api_call':calls,'sql':sql},ensure_ascii=False,separators=(',',':')).encode('utf-8'))
 return {'family_id':'vpc_hierarchy','view':p['view'],'resources':list(RESOURCES),'api_call':calls,'sql':sql,'output_columns':list(cols),'input_schema':{TABLES[r]:list(SCHEMA[r]) for r in RESOURCES},'requires_prepared_inputs':True,'runtime_adoption':'blocked_until_B_receipt_typed_empty_final_envelope_validation','transport_diagnostic':{'boundary':'expanded api_call+sql as compact ensure_ascii=False UTF-8 JSON','measured_bytes':core_bytes,'candidate_core_limit_bytes':4096,'status':'blocked_core_length' if core_bytes>4096 else 'within_candidate_core_bound','final_B_envelope_validated':False,'handling':'Do not transmit an oversized core or truncate scope/SQL/entities; B may validate a compact or bound-parameter representation and the final official envelope separately.'}}


def state_checked(receipt,resource):
 if receipt.get('ok') is not True or ('success' in receipt and receipt['success'] is not True) or receipt.get('error'):
  raise Unsupported(resource+': failed or contradictory success receipt')
 for key in ('http_status','status_code','httpStatus'):
  if key in receipt and (type(receipt[key]) is not int or not 200<=receipt[key]<300):raise Unsupported(resource+': HTTP success is not proven')


def collect(resource,envelope,expected):
 if not isinstance(envelope,dict) or envelope.get('ok') is not True or not isinstance(envelope.get('request'),dict) or envelope['request'].get('autoPagination') is not True or envelope['request']!=expected:raise Unsupported(resource+': unbound, drifted or failed request receipt')
 state_checked(envelope,resource)
 schema=envelope.get('schema')
 if envelope.get('schema_verified') is not True or not isinstance(schema,list) or any(not isinstance(k,str) for k in schema) or not set(SCHEMA[resource]).issubset(schema):raise Unsupported(resource+': verified declared schema required, including successful empty inputs')
 pages=envelope.get('pages')
 if not isinstance(pages,list) or not pages:raise Unsupported(resource+': missing successful page receipt')
 rows=[];seen=set();total=None;size=None
 for n,page in enumerate(pages,1):
  if not isinstance(page,dict) or page.get('ok') is not True or type(page.get('pageNo')) is not int or page['pageNo']!=n:raise Unsupported(resource+': failed or out-of-order page')
  state_checked(page,resource)
  t,z,np=page.get('totalNum'),page.get('pageSize'),page.get('totalPageNo')
  if type(t)is not int or t<0 or type(z)is not int or z<1 or type(np)is not int:raise Unsupported(resource+': invalid page metadata')
  if total is None:total,size=t,z
  if (total,size)!=(t,z) or (t>0 and np!=(t+z-1)//z) or (t==0 and np not in(0,1)):raise Unsupported(resource+': unstable or inconsistent pagination totals')
  batch=page.get('objList')
  if not isinstance(batch,list) or len(batch)!=min(z,max(t-len(rows),0)) or any(not isinstance(r,dict) for r in batch):raise Unsupported(resource+': missing/truncated/extra page rows')
  for raw in batch:
   if any(k not in raw for k in SCHEMA[resource]):raise Unsupported(resource+': missing required row key')
   row={k:raw[k] for k in SCHEMA[resource]};identity=row['id']
   for key,value in row.items():
    if isinstance(value,str):
     try:value.encode('utf-8')
     except UnicodeEncodeError:raise Unsupported(resource+': surrogate text is not valid UTF-8')
    if key in ('name','cidr') and value is not None and not isinstance(value,str):raise Unsupported(resource+': display fields must be text or NULL')
   if not isinstance(identity,str) or blank(identity) or identity in seen:raise Unsupported(resource+': nonblank unique object id required; duplicate rows cannot hide omissions')
   seen.add(identity)
   for key in ('nativeId','devNativeId','devId','portId','subnetId','resId'):
    if key in row:
     if blank(row[key]):row[key]=None
     elif not isinstance(row[key],str):raise Unsupported(resource+': foreign keys must be strings or unknown')
   if 'logicalRegionName' in row:
    if not isinstance(row['logicalRegionName'],str) or blank(row['logicalRegionName']):raise Unsupported(resource+': unknown region')
    condition=expected.get('condition')
    if condition and row['logicalRegionName']!=condition['constraint'][0]['simple']['value']:raise Unsupported(resource+': wrong-region response')
   rows.append(row)
 if len(rows)!=total or len(pages)!=max(1,(total+size-1)//size):raise Unsupported(resource+': incomplete or extra page collection')
 return rows

def prepare(params,receipts):
 p=params_checked(params);plan=build(p)
 if not isinstance(receipts,dict) or set(receipts)!=set(RESOURCES):raise Unsupported('all five successful resource receipts required')
 tables={r:collect(r,receipts[r],call) for r,call in zip(RESOURCES,plan['api_call'])}
 router_keys={};vm_keys={};ports={r['id']:r for r in tables['PORT']};subnets={r['id']:r for r in tables['SUBNET']}
 for r in tables['ROUTER']:
  if r['nativeId'] is not None:
   key=(r['logicalRegionName'],r['nativeId'])
   if key in router_keys:raise Unsupported('ambiguous region/nativeId VPC directory')
   router_keys[key]=r['id']
 for v in tables['VM_NOVA']:
  if v['resId'] is not None:
   key=(v['logicalRegionName'],v['resId'])
   if key in vm_keys:raise Unsupported('ambiguous region/resId VM directory')
   vm_keys[key]=v['id']
 for port in tables['PORT']:
  if (port['logicalRegionName'],port['devNativeId']) in router_keys and (port['logicalRegionName'],port['devId']) in vm_keys:raise Unsupported('one PORT has conflicting proven router and VM endpoint roles')
 refs=defaultdict(set)
 for rel in tables['R_PORT_IN_SUBNET']:
  port=ports.get(rel['portId']);subnet=subnets.get(rel['subnetId'])
  if port and subnet and port['logicalRegionName']!=subnet['logicalRegionName']:raise Unsupported('cross-region port/subnet edge')
  if port and (port['logicalRegionName'],port['devNativeId']) in router_keys and rel['subnetId'] is not None:refs[rel['subnetId']].add(port['logicalRegionName'])
 if any(len(regions)>1 for regions in refs.values()):raise Unsupported('ambiguous cross-region subnet reference through VPC ports')
 for rel in tables['R_PORT_IN_SUBNET']:
  port=ports.get(rel['portId'])
  if port and rel['subnetId'] in refs and port['logicalRegionName'] not in refs[rel['subnetId']]:raise Unsupported('cross-region VM-side port/subnet reference')
 diagnostics={'preflight_passed':True,'basis':'verified normalized local receipt assertions only; not an independent proof of server truth, atomic snapshot or B trust',
 'vm_unknown_res_id_count':sum(v['resId'] is None for v in tables['VM_NOVA']),
 'unattributed_port_endpoint_count':sum((port['logicalRegionName'],port['devNativeId']) not in router_keys and (port['logicalRegionName'],port['devId']) not in vm_keys for port in tables['PORT']),
 'unattributed_relation_port_count':sum(rel['portId'] not in ports for rel in tables['R_PORT_IN_SUBNET']),
 'unattributed_relation_subnet_count':sum(rel['subnetId'] not in subnets for rel in tables['R_PORT_IN_SUBNET']),
 'unassigned_vm_subnet_links':sum(1 for rel in tables['R_PORT_IN_SUBNET'] if rel['subnetId'] is None and (ports.get(rel['portId'],{}).get('logicalRegionName'),ports.get(rel['portId'],{}).get('devId')) in vm_keys),
 'unattributed_scope_policy':'unattributed fetched endpoints cannot be proved outside selected parents; conservatively block graph completeness even if no hierarchy row reaches them',
 'business_complete':False,'runtime_adoption':'not_verified'}
 return {TABLES[r]:rows for r,rows in tables.items()},diagnostics

def execute_local(params,receipts):
 plan=build(params);tables,diagnostics=prepare(params,receipts);conn=sqlite3.connect(':memory:')
 try:
  for resource in RESOURCES:
   columns=SCHEMA[resource];table=TABLES[resource]
   conn.execute('CREATE TABLE '+table+' ('+','.join('"'+c+'" TEXT' for c in columns)+')')
   conn.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')',[[r[c] for c in columns] for r in tables[table]])
  cur=conn.execute(plan['sql']);columns=[x[0] for x in cur.description]
  if columns!=plan['output_columns']:raise AssertionError('output contract mismatch')
  rows=[dict(zip(columns,row)) for row in cur.fetchall()]
  if params['view']=='hierarchy_rows':partial=any(r['subnet_link_status'] in ('unknown_vpc_native','unknown_subnet_reference','unresolved_subnet') or r['vm_link_status'] in ('unresolved_port','unknown_vm_reference','unresolved_vm') for r in rows)
  else:partial=any((r['unresolved_subnet_count'] or r['has_unknown_subnet_link'] or r['unknown_vm_endpoint_count']) for r in rows)
  diagnostics['known_relationship_graph_complete']=not partial and not any(diagnostics[k] for k in ('unassigned_vm_subnet_links','vm_unknown_res_id_count','unattributed_port_endpoint_count','unattributed_relation_port_count','unattributed_relation_subnet_count'))
  requested_display={'vpc_name':'vpc_id'}
  if params['view']=='hierarchy_rows':requested_display.update({'subnet_name':'subnet_id','subnet_cidr':'subnet_id','vm_name':'vm_id'})
  diagnostics['requested_display_unknown_counts']={key:len({r[identity] for r in rows if r[identity] is not None and blank(r[key])}) for key,identity in requested_display.items()}
  diagnostics['requested_display_values_complete']=not any(diagnostics['requested_display_unknown_counts'].values())
  diagnostics['business_complete']=diagnostics['known_relationship_graph_complete'] and diagnostics['requested_display_values_complete']
  diagnostics['business_complete_scope']='strictly prepared known local graph only; live snapshot, authoritative business semantics, B execution/request trust and final transport remain unverified'
  diagnostics['result_status']='complete_known_local_graph' if diagnostics['business_complete'] else 'partial_local_result_cannot_answer_as_complete'
  return {'columns':columns,'rows':rows,'diagnostics':diagnostics}
 finally:conn.close()
