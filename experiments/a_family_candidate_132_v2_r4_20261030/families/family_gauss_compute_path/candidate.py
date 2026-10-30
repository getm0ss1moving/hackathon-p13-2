"""Pure GaussDB compute-path candidate. No I/O, model, executor or old-ID routing."""
import copy
import itertools
import json
import re

FAMILY_ID = 'family_gauss_compute_path'
VIEWS = {'named_instance_vms': {'filters': ['name'],
                        'operator': 'equal',
                        'columns': ['instance_name', 'node_name', 'vm_name', 'vm_ip'],
                        'resources': ['GAUSSDB_INSTANCE'],
                        'api_call': {'method': 'GET',
                                     'url': '/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000',
                                     'condition': {'constraint': [{'simple': {'name': 'name',
                                                                              'value': '{{name}}',
                                                                              'operator': 'equal'}}]}},
                        'sql': 'SELECT CLOUD_GAUSSDB_INSTANCE.name AS instance_name, CLOUD_GAUSSDB_NODE.name '
                               'AS node_name, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS '
                               'vm_ip FROM CLOUD_GAUSSDB_INSTANCE INNER JOIN CLOUD_GAUSSDB_NODE ON '
                               'CLOUD_GAUSSDB_INSTANCE.id = CLOUD_GAUSSDB_NODE.ref_instanceId INNER JOIN '
                               'CLOUD_VM_NOVA ON CLOUD_GAUSSDB_NODE.ref_vmbmsId = CLOUD_VM_NOVA.id',
                        'join': 'INNER',
                        'dedup': 'none',
                        'order': 'none'},
 'vip_instance_hosts': {'filters': ['dataVip'],
                        'operator': 'contain',
                        'columns': ['instance_name', 'tenant_name', 'host_name'],
                        'resources': ['GAUSSDB_INSTANCE'],
                        'api_call': {'method': 'GET',
                                     'url': '/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000',
                                     'condition': {'constraint': [{'simple': {'name': 'dataVip',
                                                                              'value': '{{dataVip}}',
                                                                              'operator': 'contain'}}]}},
                        'sql': 'SELECT CLOUD_GAUSSDB_INSTANCE.name AS instance_name, '
                               'CLOUD_GAUSSDB_INSTANCE.vdcName AS tenant_name, CLOUD_HOST.name AS host_name '
                               'FROM CLOUD_GAUSSDB_INSTANCE INNER JOIN CLOUD_GAUSSDB_NODE ON '
                               'CLOUD_GAUSSDB_INSTANCE.id = CLOUD_GAUSSDB_NODE.ref_instanceId INNER JOIN '
                               'CLOUD_VM_NOVA ON CLOUD_GAUSSDB_NODE.ref_vmbmsId = CLOUD_VM_NOVA.id INNER '
                               'JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id',
                        'join': 'INNER',
                        'dedup': 'none',
                        'order': 'none'}}


ATOM = r'A-Za-z0-9_@./:#%+\-'


def _checked_materialize(item, parsed):
    if not isinstance(item, dict) or item.get('id') != FAMILY_ID or item.get('family_id') != FAMILY_ID:
        raise ValueError('wrong_family')
    if not isinstance(parsed, dict) or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ValueError('closed_parameter_schema_required')
    view = parsed['view']
    if not isinstance(view, str) or view not in VIEWS:
        raise ValueError('unknown_view')
    spec = VIEWS[view]
    filters, required = parsed['filters'], parsed['required_filters']
    if (not isinstance(filters, dict) or set(filters) != set(spec['filters'])
            or not isinstance(required, list) or any(not isinstance(x, str) for x in required)
            or len(required) != len(set(required)) or set(required) != set(filters)):
        raise ValueError('exact_filter_contract_required')
    for key, value in filters.items():
        if (not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value
                or '{{' in value or '}}' in value):
            raise ValueError('nonempty_original_text_required:' + key)
    ordinary = copy.deepcopy(item)
    for key in ['family_id', 'parameter_contract', 'default_params']:
        ordinary.pop(key, None)
    api = copy.deepcopy(spec['api_call'])
    for row in api['condition']['constraint']:
        row['simple']['value'] = filters[row['simple']['name']]
    ordinary.update(resources=copy.deepcopy(spec['resources']), api_call=api, sql=spec['sql'])
    return ordinary


def materialize_candidate(item, parsed):
    """Structural boundary only. prepare_candidate must ground the complete question."""
    try:
        return _checked_materialize(item, parsed)
    except (ValueError, TypeError):
        return None


