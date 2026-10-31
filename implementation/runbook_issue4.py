"""A 72e6062网络合同接入：原始分页、独立canonical投影及完整结果守恒。"""
from collections import Counter
from contextlib import closing
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import runbook_copy as copying

ROOT=Path(__file__).resolve().parents[1]
BINDING='experiments/b_issue4_runtime_20261031/SOURCE_MANIFEST.json'
_MODULE=None


def sources():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    binding=json.loads((ROOT/BINDING).read_text());path=ROOT/binding['A_manifest']
    if sha(path)!=binding['A_manifest_sha256']:raise ValueError('issue4_A_manifest_drift')
    manifest=json.loads(path.read_text());files={BINDING:sha(ROOT/BINDING),binding['A_manifest']:sha(path)}
    for record in manifest['files']:
        relative=record['path'];f=ROOT/relative
        if f.is_symlink() or not f.resolve().is_relative_to(ROOT) or sha(f)!=record['sha256'] or f.stat().st_size!=record['bytes']:
            raise ValueError('issue4_A_source_drift:'+relative)
        files[relative]=record['sha256']
    files.update(copying.sources())
    return path.parent,files


def module():
    global _MODULE
    package,_=sources()
    if _MODULE is None:
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(obj);return obj
        policy=load('_B_issue4_main_policy',package/'main/shared_policy.py')
        old=sys.modules.get('shared_policy');sys.modules['shared_policy']=policy
        try:_MODULE=load('_B_issue4_adapters',package/'main/adapters.py')
        finally:
            if old is None:sys.modules.pop('shared_policy',None)
            else:sys.modules['shared_policy']=old
    copying.bind(_MODULE.policy)
    return copying.bind(_MODULE)


def parameters(question):
    from runbook_issue3 import _LIT,_decode
    q=question.strip()
    prefix=r'(?:(?:请)?\s*(?:查询|查看|统计)\s*)?'
    if re.fullmatch(prefix+r'(?:一共|总共)有多少(?:个)?VPC[，,、]\s*VPC下有哪些子网[，,、]\s*子网下有哪些(?:虚拟机|ECS)\s*[。?？]?',q,re.I):
        return 'hierarchy',{'view':'hierarchy_rows'}
    found=re.fullmatch(prefix+r'(?:区域\s*(?P<region>'+_LIT+r')\s*下\s*)?VPC\s*(?P<name>'+_LIT+r')\s*下有多少(?:个)?子网(?:和|及|与)弹性IP\s*[。?？]?',q,re.I)
    if found:
        filters={'name':_decode(found['name'])}
        if found['region'] is not None:filters['logicalRegionName']=_decode(found['region'])
        return 'named_vpc',{'profile':'named_vpc_subnet_eip_counts','filters':filters,
            'required_filters':list(filters),'same_name_policy':'all_matching_parent_ids'}
    return None


def layout(family,params):
    adapter=module();a=adapter.build(family,params);columns=a['output_columns']
    values=','.join('d.'+name for name in columns)
    packed='json_group_array(json_array('+values+'))'
    header="'"+json.dumps(columns,separators=(',',':')).replace("'","''")+"'"
    if family=='hierarchy':
        sql=('WITH b_details AS ('+a['sql']+') SELECT (SELECT COUNT(*) FROM CLOUD_ROUTER) AS total,'+
             header+' AS hierarchy_columns_json,(SELECT '+packed+' FROM b_details d) AS hierarchy_rows_json')
        outputs=['total','hierarchy_columns_json','hierarchy_rows_json']
    else:
        sql=('WITH b_details AS ('+a['sql']+') SELECT COALESCE(SUM(resolved_subnet_count),0) AS subnet_count,'
             'COALESCE(SUM(known_eip_count),0) AS known_eip_count,'
             'COALESCE(SUM(unresolved_subnet_count),0) AS unresolved_subnet_count,'+
             header+' AS parent_columns_json,(SELECT '+packed+' FROM b_details d) AS parent_rows_json FROM b_details')
        outputs=['subnet_count','known_eip_count','unresolved_subnet_count','parent_columns_json','parent_rows_json']
    core={'api_call':a['api_call'],'sql':sql}
    if len(json.dumps(core,ensure_ascii=False,separators=(',',':')).encode())>4096:
        raise ValueError('issue4_B_core_exceeds4096')
    return a,sql,outputs


