"""A地址成员合同的显式接入；LIKE只取候选，完整token相等不认证所有权。"""
import copy
import importlib.util
import json
import re
import time

import runbook_copy as copying
import runbook_issue4 as shared

_MODULE=None


def module():
    global _MODULE
    package,_=shared.sources()
    if _MODULE is None:
        spec=importlib.util.spec_from_file_location('_B_issue4_address',package/'address/candidate.py')
        _MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_MODULE)
    return copying.bind(_MODULE)


def region(question):
    from runbook_issue3 import _LIT,_decode
    found=re.fullmatch(r'\s*(?:请\s*)?(?:查询|查看)?\s*区域\s*(?P<region>'+_LIT+r')\s*下\s*'
        r'(?:关联了|已关联)\s*(?:弹性\s*IP|EIP)\s*的\s*(?:ECS|虚拟机)\s*实例名\s*(?:和|及|与)\s*固定IP\s*[。?？]?\s*',question,re.I)
    return _decode(found['region']) if found is not None else None


def parameters(question,item):
    from runbook_matcher import _eip_association_status
    value=region(question)
    if value is None or not {'FLOATING_IPS','VM_NOVA'}<=set(item.get('resources',[])):return None
    statuses=_eip_association_status(question,item)
    if len(statuses)!=1:return None
    a=module()
    return {'profile':a.PROFILE,'filters':{'logicalRegionName':value,'status':statuses[0]},
        'required_filters':['logicalRegionName','status'],'address_codec':a.CODEC,
        'unknown_policy':'known_only_with_diagnostic'}


def prepare(question,item,schemas):
    params=parameters(question,item)
    if params is None:return None
    a=module();built=a.build(params)
    if any(not set(fields)<=set(schemas.get(ci,[])) for ci,fields in a.SCHEMA.items()):return None
    calls=[built['eip_request']]
    if len(a.encoded({'api_call':calls,'sql':built['sql']}))>4096:raise ValueError('address_core_exceeds4096')
    return dict(item,resources=list(a.SCHEMA),api_call=calls,sql=built['sql'],
        _expected_result_columns=built['output_columns'],
        _issue3={'kind':'issue4_address','parameters':params,'question_text':question,
                 'role_item':{k:copy.deepcopy(item[k]) for k in ['resources','api_call','sql']}})


def receipt(snapshot,request,role,capture,identity):
    pages=[]
    for index,page in enumerate(snapshot['native_pages'],1):
        stamps={'ok':True,'http_status':200,'pageNo':index}
        if page.get('currentPage')!=index or any(k in page and page[k]!=v for k,v in stamps.items()):
            raise ValueError('address_contradictory_native_metadata')
        pages.append(dict(copying.copy_value(page),**stamps))
    return {'ok':True,'http_status':200,'request':copy.deepcopy(request),'role':role,
        'capture_id':capture['capture_id'],'receipt_id':capture['capture_id']+':'+identity,
        'schema_verified':True,'schema_source':snapshot['schema_source'],
        'schema':snapshot['columns'].copy(),'pages':pages}


def execute(plan,diagnostics,reader):
    from runbook_issue3 import _local_readonly_identity,digest,Unsupported
    a=module();meta=plan['_issue3'];params=meta['parameters']
    if parameters(meta['question_text'],meta['role_item'])!=params:raise ValueError('address_question_binding_changed')
    built=a.build(params)
    if plan['sql']!=built['sql'] or plan['api_call']!=[built['eip_request']]:raise ValueError('address_plan_changed')
    before=_local_readonly_identity(reader.base)
    selected=reader.fetch(built['eip_request']);follow=a.plan_followups(params,selected['rows'])
    planned=len(follow['context_requests'])+len(follow['candidate_requests'])
    if planned>reader.max_http-diagnostics['http_requests']:
        raise Unsupported('address_followups_exceed_remaining_HTTP_budget')
    capture={'capture_id':digest({'source':before,'run':time.monotonic_ns()}),'source_ref':digest(before),
        'schema_ref':'pending','isolation':'immutable_snapshot','origin':'B_verified_native'}
    contexts=[(d,reader.fetch(d['request'])) for d in follow['context_requests']]
    candidates=[(d,reader.fetch(d['request'])) for d in follow['candidate_requests']]
    capture['schema_ref']=digest(reader.schemas)
    evidence={'capture':capture,'eip':receipt(selected,built['eip_request'],'selected_eips',capture,'selected_eips'),
              'vm_context':[],'vm_candidates':[]}
    for d,s in contexts:
        evidence['vm_context'].append(receipt(s,d['request'],d['role'],capture,'context:'+d['region']))
    for d,s in candidates:
        evidence['vm_candidates'].append(dict(receipt(s,d['request'],d['role'],capture,d['lookup_id']),lookup_id=d['lookup_id']))
    if before!=_local_readonly_identity(reader.base):raise ValueError('address_source_drift')
    prepared=a.prepare(params,evidence)
    output=a.execute_prepared(prepared)  # 原A重验保留输入、typed表、diagnostics和摘要后再执行。
    shared.sources()
    if before!=_local_readonly_identity(reader.base):raise ValueError('address_source_drift_after_execution')
    diagnostics.update(sql_executed=True,executed_api_calls=reader.actual_calls,source_snapshot=before,
        copy_execution_variant=copying.mode(),A_diagnostics=output['diagnostics'],
        address_member_semantics='same_region_complete_token_equality',
        actual_contain_requests=len(candidates),actual_VM_context_requests=len(contexts),
        all_A_details_retained=True,business_complete=False,full_original_question_certified=False,
        full_eip_objects_binding_complete=False,answer_completeness='address_candidates_with_explicit_unknowns',
        ownership_authority='not_established_by_address_membership',
        final_official_depth_and_envelope='unresolved')
    rows=output['rows']
    return {'sql':built['sql'],'result':{'columns':output['columns'],'rows':rows,'row_count':len(rows)},'error':None}
