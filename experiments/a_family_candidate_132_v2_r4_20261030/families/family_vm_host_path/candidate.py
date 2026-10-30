"""Closed detail and count views; COUNT business gates remain unresolved. Pure stdlib; no model, service, executor or old-ID routing.

Runtime must use prepare_candidate. materialize_candidate validates structure only.
"""
from copy import deepcopy
import json
import re

FAMILY_ID = 'family_vm_host_path'
VIEWS = {'private_ip_host': {'filters': ['privateIps'],
                     'columns': ['vm_name', 'privateIps', 'host_name', 'host_ip'],
                     'resources': ['VM_NOVA'],
                     'api_call': {'method': 'GET',
                                  'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                  'condition': {'constraint': [{'simple': {'name': 'privateIps',
                                                                           'value': '{{privateIps}}',
                                                                           'operator': 'contain'}}]}},
                     'sql': 'SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps, '
                            'CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS host_ip FROM '
                            'CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = '
                            'CLOUD_HOST.id'},
 'vm_host': {'filters': ['name'],
             'columns': ['vm_name', 'host_name', 'host_ip'],
             'resources': ['VM_NOVA'],
             'api_call': {'method': 'GET',
                          'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                          'condition': {'constraint': [{'simple': {'name': 'name',
                                                                   'value': '{{name}}',
                                                                   'operator': 'equal'}}]}},
             'sql': 'SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_HOST.name AS host_name, '
                    'CLOUD_HOST.ipAddress AS host_ip FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON '
                    'CLOUD_VM_NOVA.hostId = CLOUD_HOST.id'},
 'vm_host_server': {'filters': ['name'],
                    'columns': ['vm_name', 'host_name', 'host_ip', 'server_name', 'server_id'],
                    'resources': ['VM_NOVA'],
                    'api_call': {'method': 'GET',
                                 'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                 'condition': {'constraint': [{'simple': {'name': 'name',
                                                                          'value': '{{name}}',
                                                                          'operator': 'equal'}}]}},
                    'sql': 'SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_HOST.name AS host_name, '
                           'CLOUD_HOST.ipAddress AS host_ip, SYS_X86Server.name AS server_name, '
                           'SYS_X86Server.id AS server_id FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST '
                           'ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id INNER JOIN SYS_X86Server ON '
                           'CLOUD_HOST.serverId = SYS_X86Server.id'},
 'host_vm_total': {'filters': ['name', 'status'],
                   'columns': ['total'],
                   'resources': ['HOST', 'VM_NOVA'],
                   'api_call': [{'method': 'GET',
                                 'url': '/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000',
                                 'condition': {'constraint': [{'simple': {'name': 'name',
                                                                          'value': '{{name}}',
                                                                          'operator': 'equal'}}]}},
                                {'method': 'GET',
                                 'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
                                 'condition': {'constraint': [{'simple': {'name': 'hostId',
                                                                          'value': '{{id from step '
                                                                                   '1}}',
                                                                          'operator': 'equal'}},
                                                              {'simple': {'name': 'status',
                                                                          'value': '{{status}}',
                                                                          'operator': 'equal'}}]}}],
                   'sql': 'SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA'},
 'host_vm_status_distribution': {'filters': ['name'],
                                 'columns': ['status', 'count'],
                                 'resources': ['HOST'],
                                 'api_call': {'method': 'GET',
                                              'url': '/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000',
                                              'condition': {'constraint': [{'simple': {'name': 'name',
                                                                                       'value': '{{name}}',
                                                                                       'operator': 'equal'}}]}},
                                 'sql': 'SELECT CLOUD_VM_NOVA.status, COUNT(*) AS count FROM '
                                        'CLOUD_HOST INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = '
                                        'CLOUD_VM_NOVA.hostId GROUP BY CLOUD_VM_NOVA.status'}}
ATOM = r'A-Za-z0-9_@./:#%+\-'
PAIRS = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」'}
VM = r'(?:ECS(?:\s*实例)?|虚拟机(?:\s*实例)?|VM_NOVA|VM)'
HOST = r'(?:宿主机|宿主|HOST)'
SERVICE = r'(?:云服务|S_CloudService)'
APPLICATION = r'(?:应用(?:系统)?|Application)'
PREFIX = r'\s*(?:(?:请帮我|帮我|麻烦|请)\s*)?(?:(?:查询|查看|查找|列出|查一下|看一下)\s*)?'
END = r'\s*[。.!！?？]*\s*'
OUTPUT_ALIASES = {'vm_name': ['虚拟机名', 'ECS名称'],
 'privateIps': ['私有IP'],
 'host_name': ['宿主机名'],
 'host_ip': ['宿主机IP'],
 'server_name': ['物理机名'],
 'server_id': ['物理机ID']}


OUTPUT_ALIASES.update(total=['总数', '数量'], count=['数量', '计数'], status=['状态'])

