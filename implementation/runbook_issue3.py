"""B接入A已交付的有限组合合同；普通api_call+sql，A源码及官方组件只读。"""
import copy
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import parse_qsl, urlsplit

import requests

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'experiments/b_issue3_runtime_20261031/SOURCE_MANIFEST.json'
_PATHS={
    'network':'experiments/issue3_contracts_20261030/modules/network/candidate.py',
    'capacity':'experiments/issue3_contracts_20261030/modules/capacity/candidate.py',
    'tenant':'experiments/issue3_contracts_20261030/modules/tenant/tenant_details.py',
    'namespace':'experiments/issue3_contracts_20261030/modules/291_R3/materialize.py',
    'vdc_counts':'experiments/issue3_p0_compositions_20261030/modules/vdc_counts/candidate.py',
    'vdc_network':'experiments/issue3_p0_compositions_20261030/modules/vdc_network/candidate.py',
    'tenant_lists':'experiments/issue3_p0_compositions_20261030/modules/tenant_lists/candidate.py'}
_MODULES={}
VERIFIED_PROFILES=('namespace_counts','tenant_lists','vdc_network')
_MINIMUM={
    'network':{'ROUTER','SUBNET','FLOATING_IPS'},
    'capacity':{'VM_NOVA','FLAVOR','VOLUME','GAUSSDB_NODE'},
    'tenant_vm_rank':{'VM_NOVA','VOLUME'},'tenant_volume_rank':{'VOLUME'},
    'namespace_counts':{'GAUSSDB_INSTANCE','MIDDLEWARE','OBS_BUCKET'},
    'vdc_counts':{'VM_NOVA','VOLUME','GAUSSDB_INSTANCE'},
    'vdc_network':{'ROUTER','SUBNET','FLOATING_IPS'},
    'tenant_lists':{'VM_NOVA','SECURITY_GROUP','VOLUME'}}


class Unsupported(ValueError):pass


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def source_files():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    binding=json.loads(MANIFEST.read_text())
    files={str(MANIFEST.relative_to(ROOT)):sha(MANIFEST)}
    for name,value in binding.get('support_files',{}).items():
        if sha(ROOT/name)!=value:raise Unsupported('B_issue3_support_source_drift')
        files[name]=value
    for name,expected in binding['packages'].items():
        path=ROOT/name/'MANIFEST.json'
        if sha(path)!=expected:raise Unsupported('A_package_manifest_drift')
        data=json.loads(path.read_text());files[str(path.relative_to(ROOT))]=expected
        for relative,value in data['files'].items():
            f=(path.parent/relative).resolve()
            if not f.is_relative_to(ROOT) or sha(f)!=value:raise Unsupported('A_contract_source_drift:'+relative)
            files[str(f.relative_to(ROOT))]=value
    return files


def module(kind):
    if kind not in _PATHS:raise Unsupported('unknown_A_contract_module')
    if kind not in _MODULES:
        files=source_files();path=ROOT/_PATHS[kind]
        if _PATHS[kind] not in files:raise Unsupported('A_module_not_in_verified_closure')
        name='_b_issue3_'+kind
        spec=importlib.util.spec_from_file_location(name,path)
        obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj
        spec.loader.exec_module(obj);_MODULES[kind]=obj
    return _MODULES[kind]


