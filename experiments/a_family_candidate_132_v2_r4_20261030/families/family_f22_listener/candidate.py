"""Closed ELB listener details and protocol count; native COUNT gate unresolved."""
from copy import deepcopy
import json
import re

FAMILY_ID = 'family_f22_listener'
FILTER_ORDER = ('logicalRegionName', 'name')
API_URL = '/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000'
COLUMNS = {
    'listener_protocol_distribution': ['protocol', 'count'],
    'region_listener_rows': ['elb_name', 'elb_id', 'listener_name', 'listener_protocol', 'listener_port'],
    'named_listener_rows': ['elb_name', 'listener_name', 'protocol', 'port'],
    'named_listener_ports': ['listener_name', 'protocol', 'port'],
}
REQUIRED = {'listener_protocol_distribution': 'logicalRegionName', 'region_listener_rows': 'logicalRegionName', 'named_listener_rows': 'name', 'named_listener_ports': 'name'}
SQL = {
    'listener_protocol_distribution': 'SELECT CLOUD_LISTENER.protocol AS protocol, COUNT(*) AS count FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId GROUP BY CLOUD_LISTENER.protocol',
    'region_listener_rows': 'SELECT DISTINCT CLOUD_ELB.name AS elb_name, CLOUD_ELB.id AS elb_id, CLOUD_LISTENER.name AS listener_name, CLOUD_LISTENER.protocol AS listener_protocol, CLOUD_LISTENER.port AS listener_port FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId',
    'named_listener_rows': 'SELECT DISTINCT CLOUD_ELB.name AS elb_name, CLOUD_LISTENER.name AS listener_name, CLOUD_LISTENER.protocol AS protocol, CLOUD_LISTENER.port AS port FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId',
    'named_listener_ports': 'SELECT DISTINCT CLOUD_LISTENER.name AS listener_name, CLOUD_LISTENER.protocol AS protocol, CLOUD_LISTENER.port AS port FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId',
}
_PAIRS = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」'}
_ATOM_CHARS = r'A-Za-z0-9_.@#:/+%\-'
_ATOM = re.compile('[' + _ATOM_CHARS + ']+')
_BARE = re.compile('[' + _ATOM_CHARS + ']+\Z')
_RESOURCE = r'(?<![A-Za-z0-9_])(?:CLOUD_ELB|ELB)|负载均衡器|负载均衡'
_ROLE_NAMES = {
    'logicalRegionName': ('logicalRegionName', '逻辑区域', '区域', 'region', '地域', '地区'),
    'name': ('负载均衡器名称', '负载均衡名称', 'ELB名称', '名称', 'name'),
}


class ContractError(ValueError):
    """Internal unsupported reason; never a business result."""


