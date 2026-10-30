"""只做窄空根探测资格；不发请求、不改API/SQL、不接管非空执行。"""
import copy
from contextlib import closing
import re
import sqlite3
from urllib.parse import parse_qsl, urlsplit

_IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
_ENTITY = (r'(?:"(?P<double>[^"\r\n]+)"|“(?P<curly>[^”\r\n]+)”|'
           r"'(?P<single>[^'\r\n]+)'|‘(?P<curly_single>[^’\r\n]+)’|"
           r'「(?P<corner>[^」\r\n]+)」|(?P<bare>[A-Za-z0-9_][A-Za-z0-9_@./:#%+\-]*))')
_PREFIX = r'\s*(?:(?:请)?查询|(?:请)?列出)?\s*'
_END = r'\s*[。！？?!！]*\s*'
_RESERVED = {'select','distinct','from','inner','join','on','left','right','full','outer',
             'cross','natural','using','where','group','order','having','limit','union','or','and'}

_PROFILES = [
    ('cce_nodes', r'(?:CCE\s*集群|容器集群)\s*' + _ENTITY +
     r'\s*下(?:的)?(?:容器节点|节点)列表(?P<with_ip>(?:及|和)节点IP)?',
     'CCE_CLUSTER','CLOUD_CCE_CLUSTER','name','equal',
     {'CLOUD_CCE_CLUSTER','CLOUD_CCE_NODE'},
     {('CLOUD_CCE_NODE','name'):'node_name',('CLOUD_CCE_NODE','privateIP'):'node_ip',
      ('CLOUD_CCE_NODE','status'):'status',('CLOUD_CCE_NODE','managedStatus'):'status',
      ('CLOUD_CCE_NODE','cpu'):'cpu'},
     {('CLOUD_CCE_NODE','name')}),
    ('cce_pods', r'(?:CCE\s*集群|容器集群)\s*' + _ENTITY + r'\s*下(?:的)?Pod列表',
     'CCE_CLUSTER','CLOUD_CCE_CLUSTER','name','equal',
     {'CLOUD_CCE_CLUSTER','CLOUD_CCE_POD'},
     {('CLOUD_CCE_POD','name'):'pod_name',('CLOUD_CCE_POD','managedStatus'):'status'},
     {('CLOUD_CCE_POD','name')}),
    ('deployment_node_ip', r'部署节点(?:管理IP|mgmtIp)\s*' + _ENTITY +
     r'\s*对应的(?:部署)?节点名称(?:和|及)(?:所属)?云服务',
     'S_DeployNode','SYS_DeployNode','mgmtIp','contain',
     {'SYS_DeployNode','SYS_DeployInstance','SYS_DeployComponent','SYS_Service','SYS_CloudService'},
     {('SYS_DeployNode','name'):'node_name',('SYS_DeployNode','mgmtIp'):'node_ip',
      ('SYS_CloudService','name'):'cloud_service_name'},
     {('SYS_DeployNode','name'),('SYS_CloudService','name')}),
    ('modelarts_service', r'ModelArts\s*推理服务\s*' + _ENTITY +
     r'\s*(?:及|以及)(?:关联)?资源池(?:和|及)节点',
     'MODELARTS_INF_SERVICE','CLOUD_MODELARTS_INF_SERVICE','name','equal',
     {'CLOUD_MODELARTS_INF_SERVICE','CLOUD_MODELARTS_INF_POOL','CLOUD_MODELARTS_INF_NODE'},
     {('CLOUD_MODELARTS_INF_SERVICE','name'):'service_name',('CLOUD_MODELARTS_INF_POOL','name'):'pool_name',
      ('CLOUD_MODELARTS_INF_NODE','name'):'node_name'},
     {('CLOUD_MODELARTS_INF_SERVICE','name'),('CLOUD_MODELARTS_INF_POOL','name'),
      ('CLOUD_MODELARTS_INF_NODE','name')}),
]
_KNOWN_ROLES = {re.sub(r'[_\-\s]','',name).casefold():name for name in
                ['node_name','node_ip','status','cpu','service_name','pool_name','cloud_service_name',
                 'host_name','vm_name','tenant_name','vdc_name','cluster_name','pod_name']}


