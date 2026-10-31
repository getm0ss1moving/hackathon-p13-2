"""补全现有CCE列表的节点及已证VM统计；未解析VM关系保留NULL。"""
import copy
import re


TABLES = {'CCE_CLUSTER':'CLOUD_CCE_CLUSTER','CCE_NODE':'CLOUD_CCE_NODE','VM_NOVA':'CLOUD_VM_NOVA'}
FIELDS = {'CCE_CLUSTER':{'id','name','status','clusterType','logicalRegionName'},
          'CCE_NODE':{'id','ref_clusterId','ref_vmId','logicalRegionName'},
          'VM_NOVA':{'id','logicalRegionName'}}


def request_region(question):
    entity = r'''(?:"(?P<dq>[^"\n]+)"|'(?P<sq>[^'\n]+)'|“(?P<cq>[^”\n]+)”|(?P<bare>[A-Za-z0-9_@][A-Za-z0-9_@.\-]*))'''
    grammar = (r'\s*(?:请|帮我)?\s*(?:查询|查看)?\s*(?:区域|logicalRegionName)\s*'+entity+
        r'\s*(?:下|中|内)(?:的)?\s*(?:CCE|容器)集群列表\s*[、,，]\s*各集群(?:的)?节点(?:数量|数)'
        r'\s*(?:和|及|与|、|,|，)\s*各集群(?:关联)?(?:的)?(?:虚拟机|ECS)(?:数量|数)\s*[。?？]?\s*')
    found = re.fullmatch(grammar, question, re.I)
    if found is None:return None
    value = next(v for v in found.groupdict().values() if v is not None)
    return value if value.strip() and '{{' not in value and len(value)<=256 else None


def _outputs(sql):
    match = re.fullmatch(r'\s*SELECT\s+(.+?)\s+FROM\s+CLOUD_CCE_CLUSTER\s*;?\s*',sql or '',re.I)
    if not match:return None
    result=[]
    for expression in match[1].split(','):
        part=re.fullmatch(r'\s*(?:CLOUD_CCE_CLUSTER\.)?(name|status|clusterType)(?:\s+AS\s+([A-Za-z_]\w*))?\s*',expression,re.I)
        if part is None:return None
        field={'name':'name','status':'status','clustertype':'clusterType'}[part[1].casefold()]
        result.append((field,part[2] or field))
    extra={'cluster_id','node_count','known_vm_count','vm_count','unresolved_vm_node_count'}
    if (len(result)!=3 or {f for f,_ in result}!={'name','status','clusterType'}
            or len({a.casefold() for _,a in result})!=3
            or any(a.casefold() in extra for _,a in result)):return None
    return result


def compose(outputs):
    projection=', '.join('c.'+field+' AS '+alias for field,alias in outputs)
    missing="SUM(CASE WHEN n.id IS NOT NULL AND v.id IS NULL THEN 1 ELSE 0 END)"
    return ("SELECT "+projection+", c.id AS cluster_id, COUNT(n.id) AS node_count, "
        "COUNT(DISTINCT v.id) AS known_vm_count, "
        "CASE WHEN "+missing+"=0 THEN COUNT(DISTINCT v.id) ELSE NULL END AS vm_count, "+missing+" AS unresolved_vm_node_count "
        "FROM CLOUD_CCE_CLUSTER c LEFT JOIN CLOUD_CCE_NODE n "
        "ON n.ref_clusterId=c.id AND n.logicalRegionName=c.logicalRegionName "
        "LEFT JOIN CLOUD_VM_NOVA v ON n.ref_vmId=v.id AND v.logicalRegionName=n.logicalRegionName "
        "GROUP BY c.id, c.name, c.status, c.clusterType ORDER BY c.id")


def prepare(question, item, schema_columns):
    region=request_region(question); outputs=_outputs(item.get('sql'))
    if region is None or outputs is None or set(item.get('resources',[]))!=set(TABLES):return None
    if any(not fields<=set(schema_columns.get(ci,[])) for ci,fields in FIELDS.items()):return None
    calls=item.get('api_call')
    if not isinstance(calls,list) or len(calls)!=3:return None
    expected=[]
    for ci,call in zip(TABLES,calls):
        if (not isinstance(call,dict) or set(call)-{'method','url','condition','autoPagination'}
                or call.get('method','GET')!='GET' or call.get('autoPagination',True) is not True
                or call.get('url')!='/rest/hackthon/db/instances/'+ci+'?pageNo=1&pageSize=10000'):return None
        if ci=='VM_NOVA':
            if call.get('condition'):return None
        else:
            condition=call.get('condition'); constraints=condition.get('constraint') if isinstance(condition,dict) else None
            if set(condition or {})!={'constraint'} or not isinstance(constraints,list) or len(constraints)!=1:return None
            entry=constraints[0];simple=entry.get('simple',{})
            if (set(entry)-{'simple','logOp'} or entry.get('logOp','and')!='and'
                    or set(simple)!={'name','value','operator'} or simple['name']!='logicalRegionName'
                    or simple['operator']!='equal' or simple['value'] not in {region,'{{logicalRegionName}}'}):return None
        bound=copy.deepcopy(call)
        if ci!='VM_NOVA':bound['condition']['constraint'][0]['simple']['value']=region
        expected.append(bound)
    result=copy.deepcopy(item);result.update(api_call=expected,sql=compose(outputs),
        _cce_cluster_details={'region':region,'relation_source':'背景知识.md CCE_NODE→CCE_CLUSTER/ref_clusterId and CCE_NODE→VM_NOVA/ref_vmId'})
    return result


def validate_rows(ci,rows,region):
    """真实读数后检查身份、字段及请求范围；未知引用留给SQL显式投影。"""
    ids=set();normalized=[]
    for row in rows:
        identity=row.get('id')
        if not isinstance(identity,str) or not identity.strip() or identity in ids:raise ValueError('cce_missing_or_duplicate_identity')
        ids.add(identity)
        if any(row.get(field) is not None and not isinstance(row[field],str) for field in FIELDS[ci]):raise ValueError('cce_unverified_field_type')
        if ci!='VM_NOVA' and row.get('logicalRegionName')!=region:raise ValueError('cce_wrong_scope')
        # prepare已核实真实schema；稀疏记录省略的可空属性仍是未知，不能当0。
        projected=dict(row)
        for field in FIELDS[ci]:projected.setdefault(field,None)
        normalized.append(projected)
    return normalized


def validate_population(tables):
    clusters={r['id']:r for r in tables[TABLES['CCE_CLUSTER']]}
    nodes=tables[TABLES['CCE_NODE']];vms={r['id']:r for r in tables[TABLES['VM_NOVA']]}
    unknown=0
    for node in nodes:
        parent=clusters.get(node['ref_clusterId'])
        if parent is None or parent['logicalRegionName']!=node['logicalRegionName']:
            raise ValueError('cce_unassigned_node_parent')
        vm=vms.get(node['ref_vmId'])
        unknown+=vm is None or vm['logicalRegionName']!=node['logicalRegionName']
    return {'cluster_count':len(clusters),'node_count':len(nodes),'unresolved_vm_node_count':unknown,
            'complete_vm_counts':unknown==0,'unresolved_vm_policy':'NULL total; known distinct count retained'}