def _validate(item, parsed):
    if type(item) is not dict or item.get('id') != FAMILY_ID:
        raise ContractError('selected_family_required')
    if type(parsed) is not dict or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ContractError('closed_parameter_schema_required')
    view, filters, required = parsed['view'], parsed['filters'], parsed['required_filters']
    if type(view) is not str or view not in COLUMNS:
        raise ContractError('unsupported_detail_view')
    if type(filters) is not dict or not filters or not set(filters) <= set(FILTER_ORDER):
        raise ContractError('unsupported_filter_fields')
    if view == 'listener_protocol_distribution' and set(filters) != {'logicalRegionName'}:
        raise ContractError('protocol_distribution_exact_regional_scope_required')
    if REQUIRED[view] not in filters:
        raise ContractError('view_base_filter_required')
    if (type(required) is not list or any(type(key) is not str for key in required)
            or len(set(required)) != len(required) or set(required) != set(filters)):
        raise ContractError('required_filters_not_exact')
    for value in filters.values():
        if (type(value) is not str or not value or value != value.strip()
                or '{{' in value or '}}' in value
                or any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
            raise ContractError('nonempty_original_text_filter_required')
    return {'view': view, 'filters': {key: filters[key] for key in FILTER_ORDER if key in filters},
            'required_filters': [key for key in FILTER_ORDER if key in filters]}


def _materialize(item, config):
    ordinary = deepcopy(item)
    for key in ('family_id', 'parameter_contract', 'default_params', 'params', 'family_parameters'):
        ordinary.pop(key, None)
    ordinary.update(resources=['ELB'], sql=SQL[config['view']], api_call={
        'method': 'GET', 'url': API_URL, 'condition': {'constraint': [
            {'simple': {'name': key, 'value': value, 'operator': 'contain' if key == 'name' else 'equal'}}
            for key, value in config['filters'].items()]}})
    return ordinary


def materialize_candidate(item, parsed):
    """Validate parameters and return an ordinary item, or None. No question gate."""
    try:
        return _materialize(item, _validate(item, parsed))
    except (ContractError, TypeError, KeyError):
        return None


def _quote_at(text, start):
    opener = text[start]
    if opener not in _PAIRS:
        return None
    if opener == '"':
        try:
            value, length = json.JSONDecoder().raw_decode(text[start:])
            if type(value) is str and not any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF for c in value):
                return value, start + length
        except (ValueError, json.JSONDecodeError):
            pass
        raise ContractError('invalid_double_quoted_entity')
    end = text.find(_PAIRS[opener], start + 1)
    if end < 0 or '\n' in text[start:end] or '\r' in text[start:end]:
        raise ContractError('unclosed_entity_quote')
    value = text[start + 1:end]
    if any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ContractError('invalid_control_or_unicode_scalar')
    return value, end + 1


def _quotes(text):
    spans, pos = [], 0
    while pos < len(text):
        if text[pos] in _PAIRS:
            _, end = _quote_at(text, pos)
            spans.append((pos, end))
            pos = end
        else:
            pos += 1
    return spans


def _mask(text, spans):
    chars = list(text)
    for start, end in spans:
        chars[start:end] = ' ' * (end - start)
    return ''.join(chars)


def _start_allowed(pos, quotes, atoms):
    return not (any(start <= pos < end for start, end in quotes)
                or any(start < pos < end for start, end in atoms))


def _label(label):
    return (r'(?<![A-Za-z0-9_])' + re.escape(label) + r'(?![A-Za-z0-9_])'
            if label.isascii() else re.escape(label))


def _bridge(text, start, field):
    start += len(text[start:]) - len(text[start:].lstrip())
    if re.match(r'不是|不等于|不为|不包含|不属于|排除|除了|非|!=|<>|\b(?:NOT|LIKE|IN)\b', text[start:], re.I):
        return None
    if field == 'name':
        # The original named-ELB API is contain. Explicit equal is stricter.
        if re.match(r'等于|精确匹配|完全匹配|=|\bequal\b', text[start:], re.I):
            return None
        match = re.match(r'(?:(?:包含|含有|含|为|是|:|：|\bcontain\b)\s*)?', text[start:], re.I)
    else:
        if re.match(r'包含|含有|含|\b(?:contain|like)\b', text[start:], re.I):
            return None
        match = re.match(r'(?:(?:等于|为|是|=|:|：)\s*)?', text[start:])
    return start + match.end()


def _entity_end(text, start, value):
    if start >= len(text):
        return None
    if text[start] in _PAIRS:
        actual, end = _quote_at(text, start)
        return end if actual == value else None
    if not _BARE.fullmatch(value) or not text.startswith(value, start):
        return None
    end = start + len(value)
    if end < len(text) and re.match('[' + _ATOM_CHARS + ']', text[end]):
        return None
    return end


def _operand_end(text, start, value, field):
    # A complete supplied ASCII atom/quote owns its contents before any operator
    # word is interpreted; equal-api and LIKE-zone are names, not operators.
    bare_start = start + len(text[start:]) - len(text[start:].lstrip())
    end = _entity_end(text, bare_start, value)
    if end is not None:
        return end
    bridged = _bridge(text, start, field)
    return _entity_end(text, bridged, value) if bridged is not None else None