_LIT=r'(?:"(?:\\.|[^"\\])*"|“[^”\n]+”|「[^」\n]+」|\x27[^\x27\n]+\x27|[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*)'
_REG=r'(?:区域|地区|logicalRegionName)\s*(?P<region>'+_LIT+r')'
_VDC=r'(?:VDC|vdcName|虚拟数据中心)\s*(?P<vdc>'+_LIT+r')'
_TENANT=r'(?:租户|tenantName)\s*(?P<tenant>'+_LIT+r')'
_ECS=r'(?:ECS|虚拟机|云主机)'
_JOIN=r'\s*(?:、|，|,|和|与|及)\s*'
_PATTERNS={
    'vdc_network':_VDC+r'\s*在\s*'+_REG+r'\s*(?:中|下|内)的?\s*VPC名称'+_JOIN+r'子网CIDR'+_JOIN+r'弹性IP数量',
    'vdc_counts':_REG+r'\s*(?:下|中|内)各\s*VDC的?\s*'+_ECS+r'数量'+_JOIN+r'云硬盘数量'+_JOIN+r'GaussDB实例数量',
    'tenant_lists':_TENANT+r'(?:\s*在\s*'+_REG+r'\s*(?:中|下|内))?的?\s*'+_ECS+r'实例列表'+_JOIN+r'安全组列表'+_JOIN+r'云硬盘列表',
    'network':_VDC+r'\s*在\s*'+_REG+r'\s*(?:中|下|内)各\s*VPC的?\s*子网数量'+_JOIN+r'弹性IP数量',
    'tenant_vm_rank':_REG+r'\s*(?:下|中|内)'+_ECS+r'数量最多的租户\s*[,，]\s*列出该租户下所有\s*'+_ECS+r'的?\s*IP和挂载云硬盘',
    'tenant_volume_rank':_REG+r'\s*(?:下|中|内)云硬盘数量最多的租户\s*[,，]\s*列出该租户的云硬盘名称和容量',
    'capacity':_REG+r'\s*(?:下|中|内)各\s*VDC的?\s*'+_ECS+r'总vCPU核数'+_JOIN+r'云硬盘总容量'+_JOIN+r'GaussDB节点总数',
    'namespace_counts':_REG+r'\s*(?:下|中|内)GaussDB实例数量'+_JOIN+r'中间件实例数量'+_JOIN+r'OBS桶数量'}


def _decode(value):
    if value.startswith('"'):value=json.loads(value)
    elif value[:1] in {'“','「',"'"}:value=value[1:-1]
    if not value or any(ord(c)<32 or 127<=ord(c)<=159 for c in value):raise Unsupported('invalid_original_literal')
    return value


def parse_question(question):
    """有限完整语法而非整题查表；实体是任意原文字面量，额外义务必须另有合同。"""
    matches=[]
    for kind,pattern in _PATTERNS.items():
        m=re.fullmatch(r'\s*(?:(?:请|麻烦)?\s*(?:查询|查看|列出|统计)\s*)?'+pattern+r'\s*[。.!！?？]?\s*',question,re.I)
        if m:
            filters={ {'region':'logicalRegionName','vdc':'vdcName','tenant':'tenantName'}[k]:_decode(v)
                      for k,v in m.groupdict().items() if v is not None}
            matches.append((kind,filters))
    return matches[0] if len(matches)==1 else None


def namespace_template(items):
    """仅重建固定A引用配方并核指纹；旧模板ID不参与问题路由。"""
    path=ROOT/'experiments/issue3_contracts_20261030/rb196.references.json'
    recipe=json.loads(path.read_text());by_id={x['id']:x for x in items}
    aliases=json.loads((MANIFEST.parent/'NAMESPACE_REFERENCE_ALIASES.json').read_text())['aliases']
    def walk(value):
        if isinstance(value,dict) and set(value)=={'$base160'}:
            steps=value['$base160']
            alias=aliases.get(json.dumps(steps,separators=(',',':')))
            if alias:steps=alias['path']
            part=by_id[steps[0]]
            for step in steps[1:]:part=part[step]
            if alias and digest(part)!=alias['value_sha256']:raise Unsupported('namespace_reference_alias_drift')
            return copy.deepcopy(part)
        if isinstance(value,dict):return {k:walk(v) for k,v in value.items()}
        if isinstance(value,list):return [walk(v) for v in value]
        return value
    result=walk(recipe['recipe'])
    raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
    if hashlib.sha256(raw).hexdigest()!=recipe['expected_source_JSON_sha256']:
        raise Unsupported('namespace_template_rebuild_mismatch')
    if not module('namespace')._exact_template_contract(result):raise Unsupported('namespace_template_fingerprint_mismatch')
    return result


