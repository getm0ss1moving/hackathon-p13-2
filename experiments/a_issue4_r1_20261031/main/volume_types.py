"""Isolated VOLUME count+type contract. No case-ID routing, IO or service calls.

Human-readable types are supported only for a proven zero matching population.
Nonempty native volumeTypeId grouping is a separate explicitly named capability.
"""
from copy import deepcopy
import json
import re
import sqlite3

FAMILY_ID='family_volume_status_type_counts'
TABLE='A_VOLUME_STATUS_TYPE_COUNTS'
MODES=('human_type_names','native_type_references')
class Unsupported(ValueError):pass

def blank(v):return v is None or (type(v)is str and not v.strip())
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def literal(v):return "'"+v.replace("'","''")+"'"
def checked(params):
 if type(params)is not dict or set(params)!={'view','filters'} or params['view']not in MODES:raise Unsupported('closed view+filters parameters required')
 filters=params['filters']
 if type(filters)is not dict or 'status'not in filters or set(filters)-{'status','logicalRegionName'}:raise Unsupported('explicit native status; optional explicit region only')
 for value in filters.values():
  if type(value)is not str or blank(value) or value!=value.strip() or any(ord(c)<32 or ord(c)==127 for c in value):raise Unsupported('exact nonblank native text filter required')
  try:value.encode('utf-8')
  except UnicodeEncodeError:raise Unsupported('invalid UTF8 filter')
 return deepcopy(params)

def build(params):
 p=checked(params);f=p['filters'];columns=['id','status','volumeTypeId']+(['logicalRegionName'] if 'logicalRegionName'in f else [])
 constraints=[{'simple':{'name':k,'value':v,'operator':'equal'},**({'logOp':'and'} if i else {})} for i,(k,v) in enumerate(f.items())]
 call={'method':'GET','url':'/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=1000','autoPagination':True,'condition':{'constraint':constraints}}
 where=' AND '.join(k+'='+literal(v) for k,v in f.items())
 if p['view']=='human_type_names':
  sql="SELECT COUNT(*) AS total_count,CASE WHEN COUNT(*)=0 THEN '[]' END AS type_names_json,CASE WHEN COUNT(*)=0 THEN 1 ELSE 0 END AS type_names_complete FROM "+TABLE+' WHERE '+where
  output=['total_count','type_names_json','type_names_complete']
 else:
  base=' FROM '+TABLE+' WHERE '+where
  sql="SELECT 'total' AS row_kind,NULL AS type_reference_id,COUNT(*) AS volume_count FROM "+TABLE+' WHERE '+where+" UNION ALL SELECT CASE WHEN volumeTypeId IS NULL THEN 'unknown_type_reference' ELSE 'type_reference' END,volumeTypeId,COUNT(*)"+base+' GROUP BY volumeTypeId'
  output=['row_kind','type_reference_id','volume_count']
 core_bytes=len(canonical({'api_call':call,'sql':sql}).encode('utf-8'))
 if core_bytes>4096:raise Unsupported('expanded_API_SQL_exceeds_local_core_bound_no_truncation')
 return {'id':FAMILY_ID,'family_id':FAMILY_ID,'name':'volume_count_and_explicit_type_representation','resources':['VOLUME'],'api_call':call,'sql':sql,'output_columns':output,'requires_prepared_inputs':True,'source_schema':{'VOLUME':columns},'prepared_schema':{TABLE:columns},'type_policy':'names complete only if proven empty; no VOLUME_TYPE request, N/A substitution or ID-as-name','default_enabled':False,'expanded_core_bytes':core_bytes,'final_B_envelope_verified':False}

def _value(value):
 atom=r'A-Za-z0-9_@./:#%+\-';parts=[re.escape(a+value+b) for a,b in [('"','"'),("'","'"),('“','”'),('「','」')] if a not in value and b not in value]
 if re.fullmatch('['+atom+']+',value):parts.append(re.escape(value)+r'(?!['+atom+'])')
 return '(?-i:(?:'+'|'.join(parts)+'))'

