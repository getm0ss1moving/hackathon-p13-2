"""Closed detail views. Pure stdlib; no model, service, executor or old-ID routing.

Runtime must use prepare_candidate. materialize_candidate validates structure only.
"""
from copy import deepcopy
import json
import re

FAMILY_ID = 'family_application_lists'
VIEWS = {'application_modules': {'filters': ['name'],
                         'columns': ['module_name', 'status'],
                         'resources': ['Application'],
                         'api_call': {'method': 'GET',
                                      'url': '/rest/hackthon/db/instances/Application?pageNo=1&pageSize=10000',
                                      'condition': {'constraint': [{'simple': {'name': 'name',
                                                                               'value': '{{name}}',
                                                                               'operator': 'equal'}}]}},
                         'sql': 'SELECT CLOUD_ApplicationModule.name AS module_name, '
                                'CLOUD_ApplicationModule.status AS status FROM CLOUD_Application '
                                'INNER JOIN CLOUD_ApplicationModule ON CLOUD_Application.id = '
                                'CLOUD_ApplicationModule.appId'},
 'application_instances_with_module': {'filters': ['name'],
                                       'columns': ['module_name', 'instance_name'],
                                       'resources': ['Application'],
                                       'api_call': {'method': 'GET',
                                                    'url': '/rest/hackthon/db/instances/Application?pageNo=1&pageSize=10000',
                                                    'condition': {'constraint': [{'simple': {'name': 'name',
                                                                                             'value': '{{name}}',
                                                                                             'operator': 'equal'}}]}},
                                       'sql': 'SELECT DISTINCT CLOUD_ApplicationModule.name AS '
                                              'module_name, CLOUD_ApplicationModuleIns.name AS '
                                              'instance_name FROM CLOUD_Application INNER JOIN '
                                              'CLOUD_ApplicationModule ON CLOUD_Application.id = '
                                              'CLOUD_ApplicationModule.appId INNER JOIN '
                                              'CLOUD_ApplicationModuleIns ON '
                                              'CLOUD_ApplicationModule.id = '
                                              'CLOUD_ApplicationModuleIns.appModuleId'}}
ATOM = r'A-Za-z0-9_@./:#%+\-'
PAIRS = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」'}
VM = r'(?:ECS(?:\s*实例)?|虚拟机(?:\s*实例)?|VM_NOVA|VM)'
HOST = r'(?:宿主机|宿主|HOST)'
SERVICE = r'(?:云服务|S_CloudService)'
APPLICATION = r'(?:应用(?:系统)?|Application)'
PREFIX = r'\s*(?:(?:请帮我|帮我|麻烦|请)\s*)?(?:(?:查询|查看|查找|列出|查一下|看一下)\s*)?'
END = r'\s*[。.!！?？]*\s*'
OUTPUT_ALIASES = {'module_name': ['模块名称'], 'status': ['模块状态'], 'instance_name': ['实例名称']}


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
    if type(filters) is not dict or set(filters) != set(spec['filters']):
        raise ValueError('exact_view_filter_keys_required')
    if (type(required) is not list or any(type(k) is not str for k in required)
            or len(set(required)) != len(required) or set(required) != set(filters)):
        raise ValueError('required_filters_not_exact')
    for value in filters.values():
        if (type(value) is not str or not value or value != value.strip()
                or '{{' in value or '}}' in value or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f for c in value)):
            raise ValueError('nonempty_original_question_string_required')
    return {'view': view, 'filters': {k: filters[k] for k in spec['filters']},
            'required_filters': list(spec['filters'])}


def _materialize(item, config):
    spec = VIEWS[config['view']]
    ordinary = deepcopy(item)
    for key in ('family_id', 'parameter_contract', 'default_params', 'params', 'family_parameters'):
        ordinary.pop(key, None)
    api = deepcopy(spec['api_call'])
    # Repeated source predicates, their order, and their operators stay exact.
    for constraint in api['condition']['constraint']:
        simple = constraint['simple']
        simple['value'] = config['filters'][simple['name']]
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


def _intent(view, filters, explicit, quote_context):
    parent = _parent(APPLICATION, filters['name'], quote_context)
    if view == 'application_modules':
        intent = '下各模块的名称和状态|下的应用模块列表|的模块名称与状态'
    else:
        intent = '下的应用组件实例列表|下的模块实例列表'
    return parent + '\\s*(?:' + intent + ')'



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
