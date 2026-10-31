"""A consumer/provider真实上下文接入；同租户清单与已证VM端口关系分别标注。"""
from collections import Counter
import copy
import importlib.util
import json
import re
import time

import runbook_issue4 as shared
import runbook_copy as copying

_MODULE=None
OUTPUT=['floating_ip','status','eip_id','row_kind','relation_state','vm_host_columns_json','vm_host_rows_json']


def module():
    global _MODULE
    package,_=shared.sources()
    if _MODULE is None:
        path=package/'consumer/consumer.py'
        spec=importlib.util.spec_from_file_location('_B_issue4_consumer',path)
        _MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_MODULE)
    return copying.bind(_MODULE)


def parameters(question):
    from runbook_issue3 import _LIT,_decode
    found=re.fullmatch(r'\s*(?:(?:请)?\s*(?:查询|查看)\s*)?租户\s*(?P<tenant>'+_LIT+r')'
        r'(?:\s*在\s*区域\s*(?P<region>'+_LIT+r')\s*(?:中|下|内))?的?\s*(?:ECS|虚拟机)私有IP列表[、,，]\s*关联弹性IP列表(?:和|及|与)所属宿主机列表\s*[。?？]?\s*',question,re.I)
    if found is None:return None
    params={'view':'known_port_eip_host_rows','tenantName':_decode(found['tenant'])}
    if found['region'] is not None:params['logicalRegionName']=_decode(found['region'])
    return params


def layout(params):
    consumer=module();a=consumer.build_tenant_view(params)
    selection=consumer._request('FLOATING_IPS',{k:v for k,v in params.items() if k!='view'})
    calls=a['api_call']+[a['tenant_selection_request'],selection]
    columns=a['output_columns'];fields=','.join('d.'+c for c in columns)
    header="'"+json.dumps(columns,separators=(',',':')).replace("'","''")+"'"
    sql=('WITH d AS ('+a['sql']+'),c AS (SELECT * FROM B_TENANT_EIP_CATALOG UNION ALL '
        'SELECT NULL,NULL,NULL WHERE NOT EXISTS(SELECT 1 FROM B_TENANT_EIP_CATALOG) AND EXISTS(SELECT 1 FROM d)) '
        'SELECT c.floating_ip,c.status,c.id AS eip_id,CASE WHEN c.id IS NULL THEN \'vm_host_summary_only\' ELSE \'tenant_eip_catalog\' END AS row_kind,'
        'CASE WHEN c.id IS NULL THEN \'no_catalog_object\' WHEN EXISTS(SELECT 1 FROM d WHERE d.eip_id=c.id) THEN \'known_port_link\' ELSE \'catalog_only_binding_unproven\' END AS relation_state,'
        'CASE WHEN c.id IS (SELECT id FROM c ORDER BY id LIMIT 1) THEN '+header+' END AS vm_host_columns_json,'
        'CASE WHEN c.id IS (SELECT id FROM c ORDER BY id LIMIT 1) THEN (SELECT json_group_array(json_array('+fields+')) FROM d) END AS vm_host_rows_json '
        'FROM c ORDER BY c.id')
    if len(json.dumps({'api_call':calls,'sql':sql},ensure_ascii=False,separators=(',',':')).encode())>4096:
        raise ValueError('consumer_B_core_exceeds4096')
    return a,sql,calls


def prepare(question,item,schemas):
    params=parameters(question)
    if params is None or not {'VM_NOVA','FLOATING_IPS'}<=set(item.get('resources',[])):return None
    consumer=module();a,sql,calls=layout(params)
    declared=consumer.legacy().schema_for(params['view'])
    if any(not set(fields)<=set(schemas.get(ci,[])) for ci,fields in declared.items()):return None
    if not {'id','logicalRegionName','tenantName','floatingIpAddress','status'}<=set(schemas.get('FLOATING_IPS',[])):return None
    return dict(item,resources=a['resources'],api_call=calls,sql=sql,_expected_result_columns=OUTPUT.copy(),
        _issue3={'kind':'issue4_vm_links','parameters':params,'question_text':question})


def raw_receipt(snapshot,request,consumer,capture,role):
    pages=[]
    for index,source in enumerate(snapshot['native_pages'],1):
        expected=consumer.page_request(request,index)
        stamps={'ok':True,'http_status':200,'request':expected,'capture_id':capture['capture_id'],'receipt_kind':'raw_http'}
        if any(k in source and consumer.encoded(source[k])!=consumer.encoded(value) for k,value in stamps.items()):
            raise ValueError('consumer_contradictory_raw_metadata')
        pages.append(dict(copying.copy_value(source),**stamps))
    return {'ok':True,'http_status':200,'receipt_kind':'raw_http','capture_id':capture['capture_id'],
        'receipt_id':capture['capture_id']+':'+role,'request':copy.deepcopy(request),
        'schema_verified':True,'schema_source':snapshot['schema_source'],'schema':snapshot['columns'],'pages':pages}