def _quoted_tokens(text):
    """Finite quote lexer: JSON double quotes; literal single/curly/CJK quotes.

    Each tuple retains the entire original span and its complete decoded value.
    Invalid or unterminated quotes fail closed. No global text unescaping occurs.
    """
    decoder = json.JSONDecoder()
    literal_quotes = {"'": "'", '“': '”', '「': '」'}
    tokens = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            try:
                value, end = decoder.raw_decode(text, index)
            except (ValueError, TypeError) as exc:
                raise ValueError('invalid_JSON_quoted_entity') from exc
            if (not isinstance(value, str)
                    or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
                raise ValueError('invalid_JSON_string_value')
            tokens.append((index, end, value))
            index = end
        elif char in literal_quotes:
            end = text.find(literal_quotes[char], index + 1)
            if end < 0 or '\n' in text[index + 1:end] or '\r' in text[index + 1:end]:
                raise ValueError('unterminated_literal_quote')
            tokens.append((index, end + 1, text[index + 1:end]))
            index = end + 1
        elif char in {'”', '」'}:
            raise ValueError('unmatched_closing_quote')
        else:
            index += 1
    return tokens


def _quotes(text):
    return [(start, end) for start, end, _ in _quoted_tokens(text)]


def _inside(span, ranges):
    return any(a <= span[0] and span[1] <= b for a, b in ranges)


def _mask(text, spans):
    chars = list(text)
    for a, b in spans:
        chars[a:b] = ' ' * (b - a)
    return ''.join(chars)


def _label(value):
    if value.isascii():
        return r'(?<![' + ATOM + '])' + re.escape(value) + r'(?![' + ATOM + '])'
    return re.escape(value)


def _literal(value, text, left=True, tokens=None):
    if tokens is None:
        tokens = _quoted_tokens(text)
    # Only complete tokens whose decoded value equals the exact filter value qualify.
    options = [re.escape(text[start:end]) for start, end, decoded in tokens if decoded == value]
    if re.fullmatch('[' + ATOM + ']+', value):
        options.append((r'(?<![' + ATOM + '])' if left else '') + re.escape(value)
                       + r'(?![' + ATOM + '])')
    if not options:
        raise ValueError('complete_matching_entity_token_required')
    return '(?-i:(?:' + '|'.join(options) + '))'


RESOURCE = r'(?<![' + ATOM + r'])(?:CLOUD_GAUSSDB_INSTANCE|GAUSSDB_INSTANCE|GaussDB|RDS)(?![' + ATOM + r'])|数据库'


def _bind_filter(text, filters):
    key, value = next(iter(filters.items()))
    tokens = _quoted_tokens(text)
    quoted = [(start, end) for start, end, _ in tokens]
    candidates = []
    if key == 'name':
        roles = ['实例名称', '实例名', '名称', 'name']
        relation = r'\s*(?:(?:等于|为|是|=|:|：)\s*)?'
        role = '(?:' + '|'.join(_label(x) for x in roles) + ')'
        patterns = [(role + relation + _literal(value, text, tokens=tokens), False)]
        # Preserve the resource; mask only its directly attached name.
        prefix = '(?P<resource>(?:' + RESOURCE + r')(?:\s*实例)?)'
        patterns.append((prefix + r'\s*(?P<entity>' + _literal(value, text, left=False, tokens=tokens) + ')', True))
    else:
        role = '(?:' + '|'.join(_label(x) for x in ['业务地址', '业务IP', '实例IP', 'dataVip']) + ')'
        # Source wording "为" intentionally retains the contain API operator.
        patterns = [(role + r'\s*(?:(?:包含|含有|contain|为|是|:|：)\s*)?' + _literal(value, text, tokens=tokens), False)]
    for pattern, attached in patterns:
        for match in re.finditer(pattern, text, re.I):
            if _inside(match.span(), quoted):
                continue
            span = match.span('entity') if attached else match.span()
            candidates.append(span)
    candidates.sort(key=lambda s: (s[0], -s[1]))
    spans = []
    for span in candidates:
        if any(a <= span[0] and span[1] <= b for a, b in spans):
            continue
        spans.append(span)
    if len(spans) != 1:
        raise ValueError('single_grounded_filter_role_and_value_required')
    return _mask(text, spans)


FIELDS = {
    'instance_name': ['instance_name', 'CLOUD_GAUSSDB_INSTANCE.name', '数据库实例名', '实例名称', '实例名'],
    'node_name': ['node_name', 'CLOUD_GAUSSDB_NODE.name', '节点名称', '节点名'],
    'vm_name': ['vm_name', 'CLOUD_VM_NOVA.name', 'ECS实例名', '虚拟机名称', '虚拟机名'],
    'vm_ip': ['vm_ip', 'CLOUD_VM_NOVA.privateIps', 'ECS私有IP', '虚拟机私有IP', 'privateIps'],
    'tenant_name': ['tenant_name', 'CLOUD_GAUSSDB_INSTANCE.vdcName', '所属租户', '租户名称', '租户名', '租户'],
    'host_name': ['host_name', 'CLOUD_HOST.name', '宿主机名称', '宿主机名', '主机名'],
}


def _projection(text, columns):
    lookup = {alias.casefold(): key for key, aliases in FIELDS.items() for alias in aliases}
    markers = [m for m in re.finditer(r'(?:只需|仅|只)?(?:输出|返回|显示|展示)(?:字段|列)?(?:为|是|:|：)?\s*'
                                     r'|(?:字段|列)\s*(?:为|是|:|：|包括|包含)\s*', text)
               if not _inside(m.span(), _quotes(text))]
    if len(markers) > 1:
        raise ValueError('multiple_projection_clauses')
    if not markers:
        return text, False
    marker = markers[0]
    tail = text[marker.end():].strip().rstrip('。.;；!?！？ ')
    parts = re.split(r'\s*(?:、|,|，|和|与|及)\s*', tail)
    actual = [lookup.get(part.casefold()) for part in parts]
    if actual != columns:
        raise ValueError('explicit_projection_mismatch')
    return _mask(text, [(marker.start(), len(text))]), True


def _intent_pattern(view):
    if view == 'named_instance_vms':
        return (r'(?:的)?(?:(?:使用|关联使用|所用|所关联|关联)(?:的)?|运行(?:于|在)(?:哪些)?)'
                r'(?:ECS|VM_NOVA|虚拟机)(?:\s*实例)?(?:\s*(?:明细|列表|清单))?')
    roles = [r'实例名(?:称)?', r'(?:所属)?租户(?:名(?:称)?)?', r'(?:宿主机|主机)名(?:称)?']
    return r'(?:的)?(?:' + '|'.join(r'\s*[、,，和与及]\s*'.join(p) for p in itertools.permutations(roles)) + ')'


def _ground(question, parsed):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('question_required')
    spec = VIEWS[parsed['view']]
    text = _bind_filter(question, parsed['filters'])
    text, explicit = _projection(text, spec['columns'])
    matches = [m for m in re.finditer(_intent_pattern(parsed['view']), text, re.I)
               if not _inside(m.span(), _quotes(text))]
    if len(matches) > 1 or (not explicit and not matches):
        raise ValueError('single_complete_view_intent_required')
    text = _mask(text, [m.span() for m in matches])
    resources = [m for m in re.finditer(RESOURCE, text, re.I) if not _inside(m.span(), _quotes(text))]
    if len(resources) != 1:
        raise ValueError('single_database_resource_required')
    text = _mask(text, [m.span() for m in resources])
    glue = (r'请帮我|帮我查一下|帮我查询|请|帮我|查询|查看|列出|当前|所有|全部|实例|'
            r'明细|列表|清单|的|在|里|下|中|内')
    residue = re.sub(glue, ' ', text)
    residue = re.sub(r'[\s，,、。.;；!?！？:：()]+', '', residue)
    if residue:
        raise ValueError('unsupported_or_unexpressed_request_clause')
    return {'view': parsed['view'], 'filters': copy.deepcopy(parsed['filters']),
            'explicit_projection': explicit, 'columns': copy.deepcopy(spec['columns']),
            'join': 'INNER', 'dedup': 'none', 'order': 'none'}


def prepare_candidate(question, item, parsed, diagnostics=None):
    """Pure complete-question boundary. Supported -> ordinary item; otherwise None."""
    try:
        ordinary = _checked_materialize(item, parsed)
        evidence = _ground(question, parsed)
    except (ValueError, TypeError) as exc:
        if diagnostics is not None:
            diagnostics.update(family_status='unsupported', family_error=str(exc))
        return None
    if diagnostics is not None:
        diagnostics.update(family_status='materialized', family_id=FAMILY_ID, contract_evidence=evidence)
    return ordinary