def _validate(item, parsed):
    if type(item) is not dict or item.get('id') != FAMILY_ID or item.get('family_id') != FAMILY_ID:
        raise ValueError('selected_family_required')
    if type(parsed) is not dict or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ValueError('closed_parameter_schema_required')
    view = parsed['view']
    if type(view) is not str or view not in VIEWS:
        raise ValueError('unknown_detail_view')
    spec = VIEWS[view]
    filters, required = parsed['filters'], parsed['required_filters']
    if (type(filters) is not dict or not any(set(filters) == set(keys)
            for keys in spec.get('filter_sets', [spec['filters']]))):
        raise ValueError('exact_view_filter_keys_required')
    if (type(required) is not list or any(type(k) is not str for k in required)
            or len(set(required)) != len(required) or set(required) != set(filters)):
        raise ValueError('required_filters_not_exact')
    for value in filters.values():
        if (type(value) is not str or not value or value != value.strip()
                or '{{' in value or '}}' in value or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f for c in value)):
            raise ValueError('nonempty_original_question_string_required')
    keys = [k for k in spec['filters'] if k in filters]
    return {'view': view, 'filters': {k: filters[k] for k in keys},
            'required_filters': keys}


def _materialize(item, config):
    spec = VIEWS[config['view']]
    ordinary = deepcopy(item)
    for key in ('family_id', 'parameter_contract', 'default_params', 'params', 'family_parameters'):
        ordinary.pop(key, None)
    api = deepcopy(spec['api_call'])
    # Preserve list-vs-object, order, operators, dependency placeholders and flags.
    # Dependency values must reach the fixed executor intact; empty/failed parent
    # execution is not handled or certified by this pure helper.
    steps = api if type(api) is list else [api]
    for step in steps:
        constraints = step['condition']['constraint']
        if 'filter_sets' in spec:
            constraints[:] = [c for c in constraints
                              if c['simple']['name'] in config['filters']]
        for constraint in constraints:
            simple = constraint['simple']
            value = simple['value']
            if value.startswith('{{') and value.endswith('}}'):
                parameter = value[2:-2]
                if parameter in config['filters']:
                    simple['value'] = config['filters'][parameter]
                elif not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]* from step [1-9][0-9]*', parameter):
                    raise ValueError('unresolved_parameter')
    ordinary.update(resources=deepcopy(spec['resources']), api_call=api, sql=spec['sql'])
    return ordinary


def materialize_candidate(item, parsed):
    """Structure-only materializer; cannot authorize a question for execution."""
    try:
        return _materialize(item, _validate(item, parsed))
    except (ValueError, TypeError, KeyError):
        return None


def quote_tokens(text):
    """Return tuple of {start, end, value, quote}; malformed quoting raises.

    Raw line breaks inside a token and isolated closing Chinese quotes are not
    accepted. No quote is inserted and no backslash is removed globally.
    """
    if not isinstance(text, str):
        raise ValueError('question_text_required')
    decoder = json.JSONDecoder()
    raw_pairs = {"'": "'", '“': '”', '‘': '’', '「': '」'}
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
        elif opening in {'”', '’', '」'}:
            raise ValueError('unmatched_quoted_literal_closer')
        else:
            position += 1
            continue
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError('invalid_unicode_scalar_in_quoted_literal')
        tokens.append({'start': position, 'end': end, 'value': value,
                       'quote': opening})
        position = end
    return tuple(tokens)


def _literal(value, quote_context):
    text, tokens = quote_context
    # Each option is one complete original token, admitted by decoded equality.
    # JSON is decoded by quote_tokens exactly once, never by this role binder.
    variants = [re.escape(text[token['start']:token['end']])
                for token in tokens if token['value'] == value]
    if re.fullmatch('[' + ATOM + ']+', value):
        variants.append(re.escape(value) + '(?![' + ATOM + '])')
    if not variants:
        return r'(?!)'
    return '(?-i:(?:' + '|'.join(dict.fromkeys(variants)) + '))'


def _operand(value, operator, quote_context):
    literal = _literal(value, quote_context)
    bridge = (r'(?:等于|为|是|=|:|：)' if operator == 'equal'
              else r'(?:包含|含有|含|为|是|:|：|contain)')
    # The complete literal still precedes optional operator parsing.
    return r'\s*(?:' + literal + r'|' + bridge + r'\s*' + literal + ')'


def _binding(labels, value, quote_context, operator='equal'):
    return r'(?:' + labels + ')' + _operand(value, operator, quote_context)


def _parent(resource, value, quote_context, field='name', operator='equal'):
    labels = r'(?:名称|名字|name)' if field == 'name' else r'(?:索引名称|索引名|索引|indexName)'
    named = _binding(labels, value, quote_context, operator)
    operand = _operand(value, operator, quote_context)
    return (r'(?:' + resource + r'\s*(?:' + named + '|' + operand + ')|'
            + named + r'\s*的?\s*' + resource + ')')


