"""Closed VOLUME row views. Pure stdlib and no old-ID runtime routing.

prepare_candidate validates the complete original question. materialize_candidate
is structural only and cannot authorize execution without prepare_candidate.
"""
import copy
import itertools
import re

FAMILY_ID = "family_volume_rows"
ATOM = r"A-Za-z0-9_@./:#%+\-"
VIEWS = {'bootable_scoped_rows': {'filters': ['logicalRegionName', 'azoneName', 'bootable'],
                          'columns': ['name', 'size', 'status', 'bootable'],
                          'resources': ['VOLUME'],
                          'api_call': {'method': 'GET',
                                       'url': '/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000',
                                       'condition': {'constraint': [{'simple': {'name': 'logicalRegionName',
                                                                                'value': '{{logicalRegionName}}',
                                                                                'operator': 'equal'}},
                                                                    {'simple': {'name': 'azoneName',
                                                                                'value': '{{azoneName}}',
                                                                                'operator': 'equal'}},
                                                                    {'simple': {'name': 'bootable',
                                                                                'value': '{{bootable}}',
                                                                                'operator': 'equal'}}]}},
                          'sql': 'SELECT name, size, status, bootable FROM CLOUD_VOLUME'},
 'vdc_scoped_rows': {'filters': ['vdcName', 'logicalRegionName'],
                     'columns': ['name', 'size', 'status', 'type_name'],
                     'resources': ['VOLUME'],
                     'api_call': {'method': 'GET',
                                  'url': '/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000',
                                  'condition': {'constraint': [{'simple': {'name': 'vdcName',
                                                                           'value': '{{vdcName}}',
                                                                           'operator': 'equal'}},
                                                               {'simple': {'name': 'logicalRegionName',
                                                                           'value': '{{logicalRegionName}}',
                                                                           'operator': 'equal'}}]}},
                     'sql': 'SELECT CLOUD_VOLUME.name AS name, CLOUD_VOLUME.size AS size, '
                            "CLOUD_VOLUME.status AS status, 'N/A' AS type_name FROM CLOUD_VOLUME"}}

ROLES = {
    'logicalRegionName': ['logicalRegionName', '区域', '地区', '地域', 'region'],
    'azoneName': ['azoneName', '可用区', 'AZ'],
    'vdcName': ['vdcName', 'VDC名称', 'VDC', '虚拟数据中心'],
    'bootable': ['bootable', '可启动标志'],
}
TOKENS = {'logicalRegionName':'<REGION>', 'azoneName':'<AZ>', 'vdcName':'<VDC>', 'bootable':'<BOOTABLE>'}
COLUMN_ALIASES = {
    'name':['name', '名称', '卷名称', '云硬盘名称', '卷名', '云硬盘名'],
    'size':['size', '容量', '卷容量', '云硬盘容量'],
    'status':['status', '状态', '卷状态', '云硬盘状态'],
    'bootable':['bootable', '可启动标志'],
    'type_name':['type_name', '类型占位符'],
}


def _materialize(item, parsed):
    if not isinstance(item, dict) or item.get('id') != FAMILY_ID or item.get('family_id') != FAMILY_ID:
        raise ValueError('wrong_family')
    if not isinstance(parsed, dict) or set(parsed) != {'view','filters','required_filters'}:
        raise ValueError('closed_parameter_schema_required')
    view = parsed['view']
    if not isinstance(view, str) or view not in VIEWS:
        raise ValueError('unknown_view')
    spec = VIEWS[view]
    filters, required = parsed['filters'], parsed['required_filters']
    if (not isinstance(filters, dict) or set(filters) != set(spec['filters'])
            or not isinstance(required, list) or any(not isinstance(k,str) for k in required)
            or len(set(required)) != len(required) or set(required) != set(filters)):
        raise ValueError('exact_filter_profile_required')
    for field,value in filters.items():
        if (not isinstance(value,str) or not value.strip() or value != value.strip()
                or '{{' in value or '}}' in value or '\n' in value or '\r' in value):
            raise ValueError('nonempty_original_literal_required:'+field)
        if field == 'bootable' and value not in {'True','False'}:
            raise ValueError('bootable_API_string_enum_required')
    ordinary = copy.deepcopy(item)
    for key in ['family_id','parameter_contract','default_params']:
        ordinary.pop(key,None)
    api = copy.deepcopy(spec['api_call'])
    for entry in api['condition']['constraint']:
        entry['simple']['value'] = filters[entry['simple']['name']]
    ordinary.update(resources=copy.deepcopy(spec['resources']),api_call=api,sql=spec['sql'])
    return ordinary