def _decline(reason):
    return {'eligible':False,'reason':reason,'may_execute_nonempty':False}


def _question_profile(question):
    matches=[]
    for profile in _PROFILES:
        found=re.fullmatch(_PREFIX+profile[1]+_END,question,re.I)
        if found:
            value=next(found[name] for name in ['double','curly','single','curly_single','corner','bare']
                       if found.groupdict().get(name) is not None)
            if not value.strip() or '{{' in value or '}}' in value:
                continue
            if found.groupdict().get('bare') and value.endswith(('.',':')):
                continue
            required=set(profile[8])
            if found.groupdict().get('with_ip'):
                required.add(('CLOUD_CCE_NODE','privateIP'))
            matches.append((profile,value,required))
    return matches[0] if len(matches)==1 else None


def _api(item,profile,value):
    calls=item.get('api_call');calls=calls if isinstance(calls,list) else [calls]
    if len(calls)!=1 or not isinstance(calls[0],dict):return None
    call=calls[0]
    if (set(call)-{'method','url','condition','autoPagination'} or call.get('method','GET')!='GET'
            or ('autoPagination' in call and call['autoPagination'] is not True)):
        return None
    try:
        url=urlsplit(call['url']);pairs=parse_qsl(url.query,strict_parsing=True)
        query=dict(pairs)
        if (url.scheme or url.netloc or url.fragment or len(pairs)!=len(query)
                or url.path!='/rest/hackthon/db/instances/'+profile[2]
                or set(query)-{'pageNo','pageSize'} or query.get('pageNo','1')!='1'
                or query.get('pageSize','10000')!='10000'):
            return None
    except (KeyError,TypeError,ValueError):return None
    condition=call.get('condition')
    if not isinstance(condition,dict) or set(condition)!={'constraint'}:return None
    entries=condition['constraint']
    if not isinstance(entries,list) or len(entries)!=1 or not isinstance(entries[0],dict):return None
    entry=entries[0]
    if set(entry)-{'simple','logOp'} or entry.get('logOp','and')!='and':return None
    simple=entry.get('simple')
    if (not isinstance(simple,dict) or set(simple)-{'name','value','operator'}
            or simple.get('name')!=profile[4] or simple.get('value')!=value
            or simple.get('operator','equal')!=profile[5]):return None
    return copy.deepcopy(call)


