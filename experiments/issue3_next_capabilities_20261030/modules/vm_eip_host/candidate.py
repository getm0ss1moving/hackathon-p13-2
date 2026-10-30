"""Tenant VM native attributes or known EIP-port links; never full EIP authority."""
import json
import sqlite3

VIEWS=('native_ip_host_rows','known_port_eip_host_rows')
BASE_VM=('id','name','tenantName','logicalRegionName','privateIps','floatingIp','hostId')
BASE_COLUMNS=('vm_id','vm_name','logical_region_name','private_ips_raw','native_floating_ip_raw','host_reference_id','host_id','host_name','host_ip','host_link_status','native_ip_status')
PORT_COLUMNS=BASE_COLUMNS+('vm_reference_res_id','binding_port_id','eip_id','eip_address','eip_internal_role_raw','eip_link_status')
class Unsupported(ValueError):pass

def blank(value):return value is None or (isinstance(value,str) and not value.strip())
def utf8(value):
 try:value.encode('utf-8')
 except UnicodeEncodeError:raise Unsupported('surrogate text is not valid UTF-8')
def literal(value):return "'"+value.replace("'","''")+"'"
def check_params(params):
 if not isinstance(params,dict) or not {'view','tenantName'}.issubset(params) or set(params)-{'view','tenantName','logicalRegionName'}:raise Unsupported('closed view+tenantName parameters; optional explicit logicalRegionName only')
 if params['view'] not in VIEWS:raise Unsupported('unknown view')
 for key,value in params.items():
  if not isinstance(value,str) or blank(value) or any(ord(c)<32 for c in value):raise Unsupported('nonblank exact text parameters required; no default region')
  utf8(value)
 return dict(params)

def schema_for(view):
 schema={'VM_NOVA':BASE_VM,'HOST':('id','name','ipAddress','logicalRegionName')}
 if view==VIEWS[1]:schema.update(VM_NOVA=BASE_VM+('resId',),PORT=('id','devId','logicalRegionName'),FLOATING_IPS=('id','portId','floatingIpAddress','isInternal','logicalRegionName'))
 return schema

def build(params):
 cfg=check_params(params);port_view=cfg['view']==VIEWS[1];schema=schema_for(cfg['view']);calls=[]
 for resource in schema:
  constraints=[]
  if resource=='VM_NOVA' and not port_view:constraints.append({'simple':{'name':'tenantName','value':cfg['tenantName'],'operator':'equal'}})
  if 'logicalRegionName' in cfg:constraints.append({'simple':{'name':'logicalRegionName','value':cfg['logicalRegionName'],'operator':'equal'}})
  if len(constraints)>1:constraints[1]['logOp']='and'
  call={'method':'GET','url':f'/rest/hackthon/db/instances/{resource}?pageNo=1&pageSize=1000','autoPagination':True}
  if constraints:call['condition']={'constraint':constraints}
  calls.append(call)
 where='v.tenantName='+literal(cfg['tenantName'])
 if 'logicalRegionName' in cfg:where+=' AND v.logicalRegionName='+literal(cfg['logicalRegionName'])
 common="""v.id AS vm_id,v.name AS vm_name,v.logicalRegionName AS logical_region_name,v.privateIps AS private_ips_raw,v.floatingIp AS native_floating_ip_raw,
 v.hostId AS host_reference_id,h.id AS host_id,h.name AS host_name,h.ipAddress AS host_ip,
 CASE WHEN v.hostId IS NULL THEN 'unknown_host_reference' WHEN h.id IS NULL THEN 'unresolved_host_reference' ELSE 'resolved' END AS host_link_status,
 CASE WHEN v.floatingIp IS NULL THEN 'null_native_attribute' ELSE 'raw_native_attribute_only' END AS native_ip_status"""
 joins=' FROM CLOUD_VM_NOVA v LEFT JOIN CLOUD_HOST h ON h.id=v.hostId AND h.logicalRegionName=v.logicalRegionName'
 prefix=''
 if port_view:
  prefix='WITH links AS (SELECT p.devId,p.logicalRegionName,p.id AS port_id,e.id AS eip_id,e.floatingIpAddress,e.isInternal FROM CLOUD_PORT p JOIN CLOUD_FLOATING_IPS e ON e.portId=p.id AND e.logicalRegionName=p.logicalRegionName) '
  common+=",v.resId AS vm_reference_res_id,l.port_id AS binding_port_id,l.eip_id,l.floatingIpAddress AS eip_address,l.isInternal AS eip_internal_role_raw,CASE WHEN v.resId IS NULL THEN 'unknown_vm_endpoint' WHEN l.eip_id IS NULL THEN 'no_known_binding' ELSE 'known_port_link_only' END AS eip_link_status"
  joins+=' LEFT JOIN links l ON l.devId=v.resId AND l.logicalRegionName=v.logicalRegionName'
 sql=prefix+'SELECT '+common+joins+' WHERE '+where+' ORDER BY v.id'+(',l.eip_id' if port_view else '')
 core=len(json.dumps({'api_call':calls,'sql':sql},ensure_ascii=False,separators=(',',':')).encode())
 return {'family_id':'tenant_vm_ip_eip_host','view':cfg['view'],'resources':list(schema),'api_call':calls,'sql':sql,'output_columns':list(PORT_COLUMNS if port_view else BASE_COLUMNS),'input_schema':{'CLOUD_'+k:list(v) for k,v in schema.items()},'requires_prepared_inputs':True,'full_eip_binding_status':'unsupported_authority_and_coverage','transport_diagnostic':{'boundary':'expanded api_call+sql compact ensure_ascii=False UTF-8 JSON','measured_bytes':core,'candidate_core_limit_bytes':4096,'status':'blocked_core_length' if core>4096 else 'within_candidate_core_bound','final_B_envelope_validated':False,'handling':'No truncation; B must block oversized core or separately validate compact/bound encoding and final envelope.'}}

