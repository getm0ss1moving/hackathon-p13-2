"""A AZ部分人口合同：独立资源统计、原始VM标签审计及完整A分组守恒。"""
from collections import Counter
import importlib.util
import json
import re
import sys

import runbook_issue4 as shared

_MODULE=None
OUTPUT=['azoneName','ecs_count','row_kind','az_columns_json','az_rows_json']


def module():
    global _MODULE
    package,_=shared.sources()
    if _MODULE is None:
        policy=shared.module().policy;old=sys.modules.get('shared_policy');sys.modules['shared_policy']=policy
        try:
            spec=importlib.util.spec_from_file_location('_B_issue4_AZ',package/'main/az_counts.py')
            _MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_MODULE)
        finally:
            if old is None:sys.modules.pop('shared_policy',None)
            else:sys.modules['shared_policy']=old
    return _MODULE


def parameters(question):
    from runbook_issue3 import _LIT,_decode
    found=re.fullmatch(r'\s*(?:(?:请)?\s*(?:查询|查看|统计)\s*)?区域\s*(?P<region>'+_LIT+r')\s*(?:下|中|内)各可用区的?\s*'
        r'(?:ECS|虚拟机)数量[、,，]\s*云硬盘数量(?:和|及|与)VPC数量[，,]\s*按可用区分别展示\s*[。?？]?\s*',question,re.I)
    return {'logicalRegionName':_decode(found['region'])} if found else None


def layout(params):
    mod=module();a=mod.build(params);columns=list(mod.OUTPUT)
    fields=','.join('d.'+name for name in columns)
    header="'"+json.dumps(columns,separators=(',',':')).replace("'","''")+"'"
    first='g.azoneName IS (SELECT azoneName FROM b_anchor ORDER BY azoneName LIMIT 1)'
    sql=('WITH b_A AS ('+a['sql']+'),b_groups AS ('
        'SELECT azoneName,COUNT(*) AS ecs_count,MAX(native_label_nonblank) AS nonblank FROM B_RAW_VM_AZ GROUP BY azoneName),'
        'b_anchor AS (SELECT azoneName,ecs_count,nonblank,0 AS carrier FROM b_groups UNION ALL '
        'SELECT NULL,NULL,0,1 WHERE NOT EXISTS(SELECT 1 FROM b_groups) AND EXISTS(SELECT 1 FROM b_A)) '
        'SELECT g.azoneName,g.ecs_count,CASE WHEN g.carrier=1 THEN \'summary_only\' WHEN g.nonblank=1 THEN \'observed_native_az_label\' '
        'ELSE \'unknown_native_az_label\' END AS row_kind,CASE WHEN '+first+' THEN '+header+' END AS az_columns_json,'
        'CASE WHEN '+first+' THEN (SELECT json_group_array(json_array('+fields+')) FROM b_A d) END AS az_rows_json '
        'FROM b_anchor g ORDER BY g.azoneName')
    size=len(json.dumps({'api_call':a['api_call'],'sql':sql},ensure_ascii=False,separators=(',',':')).encode())
    if size>4096:raise ValueError('AZ_B_core_exceeds4096')
    return a,sql,size


def prepare(question,item,schemas):
    params=parameters(question)
    if params is None or not {'VM_NOVA','VOLUME','ROUTER'}<=set(item.get('resources',[])):return None
    mod=module();a,sql,_=layout(params)
    if any(not set(fields)<=set(schemas.get(ci,[])) for ci,fields in mod.SCHEMA.items()):return None
    return dict(item,resources=a['resources'],api_call=a['api_call'],sql=sql,_expected_result_columns=OUTPUT.copy(),
        _issue3={'kind':'issue4_az_counts','parameters':params,'question_text':question})