def prepare(question,item,schemas,*,enabled_families=None):
    if enabled_families is not None and (not isinstance(enabled_families,list)
            or any(not isinstance(f,str) or f not in {'hierarchy','named_vpc'} for f in enabled_families)
            or len(set(enabled_families))!=len(enabled_families)):
        raise ValueError('issue4_invalid_enabled_family_list')
    parsed=parameters(question)
    if parsed is None:return None
    family,params=parsed
    if enabled_families is not None and family not in enabled_families:return None
    # 只有语义和原候选资源均相符才补全组合；不按ID路由。
    if 'ROUTER' not in item.get('resources',[]):return None
    if family=='named_vpc' and 'FLOATING_IPS' not in item.get('resources',[]):return None
    adapter=module();a,sql,outputs=layout(family,params)
    declared=adapter.schemas(family,adapter.core(family),a)
    if any(not set(fields)<=set(schemas.get(ci,[])) for ci,fields in declared.items()):return None
    return dict(item,resources=a['resources'],api_call=a['api_call'],sql=sql,
        _expected_result_columns=outputs,_issue3={'kind':'issue4_'+family,'parameters':params})


def receipt(snapshot,request,policy):
    return {'ok':True,'http_status':200,'request':copy.deepcopy(request),
        'schema_verified':True,'schema_source':snapshot['schema_source'],'schema':snapshot['columns'],
        'pages':[dict(copying.copy_value(page),ok=True,http_status=200,request=policy.page_request(request,i))
                 for i,page in enumerate(snapshot['native_pages'],1)]}


def typed_sql(sql,tables):
    with closing(sqlite3.connect(':memory:')) as conn:
        for name,table in tables.items():
            columns=table['columns'];types=table['types']
            if not re.fullmatch(r'[A-Za-z_]\w*',name) or any(not re.fullmatch(r'[A-Za-z_]\w*',c) or types[c] not in {'TEXT','INTEGER','BLOB'} for c in columns):
                raise ValueError('issue4_invalid_typed_schema')
            conn.execute('CREATE TABLE '+name+' ('+','.join('"'+c+'" '+types[c] for c in columns)+')')
            conn.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for c in columns)+')',[[row[c] for c in columns] for row in table['rows']])
        conn.set_authorizer(lambda action,*args:sqlite3.SQLITE_OK if action in {
            sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE} else sqlite3.SQLITE_DENY)
        cursor=conn.execute(sql);columns=[c[0] for c in cursor.description]
        rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
        return {'columns':columns,'rows':rows,'row_count':len(rows)}


def execute(plan,diagnostics,reader):
    from runbook_issue3 import _local_readonly_identity,digest
    family=plan['_issue3']['kind'].removeprefix('issue4_');params=plan['_issue3']['parameters']
    adapter=module();a,sql,outputs=layout(family,params)
    if plan['sql']!=sql or plan['api_call']!=a['api_call']:raise ValueError('issue4_plan_drift')
    before=_local_readonly_identity(reader.base);receipts={}
    for ci,call in zip(a['receipt_resources'],a['api_call']):
        receipts[ci]=receipt(reader.fetch(call),call,adapter.policy)
    if before!=_local_readonly_identity(reader.base):raise ValueError('issue4_source_drift')
    prepared=adapter.prepare_local(family,params,receipts)
    if prepared.get('status')!='ready_for_typed_sql':raise ValueError('issue4_A_prepare_blocked:'+str(prepared.get('reason')))
    prepared=adapter.recheck_prepared(prepared)
    native=typed_sql(a['sql'],prepared['typed_tables'])
    result=typed_sql(sql,prepared['typed_tables'])
    if result['columns']!=outputs or result['row_count']!=1:raise ValueError('issue4_output_schema_changed')
    row=result['rows'][0];prefix='hierarchy' if family=='hierarchy' else 'parent'
    embedded_columns=json.loads(row[prefix+'_columns_json']);embedded=json.loads(row[prefix+'_rows_json'])
    if embedded_columns!=native['columns'] or any(len(values)!=len(embedded_columns) for values in embedded):
        raise ValueError('issue4_packed_schema_changed')
    unpacked=[dict(zip(embedded_columns,values)) for values in embedded]
    if Counter(digest(r) for r in unpacked)!=Counter(digest(r) for r in native['rows']):
        raise ValueError('issue4_detail_conservation_failed')
    sources()
    if before!=_local_readonly_identity(reader.base):raise ValueError('issue4_source_drift_after_execution')
    diagnostics.update(sql_executed=True,executed_api_calls=reader.actual_calls,
        copy_execution_variant=copying.mode(),
        answer_completeness='partial_with_explicit_unknowns',business_complete=False,
        source_snapshot=before,A_diagnostics=prepared['diagnostics'],canonical_receipts=prepared['canonical_receipts'],
        A_detail_rows=native['row_count'],all_A_details_retained=True,projection_loaded_not_raw=True,
        core_utf8_bytes=len(json.dumps({'api_call':a['api_call'],'sql':sql},ensure_ascii=False,separators=(',',':')).encode()),
        final_official_depth_and_envelope='unresolved',result_layout='one summary row; complete A rows and column schema retained in JSON')
    return {'sql':sql,'result':result,'error':None}