def materialize_candidate(item, parsed):
    """Structural boundary only. Runtime callers must use prepare_candidate."""
    try:
        return _materialize(item,parsed)
    except (ValueError,TypeError):
        return None


def _quotes(text):
    return [m.span() for m in re.finditer(r'"[^"\n]*"|\x27[^\x27\n]*\x27|“[^”\n]*”|「[^」\n]*」',text)]


def _inside(span,quotes):
    return any(a <= span[0] and span[1] <= b for a,b in quotes)


def _literal(value,left=False):
    options = [re.escape(a+value+b) for a,b in [('"','"'),("'","'"),('“','”'),('「','」')]
               if a not in value and b not in value]
    if re.fullmatch('['+ATOM+']+',value):
        options.append((r'(?<!['+ATOM+'])' if left else '')+re.escape(value)+r'(?!['+ATOM+'])')
    if not options:
        raise ValueError('unsupported_entity_quote_shape')
    return '(?-i:(?:'+'|'.join(options)+'))'


def _projection(text,columns):
    quotes = _quotes(text)
    markers = [m for m in re.finditer(r'(?:只|仅)?(?:输出|返回|显示|展示)(?:字段|列)?\s*(?:为|是|:|：)?\s*|(?:字段|列)\s*(?:为|是|:|：)\s*',text)
               if not _inside(m.span(),quotes)]
    if not markers:
        return text,False
    if len(markers) != 1:
        raise ValueError('single_projection_clause_required')
    marker = markers[0]
    tail = text[marker.end():].strip().rstrip('。.;；!?！？ ')
    names = re.split(r'\s*(?:、|,|，|和|与|及|/)\s*',tail)
    lookup = {a.casefold():key for key,aliases in COLUMN_ALIASES.items() for a in aliases}
    if not names or any(a.casefold() not in lookup for a in names):
        raise ValueError('unknown_explicit_column')
    if [lookup[a.casefold()] for a in names] != columns:
        raise ValueError('explicit_projection_mismatch')
    return text[:marker.start()].rstrip('，,、;； '),True


def _bind(text,filters):
    quotes = _quotes(text)
    all_matches = []
    for field,value in filters.items():
        roles = '(?:'+'|'.join(re.escape(a) for a in sorted(ROLES[field],key=len,reverse=True))+')'
        leading_roles = '(?:'+'|'.join((r'(?<!['+ATOM+'])' if a.isascii() else '')+re.escape(a) for a in sorted(ROLES[field],key=len,reverse=True))+')'
        leading = leading_roles+r'\s*(?:(?:为|是|等于|=|:|：)\s*)?'+_literal(value)
        trailing = _literal(value,left=True)+r'\s*(?:(?:为|是|等于|=|:|：)\s*)?'+roles+r'(?!['+ATOM+'])'
        for pattern in [leading,trailing]:
            for m in re.finditer(pattern,text,re.I):
                if not _inside(m.span(),quotes):
                    all_matches.append((m.start(),m.end(),field))
        if field == 'bootable' and value == 'True':
            for m in re.finditer(r'可启动(?!标志)',text):
                if not _inside(m.span(),quotes):all_matches.append((m.start(),m.end(),field))
    all_matches.sort(key=lambda r:(r[0],-(r[1]-r[0])))
    selected,seen,end = [],set(),-1
    for a,b,field in all_matches:
        if a < end:
            continue
        if field in seen:
            raise ValueError('repeated_filter_role:'+field)
        seen.add(field);selected.append((a,b,field));end=b
    if seen != set(filters):
        raise ValueError('missing_or_wrong_filter_role_value')
    chunks=[];last=0
    for a,b,field in selected:
        chunks.extend([text[last:a],TOKENS[field]]);last=b
    chunks.append(text[last:])
    return ''.join(chunks)