def build_plan(kind,filters,items=None):
    if kind in {'tenant_vm_rank','tenant_volume_rank'}:
        params={**filters,'metric':'vm_count' if kind=='tenant_vm_rank' else 'volume_count',
                'tie_policy':'all_ties','unknown_tenant_policy':'exclude_with_diagnostic'}
        mod=module('tenant');plan=mod.build(params)
    elif kind=='namespace_counts':
        params=filters.copy();plan=namespace_template(items)
        plan=copy.deepcopy(plan)
        for call,(_,scoped) in zip(plan['api_call'],module('namespace').API_ROLES):
            if scoped:call['condition']['constraint'][0]['simple']['value']=filters['logicalRegionName']
        plan['output_columns']=module('namespace').RESULT_COLUMNS
    else:
        mod=module(kind)
        if kind=='vdc_network':params={'profile':mod.PROFILE,'filters':filters,'required_filters':list(mod.SCOPE)}
        elif kind=='vdc_counts':params={'profile':mod.PROFILE,'resource_set':list(mod.RESOURCES),'group':'vdcName',
              'layout':'grouped_counts_wide','metric':'count_rows','filters':filters,'required_filters':['logicalRegionName']}
        elif kind=='tenant_lists':params={'profile':mod.PROFILE,'resource_set':list(mod.RESOURCES),'filters':filters,
              'required_filters':[f for f in ['tenantName','logicalRegionName'] if f in filters],'output_columns':list(mod.OUTPUT_COLUMNS)}
        else:params=filters.copy()
        plan=(mod.prepare(params) if hasattr(mod,'prepare') else mod.build(params))
    if plan.get('status')=='blocked_transport_budget':raise Unsupported('A_expanded_transport_budget_blocked')
    if kind in {'vdc_network','tenant_lists'}:
        plan=copy.deepcopy(plan)
        plan['A_source_sql']=plan['sql']
        plan['sql'],plan['output_columns']=_complete_list_layout(kind,plan['sql'])
    core={'api_call':plan['api_call'],'sql':plan['sql']}
    size=len(json.dumps(core,ensure_ascii=False,separators=(',',':')).encode())
    if size>4096:raise Unsupported('B_compact_api_sql_exceeds4096:'+str(size))
    return plan,params,size


def _complete_list_layout(kind,source_sql):
    """将完整独立清单换成明细锚点+首行JSON补充；不删除资源、身份、CIDR或总数。"""
    prefix='WITH b_complete AS ('+source_sql.strip().rstrip(';')+'),'
    if kind=='vdc_network':
        anchor='b_anchor AS (SELECT s.id,n.name AS subnet_name,s.cidr AS subnet_cidr FROM CLOUD_SUBNET s JOIN B_NATIVE_SUBNET_LABEL n ON n.id=s.id),'
        carrier='b_carrier AS (SELECT * FROM b_anchor UNION ALL SELECT NULL,NULL,NULL WHERE NOT EXISTS(SELECT 1 FROM b_anchor) AND EXISTS(SELECT 1 FROM b_complete)) '
        first='a.id IS (SELECT id FROM b_carrier ORDER BY id LIMIT 1)'
        sql=(prefix+anchor+carrier+'SELECT a.subnet_name,a.subnet_cidr,a.id AS subnet_id,CASE WHEN '+first+
             " THEN (SELECT json_group_array(json_object('id',resource_id,'name',resource_name)) FROM b_complete WHERE resource_type='VPC') END AS vpc_list_json,"+
             "(SELECT resource_count FROM b_complete WHERE resource_type='EIP_COUNT') AS scope_eip_count,"+
             "CASE WHEN a.id IS NULL THEN 'summary_only' ELSE 'subnet' END AS row_kind FROM b_carrier a ORDER BY a.id")
        columns=['subnet_name','subnet_cidr','subnet_id','vpc_list_json','scope_eip_count','row_kind']
    else:
        anchor='b_anchor AS (SELECT v.id,v.name AS volume_name,n.size AS volume_size,n.status AS volume_status FROM CLOUD_VOLUME v JOIN B_NATIVE_VOLUME_ATTR n ON n.id=v.id),'
        carrier='b_carrier AS (SELECT * FROM b_anchor UNION ALL SELECT NULL,NULL,NULL,NULL WHERE NOT EXISTS(SELECT 1 FROM b_anchor) AND EXISTS(SELECT 1 FROM b_complete)) '
        first='a.id IS (SELECT id FROM b_carrier ORDER BY id LIMIT 1)'
        ecs="(SELECT json_group_array(json_object('id',resource_id,'name',resource_name)) FROM b_complete WHERE resource_type='VM_NOVA')"
        sg="(SELECT json_group_array(json_object('id',resource_id,'name',resource_name)) FROM b_complete WHERE resource_type='SECURITY_GROUP')"
        sql=(prefix+anchor+carrier+'SELECT a.volume_name,a.volume_size,a.volume_status,a.id AS volume_id,CASE WHEN '+first+
             ' THEN '+ecs+' END AS ecs_list_json,CASE WHEN '+first+' THEN '+sg+' END AS security_group_list_json,'+
             "CASE WHEN a.id IS NULL THEN 'summary_only' ELSE 'volume' END AS row_kind FROM b_carrier a ORDER BY a.id")
        columns=['volume_name','volume_size','volume_status','volume_id','ecs_list_json','security_group_list_json','row_kind']
    return sql,columns


