"""Closed ECS/FLAVOR details and source aggregate views; no runtime old-ID routing.

This candidate does not invoke models, services, SDKs, SQL refinement or executors.
B retains ownership of full selection/refinement/official empty serialization.
COUNT business acceptance and native loading/pagination are unresolved.
"""
import copy
import itertools
import json
import re

ATOM = r'A-Za-z0-9_@./:#%+\-'

FAMILY_ID = 'family_f03_spec'
VIEWS = {'vm_status_size': {'filters': ['name'],
                    'columns': ['vm_name', 'status', 'vcpuSize', 'ramSize', 'diskSize'],
                    'api_call': [{'method': 'GET',
                                  'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                  'condition': {'constraint': [{'simple': {'name': 'name',
                                                                           'value': '{{name}}',
                                                                           'operator': 'equal'}}]}},
                                 {'method': 'GET',
                                  'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                                  'autoPagination': True,
                                  'condition': {'constraint': [{'simple': {'name': 'id',
                                                                           'value': '{{flavorId from step '
                                                                                    '1}}',
                                                                           'operator': 'equal'}}]}}],
                    'sql': 'SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.status, '
                           'CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize FROM '
                           'CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = '
                           'CLOUD_FLAVOR.id',
                    'order': 'none',
                    'join': 'INNER'},
 'tenant_specs': {'filters': ['tenantName', 'logicalRegionName'],
                  'columns': ['vm_name', 'status', 'flavor_name', 'vcpuSize', 'ramSize', 'diskSize'],
                  'api_call': [{'method': 'GET',
                                'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                'condition': {'constraint': [{'simple': {'name': 'tenantName',
                                                                         'value': '{{tenantName}}',
                                                                         'operator': 'equal'}},
                                                             {'simple': {'name': 'logicalRegionName',
                                                                         'value': '{{logicalRegionName}}',
                                                                         'operator': 'equal'}}]}},
                               {'method': 'GET',
                                'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                                'autoPagination': True,
                                'condition': {'constraint': [{'simple': {'name': 'id',
                                                                         'value': '{{flavorId from step 1}}',
                                                                         'operator': 'equal'}}]}}],
                  'sql': 'SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.status, CLOUD_FLAVOR.name AS '
                         'flavor_name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize '
                         'FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = '
                         'CLOUD_FLAVOR.id',
                  'order': 'none',
                  'join': 'INNER'},
 'tenant_specs_by_az': {'filters': ['tenantName', 'logicalRegionName'],
                        'columns': ['azoneName', 'vm_name', 'flavor_name', 'status'],
                        'api_call': [{'method': 'GET',
                                      'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                      'condition': {'constraint': [{'simple': {'name': 'tenantName',
                                                                               'value': '{{tenantName}}',
                                                                               'operator': 'equal'}},
                                                                   {'simple': {'name': 'logicalRegionName',
                                                                               'value': '{{logicalRegionName}}',
                                                                               'operator': 'equal'}}]}},
                                     {'method': 'GET',
                                      'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                                      'autoPagination': True,
                                      'condition': {'constraint': [{'simple': {'name': 'id',
                                                                               'value': '{{flavorId from '
                                                                                        'step 1}}',
                                                                               'operator': 'equal'}}]}}],
                        'sql': 'SELECT azoneName, CLOUD_VM_NOVA.name AS vm_name, CLOUD_FLAVOR.name AS '
                               'flavor_name, CLOUD_VM_NOVA.status FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR '
                               'ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id ORDER BY azoneName',
                        'order': 'azoneName',
                        'join': 'INNER'},
 'scoped_vm_ip_flavor': {'filters': ['logicalRegionName', 'status'],
                         'columns': ['vm_name', 'private_ips', 'flavor_name'],
                         'api_call': [{'method': 'GET',
                                       'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                       'condition': {'constraint': [{'simple': {'name': 'logicalRegionName',
                                                                                'value': '{{logicalRegionName}}',
                                                                                'operator': 'equal'}},
                                                                    {'simple': {'name': 'status',
                                                                                'value': '{{status}}',
                                                                                'operator': 'equal'}}]}},
                                      {'method': 'GET',
                                       'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                                       'autoPagination': True,
                                       'condition': {'constraint': [{'simple': {'name': 'id',
                                                                                'value': '{{flavorId from '
                                                                                         'step 1}}',
                                                                                'operator': 'equal'}}]}}],
                         'sql': 'SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS '
                                'private_ips, CLOUD_FLAVOR.name AS flavor_name FROM CLOUD_VM_NOVA LEFT JOIN '
                                'CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id',
                         'order': 'none',
                         'join': 'LEFT'}}