def _ground(question,parsed):
    if not isinstance(question,str) or not question.strip():
        raise ValueError('question_required')
    view=parsed['view'];spec=VIEWS[view]
    text,explicit = _projection(question.strip(),spec['columns'])
    text = _bind(text,parsed['filters'])
    sep = r'\s*(?:(?:在|中|下|内|的|并且|且|和|与|及|AND|[,，、])\s*)*'
    tokens=[re.escape(TOKENS[k]) for k in spec['filters']]
    scope='(?:'+'|'.join(sep.join(order) for order in itertools.permutations(tokens))+')'
    resource=r'(?:云硬盘|EVS(?:\s*云硬盘)?|VOLUME)'
    rows=r'(?:列表|清单|明细)'
    if view=='bootable_scoped_rows':
        intent=resource+r'\s*'+rows
    else:
        # An object-qualified name/capacity pair followed by a row-detail noun
        # is an implicit intent. It keeps all four source default columns.
        # Explicit projection markers are checked before this grammar.
        resource=r'(?:云硬盘|EVS(?:\s*云硬盘)?|VOLUME|卷)'
        rows=r'(?:列表|清单|明细|详情)'
        name=r'(?:名称|名字|名|name)'
        size=r'(?:容量|size)'
        join=r'\s*(?:和|与|及|、|,|，)\s*'
        qualified_name=resource+r'\s*(?:的)?\s*'+name
        qualified_size=resource+r'\s*(?:的)?\s*'+size
        pair='(?:'+'|'.join([
            qualified_name+join+'(?:'+size+'|'+qualified_size+')',
            qualified_size+join+'(?:'+name+'|'+qualified_name+')',
            name+join+qualified_size,
            size+join+qualified_name,
        ])+')'+r'\s*(?:的)?\s*'+rows
        listed=resource+r'\s*'+rows+r'\s*(?:及|和|与|、|，)?\s*容量'
        intent='(?:'+listed+'|'+pair+')'
        if explicit:
            intent='(?:'+intent+'|'+resource+r'\s*'+rows+')'
    prefix=r'\s*(?:(?:请帮忙|帮忙|请帮我|帮我|请)\s*)?(?:(?:查询|查看|查找|列出|查一下|查一查)\s*)?'
    loc=r'\s*(?:(?:中|下|内)(?:的)?|的)?\s*'
    layouts='(?:'+scope+loc+intent+'|'+intent+r'\s*[,，]?\s*'+scope+')'
    if view=='vdc_scoped_rows':
        # Preserve all bound roles while permitting the row intent before,
        # after, or between them; no free-text clauses are removed.
        mixed=[]
        for order in itertools.permutations(tokens):
            for split in range(len(order)+1):
                before=sep.join(order[:split])
                after=sep.join(order[split:])
                mixed.append((before+loc if before else '')+intent+
                             (r'\s*(?:[,，]|在)?\s*'+after if after else ''))
        layouts='(?:'+'|'.join(mixed)+')'
    if not re.fullmatch(prefix+layouts+r'\s*[。.!！?？]*\s*',text,re.I):
        raise ValueError('unsupported_or_unexpressed_request_clause')
    return {'view':view,'filters':copy.deepcopy(parsed['filters']),'columns':list(spec['columns']),
            'explicit_projection':explicit,'aggregation':'none','distinct':False,'order':'none'}


def prepare_candidate(question,item,parsed,diagnostics=None):
    """Full original question + closed profile -> ordinary item, otherwise None."""
    try:
        ordinary=_materialize(item,parsed)
        evidence=_ground(question,parsed)
    except (ValueError,TypeError) as exc:
        if diagnostics is not None:diagnostics.update(family_status='unsupported',family_error=str(exc))
        return None
    if diagnostics is not None:
        diagnostics.update(family_status='materialized',family_id=FAMILY_ID,contract_evidence=evidence)
    return ordinary