def ground(question,p):
 if type(question)is not str or not question.strip():raise Unsupported('full question required')
 text=question.strip();f=p['filters']
 for key in ['logicalRegionName','status']:
  if key not in f:continue
  role=r'(?:logicalRegionName|区域|地区|地域)' if key=='logicalRegionName' else r'(?:status|状态)'
  pattern=role+r'\s*(?:为|是|=|:|：)?\s*'+_value(f[key])
  matches=list(re.finditer(pattern,text,re.I))
  if not matches and key=='status' and f[key]=='error':matches=list(re.finditer(r'(?:异常|错误)状态',text))
  if len(matches)!=1:raise Unsupported('missing/repeated/wrong original filter '+key)
  m=matches[0];text=text[:m.start()]+('<REGION>' if key=='logicalRegionName' else '<STATUS>')+text[m.end():]
 prefix=r'\s*(?:(?:请帮我|请|麻烦|帮我)\s*)?(?:(?:查询|统计|查看)\s*)?'
 scope=r'(?:<REGION>\s*(?:下|中|内)?\s*)?' if 'logicalRegionName'in f else ''
 head=prefix+scope+r'(?:当前\s*)?(?:处于\s*)?<STATUS>\s*(?:的)?\s*(?:云硬盘|VOLUME)\s*'
 count=r'(?:有多少(?:块)?|总数|数量)\s*'
 join=r'\s*(?:[,，]|及|并|和)\s*'
 tail=(r'(?:分别)?\s*(?:是什么类型|是哪些类型|类型名称|类型列表)' if p['view']=='human_type_names' else r'(?:按)?\s*(?:原生类型标识|类型ID|volumeTypeId)\s*(?:分别统计数量|数量分布|分组计数)')
 if not re.fullmatch(head+count+join+tail+r'\s*[。.!！?？]*',text,re.I):raise Unsupported('type representation/extra/missing obligation not supported')
 return {'view':p['view'],'filters':deepcopy(f),'obligations':['total count','declared type representation'],'original_scope_preserved':True}

def prepare_candidate(question,item,params,diagnostics=None):
 try:
  if type(item)is not dict or item.get('id')!=FAMILY_ID or item.get('family_id')!=FAMILY_ID:raise Unsupported('selected family required')
  p=checked(params);evidence=ground(question,p);plan=build(p)
 except (ValueError,TypeError) as exc:
  if diagnostics is not None:diagnostics.update(status='unsupported',reason=str(exc))
  return None
 if diagnostics is not None:diagnostics.update(status='conditional_preflight_required',contract_evidence=evidence)
 return plan

def state_ok(x):
 if type(x)is not dict or x.get('ok')is not True or x.get('error') or ('success'in x and x['success']is not True):raise Unsupported('unsuccessful receipt')
 for k in ('http_status','httpStatus','status_code','statusCode','http_status_code','httpStatusCode'):
  if k in x and (type(x[k])is not int or not 200<=x[k]<300):raise Unsupported('HTTP failure or unknown status')
 if 'status'in x and not ((type(x['status'])is int and 200<=x['status']<300) or type(x['status'])is str and x['status']in ('ok','success')):raise Unsupported('unknown/failed receipt state')