def _filter_spans(text, config):
    quotes, atoms = _quotes(text), [match.span() for match in _ATOM.finditer(text)]
    owned, resource_owned = [], False
    for field, value in config['filters'].items():
        found = []
        for label in _ROLE_NAMES[field]:
            for match in re.finditer(_label(label), text, re.I):
                if not _start_allowed(match.start(), quotes, atoms):
                    continue
                if field == 'name' and label in ('名称', 'name'):
                    if re.search(r'监听器\s*$|listener[_ ]*$|租户\s*$|可用区\s*$|区域\s*$', text[:match.start()], re.I):
                        continue
                end = _operand_end(text, match.end(), value, field)
                if end is not None:
                    found.append((match.start(), end))
        if field == 'name':
            # The original ELB<name> shape deliberately permits ASCII adjacency.
            for match in re.finditer(_RESOURCE, text, re.I):
                if not _start_allowed(match.start(), quotes, atoms):
                    continue
                end = _operand_end(text, match.end(), value, field)
                if end is not None:
                    found.append((match.start(), end))
        found = sorted(set(found), key=lambda span: (span[0], -span[1]))
        found = [span for index, span in enumerate(found)
                 if not any(start <= span[0] and span[1] <= end for start, end in found[:index])]
        if len(found) != 1:
            raise ContractError('exact_single_filter_evidence_required:' + field)
        start, end = found[0]
        if any(max(start, a) < min(end, b) for a, b in owned):
            raise ContractError('filter_roles_cannot_share_evidence')
        if field == 'name' and re.search(_RESOURCE, text[start:end], re.I):
            # Only an outside-quote role/resource prefix can establish the resource.
            resource_owned = resource_owned or bool(re.match(_RESOURCE, text[start:end], re.I))
        owned.append((start, end))
    return owned, resource_owned


def _projection(text, view):
    markers = list(re.finditer(r'(?:仅|只)?\s*(?:依次|按顺序)?\s*(?:输出|返回|显示|展示)(?:的)?(?:字段|列)?\s*(?:为|是|:|：)?\s*', text))
    if not markers:
        return text, False
    if len(markers) != 1:
        raise ContractError('single_explicit_projection_required')
    marker = markers[0]
    tail = text[marker.end():].strip().rstrip('。.;；!?！？ ')
    fields = re.split(r'\s*(?:、|,|，|和|与|及)\s*', tail)
    # Alias names are exact SQL output names; explicit aliases cannot be rewritten.
    aliases = {name.casefold(): name for columns in COLUMNS.values() for name in columns}
    human = {'ELB名称': 'elb_name', 'ELB ID': 'elb_id', 'ELB标识': 'elb_id', '监听器名称': 'listener_name',
             '监听器名': 'listener_name', '监听协议': 'listener_protocol' if view == 'region_listener_rows' else 'protocol',
             '监听端口': 'listener_port' if view == 'region_listener_rows' else 'port',
             '数量': 'count', '计数': 'count', '监听器数量': 'count'}
    aliases.update({key.casefold(): value for key, value in human.items()})
    try:
        columns = [aliases[field.strip().casefold()] for field in fields]
    except KeyError as exc:
        raise ContractError('unknown_explicit_output_column') from exc
    if columns != COLUMNS[view]:
        raise ContractError('explicit_output_order_or_columns_mismatch')
    return _mask(text, [(marker.start(), len(text))]), True



def _ground_protocol_distribution(question, config):
    if type(question) is not str or not question.strip():
        raise ContractError('question_required')
    owned, _ = _filter_spans(question, config)
    text = _mask(question, owned)
    text, explicit = _projection(text, config['view'])
    resources = list(re.finditer(_RESOURCE, text, re.I))
    if len(resources) != 1:
        raise ContractError('single_elb_resource_required')
    text = _mask(text, [m.span() for m in resources])
    pattern = r'(?:按照|按)?\s*(?:监听器协议|监听协议|protocol)\s*(?:数量分布|计数分布|分布)'
    intents = list(re.finditer(pattern, text, re.I))
    if len(intents) != 1:
        raise ContractError('complete_single_protocol_distribution_required')
    text = _mask(text, [m.span() for m in intents])
    text = re.sub(r'帮我查询|帮我查一下|查询一下|请帮我|帮我|请|查一下|看一下|查询|查看|统计|当前|所有|全部|的|下|中|内|在', ' ', text)
    text = re.sub(r'[\s，,、。;；:：!?！？()（）]+', '', text)
    if text:
        raise ContractError('unsupported_or_unexpressed_protocol_distribution_clause')
    return {'view': config['view'], 'filters': deepcopy(config['filters']),
            'explicit_projection': explicit, 'columns': COLUMNS[config['view']],
            'grain': 'listener_join_records', 'COUNT_business_gate': 'BLOCKED_UNCHANGED'}


