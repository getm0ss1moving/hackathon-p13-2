"""Closed VM/volume mount views. Pure stdlib; no IDs, SDK, network or answer routing.

prepare_candidate is the question-aware boundary. materialize_candidate alone is
only a structural check and must not authorize execution.
"""
import copy
import re

FAMILY_ID = "family_vm_volume"
ATOM = r"A-Za-z0-9_@./:#%+\-"
VIEWS = {'vm_volumes': {'filters': ['name'],
                'columns': ['volume_name', 'size_gb', 'bootable', 'status'],
                'resources': ['VM_NOVA'],
                'api_call': {'method': 'GET',
                             'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                             'condition': {'constraint': [{'simple': {'name': 'name',
                                                                      'value': '{{name}}',
                                                                      'operator': 'equal'}}]}},
                'sql': 'SELECT CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS size_gb, '
                       'CLOUD_VOLUME.bootable AS bootable, CLOUD_VOLUME.status AS status FROM '
                       'CLOUD_VM_NOVA INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = '
                       'R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON '
                       'R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id',
                'order': 'none'},
 'vm_bootable_volumes': {'filters': ['name'],
                         'columns': ['bootable', 'volume_name', 'size'],
                         'resources': ['VM_NOVA'],
                         'api_call': {'method': 'GET',
                                      'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                      'condition': {'constraint': [{'simple': {'name': 'name',
                                                                               'value': '{{name}}',
                                                                               'operator': 'equal'}}]}},
                         'sql': 'SELECT CLOUD_VOLUME.bootable AS bootable, CLOUD_VOLUME.name AS '
                                'volume_name, CLOUD_VOLUME.size AS size FROM CLOUD_VM_NOVA INNER '
                                'JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = '
                                'R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON '
                                'R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id ORDER BY '
                                'CLOUD_VOLUME.bootable',
                         'order': 'CLOUD_VOLUME.bootable'},
 'volume_vms': {'filters': ['name'],
                'columns': ['volume_name', 'size', 'status', 'vm_name'],
                'resources': ['VOLUME'],
                'api_call': {'method': 'GET',
                             'url': '/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000',
                             'condition': {'constraint': [{'simple': {'name': 'name',
                                                                      'value': '{{name}}',
                                                                      'operator': 'equal'}}]}},
                'sql': 'SELECT CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS size, '
                       'CLOUD_VOLUME.status AS status, CLOUD_VM_NOVA.name AS vm_name FROM '
                       'CLOUD_VOLUME INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VOLUME.id = '
                       'R_VOLUME_MOUNTON_VM.volumeId INNER JOIN CLOUD_VM_NOVA ON '
                       'R_VOLUME_MOUNTON_VM.vmId = CLOUD_VM_NOVA.id',
                'order': 'none'}}


def _materialize(item, parsed):
    if not isinstance(item, dict) or item.get('id') != FAMILY_ID or item.get('family_id') != FAMILY_ID:
        raise ValueError('wrong_family')
    if not isinstance(parsed, dict) or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ValueError('closed_parameter_schema_required')
    view = parsed['view']
    if not isinstance(view, str) or view not in VIEWS:
        raise ValueError('unknown_view')
    filters, required = parsed['filters'], parsed['required_filters']
    if (not isinstance(filters, dict) or set(filters) != {'name'}
            or not isinstance(required, list) or required != ['name']):
        raise ValueError('exact_filter_contract_required')
    name = filters['name']
    if not isinstance(name, str) or not name.strip() or name != name.strip() or '{{' in name or '}}' in name or '\n' in name or '\r' in name:
        raise ValueError('nonempty_literal_name_required')
    spec = VIEWS[view]
    ordinary = copy.deepcopy(item)
    for key in ['family_id', 'parameter_contract', 'default_params']:
        ordinary.pop(key, None)
    api = copy.deepcopy(spec['api_call'])
    api['condition']['constraint'][0]['simple']['value'] = name
    ordinary.update(resources=copy.deepcopy(spec['resources']), api_call=api, sql=spec['sql'])
    return ordinary


def materialize_candidate(item, parsed):
    """Structure only; ordinary item or None. Runtime must use prepare_candidate."""
    try:
        return _materialize(item, parsed)
    except (ValueError, TypeError):
        return None


def _literal(value):
    variants = [re.escape(a + value + b) for a, b in [('"', '"'), ("'", "'"), ('“', '”'), ('「', '」')]
                if a not in value and b not in value]
    if re.fullmatch('[' + ATOM + ']+', value):
        variants.append(re.escape(value) + '(?![' + ATOM + '])')
    if not variants:
        raise ValueError('unsupported_quote_shape')
    # Entity case stays exact even though resource aliases are case-insensitive.
    return '(?-i:(?:' + '|'.join(variants) + '))'


def _quotes(text):
    return [m.span() for m in re.finditer(r'"[^"\n]*"|\x27[^\x27\n]*\x27|“[^”\n]*”|「[^」\n]*」', text)]


def _inside(span, quotes):
    return any(a <= span[0] and span[1] <= b for a, b in quotes)