def _parse_detail_sql(sql,schemas):
    if not isinstance(sql,str) or any(mark in sql for mark in ["'",'"','`','[',']','--','/*','*/','\x00']):
        return None
    clean=sql.strip().removesuffix(';').strip()
    if ';' in clean:return None
    tokens=re.findall(_IDENT+r'|\S',clean);position=0
    def take(word=None):
        nonlocal position
        if position>=len(tokens) or word is not None and tokens[position].casefold()!=word:
            raise ValueError('unexpected_token')
        token=tokens[position];position+=1;return token
    def ident():
        token=take()
        if not re.fullmatch(_IDENT,token) or token.casefold() in _RESERVED:raise ValueError('invalid_identifier')
        return token
    def ref():
        prefix=ident();take('.');return prefix,ident()
    try:
        take('select')
        if position<len(tokens) and tokens[position].casefold()=='distinct':take('distinct')
        projected=[]
        while True:
            prefix,field=ref();label=field
            if position<len(tokens) and tokens[position].casefold()=='as':take('as');label=ident()
            projected.append((prefix,field,label))
            if position<len(tokens) and tokens[position]==',':take(',');continue
            break
        take('from');tables=[];references={};edges=[]
        def table():
            raw=ident();canonical=next((name for name in schemas if name.casefold()==raw.casefold()),None)
            if canonical is None or canonical in tables:raise ValueError('unknown_or_repeated_table')
            alias=raw
            if position<len(tokens) and tokens[position].casefold()=='as':take('as');alias=ident()
            elif position<len(tokens) and tokens[position].casefold() not in _RESERVED:alias=ident()
            if alias.casefold() in references:raise ValueError('duplicate_table_alias')
            references[alias.casefold()]=canonical;tables.append(canonical);return canonical
        first=table()
        while position<len(tokens):
            if tokens[position].casefold()=='inner':take('inner')
            take('join');new=table();take('on');left=ref();take('=');right=ref()
            bound=[]
            for prefix,field in [left,right]:
                source=references.get(prefix.casefold())
                if source is None or field.casefold() not in {column.casefold() for column in schemas[source]}:
                    raise ValueError('unknown_join_field')
                bound.append((source,field))
            if (bound[0][0]==new)==(bound[1][0]==new):raise ValueError('unconnected_join')
            edges.append(bound)
        output=[];labels=[]
        for prefix,field,label in projected:
            source=references.get(prefix.casefold())
            if source is None:raise ValueError('unknown_projection_source')
            actual=[column for column in schemas[source] if column.casefold()==field.casefold()]
            if len(actual)!=1:raise ValueError('unknown_projection_field')
            output.append((source,actual[0],label));labels.append(re.sub(r'[_\-\s]','',label).casefold())
        if len(labels)!=len(set(labels)):raise ValueError('duplicate_projection_label')
        with closing(sqlite3.connect(':memory:')) as db:
            for name in tables:
                columns=schemas[name]
                if not isinstance(columns,(list,tuple)) or not columns or len({c.casefold() for c in columns})!=len(columns):
                    raise ValueError('unverified_schema')
                quote=lambda value:'"'+value.replace('"','""')+'"'
                db.execute('CREATE TABLE '+quote(name)+' ('+','.join(quote(c)+' TEXT' for c in columns)+')')
            db.execute('EXPLAIN '+sql).fetchall()
        return {'root_table':first,'tables':tables,'projections':output,'join_edges':edges}
    except (ValueError,TypeError,sqlite3.Error,KeyError,AttributeError):return None


def empty_root_eligibility(question,item,schemas):
    """只允许HTTP证实空根后的原SQL执行；不能据本返回值接管非空分支。"""
    if not isinstance(question,str) or not isinstance(item,dict) or not isinstance(schemas,dict):
        return _decline('invalid_input')
    matched=_question_profile(question)
    if matched is None:return _decline('question_outside_complete_role_grammar')
    profile,value,required=matched
    root_columns=schemas.get(profile[3])
    if not isinstance(root_columns,(list,tuple)) or profile[4] not in root_columns:
        return _decline('root_filter_field_unavailable')
    call=_api(item,profile,value)
    if call is None:return _decline('root_api_scope_not_identical_to_question')
    shape=_parse_detail_sql(item.get('sql'),schemas)
    if shape is None:return _decline('not_single_direct_inner_detail_sql')
    if shape['root_table']!=profile[3] or set(shape['tables'])!=profile[6]:
        return _decline('unexpected_resource_domain')
    allowed=profile[7];actual={(table,field) for table,field,_ in shape['projections']}
    if not required<=actual or not actual<=set(allowed):return _decline('projection_role_or_coverage_mismatch')
    for table,field,label in shape['projections']:
        known=_KNOWN_ROLES.get(re.sub(r'[_\-\s]','',label).casefold())
        expected=allowed[(table,field)]
        if known is not None and known!=expected:
            return _decline('known_output_alias_role_mismatch')
    return {'eligible':True,'reason':'complete_root_role_and_direct_inner_detail_shape',
            'profile':profile[0],'root_ci':profile[2],'root_table':profile[3],
            'root_field':profile[4],'root_value':value,'expected_api_call':call,
            'sql_tables':shape['tables'],'output_columns':[label for _,_,label in shape['projections']],
            'requires_complete_zero_response':True,'may_execute_nonempty':False,
            'certifies_positive_join_coverage':False,'sql':item['sql']}