def _ground(question, config):
    if config['view'] == 'listener_protocol_distribution':
        return _ground_protocol_distribution(question, config)
    if type(question) is not str or not question.strip():
        raise ContractError('question_required')
    owned, resource_owned = _filter_spans(question, config)
    text = _mask(question, owned)
    # Output aliases such as elb_name belong to the projection, not resources.
    text, explicit = _projection(text, config['view'])
    resources = [match.span() for match in re.finditer(_RESOURCE, text, re.I)]
    if not resources and not resource_owned:
        raise ContractError('explicit_elb_resource_required')
    text = _mask(text, resources)
    if re.search(r'或者|或|不是|不等于|不为|不包含|包含|排除|除了|!=|<>|>=|<=|\|\||\b(?:OR|NOT|LIKE|IN)\b', text, re.I):
        raise ContractError('unsupported_operator_or_disjunction')

    def consume(pattern):
        nonlocal text
        matches = list(re.finditer(pattern, text, re.I))
        text = _mask(text, [match.span() for match in matches])
        return bool(matches)

    ports = r'监听器(?:列表|清单)(?:和|及|与|以及)(?:监听)?端口'
    regional = r'列表(?:及|和|与|以及)监听器(?:列表)?'
    rows = r'监听器(?:列表|清单|明细)'
    view = config['view']
    if explicit:
        # A complete explicit source projection chooses the view, but does not
        # permit two independent listener requests to be swallowed together.
        intents = list(re.finditer(ports + '|' + regional + '|' + rows + r'|监听器', text))
        if len(intents) > 1:
            raise ContractError('multiple_listener_intents')
        text = _mask(text, [match.span() for match in intents])
        intent = bool(intents)
    elif view == 'region_listener_rows':
        intent = consume(regional)
        if not intent and ('name' not in config['filters'] or explicit):
            intent = consume(rows)
    elif view == 'named_listener_rows':
        intent = consume(ports) if explicit else False
        intent = consume(rows) or intent
    else:
        intent = consume(ports)
        if explicit:
            intent = consume(rows) or intent
    if not intent and not explicit:
        raise ContractError('implicit_view_intent_required')
    # Do not remove output names, condition roles, count/rank words, or extra view clauses.
    text = re.sub(r'帮我查询|帮我查一下|查询一下|请帮我|帮我|请|查一下|看一下|查询|查看|列出|的|下|中|内|在|并且|且|和|与|及|以及|\bAND\b', ' ', text, flags=re.I)
    text = re.sub(r'[\s，,、。;；:：!?！？()（）]+', '', text)
    if text:
        raise ContractError('unsupported_or_unexpressed_clause')
    return {'view': view, 'filters': deepcopy(config['filters']), 'explicit_projection': explicit}


def prepare_candidate(question, item, parsed, diagnostics=None):
    """B-facing boundary: complete question+parameters -> ordinary API/SQL or None."""
    try:
        config = _validate(item, parsed)
        evidence = _ground(question, config)
        ordinary = _materialize(item, config)
    except (ContractError, TypeError, KeyError) as exc:
        if isinstance(diagnostics, dict):
            diagnostics.update(status='unsupported', reason=str(exc))
        return None
    if isinstance(diagnostics, dict):
        diagnostics.update(status='materialized', evidence=evidence)
    return ordinary