def _projection(question, columns, tokens):
    spans = [(token['start'], token['end']) for token in tokens]
    markers = [m for m in re.finditer(
        r'(?:仅|只)?\s*(?:依次|按顺序)?\s*(?:输出|返回|显示|展示)(?:的)?(?:字段|列)?\s*(?:为|是|:|：)?\s*', question)
        if not any(a <= m.start() < b for a, b in spans)]
    if not markers:
        return question, False
    if len(markers) != 1:
        raise ValueError('single_projection_clause_required')
    marker = markers[0]
    tail = question[marker.end():].strip().rstrip('。.;；!?！？ ')
    fields = re.split(r'\s*(?:、|,|，|和|与|及)\s*', tail)
    lookup = {c.casefold(): c for c in columns}
    lookup.update({alias.casefold(): field for field in columns for alias in OUTPUT_ALIASES.get(field, [])})
    try:
        actual = [lookup[field.strip().casefold()] for field in fields]
    except KeyError as exc:
        raise ValueError('unknown_explicit_column') from exc
    if actual != columns:
        raise ValueError('explicit_column_order_or_shape_mismatch')
    return question[:marker.start()].rstrip('，,、;； '), True


def _detail_intent(view, filters, explicit, quote_context):
    if view == 'private_ip_host':
        value = filters['privateIps']
        ip = _binding('私有IP|私网IP|privateIps|IP', value, quote_context, 'contain')
        original = _literal(value, quote_context) + '\\s*(?:这个|该)?IP是哪台虚拟机的\\s*[,，]\\s*它跑在哪台宿主机上'
        simple = ip + '\\s*的\\s*(?:VM|虚拟机|ECS)(?:及|和|与)宿主机(?:信息|归属)?'
        return '(?:' + original + '|' + simple + ')'
    parent = _parent(VM, filters['name'], quote_context)
    if view == 'vm_host_server':
        intent = '\\s*的完整归属链(?:\\s*[（(]\\s*VM\\s*→\\s*宿主机\\s*→\\s*物理机\\s*[）)])?|\\s*的VM到宿主机到物理机归属链'
    else:
        intent = '\\s*(?:的)?(?:跑在|运行在|位于)哪(?:一)?台宿主机上?|\\s*的宿主机(?:信息|归属)?'
    return parent + '(?:' + intent + ')'




def _status_literal(value, quote_context):
    literal = _literal(value, quote_context)
    # Natural all-caps status spelling can bind its lowercase parameter, without
    # an entity/default lookup or a business-state synonym map. Explicit status
    # equality and all HOST/entity literals retain exact case and value.
    if re.fullmatch(r'[a-z][a-z0-9_]*', value):
        literal = '(?:' + literal + '|(?-i:' + re.escape(value.upper()) + ')(?![' + ATOM + ']))'
    return literal


def _intent(view, filters, explicit, quote_context):
    if view == 'host_vm_total':
        parent = _parent(HOST, filters['name'], quote_context)
        natural_status = _status_literal(filters['status'], quote_context)
        explicit_status = _binding(r'VM_NOVA\.status|VM\.status|VM状态|虚拟机状态|状态',
                                   filters['status'], quote_context)
        natural = (r'上\s*(?:目前|当前)?\s*有多少(?:台|个)?\s*处于\s*'
                   + natural_status + r'\s*状态的\s*' + VM)
        counted = (r'上\s*(?:的)?\s*' + explicit_status + r'\s*的\s*' + VM
                   + r'\s*(?:数量|总数)')
        return parent + '(?:' + natural + '|' + counted + ')'
    if view == 'host_vm_status_distribution':
        parent = _parent(HOST, filters['name'], quote_context)
        return (parent + r'\s*(?:上\s*' + VM + r'\s*按状态(?:的)?分布(?:情况)?'
                + r'|上\s*(?:的)?\s*' + VM + r'\s*(?:的)?状态分布(?:情况)?)')
    return _detail_intent(view, filters, explicit, quote_context)


def _ground(question, config):
    if type(question) is not str or not question.strip():
        raise ValueError('question_required')
    # Preserve original offsets. Exactly one complete lexical scan per prepare.
    tokens = quote_tokens(question)
    quote_context = (question, tokens)
    spec = VIEWS[config['view']]
    text, explicit = _projection(question, spec['columns'], tokens)
    body = _intent(config['view'], config['filters'], explicit, quote_context)
    if not re.fullmatch(PREFIX + body + END, text, re.I):
        raise ValueError('unbound_role_value_or_unexpressed_clause')
    return {'view': config['view'], 'filters': deepcopy(config['filters']),
            'columns': list(spec['columns']), 'explicit_projection': explicit,
            'scope': 'filtered', 'source_api_and_sql_preserved': True,
            'quoted_token_spans': [[token['start'], token['end']] for token in tokens]}


def prepare_candidate(question, item, parsed, diagnostics=None):
    """Complete original question + closed params -> ordinary item, or None."""
    try:
        config = _validate(item, parsed)
        evidence = _ground(question, config)
        ordinary = _materialize(item, config)
    except (ValueError, TypeError, KeyError) as exc:
        if type(diagnostics) is dict:
            diagnostics.update(status='unsupported', reason=str(exc))
        return None
    if type(diagnostics) is dict:
        diagnostics.update(status='materialized', evidence=evidence)
    return ordinary
