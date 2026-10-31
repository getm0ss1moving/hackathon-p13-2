"""绑定原样A集群排名合同；审计计数+已知领先者完整明细，未知排名不冒称全域最大。"""
import copy
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
BINDING='experiments/b_cluster_rank_runtime_20261031/SOURCE_MANIFEST.json'
OUTPUT=['clusterName','ecs_count','observed_leader_details_json','unknown_rank_vm_count','scope_max_certified']


def sources():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    binding=json.loads((ROOT/BINDING).read_text());manifest=ROOT/binding['A_manifest']
    if sha(manifest)!=binding['A_manifest_sha256']:raise ValueError('cluster_A_manifest_drift')
    files={BINDING:sha(ROOT/BINDING),str(manifest.relative_to(ROOT)):sha(manifest)}
    package=json.loads(manifest.read_text())
    for name,h in package['files'].items():
        path=(manifest.parent/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=h:raise ValueError('cluster_A_source_drift')
        files[str(path.relative_to(ROOT))]=h
    return manifest.parent/binding['candidate_path'],files


def module():
    path,_=sources();spec=importlib.util.spec_from_file_location('_B_ranked_cluster_candidate',path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj


def parameters(question):
    literal=r'''(?:"(?P<dq>[^"\n]+)"|'(?P<sq>[^'\n]+)'|“(?P<cq>[^”\n]+)”|(?P<bare>[A-Za-z0-9_][A-Za-z0-9_.\-]*))'''
    match=re.fullmatch(r'\s*(?:查询|查看)?\s*可用区\s*'+literal+r'\s*下(?:ECS|虚拟机)数量最多的集群\s*[,，]\s*列出该集群下所有宿主机的vCPU总量和运行中虚拟机\s*[。?？]?\s*',question,re.I)
    if not match:return None
    az=next(v for v in match.groupdict().values() if v is not None)
    if not az.strip() or '{{' in az or any(ord(c)<32 for c in az):return None
    return {'profile':'cluster_max_vm_host_running_details','filters':{'azoneName':az},'tie_policy':'all_ties',
            'unknown_rank_policy':'known_only_with_diagnostic','details_population':'all_hosts_all_active_VMs'}


def layout(mod,params):
    original=mod.build(params)
    if original['status']=='blocked_transport_budget':raise ValueError('A_cluster_core_budget')
    fields=','.join("'"+f+"',"+f for f in mod.OUTPUT_COLUMNS)
    sql=('WITH b_details AS ('+original['sql']+'), b_counts AS ('
        'SELECT clusterName,COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA WHERE rank_eligible=1 GROUP BY clusterName) '
        'SELECT c.clusterName,c.ecs_count,CASE WHEN c.clusterName IS '
        '(SELECT clusterName FROM b_counts ORDER BY clusterName LIMIT 1) THEN '
        '(SELECT json_group_array(json_object('+fields+')) FROM b_details) END AS observed_leader_details_json, '
        '(SELECT unknown_rank_vm_count FROM B_RANK_DIAGNOSTIC) AS unknown_rank_vm_count, '
        '(SELECT scope_max_certified FROM B_RANK_DIAGNOSTIC) AS scope_max_certified '
        'FROM b_counts c ORDER BY c.clusterName')
    rank_call={'method':'GET','url':'/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=1000',
        'condition':{'constraint':[{'simple':{'name':k,'value':v,'operator':'equal'}} for k,v in params['filters'].items()]}}
    calls=original['api_call']+[rank_call]
    if len(json.dumps({'api_call':calls,'sql':sql},ensure_ascii=False,separators=(',',':')).encode())>4096:
        raise ValueError('B_cluster_layout_core_budget')
    return sql,calls


def prepare(question,item,schemas):
    params=parameters(question)
    if params is None or set(item.get('resources',[]))!={'VM_NOVA','CLUSTER','HOST'}:return None
    if not re.fullmatch(r'\s*SELECT\s+clusterName\s*,\s*COUNT\(\*\)\s+AS\s+ecs_count\s+FROM\s+CLOUD_VM_NOVA\s+GROUP\s+BY\s+clusterName\s*;?\s*',item.get('sql',''),re.I):return None
    mod=module()
    if any(not set(fields)<=set(schemas.get(ci,[])) for ci,fields in mod.SCHEMA.items()):return None
    if 'clusterName' not in schemas.get('VM_NOVA',[]):return None
    sql,calls=layout(mod,params)
    return dict(item,api_call=calls,sql=sql,_expected_result_columns=OUTPUT.copy(),
        _issue3={'kind':'cluster_rank_details','parameters':params})


def project(mod,params,snaps):
    packets={ci:{'ok':True,'http_status':200,'columns':snap['columns'],'schema_source':snap['schema_source'],
        'pages':[dict(copy.deepcopy(p),ok=True,http_status=200,request=mod.request(ci,i,p['pageSize']))
                 for i,p in enumerate(snap['native_pages'],1)]} for ci,snap in snaps.items()}
    checked=mod.preflight(params,packets)
    if checked['status']!='ready_for_typed_sql':raise ValueError('A_cluster_preflight:'+str(checked.get('reason')))
    audited=mod.execute_prepared(params,checked)
    if audited['status']!='local_sql_ok_policy_conditional':raise ValueError('A_cluster_recheck_failed')
    if 'clusterName' not in snaps['VM_NOVA']['columns']:raise ValueError('native_cluster_label_schema_missing')
    labels={r['id']:r.get('clusterName') for r in snaps['VM_NOVA']['rows']}
    if any(v is not None and not isinstance(v,str) for v in labels.values()):raise ValueError('invalid_cluster_display_label')
    tables=copy.deepcopy(checked['tables']);schemas=copy.deepcopy(mod.PREPARED)
    schemas['VM_NOVA'].append('clusterName')
    for row in tables['VM_NOVA']:row['clusterName']=labels[row['id']]
    return tables,schemas,audited


def execute(plan,diagnostics,reader):
    from runbook_issue3 import _local_readonly_identity
    mod=module();params=plan['_issue3']['parameters'];sql,calls=layout(mod,params)
    if plan['sql']!=sql or plan['api_call']!=calls:raise ValueError('cluster_plan_scope_or_sql_drift')
    before=_local_readonly_identity(reader.base)
    snaps={ci:reader.fetch(call) for ci,call in zip(mod.RESOURCES,calls)}
    tables,schemas,audited=project(mod,params,snaps)
    scoped=reader.fetch(calls[-1]);expected={r['id'] for r in tables['VM_NOVA'] if r['rank_eligible']==1}
    if expected!={r['id'] for r in scoped['rows']}:raise ValueError('cluster_rank_API_population_mismatch')
    raw_context={r['id']:r for r in snaps['VM_NOVA']['rows']}
    if any(row!=raw_context[row['id']] for row in scoped['rows']):raise ValueError('cluster_rank_API_context_drift')
    if before!=_local_readonly_identity(reader.base):raise ValueError('cluster_native_source_changed')
    proof=audited['diagnostics'];integers={'rank_eligible','is_running','status_known','host_graph_complete','vcpu_known'}
    with closing(sqlite3.connect(':memory:')) as conn:
        for ci,columns in schemas.items():
            table=ci if ci.startswith('M_') else 'CLOUD_'+ci
            conn.execute('CREATE TABLE '+table+' ('+','.join('"'+k+'" '+('INTEGER' if k in integers else 'BLOB' if k=='totalVcpuCores' else 'TEXT') for k in columns)+')')
            conn.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for k in columns)+')',[[r[k] for k in columns] for r in tables[ci]])
        conn.execute('CREATE TABLE B_RANK_DIAGNOSTIC(unknown_rank_vm_count INTEGER,scope_max_certified INTEGER)')
        conn.execute('INSERT INTO B_RANK_DIAGNOSTIC VALUES (?,?)',(proof['unknown_rank_vm_count'],int(proof['scope_max_certified'])))
        cursor=conn.execute(sql);columns=[c[0] for c in cursor.description];rows=[dict(zip(columns,r)) for r in cursor.fetchall()]
    embedded=[d for row in rows if row['observed_leader_details_json'] is not None for d in json.loads(row['observed_leader_details_json'])]
    if embedded!=audited['rows']:raise ValueError('cluster_A_detail_conservation_failed')
    if columns!=OUTPUT:raise ValueError('cluster_output_columns_changed')
    diagnostics.update(sql_executed=True,business_complete=False,answer_completeness='partial_with_explicit_unknowns',
        executed_api_calls=reader.actual_calls,ranking_proof=proof,rank_API_population_count=len(expected),
        presentation='all observed cluster-label counts for audit; every A known-leader detail retained in first-row JSON',
        projection_loaded_not_raw=True)
    return {'sql':sql,'result':{'columns':columns,'rows':rows,'row_count':len(rows)},'error':None}