# Aggregate contracts remain separate from the four original detail views.
VIEWS.update({'flavor_topk': {'filters': [],
                 'columns': ['flavor_name', 'vcpuSize', 'ramSize', 'diskSize', 'count'],
                 'api_call': [{'method': 'GET',
                               'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000'},
                              {'method': 'GET',
                               'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                               'autoPagination': True,
                               'condition': {'constraint': [{'simple': {'name': 'id',
                                                                        'value': '{{flavorId from '
                                                                                 'step 1}}',
                                                                        'operator': 'equal'}}]}}],
                 'sql': 'SELECT CLOUD_FLAVOR.name AS flavor_name, CLOUD_FLAVOR.vcpuSize, '
                        'CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize, COUNT(*) AS count FROM '
                        'CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = '
                        'CLOUD_FLAVOR.id GROUP BY CLOUD_FLAVOR.name, CLOUD_FLAVOR.vcpuSize, '
                        'CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize ORDER BY count DESC LIMIT 10',
                 'order': 'count DESC',
                 'join': 'INNER',
                 'filter_sets': [[], ['logicalRegionName']],
                 'regional_api_call': [{'method': 'GET',
                                        'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                        'condition': {'constraint': [{'simple': {'name': 'logicalRegionName',
                                                                                 'value': '{{logicalRegionName}}',
                                                                                 'operator': 'equal'}}]}},
                                       {'method': 'GET',
                                        'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                                        'autoPagination': True,
                                        'condition': {'constraint': [{'simple': {'name': 'id',
                                                                                 'value': '{{flavorId '
                                                                                          'from '
                                                                                          'step '
                                                                                          '1}}',
                                                                                 'operator': 'equal'}}]}}]},
 'tenant_flavor_distribution': {'filters': ['logicalRegionName'],
                                'columns': ['tenantName',
                                            'flavor_name',
                                            'vcpuSize',
                                            'ramSize',
                                            'count'],
                                'api_call': [{'method': 'GET',
                                              'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                              'condition': {'constraint': [{'simple': {'name': 'logicalRegionName',
                                                                                       'value': '{{logicalRegionName}}',
                                                                                       'operator': 'equal'}}]}},
                                             {'method': 'GET',
                                              'url': '/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000',
                                              'autoPagination': True,
                                              'condition': {'constraint': [{'simple': {'name': 'id',
                                                                                       'value': '{{flavorId '
                                                                                                'from '
                                                                                                'step '
                                                                                                '1}}',
                                                                                       'operator': 'equal'}}]}}],
                                'sql': 'SELECT tenantName, CLOUD_FLAVOR.name AS flavor_name, '
                                       'CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, COUNT(*) AS '
                                       'count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON '
                                       'CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id GROUP BY '
                                       'tenantName, CLOUD_FLAVOR.name, CLOUD_FLAVOR.vcpuSize, '
                                       'CLOUD_FLAVOR.ramSize',
                                'order': 'none',
                                'join': 'INNER'}})