def catalog_projection(params,context,selected):
    required={'id','logicalRegionName','tenantName','floatingIpAddress','status'}
    if not required<=set(context['columns']) or not required<=set(selected['columns']):raise ValueError('consumer_catalog_schema_missing')
    filters={k:v for k,v in params.items() if k!='view'}
    expected={r['id']:r for r in context['rows'] if all(r.get(k)==v for k,v in filters.items())}
    actual={r['id']:r for r in selected['rows']}
    if len(actual)!=len(selected['rows']) or module().encoded(actual)!=module().encoded(expected):raise ValueError('consumer_actual_EIP_selection_context_mismatch')
    rows=[]
    for identity,row in actual.items():
        if any(k not in row or row[k]!=v for k,v in filters.items()):raise ValueError('consumer_catalog_scope_missing')
        if any(row.get(k) is not None and not isinstance(row[k],str) for k in required):raise ValueError('consumer_catalog_invalid_type')
        rows.append({'id':identity,'floating_ip':row.get('floatingIpAddress'),'status':row.get('status')})
    return {'columns':['id','floating_ip','status'],'types':{'id':'TEXT','floating_ip':'TEXT','status':'TEXT'},'rows':rows}


def execute(plan,diagnostics,reader):
    from runbook_issue3 import _local_readonly_identity,digest
    params=plan['_issue3']['parameters'];question=plan['_issue3']['question_text']
    if parameters(question)!=params:raise ValueError('consumer_full_question_binding_changed')
    consumer=module();a,sql,calls=layout(params)
    if plan['sql']!=sql or plan['api_call']!=calls:raise ValueError('consumer_plan_changed')
    before=_local_readonly_identity(reader.base)
    snapshots={ci:reader.fetch(call) for ci,call in zip(a['resources'],a['api_call'])}
    vm_selection=reader.fetch(calls[-2]);eip_selection=reader.fetch(calls[-1])
    if before!=_local_readonly_identity(reader.base):raise ValueError('consumer_native_source_drift')
    capture={'capture_id':digest({'source':before,'question':question,'run':time.monotonic_ns()}),
        'source_ref':digest(before),'schema_ref':digest(reader.schemas),'origin':'B_verified_native','isolation':'immutable_snapshot'}
    raw={ci:raw_receipt(snapshots[ci],call,consumer,capture,ci) for ci,call in zip(a['resources'],a['api_call'])}
    raw['VM_NOVA_SELECTION']=raw_receipt(vm_selection,calls[-2],consumer,capture,'VM_NOVA_SELECTION')
    evidence={'capture':capture,'raw_receipts':raw,'question_text':question}
    prepared=consumer.prepare_tenant_view(params,evidence)
    prepared=consumer.recheck_tenant_prepared(prepared)
    if prepared['diagnostics']['actual_tenant_selection_receipt_proven'] is not True:raise ValueError('consumer_tenant_API_not_proven')
    tables=dict(prepared['typed_tables'])
    if any(any(v!='BINARY' for v in t['collations'].values()) for t in tables.values()):raise ValueError('consumer_unproven_collation')
    native=shared.typed_sql(a['sql'],tables)
    if native['columns']!=a['output_columns']:raise ValueError('consumer_A_output_schema_changed')
    catalog=catalog_projection(params,snapshots['FLOATING_IPS'],eip_selection)
    tables['B_TENANT_EIP_CATALOG']=catalog
    result=shared.typed_sql(sql,tables)
    embedded=[]
    for row in result['rows']:
        if row['vm_host_rows_json'] is not None:
            columns=json.loads(row['vm_host_columns_json'])
            if columns!=native['columns']:raise ValueError('consumer_packed_schema_changed')
            for values in json.loads(row['vm_host_rows_json']):
                if len(values)!=len(columns):raise ValueError('consumer_packed_row_shape_changed')
                embedded.append(dict(zip(columns,values)))
    if Counter(digest(r) for r in embedded)!=Counter(digest(r) for r in native['rows']):raise ValueError('consumer_A_detail_conservation_failed')
    if result['columns']!=OUTPUT:raise ValueError('consumer_B_output_schema_changed')
    shared.sources()
    if before!=_local_readonly_identity(reader.base):raise ValueError('consumer_native_source_drift_after_execution')
    counts=Counter(r['relation_state'] for r in result['rows'])
    diagnostics.update(sql_executed=True,executed_api_calls=reader.actual_calls,source_snapshot=before,
        copy_execution_variant=copying.mode(),
        answer_completeness='partial_with_explicit_unknowns',business_complete=False,
        full_original_question_certified=False,full_eip_objects_binding_complete=False,
        A_diagnostics=prepared['diagnostics'],canonical_receipts=prepared['canonical_receipts'],
        provider_canonical_receipt=prepared['provider_prepared']['canonical_receipt'],
        port_scoped_batch_set_executed=False,PORT_mode='complete_global_or_region_context; no IN request claimed',
        actual_tenant_VM_selection_proven=True,actual_tenant_EIP_catalog_selection_proven=True,
        selected_tenant_EIP_catalog_count=len(catalog['rows']),A_detail_rows=native['row_count'],
        relation_state_counts=dict(counts),all_A_details_retained=True,projection_loaded_not_raw=True,
        core_utf8_bytes=len(json.dumps({'api_call':calls,'sql':sql},ensure_ascii=False,separators=(',',':')).encode()),
        final_official_depth_and_envelope='unresolved')
    return {'sql':sql,'result':result,'error':None}