OUTPUT_ALIASES = {
    'volume_name': ['volume_name', '云硬盘名称', '云硬盘名', '卷名称', '卷名'],
    'size_gb': ['size_gb', '容量GB'],
    'size': ['size', '容量', '云硬盘容量'],
    'bootable': ['bootable', '可启动标志'],
    'status': ['status', '状态', '卷状态'],
    'vm_name': ['vm_name', 'ECS名称', 'ECS名', '虚拟机名'],
}


def _projection(text, columns):
    quotes = _quotes(text)
    markers = [m for m in re.finditer(r'(?:只|仅)?(?:输出|返回|显示|展示)(?:字段|列)?\s*(?:为|是|:|：)?\s*|(?:字段|列)\s*(?:为|是|:|：)\s*', text)
               if not _inside(m.span(), quotes)]
    if not markers:
        return text, False
    if len(markers) != 1:
        raise ValueError('multiple_projection_clauses')
    marker = markers[0]
    tail = text[marker.end():].strip().rstrip('。.;；!?！？ ')
    lookup = {a.casefold(): field for field, aliases in OUTPUT_ALIASES.items() for a in aliases}
    parts = re.split(r'\s*(?:、|,|，|和|与|及|/)\s*', tail)
    if not parts or any(part.casefold() not in lookup for part in parts):
        raise ValueError('unknown_explicit_output')
    actual = [lookup[part.casefold()] for part in parts]
    if actual != columns:
        raise ValueError('explicit_projection_mismatch')
    return text[:marker.start()].rstrip('，,、;； '), True


def _parent(resource, name):
    literal = _literal(name)
    roles = r'(?:名称|名字|name)\s*(?:(?:等于|为|是|=|:|：)\s*)?'
    # Both resource-name and name-resource forms stay in one full grammar.
    named = r'(?:' + roles + literal + r'|' + literal + ')'
    return (r'(?:' + resource + r'\s*' + named + r'|'
            + roles + literal + r'\s*(?:的)?\s*' + resource + r'|'
            + literal + r'\s*(?:为|是)?\s*(?:名称|名字|name)\s*(?:的)?\s*' + resource + r')')


# Request phrasing, current/aspect markers and mount direction are separate
# grammar components. None can erase negation, history, filters or other clauses.
_REQUEST = r'\s*(?:(?:请(?:帮我|帮忙)?|帮我|帮忙)\s*)?(?:(?:查询|查看|查找|列出|查一下|查一查)\s*)?'
_CURRENT = r'(?:(?:目前|现在|当前)\s*)?'
_ASPECT = r'(?:(?:已经|已)\s*)?'
_VM_OBJECT = r'(?:ECS(?:\s*实例)?|虚拟机(?:\s*实例)?|VM_NOVA)'
_VOLUME_OBJECT = r'(?:云硬盘|卷|EVS(?:\s*云硬盘)?|VOLUME)'
_ROWS = r'(?:\s*(?:列表|明细|清单))?'


def _mount_intent(view, explicit):
    forward = (r'\s*(?:所\s*)?' + _CURRENT + _ASPECT
               + r'挂载(?:着)?的\s*(?:所有|全部)?\s*' + _VOLUME_OBJECT)
    if view == 'vm_volumes':
        return forward + _ROWS
    if view == 'vm_bootable_volumes':
        distinguish = (r'(?:\s*中\s*哪些是系统盘\s*[,，、]\s*哪些是数据盘'
                       r'|\s*[,，]?\s*(?:区分|分别查看)\s*系统盘(?:和|与|及)数据盘)')
        classified = forward + distinguish + _ROWS
        return r'(?:' + classified + r'|' + forward + _ROWS + ')' if explicit else classified
    # "几台" by itself requests a count. Only interrogative object phrases
    # containing 哪 are row-list synonyms here.
    target = r'(?:哪台|哪些|哪一台|哪几台|的)\s*' + _VM_OBJECT
    relation = (r'\s*' + _CURRENT + _ASPECT + r'(?:挂载|挂)\s*(?:到|在)了?\s*')
    return relation + target + r'(?:\s*上)?' + _ROWS


def _ground(question, parsed):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('question_required')
    view, name = parsed['view'], parsed['filters']['name']
    spec = VIEWS[view]
    text, explicit = _projection(question.strip(), spec['columns'])
    parent = _parent(_VOLUME_OBJECT if view == 'volume_vms' else _VM_OBJECT, name)
    intent = _mount_intent(view, explicit)
    if not re.fullmatch(_REQUEST + parent + intent + r'\s*[。.!！?？]*\s*', text, re.I):
        raise ValueError('unbound_role_value_or_unexpressed_request_clause')
    return {'view': view, 'filters': {'name': name}, 'columns': list(spec['columns']),
            'resources': list(spec['resources']), 'explicit_projection': explicit,
            'join': 'INNER', 'distinct': False, 'order': spec['order']}


def prepare_candidate(question, item, parsed, diagnostics=None):
    """Validate full original question and closed parameters, then ordinary item."""
    try:
        ordinary = _materialize(item, parsed)
        evidence = _ground(question, parsed)
    except (ValueError, TypeError) as exc:
        if diagnostics is not None:
            diagnostics.update(family_status='unsupported', family_error=str(exc))
        return None
    if diagnostics is not None:
        diagnostics.update(family_status='materialized', family_id=FAMILY_ID, contract_evidence=evidence)
    return ordinary