def preflight(params,receipt):
 p=checked(params);plan=build(p);state_ok(receipt)
 if type(receipt.get('request'))is not dict or canonical(receipt['request'])!=canonical(plan['api_call']):raise Unsupported('typed request binding mismatch')
 required=plan['source_schema']['VOLUME'];schema=receipt.get('schema')
 if receipt.get('schema_verified')is not True or type(schema)is not list or any(type(k)is not str for k in schema) or len(schema)!=len(set(schema)) or not set(required)<=set(schema):raise Unsupported('trusted schema required including for empty data')
 pages=receipt.get('pages')
 if type(pages)is not list or not pages:raise Unsupported('complete pages required')
 rows=[];seen=set();total=None
 for page_no,page in enumerate(pages,1):
  state_ok(page);t,z,n=page.get('totalNum'),page.get('pageSize'),page.get('totalPageNo')
  if type(page.get('pageNo'))is not int or page['pageNo']!=page_no or type(t)is not int or t<0 or type(z)is not int or z!=1000 or type(n)is not int:raise Unsupported('invalid page metadata')
  if total is None:total=t
  if t!=total or (t>0 and n!=(t+999)//1000) or (t==0 and n not in (0,1)):raise Unsupported('inconsistent totals')
  batch=page.get('objList')
  if type(batch)is not list or len(batch)!=min(1000,max(t-len(rows),0)):raise Unsupported('truncated/extra rows')
  for raw in batch:
   if type(raw)is not dict or 'id'not in raw or any(k not in raw for k in p['filters']):raise Unsupported('required row identity/filter key missing')
   row={k:raw.get(k) for k in required};identity=row['id']
   if type(identity)is not str or blank(identity) or identity in seen:raise Unsupported('blank/duplicate identity')
   seen.add(identity)
   for key,value in row.items():
    if value is not None and type(value)is not str:raise Unsupported('native text field type mismatch')
    if type(value)is str:
     try:value.encode('utf-8')
     except UnicodeEncodeError:raise Unsupported('invalid UTF8 row')
   if any(row[k]!=v for k,v in p['filters'].items()):raise Unsupported('response wrong explicit status/region')
   if blank(row['volumeTypeId']):row['volumeTypeId']=None
   rows.append(row)
 if len(rows)!=total or len(pages)!=max(1,(total+999)//1000):raise Unsupported('incomplete/extra pages')
 if p['view']=='human_type_names' and rows:raise Unsupported('authoritative_type_name_catalog_required_for_nonempty_population')
 unknown=sum(r['volumeTypeId']is None for r in rows)
 return {TABLE:rows},{'matching_volume_count':len(rows),'unknown_native_type_reference_count':unknown,'human_type_names_complete':len(rows)==0,'native_type_reference_values_complete':unknown==0,'empty_population_proven_by_complete_bound_receipt':len(rows)==0,'receipt_trust':'trusted B assertions, not authentication/live snapshot proof','catalog_supported':False}

def execute_local(params,receipt):
 plan=build(params);tables,diagnostic=preflight(params,receipt);cols=plan['prepared_schema'][TABLE];conn=sqlite3.connect(':memory:')
 try:
  conn.execute('CREATE TABLE '+TABLE+' ('+','.join('"'+c+'" TEXT' for c in cols)+')')
  conn.executemany('INSERT INTO '+TABLE+' VALUES ('+','.join('?'for c in cols)+')',[[r[c] for c in cols] for r in tables[TABLE]])
  cur=conn.execute(plan['sql']);names=[c[0] for c in cur.description]
  if names!=plan['output_columns']:raise AssertionError('column drift')
  return {'columns':names,'rows':[dict(zip(names,row)) for row in cur.fetchall()],'diagnostics':diagnostic}
 finally:conn.close()

def self_test(output):
 from pathlib import Path
 checks=[]
 def check(name,v):checks.append({'id':name,'passed':bool(v)})
 p={'view':'human_type_names','filters':{'status':'error'}};item={'id':FAMILY_ID,'family_id':FAMILY_ID};q='当前处于异常状态的云硬盘有多少块，分别是什么类型'
 def receipt(rows,p=p):return {'ok':True,'request':build(p)['api_call'],'schema_verified':True,'schema':build(p)['source_schema']['VOLUME'],'pages':[{'ok':True,'pageNo':1,'pageSize':1000,'totalNum':len(rows),'totalPageNo':int(bool(rows)),'objList':deepcopy(rows)}]}
 def reject(name,call):
  try:call()
  except (ValueError,TypeError):check(name,True)
  else:check(name,False)
 check('full_name_obligations_prepare',prepare_candidate(q,item,p)is not None)
 empty=execute_local(p,receipt([]));check('zero_plus_empty_type_names',empty['rows']==[{'total_count':0,'type_names_json':'[]','type_names_complete':1}])
 check('no_type_catalog_request',build(p)['resources']==['VOLUME'] and 'VOLUME_TYPE'not in build(p)['api_call']['url'])
 reject('nonempty_names_blocked',lambda:execute_local(p,receipt([{'id':'v-a','status':'error','volumeTypeId':'t-a'}])))
 conn=sqlite3.connect(':memory:');conn.execute('CREATE TABLE '+TABLE+' (id TEXT,status TEXT,volumeTypeId TEXT)');conn.execute('INSERT INTO '+TABLE+' VALUES (?,?,?)',('v-a','error','t-a'));check('SQL_defense_nonempty_never_fake_empty_names',conn.execute(build(p)['sql']).fetchone()==(1,None,0));conn.close()
 refs={'view':'native_type_references','filters':{'status':'error'}};qr='查询status="error"的云硬盘总数及按原生类型标识分别统计数量'
 check('explicit_native_reference_prepare',prepare_candidate(qr,item,refs)is not None)
 check('names_not_satisfied_by_ID_mode',prepare_candidate(q,item,refs)is None)
 data=[{'id':'v-a','status':'error','volumeTypeId':'t-a'},{'id':'v-b','status':'error','volumeTypeId':'t-a'},{'id':'v-c','status':'error','volumeTypeId':'t-b'},{'id':'v-d','status':'error'}]
 result=execute_local(refs,receipt(data,refs));groups={r['type_reference_id']:r['volume_count'] for r in result['rows'] if r['row_kind']!='total'}
 check('independent_total_and_type_groups',result['rows'][0]['volume_count']==4 and groups=={'t-a':2,'t-b':1,None:1})
 check('unknown_type_not_NA_name',result['diagnostics']['unknown_native_type_reference_count']==1 and any(r['row_kind']=='unknown_type_reference' for r in result['rows']))
 check('nonempty_ID_mode_not_human_names_complete',result['diagnostics']['human_type_names_complete']is False)
 check('unscoped_has_no_region_default','logicalRegionName'not in canonical(build(p)['api_call']))
 scoped={'view':'human_type_names','filters':{'status':'error','logicalRegionName':'geo-cedar'}};qs='查询区域“geo-cedar”下status="error"的云硬盘总数及类型名称'
 check('explicit_region_prepare',prepare_candidate(qs,item,scoped)is not None)
 for label,question,params in [('wrong_region',qs.replace('geo-cedar','geo-other'),scoped),('wrong_case',qs.replace('geo-cedar','Geo-cedar'),scoped),('extra_AZ',q+'且可用区zone-other',p),('extra_resource',q+'及虚拟机数量',p),('extra_mutation',q+'并删除这些卷',p),('wrong_status',q,{'view':'human_type_names','filters':{'status':'stopped'}})]:check(label,prepare_candidate(question,item,params)is None)
 for label,mutate in [('missing_schema',lambda r:r.pop('schema_verified')),('failure',lambda r:r.update(ok=False)),('HTTP_contradiction',lambda r:r.update(http_status=503)),('page_failure',lambda r:r['pages'][0].update(status_code=503)),('truncated',lambda r:r['pages'][0].update(totalNum=1)),('extra_page',lambda r:r['pages'].append(deepcopy(r['pages'][0]))),('request_drift',lambda r:r['request']['condition']['constraint'][0]['simple'].update(value='stopped'))]:
  r=receipt([]);mutate(r);reject(label,lambda r=r:execute_local(p,r))
 for label,rows in [('duplicate',[data[0],data[0]]),('wrong_status',[{**data[0],'status':'stopped'}]),('nontext_type',[{**data[0],'volumeTypeId':True}]),('missing_id',[{'status':'error','volumeTypeId':'t-a'}])]:reject(label,lambda rows=rows:execute_local(refs,receipt(rows,refs)))
 r=receipt([{**data[0],'logicalRegionName':'geo-other'}],scoped);reject('wrong_region_receipt',lambda:execute_local(scoped,r))
 r=receipt(data,refs);before=deepcopy((refs,r));execute_local(refs,r);check('no_input_mutation',(refs,r)==before)
 reject('long_scope_not_truncated',lambda:build({'view':'human_type_names','filters':{'status':'error','logicalRegionName':'岭'*2000}}))
 quoted={'view':'human_type_names','filters':{'status':"error'quote"}};check('SQL_literal_escaped',"error''quote"in build(quoted)['sql'])
 report={'status':'PASS'if all(c['passed']for c in checks)else'FAIL','checks':len(checks),'passed':sum(c['passed']for c in checks),'failed':[c for c in checks if not c['passed']],'checks_detail':checks,'synthetic_only':True,'model_calls':0,'business_API_calls':0,'source_records_executed':False,'default_enabled':False,'runtime_N_delta':0}
 Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(canonical({k:v for k,v in report.items()if k!='checks_detail'}))
 if report['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--self-test',type=str,required=True);self_test(parser.parse_args().self_test)
