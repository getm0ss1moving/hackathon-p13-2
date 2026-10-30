"""Closed CCE child-detail candidates; stdlib only, no model/service/runtime I/O."""
import copy
import itertools
import json
import re


FAMILY_ID = 'family_cce_children'
CONTRACTS = {
    'node_address_status': {
        'columns': ['node_name', 'node_ip', 'status'],
        'sql': 'SELECT DISTINCT CLOUD_CCE_NODE.name AS node_name, CLOUD_CCE_NODE.privateIP AS node_ip, CLOUD_CCE_NODE.status AS status FROM CLOUD_CCE_CLUSTER INNER JOIN CLOUD_CCE_NODE ON CLOUD_CCE_CLUSTER.id = CLOUD_CCE_NODE.ref_clusterId',
        'fields': {
            'node_name': ['node_name', '节点名称', '节点名'],
            'node_ip': ['node_ip', 'privateIP', '节点IP地址', '节点IP', 'IP地址'],
            'status': ['status', '节点运行状态', '节点状态', '状态'],
        },
    },
    'pod_managed_status': {
        'columns': ['pod_name', 'status'],
        'sql': 'SELECT DISTINCT CLOUD_CCE_POD.name AS pod_name, CLOUD_CCE_POD.managedStatus AS status FROM CLOUD_CCE_CLUSTER INNER JOIN CLOUD_CCE_POD ON CLOUD_CCE_CLUSTER.nativeId = CLOUD_CCE_POD.clusterId',
        'fields': {
            'pod_name': ['pod_name', 'Pod名称', 'Pod名'],
            'status': ['status', 'managedStatus', 'Pod管理状态', '管理状态'],
        },
    },
    'node_managed_cpu': {
        'columns': ['node_name', 'status', 'cpu'],
        'sql': 'SELECT DISTINCT CLOUD_CCE_NODE.name AS node_name, CLOUD_CCE_NODE.managedStatus AS status, CLOUD_CCE_NODE.cpu AS cpu FROM CLOUD_CCE_CLUSTER INNER JOIN CLOUD_CCE_NODE ON CLOUD_CCE_CLUSTER.nativeId = CLOUD_CCE_NODE.clusterId',
        'fields': {
            'node_name': ['node_name', '节点名称', '节点名'],
            'status': ['status', 'managedStatus', '节点管理状态', '管理状态'],
            'cpu': ['cpu', 'CPU核数'],
        },
    },
}


def _parameters(item, parsed):
    if not isinstance(item, dict) or item.get('family_id') != FAMILY_ID or item.get('id') != FAMILY_ID:
        raise ValueError('wrong_candidate_family')
    if not isinstance(parsed, dict) or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ValueError('exact_view_filters_required_filters_required')
    view = parsed['view']
    if not isinstance(view, str) or view not in CONTRACTS:
        raise ValueError('unsupported_view')
    filters, required = parsed['filters'], parsed['required_filters']
    if not isinstance(filters, dict) or set(filters) != {'name'}:
        raise ValueError('only_parent_cluster_name_filter_supported')
    if not isinstance(required, list) or required != ['name']:
        raise ValueError('exact_required_name_contract')
    value = filters['name']
    if not isinstance(value, str) or not value.strip() or any(token in value for token in ['{{', '}}', '\n', '\r']):
        raise ValueError('original_nonempty_cluster_name_required')
    return view, value


def materialize_candidate(item, parsed):
    """Return ordinary API+SQL or None; no old-ID routing or entity defaults."""
    try:
        view, value = _parameters(item, parsed)
    except (ValueError, TypeError):
        return None
    ordinary = copy.deepcopy(item)
    for key in ['family_id', 'default_params', 'views', 'family_views', 'parameter_axes',
                'parameter_contract', 'view', 'filters', 'required_filters']:
        ordinary.pop(key, None)
    ordinary['api_call'] = {
        'method': 'GET',
        'url': '/rest/hackthon/db/instances/CCE_CLUSTER?pageNo=1&pageSize=10000',
        'condition': {'constraint': [
            {'simple': {'name': 'name', 'value': value, 'operator': 'equal'}}]},
    }
    ordinary['sql'] = CONTRACTS[view]['sql']
    return ordinary


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
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError('invalid_unicode_scalar_in_quoted_literal')
        tokens.append({'start': position, 'end': end, 'value': value,
                       'quote': opening})
        position = end
    return tuple(tokens)


def _quoted(text):
    return [(token['start'], token['end']) for token in quote_tokens(text)]