def prepare_selected(question,selected,items,diagnostics,*,enabled_profiles=None):
    parsed=parse_question(question)
    if parsed is None:return None
    kind,filters=parsed
    if enabled_profiles is not None:
        if (not isinstance(enabled_profiles,list) or any(k not in _MINIMUM for k in enabled_profiles)
                or len(set(enabled_profiles))!=len(enabled_profiles)):
            raise Unsupported('invalid_enabled_A_profile_list')
        if kind not in enabled_profiles:return None
    if not _MINIMUM[kind] <= set(selected.get('resources',[])):return None
    plan,params,size=build_plan(kind,filters,items)
    diagnostics.update(issue3_contract={'kind':kind,'parameters':copy.deepcopy(params),
        'api_sql_bytes':size,'formal_depth_policy':'unresolved','business_complete':'pending_native_preflight'},
        parameter_mode='complete_question_rules_A_contract')
    ordinary={'id':selected['id'],'name':selected['name']+' / '+kind,'resources':plan['resources'],
              'api_call':plan['api_call'],'sql':plan['sql'],'_issue3':{'kind':kind,'parameters':params},
              '_expected_result_columns':list(plan['output_columns'])}
    return ordinary


class NativeReader:
    """从真实HTTP取得schema、状态、精确请求及完整分页；不接受模型提供的回执。"""
    def __init__(self,diagnostics,*,session=None,base_url=None,max_http=128,max_records=1000000,seconds=90):
        import runbook_executor as executor
        self.base=(base_url or executor.BASE_URL).rstrip('/')
        target=urlsplit(self.base)
        if target.scheme not in {'http','https'} or target.username or target.password or target.path not in {'','/'}:
            raise Unsupported('unverified_data_service_origin')
        self.session=session or requests.Session();self.owned=session is None
        if self.owned:
            self.session.trust_env=False
            self.session.mount('http://',requests.adapters.HTTPAdapter(max_retries=0))
            self.session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        self.deadline=time.perf_counter()+seconds;self.max_http=max_http;self.max_records=max_records
        self.diag=diagnostics;self.schemas={};self.cache={};self.actual_calls=[];self.total_records=0
        self.diag.update(http_requests=0,steps=[],source_schemas={},sql_executed=False)

    def close(self):
        if self.owned:self.session.close()

    def get(self,url,params=None):
        if self.diag['http_requests']>=self.max_http or time.perf_counter()>=self.deadline:
            raise Unsupported('native_read_budget_exhausted')
        prepared=requests.Request('GET',url,params=params).prepare()
        size=len(('GET '+prepared.path_url+' HTTP/1.1\r\n').encode())
        if size>4096:raise Unsupported('native_request_line_exceeds4096')
        self.diag['http_requests']+=1
        self.diag['max_request_line_bytes']=max(self.diag.get('max_request_line_bytes',0),size)
        response=self.session.get(prepared.url,timeout=min(10,max(.01,self.deadline-time.perf_counter())),allow_redirects=False)
        if response.status_code!=200:raise Unsupported('native_HTTP_'+str(response.status_code))
        body=response.json()
        if not isinstance(body,dict) or body.get('error') or body.get('success') is False:
            raise Unsupported('native_response_failure')
        return body

    def schema(self,ci):
        if ci not in self.schemas:
            payload=self.get(self.base+'/rest/hackthon/db/schema/'+ci)
            columns=payload.get('columns')
            if (payload.get('ci_name')!=ci or not isinstance(columns,list)
                    or len(set(columns))!=len(columns) or not all(isinstance(c,str) and re.fullmatch(r'[A-Za-z_]\w*',c) for c in columns)):
                raise Unsupported('native_schema_invalid:'+ci)
            self.schemas[ci]=columns
            self.diag['source_schemas'][ci]={'endpoint':'/rest/hackthon/db/schema/'+ci,
                'payload_sha256':digest(payload),'columns':columns,'provenance':'actual_HTTP200_schema_response'}
        return self.schemas[ci]

    def fetch(self,call):
        parsed=urlsplit(call.get('url',''));query=parse_qsl(parsed.query,keep_blank_values=True)
        match=re.fullmatch(r'/rest/hackthon/db/(instances|relations)/([A-Za-z_]\w*)',parsed.path)
        if (call.get('method','GET')!='GET' or parsed.scheme or parsed.netloc or parsed.fragment or not match
                or len(dict(query))!=len(query) or set(dict(query))-{'pageNo','pageSize'}
                or dict(query).get('pageNo','1')!='1'):
            raise Unsupported('unverified_native_API_plan')
        size=int(dict(query).get('pageSize','1000'))
        if not 1<=size<=10000:raise Unsupported('unverified_native_page_size')
        ci=match[2];columns=self.schema(ci);condition=call.get('condition',{})
        if not isinstance(condition,dict) or set(condition)-{'constraint'}:raise Unsupported('unverified_native_condition')
        constraints=condition.get('constraint',[])
        if not isinstance(constraints,list):raise Unsupported('unverified_native_condition')
        for entry in constraints:
            simple=entry.get('simple',{}) if isinstance(entry,dict) else {}
            if (entry.get('logOp','and')!='and' or simple.get('name') not in columns
                    or simple.get('operator','equal')!='equal' or type(simple.get('value')) not in {str,int,bool}
                    or '{{' in str(simple.get('value'))):raise Unsupported('unverified_native_scope:'+ci)
        key=digest({'resource':ci,'condition':condition,'pageSize':size})
        if key in self.cache:return self.cache[key]
        pages=[];native=[];rows=[];seen=set();state=None;page=1
        while True:
            params={'pageNo':page,'pageSize':size}
            if condition:params['condition']=json.dumps(condition,ensure_ascii=False,separators=(',',':'))
            body=self.get(self.base+parsed.path,params)
            total,count,current,actual_size=(body.get(k) for k in ['totalNum','totalPageNo','currentPage','pageSize'])
            batch=body.get('objList')
            if (any(type(n) is not int for n in [total,count,current,actual_size]) or total<0 or actual_size!=size
                    or current!=page or count!=(total+size-1)//size or not isinstance(batch,list)
                    or len(batch)!=min(size,max(0,total-(page-1)*size))):
                raise Unsupported('native_incomplete_or_invalid_page:'+ci)
            if state is not None and state!=(total,count):raise Unsupported('native_page_total_drift:'+ci)
            state=(total,count)
            for row in batch:
                if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'].strip() or row['id'] in seen:
                    raise Unsupported('native_duplicate_or_missing_identity:'+ci)
                seen.add(row['id'])
                for entry in constraints:
                    simple=entry['simple']
                    if row.get(simple['name'])!=simple['value']:raise Unsupported('native_wrong_scope_row:'+ci)
            native.append(copy.deepcopy(body))
            normalized=copy.deepcopy(body);normalized.update(ok=True,pageNo=body['currentPage'])
            pages.append(normalized);rows.extend(batch)
            self.total_records+=len(batch)
            if self.total_records>self.max_records:raise Unsupported('native_row_budget_exhausted')
            if page>=max(1,count):break
            page+=1
        if len(rows)!=state[0]:raise Unsupported('native_missing_rows:'+ci)
        snapshot={'ci':ci,'request':copy.deepcopy(call),'columns':columns,'pages':pages,'native_pages':native,
                  'rows':rows,'schema_source':'HTTP200 schema/'+ci+' '+self.diag['source_schemas'][ci]['payload_sha256']}
        self.cache[key]=snapshot;self.actual_calls.append(copy.deepcopy(call))
        self.diag['steps'].append({'ci':ci,'request':copy.deepcopy(call),'pages':len(pages),'rows':len(rows),
            'response_sha256':digest(native),'scope_checked_against_every_row':True})
        return snapshot