def execute(plan,diagnostics,reader):
    from runbook_issue3 import _local_readonly_identity,digest
    params=plan['_issue3']['parameters'];question=plan['_issue3']['question_text']
    if parameters(question)!=params:raise ValueError('AZ_full_question_binding_changed')
    mod=module();a,sql,size=layout(params)
    if plan['sql']!=sql or plan['api_call']!=a['api_call']:raise ValueError('AZ_plan_changed')
    before=_local_readonly_identity(reader.base);snapshots={};receipts={}
    for ci,call in zip(mod.SCHEMA,a['api_call']):
        snapshots[ci]=reader.fetch(call);receipts[ci]=shared.receipt(snapshots[ci],call,mod.policy)
    if before!=_local_readonly_identity(reader.base):raise ValueError('AZ_native_source_drift')
    raw_hash=mod.policy.digest(receipts)
    expected=mod.execute_local(params,receipts)
    projected={};tables={}
    for ci,fields in mod.SCHEMA.items():
        optional={'azoneName'} if ci=='VM_NOVA' else set()
        p=mod.policy.collect(ci,receipts[ci],a['api_call'][list(mod.SCHEMA).index(ci)],fields,
            nullable=optional,blank_to_null={'azoneName'} if 'azoneName' in fields else set())
        projected[ci]=p
        tables['CLOUD_'+ci]={'columns':list(fields),'types':{f:'TEXT' for f in fields},'rows':p['rows']}
    native=shared.typed_sql(a['sql'],tables)
    if native['columns']!=expected['columns'] or Counter(digest(r) for r in native['rows'])!=Counter(digest(r) for r in expected['rows']):
        raise ValueError('AZ_B_typed_changed_A_result')
    audit=[]
    for row in snapshots['VM_NOVA']['rows']:
        value=row.get('azoneName')
        if value is not None and not isinstance(value,str):raise ValueError('AZ_native_label_invalid_type')
        audit.append({'id':row['id'],'azoneName':value,'native_label_nonblank':int(not mod.policy.blank(value))})
    tables['B_RAW_VM_AZ']={'columns':['id','azoneName','native_label_nonblank'],
        'types':{'id':'TEXT','azoneName':'TEXT','native_label_nonblank':'INTEGER'},'rows':audit}
    result=shared.typed_sql(sql,tables);embedded=[]
    for row in result['rows']:
        if row['az_rows_json'] is not None:
            columns=json.loads(row['az_columns_json'])
            if columns!=expected['columns']:raise ValueError('AZ_packed_schema_changed')
            for values in json.loads(row['az_rows_json']):
                if len(values)!=len(columns):raise ValueError('AZ_packed_row_shape_changed')
                embedded.append(dict(zip(columns,values)))
    if Counter(digest(r) for r in embedded)!=Counter(digest(r) for r in expected['rows']):raise ValueError('AZ_A_group_conservation_failed')
    if result['columns']!=OUTPUT:raise ValueError('AZ_B_output_schema_changed')
    if sum(r['ecs_count'] or 0 for r in result['rows'])!=len(audit):raise ValueError('AZ_VM_audit_population_changed')
    for ci,field in [('VM_NOVA','known_ecs_count'),('VOLUME','known_volume_count'),('ROUTER','known_vpc_count')]:
        if sum(r[field] for r in native['rows'])!=len(projected[ci]['rows']):raise ValueError('AZ_independent_population_changed:'+ci)
    if mod.policy.digest(receipts)!=raw_hash:raise ValueError('AZ_raw_receipts_mutated')
    shared.sources()
    if before!=_local_readonly_identity(reader.base):raise ValueError('AZ_native_source_drift_after_execution')
    diagnostics.update(sql_executed=True,executed_api_calls=reader.actual_calls,source_snapshot=before,
        answer_completeness='partial_with_explicit_unknowns',business_complete=False,full_requested_operation_supported=False,
        A_diagnostics=expected['diagnostics'],canonical_receipts={ci:p['canonical_receipt'] for ci,p in projected.items()},
        A_group_rows=len(native['rows']),all_A_groups_retained=True,projection_loaded_not_raw=True,core_utf8_bytes=size,
        VM_audit_population=len(audit),VM_label_policy='raw labels retained; NULL, empty and whitespace audit groups are not real AZ identities',
        VPC_AZ_policy='all scoped ROUTER objects occur once in the derived unknown bucket; no source AZ field inferred',
        final_official_depth_and_envelope='unresolved')
    return {'sql':sql,'result':result,'error':None}