def _overlaps(span, ranges):
    return any(a < span[1] and span[0] < b for a, b in ranges)


def _parent_clause(question, value):
    # Match an entire lexical token, then bind its original span to an owned
    # parent role. A decoded value merely appearing elsewhere is insufficient.
    tokens = quote_tokens(question)
    quoted_ranges = [(token['start'], token['end']) for token in tokens]
    owned_tokens = {(token['start'], token['end']) for token in tokens
                    if token['value'] == value}
    alternatives = [re.escape(question[start:end]) for start, end in sorted(owned_tokens)]
    if re.fullmatch(r'[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*', value):
        alternatives.append(r'(?<![A-Za-z0-9_@./:#%+\-])' + re.escape(value)
                            + r'(?![A-Za-z0-9_@./:#%+\-])')
    if not alternatives:
        raise ValueError('one_exact_CCE_cluster_name_role_required')
    literal = '(?P<literal>(?-i:(?:' + '|'.join(alternatives) + ')))'
    parent = r'(?<![A-Za-z0-9_])(?:CCE\s*集群|容器集群|CCE_CLUSTER(?![A-Za-z0-9_]))'
    equal = r'\s*(?:(?:名称|名字|名)\s*)?(?:(?:等于|为|是|=|:|：)\s*)?'
    matches = []
    for pattern in [parent + equal + literal, literal + r'\s*' + parent]:
        for match in re.finditer(pattern, question, re.I):
            literal_span = match.span('literal')
            if literal_span in owned_tokens:
                role_spans = [(match.start(), literal_span[0]), (literal_span[1], match.end())]
                if any(_overlaps(span, quoted_ranges) for span in role_spans):
                    continue
            elif _overlaps(match.span(), quoted_ranges):
                # An unquoted atom or parent label cannot borrow text from any
                # quoted token, including a different entity's quoted value.
                continue
            matches.append(match)
    if len(matches) != 1:
        raise ValueError('one_exact_CCE_cluster_name_role_required')
    return matches[0]


def _projection(text):
    # Explicit projection owns one terminal clause. Predicates elsewhere remain.
    intro = (r'(?:(?:只需|仅|只)\s*)?(?:(?:输出|返回|显示|展示)\s*(?:字段|列)?'
             r'|(?:字段|列)\s*(?:为|是|:|：|包括|包含))\s*(?:为|是|:|：)?\s*')
    labels = set(label for spec in CONTRACTS.values() for group in spec['fields'].values() for label in group)
    label_pattern = '|'.join(r'(?<![A-Za-z0-9_])' + re.escape(label) + r'(?![A-Za-z0-9_])'
                             if label.isascii() else re.escape(label)
                             for label in sorted(labels, key=len, reverse=True))
    fields = '(?:' + label_pattern + ')'
    sep = r'\s*(?:、|,|，|和|与|及|/)\s*'
    pattern = intro + '(?P<columns>' + fields + '(?:' + sep + fields + ')*)' + r'\s*(?P<suffix>这三列|三列|这两列|两列)?(?=\s*[。;；!?！？]*\s*$)'
    matches = list(re.finditer(pattern, text, re.I))
    if len(matches) > 1:
        raise ValueError('one_complete_projection_clause_required')
    if not matches:
        return text, None
    match = matches[0]
    tokens = re.split(sep, match['columns'])
    if match['suffix'] and len(tokens) != (3 if '三' in match['suffix'] else 2):
        raise ValueError('projection_column_count_suffix_mismatch')
    compatible = []
    for view, spec in CONTRACTS.items():
        lookup = {label.casefold(): field for field, labels in spec['fields'].items() for label in labels}
        normalized = [lookup.get(token.strip().casefold()) for token in tokens]
        if normalized == spec['columns']:
            compatible.append(view)
    if len(compatible) != 1:
        raise ValueError('exact_ordered_view_projection_required')
    return text[:match.start()] + ' ' + text[match.end():], compatible[0]