def _local_readonly_identity(base_url):
    """本地只读数据服务的PID/启动身份、源代码和启动前数据文件指纹，非caller标签。"""
    target=urlsplit(base_url)
    if target.scheme!='http' or target.hostname not in {'127.0.0.1','localhost'}:
        raise Unsupported('trusted_local_readonly_source_not_available')
    lsof=shutil.which('lsof') or '/usr/sbin/lsof';port=target.port or 80
    pids=subprocess.check_output([lsof,'-nP',f'-iTCP:{port}','-sTCP:LISTEN','-t'],text=True).split()
    if len(set(pids))!=1:raise Unsupported('ambiguous_native_service_process')
    pid=pids[0]
    command=subprocess.check_output(['ps','-p',pid,'-o','command='],text=True).strip()
    start=subprocess.check_output(['ps','-p',pid,'-o','lstart='],text=True).strip()
    elapsed=subprocess.check_output(['ps','-p',pid,'-o','etime='],text=True).strip()
    days,clock=(elapsed.split('-',1) if '-' in elapsed else ('0',elapsed))
    parts=[int(v) for v in clock.split(':')];seconds=int(days)*86400
    for index,value in enumerate(reversed(parts)):seconds+=value*60**index
    started=time.time()-seconds
    cwd_lines=subprocess.check_output([lsof,'-a','-p',pid,'-d','cwd','-Fn'],text=True).splitlines()
    directories=[x[1:] for x in cwd_lines if x.startswith('n')]
    scripts=[x for x in shlex.split(command) if x.endswith('data_server.py')]
    if len(directories)!=1 or len(scripts)!=1:raise Unsupported('unproven_native_server_program')
    script=(Path(directories[0])/scripts[0]).resolve()
    binding=json.loads(MANIFEST.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(script)!=binding['readonly_data_server_sha256'] or script.stat().st_mtime>started+2:
        raise Unsupported('native_server_source_changed_since_start')
    folder=script.parent/'CI+md数据-脱敏-最终-0924'
    files=sorted(folder.glob('*.json'))
    if not files or any(p.stat().st_mtime>started+2 for p in files):
        raise Unsupported('native_data_source_changed_since_server_start')
    version=digest({p.name:sha(p) for p in files})
    return {'pid':pid,'process_started':start,'server_sha256':sha(script),'data_manifest_sha256':version,
            'source_contract':'pinned native data_server.py loads static JSON into private in-memory SQLite; GET-only API'}


def _execute_namespace(plan,items,reader,diagnostics):
    mod=module('namespace');params=plan['_issue3']['parameters'];template=namespace_template(items)
    before=_local_readonly_identity(reader.base)
    snapshot_id='local-readonly-'+digest(before)
    execution_id=digest({'snapshot':snapshot_id,'params':params,'started_monotonic_ns':time.monotonic_ns()})
    global_reads={}
    for ci in mod.FIELDS:
        snap=reader.fetch({'method':'GET','url':f'/rest/hackthon/db/instances/{ci}?pageNo=1&pageSize=10000'})
        request={'method':'GET','ci':ci,'endpoint':'instances','constraints':[]}
        packets=[{'http_status':200,'snapshot_id':snapshot_id,'request_page':i,'body':body,
                  'request':dict(request,pageNo=i,pageSize=body['pageSize'])} for i,body in enumerate(snap['native_pages'],1)]
        global_reads[ci]={'request':request,'schema':snap['columns'],'pages':packets}
    capture={'execution_id':execution_id,'snapshot_id':snapshot_id,'reads':global_reads}
    if before!=_local_readonly_identity(reader.base):raise Unsupported('native_source_process_or_data_drift')
    # 捕获只能由本函数的真实reader产生，模型/参数里不存在capture或callback入口。
    binder=mod.make_region_count_binder(lambda eid:capture if eid==execution_id else None)
    proof={};bound=binder(template,params,execution_id,proof)
    diagnostics['namespace_binding']=proof
    if bound is None:raise Unsupported(proof.get('reason','namespace_binding_rejected'))
    tables={};schemas={};actual_namespace={}
    import runbook_executor as executor
    for call,(ci,_) in zip(bound['api_call'],mod.API_ROLES):
        snap=reader.fetch(call)
        required=list(mod.FIELDS.get(ci,('id',)))
        if not set(required)<=set(snap['columns']):raise Unsupported('namespace_count_schema_missing:'+ci)
        records=[{key:row.get(key) for key in required} for row in snap['rows']]
        if ci in mod.FIELDS:actual_namespace[ci]=records
        table=executor.CI_NAME_MAP[ci];tables[table]=records;schemas[table]=required
    checked={}
    if mod.check_execution_namespace(bound,execution_id,snapshot_id,actual_namespace,checked) is None:
        raise Unsupported(checked.get('reason','namespace_SQL_input_check_failed'))
    diagnostics.update(namespace_execution_check=checked,source_snapshot=before)
    if before!=_local_readonly_identity(reader.base):raise Unsupported('native_source_snapshot_drift')
    return bound['sql'],tables,schemas,True


def execute_plan(plan,items,diagnostics,*,reader=None):
    """真实分页→A预检投影→typed表→原合同SQL。失败不转业务0，不写官方缓存。"""
    kind=plan['_issue3']['kind'];params=plan['_issue3']['parameters']
    owned=reader is None
    reader=reader or NativeReader(diagnostics)
    try:
        complete=True;extension_sources={}
        if kind=='namespace_counts':
            sql,tables,schemas,complete=_execute_namespace(plan,items,reader,diagnostics)
        else:
            mod=module('tenant' if kind.startswith('tenant_') and kind!='tenant_lists' else kind)
            snaps={call['url'].split('?')[0].rsplit('/',1)[-1]:reader.fetch(call) for call in plan['api_call']}
            if kind.startswith('tenant_') and kind!='tenant_lists':declared=mod.SCHEMAS
            elif kind=='capacity':declared=mod.REQUIRED_COLUMNS
            elif kind=='vdc_counts':declared={ci:mod.COLUMNS for ci in mod.RESOURCES}
            elif kind=='tenant_lists':declared=mod.prepare(params)['required_schema']
            else:declared=mod.COLUMNS
            diagnostics['native_field_audit']={ci:{
                'schema_missing_fields':sorted(set(declared[ci])-set(snap['columns'])),
                'per_row_absent_fields':{key:sum(key not in row for row in snap['rows']) for key in declared[ci]
                                        if any(key not in row for row in snap['rows'])},
                'null_or_blank_fields':{key:sum(row.get(key) is None or isinstance(row.get(key),str) and not row[key].strip() for row in snap['rows'])
                                       for key in declared[ci]}}
                for ci,snap in snaps.items()}
            packets={ci:snap['pages'] for ci,snap in snaps.items()}
            if kind=='capacity':
                data={ci:{'status':'ok','schema_source':snap['schema_source'],'columns':snap['columns'],
                          'pages':snap['native_pages']} for ci,snap in snaps.items()}
                validated=mod.validate_pages(data,params)
                projected={ci:[{k:r.get(k) for k in mod.REQUIRED_COLUMNS[ci]} for r in rows] for ci,rows in validated.items()}
                schemas={_table(ci):list(mod.REQUIRED_COLUMNS[ci]) for ci in projected}
                tables={_table(ci):rows for ci,rows in projected.items()}
                diagnostics['projection']={'status':'A_capacity_native_pages_validated','source_units':'unconverted'}
            elif kind=='network':
                projected,proof=mod.preflight(params,packets)
                tables={mod.TABLES[ci]:rows for ci,rows in projected.items()}
                schemas={mod.TABLES[ci]:list(mod.COLUMNS[ci]) for ci in projected}
                complete=proof.get('business_complete') is True;diagnostics['projection']=proof
            else:
                receipts=packets
                if kind=='vdc_counts':
                    receipts={ci:{'resource':ci,'table':mod.TABLES[ci],'request':snap['request'],
                        'columns':snap['columns'],'schema_source':snap['schema_source'],'pages':snap['pages']} for ci,snap in snaps.items()}
                prepared=mod.preflight(params,receipts)
                if prepared.get('status')!='ready_for_typed_sql':
                    diagnostics['projection']=prepared
                    raise Unsupported('A_preflight_blocked:'+str(prepared.get('reason')))
                diagnostics['projection']={k:v for k,v in prepared.items() if k!='tables'}
                raw=prepared['tables']
                if kind in {'tenant_vm_rank','tenant_volume_rank','tenant_lists'}:
                    tables={_table(ci):rows for ci,rows in raw.items()}
                    declared=prepared.get('required_schema') or prepared.get('schemas')
                    schemas={_table(ci):list(declared[ci]) for ci in raw}
                    if kind!='tenant_lists':
                        complete=prepared.get('ranking_population')=='complete_ranked_resource_population' and prepared.get('complete_mount_details') is True
                        diagnostics['ranking_policy']={'tie_policy':'all_ties','unknown_policy':'exclude_with_diagnostic',
                            'population':prepared.get('ranking_population'),'external_business_acceptance':False}
                    else:complete=prepared.get('diagnostics',{}).get('requested_values_complete') is True
                else:
                    tables=raw
                    schemas=(prepared['schema'] if kind=='vdc_network' else
                             {mod.TABLES[ci]:list(mod.COLUMNS) for ci in mod.RESOURCES})
                    if kind=='vdc_network':complete=prepared['diagnostics']['requested_values_complete']
                    else:
                        diagnostics['vdc_identity']='exact_name_buckets_not_authoritative_owner_ids'
                        complete=prepared['diagnostics']['named_vdc_identity_complete']
            sql=plan['sql']
            if kind in {'vdc_network','tenant_lists'}:
                ci='SUBNET' if kind=='vdc_network' else 'VOLUME'
                fields=['id','name'] if kind=='vdc_network' else ['id','size','status']
                table='B_NATIVE_SUBNET_LABEL' if kind=='vdc_network' else 'B_NATIVE_VOLUME_ATTR'
                if not set(fields)<=set(snaps[ci]['columns']):raise Unsupported('native_layout_attribute_schema_unproven:'+ci)
                projected=[]
                for row in snaps[ci]['rows']:
                    if any(row.get(f) is not None and type(row.get(f)) not in {str,int,float} for f in fields):
                        raise Unsupported('native_layout_attribute_nonscalar:'+ci)
                    projected.append({f:row.get(f) for f in fields})
                tables[table]=projected;schemas[table]=fields;extension_sources[table]=ci
                diagnostics['layout_extension']={'source_ci':ci,'columns':fields,
                    'source':'same completed scoped HTTP reads; one-to-one id; separate validated attribute projection',
                    'missing_optional_attributes':{f:sum(f not in r for r in snaps[ci]['rows']) for f in fields},
                    'extra_resource_lists':'all IDs/names retained in first-row JSON; summary carrier when anchor empty'}
        for table,columns in schemas.items():
            ci=extension_sources.get(table) or next((ci for ci in reader.schemas if _table(ci)==table),None)
            if ci is None or not set(columns)<=set(reader.schemas[ci]):
                raise Unsupported('typed_schema_not_proven_by_native_endpoint:'+table)
        result=_typed_sql(sql,tables,schemas)
        if kind=='capacity':
            complete=all(row['unknown_cpu_vm_count']==0 and row['unknown_volume_count']==0 for row in result['rows'])
        if result['columns']!=plan['_expected_result_columns']:raise Unsupported('A_contract_output_schema_drift')
        diagnostics.update(sql_executed=True,business_complete=complete,
            answer_completeness='complete_under_declared_contract' if complete else 'partial_with_explicit_unknowns',
            executed_api_calls=reader.actual_calls,projection_loaded_not_raw=True)
        return {'sql':sql,'result':result,'error':None}
    finally:
        diagnostics['executed_api_calls']=reader.actual_calls
        if owned:reader.close()


def _table(ci):
    import runbook_executor as executor
    if ci not in executor.CI_NAME_MAP:raise Unsupported('unverified_CI_table_mapping:'+ci)
    return executor.CI_NAME_MAP[ci]


def _typed_sql(sql,tables,schemas):
    import runbook_executor as executor
    if set(tables)!=set(schemas):raise Unsupported('projection_schema_table_mismatch')
    with closing(sqlite3.connect(':memory:')) as conn:
        for table,columns in schemas.items():
            if (not re.fullmatch(r'[A-Za-z_]\w*',table) or not columns
                    or any(not re.fullmatch(r'[A-Za-z_]\w*',c) for c in columns)):
                raise Unsupported('unsafe_typed_projection_identifier')
            conn.execute('CREATE TABLE "'+table+'" ('+','.join('"'+c+'" TEXT' for c in columns)+')')
            conn.executemany('INSERT INTO "'+table+'" VALUES ('+','.join('?' for c in columns)+')',
                [[executor._to_sqlite_val(row[c]) for c in columns] for row in tables[table]])
        conn.commit()
        conn.set_authorizer(lambda action,*args:sqlite3.SQLITE_DENY if action not in {
            sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE} else sqlite3.SQLITE_OK)
        cursor=conn.execute(sql);columns=[c[0] for c in cursor.description]
        rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
        return {'columns':columns,'rows':rows,'row_count':len(rows)}
