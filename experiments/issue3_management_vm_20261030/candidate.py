"""Management VM source-field details through documented FK graph; pure stdlib.

Requires prepared tables. No service/model, raw data, matcher or evaluator imports.
"""
from copy import deepcopy
import json
import re
import sqlite3

FAMILY_ID='family_management_vm_details'
VIEW='management_vm_service_flavor_volume_rows'
SCHEMA={
 'VM_NOVA':('id','name','logicalRegionName','management','vdcId','vdcName','privateIps','ipAddress','flavorId'),
 'FLAVOR':('id','name','logicalRegionName','vcpuSize','ramSize','diskSize'),
 'VOLUME':('id','name','logicalRegionName','size'),
 'R_VOLUME_MOUNTON_VM':('id','vmId','volumeId'),
 'S_DeployNode':('id','vmId','hostClass'),
 'S_DeployInstance':('id','deployNodeId','deployComponentId'),
 'S_DeployComponent':('id','serviceId'),
 'S_Service':('id','cloudServiceId'),
 'S_CloudService':('id','name'),
}
OUTPUT=('vm_id','vm_name','logical_region_name','vdc_id','vdc_name','vdc_status',
 'private_ips_raw','vm_ip_address_raw','requested_ip_role','flavor_reference_id','flavor_id','flavor_name',
 'flavor_vcpu_raw','flavor_ram_raw','flavor_disk_raw','flavor_status','services_json','service_status',
 'unknown_service_link_count','mounted_volumes_json','known_size_sum_native_numbers',
 'unknown_size_reference_count','complete_size_sum_native_numbers','mount_status','declared_values_complete')
TABLE='A_MANAGEMENT_VM_DETAILS'
class Unsupported(ValueError):pass

def blank(v):return v is None or (isinstance(v,str) and not v.strip())
def utf8(v):
 try:v.encode('utf-8')
 except UnicodeEncodeError:raise Unsupported('invalid UTF-8 text')