def _checked_materialize(item, parsed):
    if not isinstance(item, dict) or item.get('family_id') != FAMILY_ID:
        raise ValueError('wrong_family')
    if not isinstance(parsed, dict):
        raise ValueError('closed_parameter_schema_required')
    view = parsed.get('view')
    keys = {'view', 'filters', 'required_filters'}
    if view == 'flavor_topk':
        keys.add('top_k')
    if set(parsed) != keys:
        raise ValueError('closed_parameter_schema_required')
    if view == 'flavor_topk' and (type(parsed['top_k']) is not int or parsed['top_k'] != 10):
        raise ValueError('only_source_top10_supported')
    if not isinstance(view, str) or view not in VIEWS:
        raise ValueError('unknown_view')
    spec = VIEWS[view]
    filters, required = parsed['filters'], parsed['required_filters']
    if (not isinstance(filters, dict) or any(not isinstance(k, str) for k in filters)
            or set(filters) not in [set(fields) for fields in spec.get('filter_sets', [spec['filters']])] or not isinstance(required, list)
            or any(not isinstance(k, str) for k in required)
            or len(required) != len(set(required)) or set(required) != set(filters)):
        raise ValueError('exact_filter_contract_required')
    for field, value in filters.items():
        if (not isinstance(value, str) or not value.strip() or '{{' in value or '}}' in value
                or any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
            raise ValueError('nonempty_original_text_required:' + field)
    api = copy.deepcopy(spec['regional_api_call'] if view == 'flavor_topk' and filters else spec['api_call'])
    for constraint in api[0].get('condition', {}).get('constraint', []):
        field = constraint['simple']['name']
        constraint['simple']['value'] = filters[field]
    ordinary = copy.deepcopy(item)
    for key in ['family_id', 'parameter_contract', 'default_params']:
        ordinary.pop(key, None)
    ordinary.update(api_call=api, sql=spec['sql'])
    return ordinary


def materialize_candidate(item, parsed):
    """Closed structural contract -> ordinary item; invalid input -> None.

    This function does not validate a question. prepare_candidate is required
    for original text/role/output evidence before any runtime execution.
    """
    try:
        return _checked_materialize(item, parsed)
    except (ValueError, TypeError):
        return None


def quote_tokens(text):
    """Return tuple of {start, end, value, quote}; malformed quoting raises.

    Raw line breaks inside a token and isolated closing Chinese quotes are not
    accepted. No quote is inserted and no backslash is removed globally.
    """
    if not isinstance(text, str):
        raise ValueError('question_text_required')
    decoder = json.JSONDecoder()
    raw_pairs = {"'": "'", '“': '”', '「': '」'}
    tokens, position = [], 0
    while position < len(text):
        opening = text[position]
        if opening == '"':
            try:
                value, end = decoder.raw_decode(text, position)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError('invalid_or_unclosed_JSON_quoted_literal') from exc
            if not isinstance(value, str):
                raise ValueError('quoted_literal_must_decode_to_string')
        elif opening in raw_pairs:
            end_at = text.find(raw_pairs[opening], position + 1)
            if end_at < 0:
                raise ValueError('unclosed_raw_quoted_literal')
            value = text[position + 1:end_at]
            if '\n' in value or '\r' in value:
                raise ValueError('raw_quoted_literal_line_break')
            end = end_at + 1
        elif opening in {'”', '」'}:
            raise ValueError('unmatched_quoted_literal_closer')
        else:
            position += 1
            continue
        if any(ord(character) < 32 or 0x7F <= ord(character) <= 0x9F or 0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError('invalid_unicode_scalar_in_quoted_literal')
        tokens.append({'start': position, 'end': end, 'value': value,
                       'quote': opening})
        position = end
    return tuple(tokens)


def _quoted(text):
    return [(token['start'], token['end']) for token in quote_tokens(text)]


def _inside(span, ranges):
    return any(a <= span[0] and span[1] <= b for a, b in ranges)


def _mask(text, spans):
    chars = list(text)
    for a, b in spans:
        chars[a:b] = ' ' * (b - a)
    return ''.join(chars)


def _label(value):
    return (r'(?<![' + ATOM + '])' + re.escape(value) + r'(?![' + ATOM + '])'
            if value.isascii() else re.escape(value))


def _literal(value, text, left=True):
    # Quoted entities bind by a complete original token plus its decoded value,
    # not by serialized spelling or a substring occurring elsewhere.
    options = [re.escape(text[token['start']:token['end']])
               for token in quote_tokens(text) if token['value'] == value]
    if re.fullmatch(r'[' + ATOM + ']+', value):
        options.append((r'(?<![' + ATOM + '])' if left else '') + re.escape(value) + r'(?![' + ATOM + '])')
    if not options:
        raise ValueError('unsupported_or_unbound_entity_literal')
    return '(?-i:(?:' + '|'.join(options) + '))'


def _entity_match_allowed(span, tokens, value):
    # No role may start inside a different opaque token or cross its boundary.
    return all(not (span[0] < token['end'] and token['start'] < span[1])
               or (span[0] <= token['start'] and token['end'] <= span[1]
                   and token['value'] == value)
               for token in tokens)


def _quote(value):
    return json.dumps(value, ensure_ascii=False)


def _normalize_name(text, filters):
    if 'name' not in filters:
        return text
    resource = r'(?P<resource>(?:ECS|VM_NOVA|虚拟机)(?:\s*实例)?)'
    pattern = r'(?<![' + ATOM + '])' + resource + r'\s*' + _literal(filters['name'], text, left=False)
    tokens = quote_tokens(text)
    matches = [m for m in re.finditer(pattern, text, re.I)
               if _entity_match_allowed(m.span(), tokens, filters['name'])]
    if len(matches) > 1:
        raise ValueError('multiple_implicit_names')
    if matches:
        m = matches[0]
        return text[:m.start()] + m['resource'] + '，名称=' + _quote(filters['name']) + text[m.end():]
    return text


_FIELDS = {
    'vm_name': ['CLOUD_VM_NOVA.name', 'vm_name', 'name', '实例名称', '实例名', '虚拟机名'],
    'status': ['CLOUD_VM_NOVA.status', 'status', '状态'],
    'flavor_name': ['CLOUD_FLAVOR.name', 'flavor_name', '规格名称', '规格名'],
    'vcpuSize': ['CLOUD_FLAVOR.vcpuSize', 'vcpuSize', 'vCPU核数', 'CPU核数'],
    'ramSize': ['CLOUD_FLAVOR.ramSize', 'ramSize', '内存'],
    'diskSize': ['CLOUD_FLAVOR.diskSize', 'diskSize', '磁盘'],
    'azoneName': ['azoneName', '可用区'],
    'tenantName': ['tenantName', '租户名称', '租户名'],
    'count': ['count', '数量', '实例数', '计数'],
    'private_ips': ['CLOUD_VM_NOVA.privateIps', 'private_ips', 'privateIps', 'IP地址', 'IP'],
}


def _projection(text, columns):
    aliases = {alias: field for field, names in _FIELDS.items() for alias in names}
    lookup = {k.casefold(): v for k, v in aliases.items()}
    pattern = '(?:' + '|'.join(_label(a) for a in sorted(aliases, key=len, reverse=True)) + ')'
    markers = list(re.finditer(r'(?:只需|仅|只)?(?:输出|返回|显示|展示)(?:字段|列)?(?:为|是|:|：)?\s*'
                               r'|(?:字段|列)\s*(?:为|是|:|：|包括|包含)\s*', text))
    projection = None
    for marker in markers:
        if _inside(marker.span(), _quoted(text)):
            continue
        tail = text[marker.end():].strip().rstrip('。.;；!?！？ ')
        parts = re.split(r'\s*(?:、|,|，|和|与|及|/)\s*', tail)
        first_known = bool(parts and re.fullmatch(pattern, parts[0], re.I))
        strong = bool(re.search(r'输出|返回|字段|列|仅|只', marker.group()))
        if not first_known:
            if strong:
                raise ValueError('unrecognized_explicit_output')
            continue
        if any(not re.fullmatch(pattern, part, re.I) for part in parts):
            raise ValueError('unsupported_explicit_projection')
        actual = [lookup[part.casefold()] for part in parts]
        if actual != columns:
            raise ValueError('explicit_projection_mismatch')
        if projection is not None:
            raise ValueError('multiple_projection_clauses')
        projection = (marker.start(), len(text))
    return (_mask(text, [projection]), True) if projection else (text, False)


def _permutations(groups):
    return ['(?:' + r'\s*[、,，和与及]\s*'.join(order) + ')' for order in itertools.permutations(groups)]


def _intent_pattern(view):
    name, flavor, status = r'实例名(?:称)?', r'(?:所属)?规格(?:名称|配置)?', r'状态'
    if view == 'vm_status_size':
        variants = _permutations([status, flavor])
    elif view == 'tenant_specs':
        variants = _permutations([name, flavor, status]) + _permutations([flavor, status])
    elif view == 'tenant_specs_by_az':
        variants = (_permutations([name, flavor, status]) + _permutations([name, flavor])
                    + [r'(?:所属)?规格(?:名称)?列表'])
    else:
        variants = _permutations([name, r'IP(?:地址)?', flavor])
    return r'(?:的)?(?:' + '|'.join(variants) + r')(?:\s*(?:分别)?(?:是)?(?:什么|哪些)(?:呢)?)?'


_ROLES = {
    'name': ['实例名称', '实例名', '名称', 'name'],
    'tenantName': ['tenantName', '租户名称', '租户名', '租户'],
    'logicalRegionName': ['logicalRegionName', '区域', '地区', '地域', 'region'],
    'status': ['status', '状态'],
}
_STATUS = {'active': ['正在运行', '正在跑', '运行中'], 'stopped': ['已停止', '停机']}


def _bind_filters(text, filters):
    tokens = quote_tokens(text)
    quoted = [(token['start'], token['end']) for token in tokens]
    candidates = []
    equal = r'\s*(?:(?:为|是|等于|=|:|：)\s*)?'
    for field, value in filters.items():
        role = '(?:' + '|'.join(_label(a) for a in sorted(_ROLES[field], key=len, reverse=True)) + ')'
        literal = _literal(value, text)
        for pattern in [role + equal + literal, literal + r'\s*(?:(?:为|是|等于)\s*)?' + role]:
            for m in re.finditer(pattern, text, re.I):
                if _entity_match_allowed(m.span(), tokens, value):
                    candidates.append((m.start(), m.end(), field))
        if field == 'status' and value in _STATUS:
            aliases = '(?:' + '|'.join(_STATUS[value]) + ')'
            for m in re.finditer(r'(?:状态\s*(?:为|是|=)?\s*)?' + aliases, text):
                if not _inside(m.span(), quoted):
                    candidates.append((m.start(), m.end(), field))
    candidates.sort(key=lambda row: (row[0], -(row[1] - row[0])))
    seen, spans, end = set(), [], -1
    for start, stop, field in candidates:
        if start < end:
            continue
        if field in seen:
            raise ValueError('repeated_filter_role:' + field)
        seen.add(field)
        spans.append((start, stop))
        end = stop
    if seen != set(filters):
        raise ValueError('unbound_or_wrong_role_or_value')
    return _mask(text, spans)



def _ground_aggregate(question, parsed):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('question_required')
    view, filters = parsed['view'], parsed['filters']
    # Bind complete decoded literals before interpreting syntax or output words.
    text = _bind_filters(question, filters)
    layout = r'(?:按照|按)\s*租户\s*分别展示'
    layouts = list(re.finditer(layout, text)) if view == 'tenant_flavor_distribution' else []
    if len(layouts) > 1:
        raise ValueError('multiple_tenant_layouts')
    text = _mask(text, [m.span() for m in layouts])
    text, explicit = _projection(text, VIEWS[view]['columns'])
    resource = r'(?<![' + ATOM + r'])(?:CLOUD_VM_NOVA|VM_NOVA|ECS)(?![' + ATOM + r'])(?:\s*实例)?|虚拟机(?:实例)?'
    resources = list(re.finditer(resource, text, re.I))
    if len(resources) != 1:
        raise ValueError('single_ECS_resource_required')
    text = _mask(text, [m.span() for m in resources])
    if view == 'flavor_topk':
        # K is an obligation from the original question, never an implicit cap.
        intent = (r'(?:使用(?:数量|次数)?最多|使用量最多|数量最多|用得最多)(?:的)?\s*'
                  r'(?:前\s*10\s*种\s*规格|Top\s*10\s*(?:种)?\s*规格)')
    else:
        intent = r'(?:各(?:个)?|每(?:个)?)租户(?:的)?\s*规格(?:使用)?分布'
    intents = list(re.finditer(intent, text, re.I))
    if len(intents) != 1:
        raise ValueError('complete_single_aggregate_intent_required')
    text = _mask(text, [m.span() for m in intents])
    glue = r'请帮我|帮我查询|帮我查一下|请|帮我|查询|查看|统计|列出|当前|所有|全部|实例|的|在|里|下|中|内'
    residue = re.sub(glue, ' ', text, flags=re.I)
    residue = re.sub(r'[\s，,、。.;；!?！？:：()（）]+', '', residue)
    if residue:
        raise ValueError('unsupported_or_unexpressed_aggregate_clause')
    return {'view': view, 'filters': copy.deepcopy(filters), 'explicit_projection': explicit,
            'columns': VIEWS[view]['columns'], 'join': 'INNER', 'order': VIEWS[view]['order'],
            'scope': 'regional' if filters else 'global', 'COUNT_business_gate': 'BLOCKED_UNCHANGED'}


def _ground(question, parsed):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('question_required')
    view, filters = parsed['view'], parsed['filters']
    if view in {'flavor_topk', 'tenant_flavor_distribution'}:
        return _ground_aggregate(question, parsed)
    text = _normalize_name(question, filters)
    # Fixed source sorting is a view contract, never a GROUP BY.
    sorts = []
    if view == 'tenant_specs_by_az':
        pattern = r'(?:按照|按)\s*(?:可用区|azoneName)\s*(?:升序\s*)?排序(?:\s*升序)?'
        sorts = [m.span() for m in re.finditer(pattern, text, re.I) if not _inside(m.span(), _quoted(text))]
        if len(sorts) > 1:
            raise ValueError('multiple_sort_claims')
        text = _mask(text, sorts)
    text, explicit = _projection(text, VIEWS[view]['columns'])
    # A terminal explicit projection proves the output contract, but does not
    # erase a complete natural request preceding it. Consume only a complete
    # same-view phrase; unmatched or conflicting semantic obligations survive.
    layouts = []
    if view == 'tenant_specs_by_az':
        pattern = r'(?:各个|每个|各)\s*(?:可用区|AZ)(?:中)?(?:的)?'
        layouts = [m.span() for m in re.finditer(pattern, text, re.I) if not _inside(m.span(), _quoted(text))]
        if len(layouts) > 1 or (not explicit and not layouts and not sorts):
            raise ValueError('AZ_row_layout_required')
        text = _mask(text, layouts)
    matches = [m for m in re.finditer(_intent_pattern(view), text) if not _inside(m.span(), _quoted(text))]
    if len(matches) > 1 or (not explicit and len(matches) != 1):
        raise ValueError('complete_single_view_intent_required')
    text = _mask(text, [m.span() for m in matches])
    text = _bind_filters(text, filters)
    resource = r'(?<![' + ATOM + r'])(?:CLOUD_VM_NOVA|VM_NOVA|ECS)(?![' + ATOM + r'])(?:\s*实例)?|虚拟机(?:实例)?'
    matches = list(re.finditer(resource, text, re.I))
    if len(matches) != 1:
        raise ValueError('single_ECS_resource_required')
    text = _mask(text, [m.span() for m in matches])
    glue = (r'请帮我|帮我查询|帮我查一下|请|帮我|查询|查看|列出|显示|展示|当前|所有|全部|'
            r'实例|明细|列表|清单|的|在|里|下|中|内|以及|并且|且|并|和|与|及|(?<![' + ATOM + r'])AND(?![' + ATOM + r'])')
    residue = re.sub(glue, ' ', text, flags=re.I)
    residue = re.sub(r'[\s，,、。.;；!?！？:：()]+', '', residue)
    if residue:
        raise ValueError('unsupported_or_unexpressed_request_clause')
    return {'view': view, 'filters': copy.deepcopy(filters), 'explicit_projection': explicit,
            'columns': VIEWS[view]['columns'], 'join': VIEWS[view]['join'], 'order': VIEWS[view]['order']}


def prepare_candidate(question, item, parsed, diagnostics=None):
    """Pure handoff boundary. Success ordinary item; unsupported None."""
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