def check_state(receipt,resource):
 if receipt.get('ok') is not True or ('success'in receipt and receipt['success'] is not True) or receipt.get('error'):raise Unsupported(resource+': failed or contradictory success receipt')
 for key in ('http_status','httpStatus','status_code'):
  if key in receipt and (type(receipt[key])is not int or not 200<=receipt[key]<300):raise Unsupported(resource+': HTTP success not proven')

def collect(resource,envelope,expected,columns):
 if not isinstance(envelope,dict):raise Unsupported(resource+': receipt object required')
 check_state(envelope,resource)
 request=envelope.get('request');schema=envelope.get('schema')
 if not isinstance(request,dict) or request.get('autoPagination')is not True or request!=expected:raise Unsupported(resource+': request method/resource/scope binding drift')
 if envelope.get('schema_verified')is not True or not isinstance(schema,list) or any(not isinstance(k,str) for k in schema) or not set(columns).issubset(schema):raise Unsupported(resource+': verified declared schema required, even when empty')
 pages=envelope.get('pages')
 if not isinstance(pages,list) or not pages:raise Unsupported(resource+': missing pages')
 rows=[];seen=set();total=None;size=None
 for n,page in enumerate(pages,1):
  if not isinstance(page,dict):raise Unsupported(resource+': page object required')
  check_state(page,resource)
  t,z,np=page.get('totalNum'),page.get('pageSize'),page.get('totalPageNo')
  if type(page.get('pageNo'))is not int or page['pageNo']!=n or type(t)is not int or t<0 or type(z)is not int or z<1 or type(np)is not int:raise Unsupported(resource+': invalid page metadata')
  if total is None:total,size=t,z
  if (t,z)!=(total,size) or (t and np!=(t+z-1)//z) or (not t and np not in(0,1)):raise Unsupported(resource+': inconsistent pagination')
  batch=page.get('objList')
  if not isinstance(batch,list) or len(batch)!=min(z,max(t-len(rows),0)):raise Unsupported(resource+': truncated or extra page')
  for raw in batch:
   if not isinstance(raw,dict) or any(k not in raw for k in columns):raise Unsupported(resource+': missing row schema key')
   row={k:raw[k] for k in columns};identity=row['id']
   if not isinstance(identity,str) or blank(identity) or identity in seen:raise Unsupported(resource+': unique nonblank id required; repeated identities may hide missing objects')
   seen.add(identity)
   for key,value in row.items():
    if resource=='FLOATING_IPS' and key=='isInternal' and isinstance(value,bool):row[key]='true' if value else 'false';continue
    if value is not None and not isinstance(value,str):raise Unsupported(resource+': declared fields must be text or NULL (isInternal also bool)')
    if isinstance(value,str):utf8(value)
    if key in ('hostId','resId','devId','portId') and blank(value):row[key]=None
   if not isinstance(row['logicalRegionName'],str) or blank(row['logicalRegionName']):raise Unsupported(resource+': unknown region')
   for predicate in expected.get('condition',{}).get('constraint',[]):
    key,value=predicate['simple']['name'],predicate['simple']['value']
    if row[key]!=value:raise Unsupported(resource+': wrong explicit request scope')
   rows.append(row)
 if len(rows)!=total or len(pages)!=max(1,(total+size-1)//size):raise Unsupported(resource+': incomplete/extra page collection')
 return rows

def prepare(params,receipts):
 cfg=check_params(params);plan=build(cfg);schema=schema_for(cfg['view'])
 if not isinstance(receipts,dict) or set(receipts)!=set(schema):raise Unsupported('exact view resource receipts required')
 tables={r:collect(r,receipts[r],call,schema[r]) for r,call in zip(schema,plan['api_call'])}
 parents=[v for v in tables['VM_NOVA'] if v['tenantName']==cfg['tenantName'] and ('logicalRegionName'not in cfg or v['logicalRegionName']==cfg['logicalRegionName'])]
 hosts={h['id']:h for h in tables['HOST']}
 for v in parents:
  h=hosts.get(v['hostId'])
  if h and h['logicalRegionName']!=v['logicalRegionName']:raise Unsupported('cross-region VM/host endpoint')
 diagnostic={'selected_vm_count':len(parents),'unknown_host_reference_vm_count':sum(v['hostId']is None for v in parents),'unresolved_host_vm_count':sum(v['hostId']is not None and v['hostId']not in hosts for v in parents),'unknown_vm_tenant_count':sum(blank(v['tenantName']) for v in tables['VM_NOVA']),'preflight_passed':True,'receipt_basis':'B trusted normalized request/schema/page assertions only; not server authenticity or live atomic proof','full_eip_binding_status':'unsupported_authority_and_coverage','full_eip_objects_binding_complete':False,'business_complete':False,'business_complete_scope':'Original full EIP-binding obligation is never certified by either declared view.'}
 if cfg['view']==VIEWS[1]:
  vm_keys={}
  for v in tables['VM_NOVA']:
   if v['resId']is not None:
    key=(v['logicalRegionName'],v['resId'])
    if key in vm_keys:raise Unsupported('ambiguous region/resId VM directory, including cross-tenant collisions')
    vm_keys[key]=v['id']
  ports={p['id']:p for p in tables['PORT']}
  for e in tables['FLOATING_IPS']:
   p=ports.get(e['portId'])
   if p and p['logicalRegionName']!=e['logicalRegionName']:raise Unsupported('cross-region EIP/PORT edge')
  diagnostic.update(unknown_vm_res_id_count=sum(v['resId']is None for v in tables['VM_NOVA']),eips_missing_or_dangling_port_count=sum(e['portId']not in ports for e in tables['FLOATING_IPS']),eips_unattributed_vm_count=sum(e['portId']in ports and (ports[e['portId']]['logicalRegionName'],ports[e['portId']]['devId'])not in vm_keys for e in tables['FLOATING_IPS']),ports_unattributed_vm_count=sum((p['logicalRegionName'],p['devId'])not in vm_keys for p in tables['PORT']))
 diagnostic['parent_population_complete_in_declared_snapshot']=diagnostic['unknown_vm_tenant_count']==0
 return {'CLOUD_'+r:rows for r,rows in tables.items()},diagnostic

preflight=prepare

def execute_local(params,receipts):
 plan=build(params);tables,diagnostic=prepare(params,receipts);schema=schema_for(params['view']);conn=sqlite3.connect(':memory:')
 try:
  for r,columns in schema.items():
   conn.execute('CREATE TABLE CLOUD_'+r+' ('+','.join('"'+k+'" TEXT' for k in columns)+')')
   conn.executemany('INSERT INTO CLOUD_'+r+' VALUES ('+','.join('?' for _ in columns)+')',[[row[k] for k in columns] for row in tables['CLOUD_'+r]])
  cur=conn.execute(plan['sql']);columns=[x[0] for x in cur.description]
  if columns!=plan['output_columns']:raise AssertionError('output column contract drift')
  rows=[dict(zip(columns,row)) for row in cur.fetchall()]
  requested={'vm_name':'vm_id','private_ips_raw':'vm_id','native_floating_ip_raw':'vm_id','host_name':'host_id','host_ip':'host_id'}
  if params['view']==VIEWS[1]:requested.update(eip_address='eip_id',eip_internal_role_raw='eip_id')
  diagnostic['requested_display_unknown_counts']={field:len({row[identity] for row in rows if row[identity]is not None and blank(row[field])}) for field,identity in requested.items()}
  diagnostic['requested_display_values_complete']=not any(diagnostic['requested_display_unknown_counts'].values())
  diagnostic['declared_view_values_complete']=diagnostic['parent_population_complete_in_declared_snapshot'] and diagnostic['requested_display_values_complete'] and diagnostic['unknown_host_reference_vm_count']==0 and diagnostic['unresolved_host_vm_count']==0
  if params['view']==VIEWS[1]:diagnostic['declared_view_values_complete']=diagnostic['declared_view_values_complete'] and not any(diagnostic[k] for k in ('unknown_vm_res_id_count','eips_missing_or_dangling_port_count','eips_unattributed_vm_count','ports_unattributed_vm_count'))
  diagnostic['declared_complete_limit']='Only the declared native-attribute/host or known-link local view; never complete EIP-object binding, live snapshot or final B adoption.'
  return {'columns':columns,'rows':rows,'diagnostics':diagnostic}
 finally:conn.close()