def _request_view(text, projected_view):
    node = r'(?<![A-Za-z0-9_])(?:容器\s*节点|CCE_NODE|节点)(?![A-Za-z0-9_])'
    pod = r'(?<![A-Za-z0-9_])(?:Pod|CCE_POD)(?![A-Za-z0-9_])'
    listing = r'\s*(?:的\s*)?(?:列表|清单)'
    address = node + listing + r'\s*(?:及|和|与|、)\s*(?:节点\s*)?IP(?:\s*地址)?(?![A-Za-z0-9_])'
    cpu = node + listing + r'\s*(?:及|和|与|、)\s*CPU(?:\s*核数)?(?![A-Za-z0-9_])'
    # A complete natural attribute phrase owns a set request. Unlike an
    # explicit projection its mention order does not alter source column order.
    # Predicates, missing attributes and extra obligations cannot be consumed.
    separator = r'\s*(?:、|,|，|和|与|及|/)\s*'
    name = r'(?:节点名称|节点名|名称|名字|名|node_name)'
    ip = r'(?:(?:节点\s*)?IP(?:\s*地址)?|privateIP|node_ip)'
    state = r'(?:节点运行状态|节点状态|运行状态|状态|status)'
    managed = r'(?:节点管理状态|管理状态|managedStatus|status)'
    cpu_field = r'CPU(?:\s*核数)?(?![A-Za-z0-9_])'
    def attributes(resource, groups):
        return (resource + r'\s*(?:的\s*)?(?:' +
                '|'.join(separator.join(order) for order in itertools.permutations(groups)) + ')')
    address_attributes = attributes(node, [name, ip, state])
    cpu_attributes = attributes(node, [name, managed, cpu_field])
    pod_attributes = attributes(pod, [r'(?:Pod名称|Pod名|名称|名字|名|pod_name)',
                                      r'(?:Pod管理状态|管理状态|状态|managedStatus|status)'])
    expression = ('(?P<address_attributes>' + address_attributes + ')|(?P<cpu_attributes>' + cpu_attributes +
                  ')|(?P<pod_attributes>' + pod_attributes + ')|(?P<address>' + address +
                  ')|(?P<cpu>' + cpu + ')|(?P<pod>' + pod + listing + ')|(?P<node>' + node + listing + ')')
    requests = list(re.finditer(expression, text, re.I))
    if len(requests) > 1:
        raise ValueError('multiple_child_output_obligations_unsupported')
    if not requests:
        if projected_view is None:
            raise ValueError('explicit_child_view_intent_required')
        return text, projected_view
    request = requests[0]
    kind = request.lastgroup
    if kind in {'address', 'address_attributes'}:
        desired = 'node_address_status'
    elif kind in {'cpu', 'cpu_attributes'}:
        desired = 'node_managed_cpu'
    elif kind in {'pod', 'pod_attributes'}:
        desired = 'pod_managed_status'
    else:
        # With an already proven CCE parent, plain node list/roster is the
        # ordinary container-node synonym and owns managedStatus+cpu defaults.
        if projected_view:
            if projected_view == 'pod_managed_status':
                raise ValueError('node_request_cannot_select_pod_projection')
            desired = projected_view
        else:
            desired = 'node_managed_cpu'
    if projected_view and projected_view != desired:
        raise ValueError('natural_and_explicit_output_contract_conflict')
    return text[:request.start()] + ' ' + text[request.end():], desired


def prepare_candidate(question, item, parsed, diagnostics=None):
    """Validate finite intent and all residual text, then ordinary API+SQL."""
    try:
        view, value = _parameters(item, parsed)
        if not isinstance(question, str) or not question.strip():
            raise ValueError('question_required')
        parent = _parent_clause(question, value)
        remaining = question[:parent.start()] + ' ' + question[parent.end():]
        remaining, projection_view = _projection(remaining)
        remaining, desired = _request_view(remaining, projection_view)
        if desired != view:
            raise ValueError('parsed_view_does_not_cover_request')
        # Only grammatical glue is discarded after each semantic owner consumed
        # its complete clause. Operators and unknown roles/fields survive.
        remaining = re.sub(r'请|帮我|一下|查询|查看|查找|列出|显示|展示|当前|所有|全部|分别|的|下|中|内', ' ', remaining)
        remaining = re.sub(r'[\s，,、。.:：;；!?！？()/]+', '', remaining)
        if remaining:
            raise ValueError('unsupported_or_unfulfilled_clause')
        result = materialize_candidate(item, parsed)
        if result is None:
            raise ValueError('materialization_failed')
    except (ValueError, TypeError) as exc:
        if diagnostics is not None:
            diagnostics.update(candidate_status='unsupported', candidate_reason=str(exc))
        return None
    if diagnostics is not None:
        diagnostics.update(candidate_status='prepared', candidate_family=FAMILY_ID,
                           candidate_view=view, output_columns=copy.deepcopy(CONTRACTS[view]['columns']),
                           parent_role='CCE_CLUSTER.name equal', execution_validated=False)
    return result