def compact(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def lit(v):return "'"+v.replace("'","''")+"'"
def params_checked(p):
 if type(p)is not dict or set(p)!={'view','logicalRegionName','ip_role','capacity_mode'} or p['view']!=VIEW:raise Unsupported('closed view/explicit region/IP role/capacity mode required')
 region=p['logicalRegionName']
 if type(region)is not str or blank(region) or region!=region.strip() or any(ord(c)<32 or ord(c)==127 for c in region):raise Unsupported('exact nonblank control-free region required')
 utf8(region)
 if p['ip_role'] not in ('both_raw','private_ips_raw','vm_ip_address_raw') or p['capacity_mode']!='per_volume_raw_and_numeric_summary':raise Unsupported('unsupported IP/capacity role')
 return deepcopy(p)

def build(params):
 p=params_checked(params);calls=[]
 for ci in SCHEMA:
  endpoint='relations' if ci.startswith('R_') else 'instances'
  call={'method':'GET','url':f'/rest/hackthon/db/{endpoint}/{ci}?pageNo=1&pageSize=1000','autoPagination':True}
  if ci=='VM_NOVA':call['condition']={'constraint':[{'simple':{'name':'logicalRegionName','value':p['logicalRegionName'],'operator':'equal'}},{'logOp':'and','simple':{'name':'management','value':True,'operator':'equal'}}]}
  calls.append(call)
 sql='SELECT '+','.join(OUTPUT)+' FROM '+TABLE+' WHERE management=1 AND logical_region_name='+lit(p['logicalRegionName'])+' ORDER BY vdc_id IS NULL,vdc_id,vm_id'
 core={'api_call':calls,'sql':sql};size=len(compact(core).encode())
 return {'id':FAMILY_ID,'family_id':FAMILY_ID,'view':VIEW,'resources':list(SCHEMA),'api_call':calls,'sql':sql,'output_columns':list(OUTPUT),
  'requires_prepared_inputs':True,'prepared_schema':{TABLE:list(OUTPUT)+['management']},'source_schema':{k:list(v) for k,v in SCHEMA.items()},
  'transport':{'expanded_core_bytes':size,'local_core_limit_bytes':4096,'status':'within_local_core_bound' if size<=4096 else 'blocked_core_length','final_B_envelope_verified':False},
  'business_authority':'documented deployment association, raw IP roles and source size numbers; no ownership or unit conversion claim'}

def ground(question,p):
 if type(question)is not str or blank(question):raise Unsupported('complete original question required')
 # Only the exact explicit region value is masked; role/value case remains strict.
 value=re.escape(p['logicalRegionName']);quoted='(?:'+ '|'.join(re.escape(a)+value+re.escape(b) for a,b in [('"','"'),("'","'"),('“','”'),('「','」')])+')'
 atom=r'A-Za-z0-9_@./:#%+\-'
 if re.fullmatch('['+atom+']+',p['logicalRegionName']):quoted+='|'+value+r'(?!['+atom+'])'
 role=r'(?:区域|地区|地域|logicalRegionName)\s*(?:为|是|=|:|：)?\s*(?-i:(?:'+quoted+'))'
 matches=list(re.finditer(role,question,re.I))
 if len(matches)!=1:raise Unsupported('missing/repeated/wrong explicit region')
 m=matches[0];text=question[:m.start()]+'<REGION>'+question[m.end():]
 prefix=r'\s*(?:(?:请帮我|请帮忙|帮我|麻烦|烦请|请)\s*)?(?:查询|查看|列出)\s*'
 layout=prefix+r'<REGION>\s*(?:下|内|中)?\s*(?:(?:各|每个|按)\s*VDC\s*(?:的|中|下|分别展示)?\s*)?(?:管理虚拟机|管理VM)\s*(?:的)?\s*(.+?)\s*[。.!！?？]*\s*'
 match=re.fullmatch(layout,text,re.I)
 if not match:raise Unsupported('unsupported scope/resource/clause')
 fields=re.split(r'\s*(?:、|,|，|和|与|及)\s*',match[1])
 aliases={'名称':'name','虚拟机名称':'name','name':'name','IP':'ip','IP地址':'ip','私网IP':'private','原生IP地址':'native',
  '所属云服务':'service','云服务':'service','云服务名称':'service','规格':'flavor','规格名称':'flavor',
  '挂载云硬盘容量':'volume','挂载卷容量':'volume'}
 canonical=[aliases.get(x) for x in fields]
 if len(canonical)!=5 or None in canonical or set('ip' if x in ('private','native') else x for x in canonical)!={'name','ip','service','flavor','volume'}:raise Unsupported('complete unique five-field obligation required; extra or missing obligation rejected')
 ip=next(x for x in canonical if x in ('ip','private','native'))
 expected={'ip':'both_raw','private':'private_ips_raw','native':'vm_ip_address_raw'}[ip]
 if p['ip_role']!=expected:raise Unsupported('explicit IP role mismatch; generic IP requires both raw fields')
 return {'scope':{'logicalRegionName':p['logicalRegionName'],'management':True},'ip_role':expected,'fields':canonical,'aggregation':'per-VM independent collections; no VDC grand sum'}

def prepare_candidate(question,item,params,diagnostics=None):
 try:
  if type(item)is not dict or item.get('id')!=FAMILY_ID or item.get('family_id')!=FAMILY_ID:raise Unsupported('selected family required')
  p=params_checked(params);evidence=ground(question,p);plan=build(p)
 except (ValueError,TypeError) as exc:
  if diagnostics is not None:diagnostics.update(status='unsupported',reason=str(exc))
  return None
 if diagnostics is not None:diagnostics.update(status='materialized_requires_receipts',contract_evidence=evidence)
 return plan

def state_ok(x):
 if type(x)is not dict or x.get('ok')is not True or x.get('error') or ('success'in x and x['success']is not True):raise Unsupported('failed/contradictory receipt')
 for key in ('http_status','httpStatus','status_code','statusCode','http_status_code','httpStatusCode'):
  if key in x and (type(x[key])is not int or not 200<=x[key]<300):raise Unsupported('non-2xx/unknown HTTP status')
 if 'status'in x:
  status=x['status']
  if not ((type(status)is int and 200<=status<300) or (type(status)is str and status in ('ok','success'))):raise Unsupported('unknown/failed receipt status')

def collect(ci,receipt,expected):
 state_ok(receipt)
 if type(receipt.get('request'))is not dict or canonical(receipt['request'])!=canonical(expected):raise Unsupported(ci+': typed request method/endpoint/scope mismatch')
 schema=receipt.get('schema')
 if receipt.get('schema_verified')is not True or type(schema)is not list or any(type(k)is not str for k in schema) or len(schema)!=len(set(schema)) or not set(SCHEMA[ci])<=set(schema):raise Unsupported(ci+': verified schema required even for zero rows')
 pages=receipt.get('pages')
 if type(pages)is not list or not pages:raise Unsupported(ci+': complete page collection required')
 rows=[];seen=set();total=None
 for number,page in enumerate(pages,1):
  state_ok(page);t,z,n=page.get('totalNum'),page.get('pageSize'),page.get('totalPageNo')
  if type(page.get('pageNo'))is not int or page['pageNo']!=number or type(t)is not int or t<0 or type(z)is not int or z!=1000 or type(n)is not int:raise Unsupported(ci+': invalid page metadata')
  if total is None:total=t
  if t!=total or (t>0 and n!=(t+z-1)//z) or (t==0 and n not in (0,1)):raise Unsupported(ci+': changing/invalid pagination totals')
  batch=page.get('objList')
  if type(batch)is not list or len(batch)!=min(z,max(t-len(rows),0)):raise Unsupported(ci+': truncated/extra page rows')
  for raw in batch:
   if type(raw)is not dict or 'id'not in raw:raise Unsupported(ci+': object identity required')
   row={k:raw.get(k) for k in SCHEMA[ci]};identity=row['id']
   if type(identity)is not str or blank(identity) or identity in seen:raise Unsupported(ci+': blank/duplicate identity')
   seen.add(identity)
   for key,value in row.items():
    if ci=='VM_NOVA' and key=='management':
     if type(value)is not bool or value is not True:raise Unsupported('VM management must be native JSON bool true; false/string/numeric is wrong scope')
    elif value is not None and type(value)is not str:raise Unsupported(ci+': native field type mismatch '+key)
    if type(value)is str:utf8(value)
    if key!='id' and blank(value):row[key]=None
   if ci=='VM_NOVA' and row['logicalRegionName']!=expected['condition']['constraint'][0]['simple']['value']:raise Unsupported('VM wrong explicit region')
   rows.append(row)
 if len(rows)!=total or len(pages)!=max(1,(total+999)//1000):raise Unsupported(ci+': incomplete/extra pages')
 return rows

SCALE=12
SIZE=re.compile(r'^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?$')
def size_number(raw):
 if type(raw)is not str or len(raw)>64 or not SIZE.fullmatch(raw):return None
 parts=raw.split('.');return int(parts[0])*10**SCALE+int((parts[1] if len(parts)>1 else '').ljust(SCALE,'0') or '0')
def size_text(value):
 whole,part=divmod(value,10**SCALE);return str(whole)+('.'+str(part).zfill(SCALE).rstrip('0') if part else '')

def prepare(params,receipts):
 p=params_checked(params);plan=build(p)
 if type(receipts)is not dict or set(receipts)!=set(SCHEMA):raise Unsupported('exact resource receipts required')
 data={ci:collect(ci,receipts[ci],call) for ci,call in zip(SCHEMA,plan['api_call'])}
 idx={ci:{r['id']:r for r in rows} for ci,rows in data.items()}
 nodes_by_vm={};instances_by_node={};mounts_by_vm={}
 unknown_node_owners=0
 for n in data['S_DeployNode']:
  if n['vmId']is None:
   unknown_node_owners+=n['hostClass'] not in ('PM','BMS','SDI')
  else:nodes_by_vm.setdefault(n['vmId'],[]).append(n)
 unknown_instance_nodes=sum(i['deployNodeId'] not in idx['S_DeployNode'] for i in data['S_DeployInstance'])
 for i in data['S_DeployInstance']:instances_by_node.setdefault(i['deployNodeId'],[]).append(i)
 unknown_mount_owners=sum(r['vmId']is None for r in data['R_VOLUME_MOUNTON_VM'])
 for r in data['R_VOLUME_MOUNTON_VM']:mounts_by_vm.setdefault(r['vmId'],[]).append(r)
 prepared=[];global_service_unknown=unknown_node_owners+unknown_instance_nodes
 for vm in data['VM_NOVA']:
  f=idx['FLAVOR'].get(vm['flavorId']);fstatus='unknown_reference' if vm['flavorId']is None else 'unresolved_reference' if f is None else 'resolved'
  if f and f['logicalRegionName']!=vm['logicalRegionName']:raise Unsupported('resolved flavor has mismatched/unknown region')
  if f and any(blank(f[k]) for k in ('name','vcpuSize','ramSize','diskSize')):fstatus='resolved_missing_values'
  services={};bad=global_service_unknown
  for node in nodes_by_vm.get(vm['id'],[]):
   if node['hostClass']!='VM':bad+=1
   for ins in instances_by_node.get(node['id'],[]):
    comp=idx['S_DeployComponent'].get(ins['deployComponentId']);srv=idx['S_Service'].get(comp['serviceId']) if comp else None;cloud=idx['S_CloudService'].get(srv['cloudServiceId']) if srv else None
    if cloud:services[cloud['id']]={'service_id':cloud['id'],'service_name':cloud['name']}
    else:bad+=1
  service_complete=bool(services) and bad==0 and all(not blank(s['service_name']) for s in services.values())
  service_status='resolved_in_declared_graph' if service_complete else 'no_known_service' if not services else 'known_services_incomplete'
  links=mounts_by_vm.get(vm['id'],[]);refs={r['volumeId'] for r in links if r['volumeId']is not None};unknown=sum(r['volumeId']is None for r in links);volumes=[];subtotal=0
  for ref in sorted(refs):
   v=idx['VOLUME'].get(ref)
   if v and v['logicalRegionName']!=vm['logicalRegionName']:raise Unsupported('resolved mounted volume has mismatched/unknown region')
   number=size_number(v['size']) if v else None
   if number is None:unknown+=1
   else:subtotal+=number
   volumes.append({'volume_reference_id':ref,'volume_id':v['id'] if v else None,'volume_name':v['name'] if v else None,'size_raw':v['size'] if v else None,'status':'unresolved_reference' if v is None else 'unknown_size' if number is None else 'resolved'})
  complete_size=unknown==0 and unknown_mount_owners==0
  mount_status='complete_numeric_source_fields' if complete_size else 'incomplete_mounts_or_size'
  if not links and complete_size:mount_status='no_recorded_mounts_in_snapshot'
  vdc_status='present_source_identity_and_name' if vm['vdcId']is not None and vm['vdcName']is not None else 'unknown_source_VDC'
  ip_fields=('privateIps','ipAddress') if p['ip_role']=='both_raw' else ('privateIps',) if p['ip_role']=='private_ips_raw' else ('ipAddress',)
  values_complete=bool(vm['name']) and vdc_status=='present_source_identity_and_name' and all(not blank(vm[k]) for k in ip_fields) and fstatus=='resolved' and service_complete and complete_size and all(v['volume_name']is not None for v in volumes)
  prepared.append(dict(zip(OUTPUT,[vm['id'],vm['name'],vm['logicalRegionName'],vm['vdcId'],vm['vdcName'],vdc_status,vm['privateIps'],vm['ipAddress'],p['ip_role'],vm['flavorId'],f['id'] if f else None,f['name'] if f else None,f['vcpuSize'] if f else None,f['ramSize'] if f else None,f['diskSize'] if f else None,fstatus,compact([services[k] for k in sorted(services)]),service_status,bad,compact(volumes),size_text(subtotal),unknown,size_text(subtotal) if complete_size else None,mount_status,int(values_complete)]),management=1))
 diag={'selected_VM_count':len(prepared),'unknown_VDC_count':sum(r['vdc_status']=='unknown_source_VDC' for r in prepared),'unknown_global_service_owner_nodes':unknown_node_owners,'unresolved_global_instance_nodes':unknown_instance_nodes,'unknown_global_mount_owners':unknown_mount_owners,'requested_values_complete_in_declared_snapshot':all(r['declared_values_complete'] for r in prepared),'empty_parent_scope':not prepared,'full_answer_certified':False,'unit_policy':'source native size numbers only; physical capacity unit/conversion unverified','service_policy':'documented deployment graph membership only; no broader service ownership claim','IP_policy':'raw native fields, no tokenization/substitution','receipt_trust':'B normalized complete request/schema/page assertions; not an authenticator or live atomic snapshot proof'}
 return {TABLE:prepared},diag

preflight=prepare

def execute_local(params,receipts):
 plan=build(params);tables,diagnostics=prepare(params,receipts);columns=list(OUTPUT)+['management'];conn=sqlite3.connect(':memory:')
 try:
  ints={'management','declared_values_complete','unknown_service_link_count','unknown_size_reference_count'}
  conn.execute('CREATE TABLE '+TABLE+' ('+','.join('"'+c+'" '+('INTEGER' if c in ints else 'TEXT') for c in columns)+')')
  conn.executemany('INSERT INTO '+TABLE+' VALUES ('+','.join('?' for c in columns)+')',[[r[c] for c in columns] for r in tables[TABLE]])
  cur=conn.execute(plan['sql']);names=[c[0] for c in cur.description]
  if names!=list(OUTPUT):raise AssertionError('output schema drift')
  return {'columns':names,'rows':[dict(zip(names,r)) for r in cur.fetchall()],'diagnostics':diagnostics}
 finally:conn.close()
