"""Review/build input for existing matcher: closed F02/F19 direct-attribute contracts.

No runtime old-ID routing, SDK extension, model call or executor is introduced.
B may insert these functions into its existing matcher after separate integration.
"""
import copy
import re


_B3_SPECS = {
    'F02': {'ci': 'VM_NOVA', 'table': 'CLOUD_VM_NOVA', 'shapes': {
        ('name', 'privateIps', 'tenantName'): {'none': [
            ('azoneName', 'status'), ('logicalRegionName', 'azoneName')]},
        ('name', 'createdAt'): {'none': [('name',)]},
        ('name', 'clusterName', 'azoneName'): {'none': [('name',)]},
        ('name', 'privateIps', 'status'): {'none': [
            ('tenantName', 'logicalRegionName'), ('tenantName', 'logicalRegionName', 'azoneName')]},
        ('tenantName', 'name', 'privateIps'): {'tenantName': [
            ('vdcName', 'logicalRegionName', 'azoneName')]},
    }},
    'F19': {'ci': 'GAUSSDB_INSTANCE', 'table': 'CLOUD_GAUSSDB_INSTANCE', 'shapes': {
        ('name', 'engineName', 'engineVersion', 'haMode', 'flavorCode'): {'none': [('logicalRegionName',)]},
        ('engineVersion', 'haMode', 'flavorCode'): {'none': [('name',)]},
        ('name', 'engineVersion', 'dataVip'): {'none': [('logicalRegionName',)]},
        ('haMode', 'dataVip'): {'none': [('name',)]},
    }},
}


def _materialize_batch3(item: dict, parameters: dict) -> dict:
    family = item.get('family_id')
    if family not in _B3_SPECS or not isinstance(parameters, dict):
        raise ValueError('unknown_batch3_family_or_parameters')
    if set(parameters) != {'scope', 'projection', 'order', 'filters', 'required_filters'}:
        raise ValueError('closed_batch3_parameter_schema_required')
    projection = parameters['projection']
    if not isinstance(projection, list) or not all(isinstance(c, str) for c in projection):
        raise ValueError('projection_list_required')
    shape = _B3_SPECS[family]['shapes'].get(tuple(projection))
    order = parameters['order']
    if shape is None or not isinstance(order, str) or order not in shape:
        raise ValueError('unreviewed_projection_or_order')
    filters, required = parameters['filters'], parameters['required_filters']
    if (parameters['scope'] != 'filtered' or not isinstance(filters, dict) or not filters
            or not isinstance(required, list) or any(not isinstance(k, str) for k in required)
            or len(set(required)) != len(required) or set(required) != set(filters)):
        raise ValueError('explicit_complete_filter_contract_required')
    field_order = next((fields for fields in shape[order] if set(fields) == set(filters)), None)
    if field_order is None:
        raise ValueError('unreviewed_projection_filter_pair')
    for field, value in filters.items():
        if not isinstance(value, str) or not value.strip() or '{{' in value or '}}' in value:
            raise ValueError('nonempty_original_text_required:' + field)
    spec = _B3_SPECS[family]
    sql = 'SELECT ' + ', '.join(projection) + ' FROM ' + spec['table']
    if order != 'none':
        sql += ' ORDER BY ' + order
    api = {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + spec['ci'] + '?pageNo=1&pageSize=10000',
           'condition': {'constraint': [
               {'simple': {'name': field, 'value': filters[field], 'operator': 'equal'}} for field in field_order]}}
    ordinary = copy.deepcopy(item)
    for key in ['family_id', 'parameter_contract', 'default_params']:
        ordinary.pop(key, None)
    ordinary.update(api_call=api, sql=sql)
    return ordinary


_B3_FIELD_LABELS = {
    'name': ['实例名称', '虚拟机名称', '实例名', '虚拟机名', '名称', 'name'],
    'privateIps': ['私网IP', '私有IP', 'IP地址', 'privateIps', 'IP'],
    'tenantName': ['租户名称', '租户名', '租户', 'tenantName'],
    'status': ['状态', 'status'],
    'createdAt': ['创建时间', 'createdAt'],
    'clusterName': ['集群名称', '集群名', '集群', 'clusterName'],
    'azoneName': ['可用区名称', '可用区', 'azoneName', 'AZ'],
    'engineName': ['引擎名称', '引擎类型', '引擎名', 'engineName'],
    'engineVersion': ['引擎版本', '数据库版本', 'engineVersion'],
    'haMode': ['高可用模式', 'haMode'],
    'flavorCode': ['规格编码', '规格', 'flavorCode'],
    'dataVip': ['数据VIP地址', '数据VIP', '业务VIP', 'dataVip'],
}

_B3_ROLE_LABELS = {
    'logicalRegionName': ['logicalRegionName', '区域', '地区', '地域', 'region'],
    'tenantName': ['tenantName', '租户名称', '租户名', '租户'],
    'vdcName': ['vdcName', 'VDC名称', 'VDC名', 'VDC'],
    'azoneName': ['azoneName', '可用区名称', '可用区', 'AZ'],
    'status': ['status', '状态'],
    'name': ['实例名称', '虚拟机名称', '实例名', '虚拟机名', '资源名称', '名称', 'name'],
}


def _b3_label_pattern(label):
    escaped = re.escape(label)
    return r'(?<![A-Za-z0-9_])' + escaped + r'(?![A-Za-z0-9_])' if label.isascii() else escaped


def _b3_mask(text, spans):
    chars = list(text)
    for start, end in spans:
        chars[start:end] = ' ' * (end - start)
    return ''.join(chars)


def _ground_batch3_parameters(question: str, item: dict, parameters: dict) -> dict:
    """Finite explicit-role/explicit-column grammar, complete residual coverage.

    This helper has no model or retrieval. It does not claim all original natural
    phrasings are supported. B must review its own extraction/selection path.
    """
    _materialize_batch3(item, parameters)
    if not isinstance(question, str) or not question.strip():
        raise ValueError('batch3_question_required')
    family = item['family_id']
    quoted = [m.span() for m in re.finditer(r'''"[^"\n]*"|'[^'\n]*'|“[^”\n]*”|「[^」\n]*」''', question)]
    inside_quote = lambda span: any(a <= span[0] and span[1] <= b for a, b in quoted)

    # Sorting owns a complete phrase; never infer grouping from an ORDER BY.
    tenant = '(?:' + '|'.join(_b3_label_pattern(x) for x in _B3_ROLE_LABELS['tenantName']) + ')'
    order_pattern = r'(?:按照|按)\s*' + tenant + r'\s*(?:升序\s*)?排序(?:\s*升序)?'
    orders = [m for m in re.finditer(order_pattern, question, re.I) if not inside_quote(m.span())]
    if len(orders) > 1 or ('tenantName' if orders else 'none') != parameters['order']:
        raise ValueError('batch3_order_evidence_mismatch')
    remaining = _b3_mask(question, [m.span() for m in orders])

    # Projection fields are recognized only inside a complete terminal clause.
    # A name/status predicate cannot donate field words to that projection.
    labels = {label: field for field, aliases in _B3_FIELD_LABELS.items() for label in aliases}
    field_pattern = '|'.join(_b3_label_pattern(x) for x in sorted(labels, key=len, reverse=True))
    canonical = {label.casefold(): field for label, field in labels.items()}
    intro = (r'(?:只需|仅|只)?\s*(?:(?:输出|返回|显示|展示)\s*(?:字段|列)?'
             r'|(?:字段|列)\s*(?:为|是|:|：|包括|包含))\s*(?:为|是|:|：)?\s*')
    field = '(?:' + field_pattern + ')'
    separator = r'\s*(?:、|,|，|和|与|及|/)\s*'
    projection_pattern = intro + field + '(?:' + separator + field + ')*' + r'(?=\s*[。;；!?！？]*\s*$)'
    projections = [m for m in re.finditer(projection_pattern, remaining, re.I) if not inside_quote(m.span())]
    if len(projections) != 1:
        raise ValueError('batch3_complete_explicit_projection_required')
    projection = projections[0]
    columns = [canonical[m.group().casefold()] for m in re.finditer(field_pattern, projection.group(), re.I)]
    if columns != parameters['projection']:
        raise ValueError('batch3_projection_evidence_mismatch')
    remaining = _b3_mask(remaining, [projection.span()])

    # Leftmost whole bindings own values once. Postfixed chains start at each
    # entity before the role, avoiding greedy role->next-entity reassignment.
    literal = r'''(?:"(?P<dq>[^"\n]+)"|'(?P<sq>[^'\n]+)'|“(?P<cq>[^”\n]+)”|「(?P<jq>[^」\n]+)」|(?P<bare>[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*))'''
    equal = r'\s*(?:(?:等于|为|是|=|:|：)\s*)?'
    bindings = []
    for field, aliases in _B3_ROLE_LABELS.items():
        role = '(?:' + '|'.join(_b3_label_pattern(x) for x in sorted(aliases, key=len, reverse=True)) + ')'
        for pattern in [role + equal + literal, literal + r'\s*(?:(?:为|是|等于)\s*)?' + role]:
            for match in re.finditer(pattern, remaining, re.I):
                value = next(v for v in match.groupdict().values() if v is not None)
                bindings.append((match.start(), match.end(), field, value))
    bindings.sort(key=lambda row: (row[0], -(row[1] - row[0])))
    owned, end, actual = [], -1, {}
    for start, stop, field, value in bindings:
        if start < end:
            continue
        if field in actual:
            raise ValueError('batch3_repeated_filter_role:' + field)
        actual[field] = value
        owned.append((start, stop))
        end = stop
    if actual != parameters['filters']:
        raise ValueError('batch3_complete_role_value_evidence_required')
    remaining = _b3_mask(remaining, owned)

    resources = {
        'F02': r'(?:(?<![A-Za-z0-9_])(?:VM_NOVA|ECS)(?![A-Za-z0-9_])(?:实例|虚拟机)?|虚拟机)',
        'F19': r'(?<![A-Za-z0-9_])(?:GAUSSDB_INSTANCE|GaussDB)(?![A-Za-z0-9_])(?:实例|数据库)?',
    }
    matches = list(re.finditer(resources[family], remaining, re.I))
    if len(matches) != 1:
        raise ValueError('batch3_explicit_single_resource_required')
    remaining = _b3_mask(remaining, [m.span() for m in matches])
    glue = r'请|帮我|一下|查询|查看|查找|列出|显示|展示|返回|获取|当前|所有|全部|实例|列表|清单|明细|的|在|下|中|内|并且|并|且|和|与|及'
    remaining = re.sub(glue, ' ', remaining)
    remaining = re.sub(r'[\s，,、。.:：;；!?！？()/]+', '', remaining)
    if remaining:
        raise ValueError('batch3_unsupported_request_clause')
    return {'family_id': family, 'resource': _B3_SPECS[family]['ci'], 'projection': columns,
            'order': parameters['order'], 'filters': actual, 'grammar': 'explicit_equal_roles_and_terminal_projection'}


def _prepare_batch3_candidate(question: str, item: dict, parameters: dict, diagnostics: dict = None):
    """Offline/B handoff boundary: externally extracted JSON -> ordinary item/None.

    B retains ownership of retrieval, model stages, SQL refinement and official
    empty serialization. Do not substitute this helper for that full pipeline.
    """
    try:
        ordinary = _materialize_batch3(item, parameters)
        evidence = _ground_batch3_parameters(question, item, parameters)
    except (ValueError, TypeError) as exc:
        if diagnostics is not None:
            diagnostics.update(family_status='invalid_or_ungrounded_parameters', family_error=str(exc))
        return None
    if diagnostics is not None:
        diagnostics.update(family_status='materialized', family_id=item['family_id'],
                           batch3_contract_evidence=evidence, parameters=copy.deepcopy(parameters))
    return ordinary


"""Offline prototype: closed view defaults with owned natural output phrases.

Never modifies the frozen batch3 helper. No model/retrieval/executor/SDK changes.
"""
import copy
import itertools
import re


VIEWS = {
    'ecs_creation_time': ('F02', ['name', 'createdAt'], 'none', r'(?:的)?(?:创建时间|(?:是)?什么时候创建的)'),
    'ecs_cluster_zone': ('F02', ['name', 'clusterName', 'azoneName'], 'none',
                         r'(?:(?:的)?所属(?:的)?|属于哪个|的)?集群(?:名称)?[和、与及](?:所属|哪个)?可用区(?:名称)?'),
    'ecs_ip_tenant': ('F02', ['name', 'privateIps', 'tenantName'], 'none',
                      r'(?:的)?(?:有哪些\s*IP(?:地址)?[，,、]?\s*(?:分别)?属于哪个租户|IP(?:地址)?(?:列表)?[和、与及](?:所属)?租户(?:归属|名称)?|(?:IP)?列表|清单)'),
    'ecs_filtered_list': ('F02', ['name', 'privateIps', 'status'], 'none', r'(?:的)?(?:IP)?(?:列表|清单)'),
    'ecs_tenant_ordered_ip': ('F02', ['tenantName', 'name', 'privateIps'], 'tenantName',
                              r'(?:的)?(?:租户归属[和、与及])?(?:(?:实例名|实例名称)[和、与及]IP(?:地址)?|(?:IP)?列表|清单)'),
    'db_region_inventory': ('F19', ['name', 'engineName', 'engineVersion', 'haMode', 'flavorCode'], 'none',
                             r'(?:的)?(?:实例清单|实例列表|清单|列表|配置概览)(?:[和、与及](?:引擎版本|数据库版本|版本))?'),
    'db_named_config': ('F19', ['engineVersion', 'haMode', 'flavorCode'], 'none',
                        r'(?:的)?(?:配置信息|配置概览|引擎版本[和、与及]高可用模式[和、与及]规格(?:编码)?)'),
    'db_region_version_vip': ('F19', ['name', 'engineVersion', 'dataVip'], 'none',
                              r'(?:的)?(?:引擎版本|数据库版本|版本)[和、与及]数据VIP(?:地址)?'),
    'db_named_ha_vip': ('F19', ['haMode', 'dataVip'], 'none', r'(?:的)?高可用模式[和、与及]数据VIP(?:地址)?'),
}


def _attribute_intent(view):
    """Natural attribute order is a set request; explicit projection stays strict."""
    groups = {
        'db_named_config': [r'(?:引擎版本|数据库版本|版本)', r'高可用模式', r'规格(?:编码)?'],
        'db_named_ha_vip': [r'高可用模式', r'数据VIP(?:地址)?'],
        'ecs_cluster_zone': [r'(?:哪个)?集群(?:名称)?', r'(?:哪个)?可用区(?:名称)?'],
        'ecs_ip_tenant': [r'IP(?:地址)?(?:列表)?', r'(?:所属)?租户(?:归属|名称)?'],
    }
    if view not in groups:
        return VIEWS[view][3]
    alternatives = ['[和、与及]'.join(order) for order in itertools.permutations(groups[view])]
    prefix = r'(?:(?:的)?所属(?:的)?|属于哪个|的)?' if view == 'ecs_cluster_zone' else r'(?:的)?'
    # Keep existing generic-list/config and split-question alternatives as well.
    return '(?:' + prefix + '(?:' + '|'.join(alternatives) + ')|' + VIEWS[view][3] + ')'


def view_parameters(item, parsed):
    if not isinstance(parsed, dict) or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ValueError('closed_view_schema_required')
    view = parsed['view']
    if not isinstance(view, str) or view not in VIEWS or VIEWS[view][0] != item.get('family_id'):
        raise ValueError('unsupported_or_wrong_family_view')
    family, columns, order, _ = VIEWS[view]
    return dict(scope='filtered', projection=copy.deepcopy(columns), order=order,
                filters=copy.deepcopy(parsed['filters']), required_filters=copy.deepcopy(parsed['required_filters']))


def _quoted(text):
    return [m.span() for m in re.finditer(r'''"[^"\n]*"|'[^'\n]*'|“[^”\n]*”|「[^」\n]*」''', text)]


def _inside(span, quoted):
    return any(a <= span[0] and span[1] <= b for a, b in quoted)


def _quote_value(value):
    for left, right in [('"', '"'), ("'", "'"), ('“', '”'), ('「', '」')]:
        if left not in value and right not in value:
            return left + value + right
    raise ValueError('unsupported_entity_quote_shape')


def _normalize_named_instance(text, family, filters):
    """Add a name role only to an actual resource+实例+exact entity occurrence."""
    value = filters.get('name')
    if not isinstance(value, str) or not value:
        return text, []
    escaped = re.escape(value)
    alternatives = [re.escape(a) + escaped + re.escape(b)
                    for a, b in [('"', '"'), ("'", "'"), ('“', '”'), ('「', '」')]]
    if re.fullmatch(r'[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*', value):
        alternatives.append(escaped + r'(?![A-Za-z0-9_@./:#%+\-])')
    resource = r'(?:ECS|VM_NOVA|虚拟机)' if family == 'F02' else r'(?:GaussDB|GAUSSDB_INSTANCE)'
    pattern = (r'(?<![A-Za-z0-9_])(?P<resource>' + resource + r'(?:\s*实例)?)\s*'
               + '(?-i:(?:' + '|'.join(alternatives) + '))')
    quoted = _quoted(text)
    matches = [m for m in re.finditer(pattern, text, re.I) if not _inside(m.span(), quoted)]
    if len(matches) > 1:
        raise ValueError('multiple_implicit_instance_mentions')
    if not matches:
        return text, []
    match = matches[0]
    # A clause separator prevents the frozen postfix-role parser from treating
    # the resource token itself (e.g. ECS 名称) as the name value.
    replacement = match['resource'] + '，名称=' + _quote_value(value)
    return (text[:match.start()] + replacement + text[match.end():],
            [dict(kind='resource_instance_name', original=match.group(), replacement=replacement)])


def _normalize_role_attachments(text, filters):
    """Recover lexical role boundaries, never infer roles by value occurrence."""
    changes = []
    for field, role in [('vdcName', 'VDC'), ('azoneName', 'AZ'),
                        ('logicalRegionName', 'region'), ('tenantName', 'tenantName')]:
        value = filters.get(field)
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*', value):
            continue
        pattern = r'(?<![A-Za-z0-9_])' + role + '(?-i:' + re.escape(value) + r')(?![A-Za-z0-9_@./:#%+\-])'
        matches = [m for m in re.finditer(pattern, text, re.I) if not _inside(m.span(), _quoted(text))]
        for match in reversed(matches):
            replacement = role + '=' + _quote_value(value)
            changes.append(dict(kind='attached_role_value', original=match.group(), replacement=replacement))
            text = text[:match.start()] + replacement + text[match.end():]
    return text, changes


def _normalize_postfixed_roles(text, filters):
    """Exact value+role evidence -> prefix clause, avoiding frozen quote overlap."""
    labels = {'name': ['名称', '实例名称', 'name'], 'logicalRegionName': ['区域', '地区', '地域', 'region', 'logicalRegionName'],
              'tenantName': ['租户', '租户名称', 'tenantName'], 'vdcName': ['VDC', 'VDC名称', 'vdcName'],
              'azoneName': ['可用区', '可用区名称', 'AZ', 'azoneName'], 'status': ['状态', 'status']}
    changes = []
    for field, value in filters.items():
        if field not in labels:
            continue
        escaped = re.escape(value)
        values = [re.escape(a) + escaped + re.escape(b) for a, b in [('"', '"'), ("'", "'"), ('“', '”'), ('「', '」')]]
        if re.fullmatch(r'[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*', value):
            values.append(escaped + r'(?![A-Za-z0-9_@./:#%+\-])')
        role = '|'.join(r'(?<![A-Za-z0-9_])' + re.escape(v) + r'(?![A-Za-z0-9_])' if v.isascii() else re.escape(v)
                        for v in sorted(labels[field], key=len, reverse=True))
        pattern = '(?-i:(?:' + '|'.join(values) + r'))\s*(?:(?:为|是|等于)\s*)?(?:' + role + ')'
        matches = [m for m in re.finditer(pattern, text, re.I) if not _inside(m.span(), _quoted(text))]
        for match in reversed(matches):
            replacement = field + '=' + _quote_value(value)
            changes.append(dict(kind='postfixed_exact_role', original=match.group(), replacement=replacement))
            text = text[:match.start()] + replacement + text[match.end():]
    return text, changes


def _normalize_source_az_status(text, view, filters):
    """Finite predicates established by the AZ/status source contract and R5.

    In this view, an actual status predicate plus one bare spatial operand
    has a unique reviewed AZ/status profile. The role comes from that profile,
    never from an entity's spelling. Explicit region/tenant roles still win.
    """
    changes = []
    if view == 'ecs_ip_tenant' and set(filters) == {'azoneName', 'status'}:
        zone = filters['azoneName']
        if zone:
            literal = [re.escape(a) + re.escape(zone) + re.escape(b)
                       for a, b in [('"', '"'), ("'", "'"), ('“', '”'), ('「', '」')]]
            literal.append(re.escape(zone))
            pattern = r'(?<![A-Za-z0-9_@./:#%+\-])(?-i:(?:' + '|'.join(literal) + r'))(?P<location>里|内|中)'
            explicit_role = r'(?:区域|地区|地域|region|logicalRegionName|租户|tenantName|VDC|vdcName|可用区|AZ|azoneName|名称|name)\s*(?:为|是|等于|=|:|：)?\s*$'
            matches = [m for m in re.finditer(pattern, text) if not _inside(m.span(), _quoted(text))
                       and not re.search(explicit_role, text[:m.start()], re.I)]
            for match in reversed(matches):
                replacement = '可用区=' + _quote_value(zone) + '中'
                changes.append(dict(kind='source_AZ_spatial_attachment', original=match.group(), replacement=replacement))
                text = text[:match.start()] + replacement + text[match.end():]
    aliases = {'active': ['正在跑', '正在运行', '运行中'], 'stopped': ['已停止', '停机']}
    code = filters.get('status')
    if code in aliases:
        words = '|'.join(sorted(aliases[code], key=len, reverse=True))
        pattern = r'(?:状态\s*(?:为|是|=)?\s*)?(?:' + words + ')'
        matches = [m for m in re.finditer(pattern, text) if not _inside(m.span(), _quoted(text))]
        for match in reversed(matches):
            replacement = '状态=' + _quote_value(code)
            changes.append(dict(kind='supported_status_predicate', original=match.group(), replacement=replacement))
            text = text[:match.start()] + replacement + text[match.end():]
    return text, changes


def prepare_natural_candidate(question, item, parsed, frozen_prepare, diagnostics=None):
    """Reference boundary for B: explicit view -> frozen ordinary item or None.

    Only owned output intent / bound implicit instance syntax is normalized.
    Every other original token stays for the frozen all-conditions validator.
    """
    diagnostic = diagnostics if diagnostics is not None else {}
    try:
        params = view_parameters(item, parsed)
        if not isinstance(question, str) or not question.strip():
            raise ValueError('question_required')
        # Validate types/profile before using entity text in lexical patterns.
        if (not isinstance(params['filters'], dict) or
                any(not isinstance(v, str) or not v.strip() for v in params['filters'].values())):
            raise ValueError('original_entity_text_required')
        normalized, name_changes = _normalize_named_instance(question, item['family_id'], params['filters'])
        normalized, role_changes = _normalize_role_attachments(normalized, params['filters'])
        normalized, postfix_changes = _normalize_postfixed_roles(normalized, params['filters'])
        normalized, predicate_changes = _normalize_source_az_status(normalized, parsed['view'], params['filters'])
        name_changes += role_changes + postfix_changes + predicate_changes
        explicit_diagnostic = {}
        existing = frozen_prepare(normalized, item, params, explicit_diagnostic)
        if existing is not None:
            diagnostic.update(path='existing_explicit_projection', normalized_question=normalized,
                              parameters=params, owned_changes=name_changes)
            return existing

        # An explicit output restriction must not be replaced by view defaults.
        quoted = _quoted(normalized)
        explicit = r'输出|返回字段|显示字段|展示字段|显示列|只返回|仅返回|字段\s*(?:为|是|:|：|包括|包含)|列\s*(?:为|是|:|：|包括|包含)'
        if any(not _inside(m.span(), quoted) for m in re.finditer(explicit, normalized, re.I)):
            raise ValueError('explicit_output_contract_cannot_be_overridden')
        # Natural output intent may precede or follow conditions. Own its whole
        # phrase and question particles; preserve every other original token.
        core = _attribute_intent(parsed['view']).replace('[和、与及]', r'\s*[和、与及]\s*')
        intent = re.compile(r'(?:(?:它们|这些实例|该实例)\s*的\s*)?' + core
                            + r'(?:\s*(?:分别)?(?:是)?(?:什么|哪些)(?:呢)?)?', re.I)
        matches = [m for m in intent.finditer(normalized) if not _inside(m.span(), quoted)]
        if len(matches) != 1:
            raise ValueError('unambiguous_natural_view_evidence_required')
        match = matches[0]
        suffix = normalized[match.end():]
        if re.match(r'\s*(?:等于|为|是(?!什么|哪些)|包含|不是|不等于|[=<>]|在(?!\s*(?:区域|地区|地域|可用区|租户|VDC)))', suffix, re.I):
            raise ValueError('output_attribute_used_as_unsupported_predicate')
        # The intent span contains no entity values or filter operators. A
        # condition inside/after an attribute phrase remains as residual text.
        retained = normalized[:match.start()] + normalized[match.end():]
        owned_changes = name_changes + [dict(kind='output_intent', original=match.group(),
                                             replacement=params['projection'])]
        # Generic row-layout qualifiers differ from aggregate grouping. This
        # view retains original tenantName ordering and per-record columns.
        if parsed['view'] == 'ecs_tenant_ordered_ip':
            layouts = [m for m in re.finditer(r'各租户的', retained) if not _inside(m.span(), _quoted(retained))]
            for layout in reversed(layouts):
                owned_changes.append(dict(kind='row_layout_qualifier', original=layout.group(), replacement=''))
                retained = retained[:layout.start()] + retained[layout.end():]
        request_prefix = re.match(r'^\s*(?:我想看|(?:请)?帮我(?:查一下|查看|查询|看看|查)|麻烦(?:查看|查询))\s*', retained)
        if request_prefix:
            owned_changes.append(dict(kind='request_verb', original=request_prefix.group(), replacement='查询'))
            retained = '查询' + retained[request_prefix.end():]
        default_order = False
        if params['order'] == 'tenantName':
            claims = [m for m in re.finditer(r'排序|排列|升序|降序', retained) if not _inside(m.span(), _quoted(retained))]
            if not claims:
                retained += '，按tenantName排序'
                default_order = True
        canonical = retained + '，输出' + '、'.join(params['projection'])
        frozen_diagnostic = {}
        ordinary = frozen_prepare(canonical, item, params, frozen_diagnostic)
        if ordinary is None:
            diagnostic.update(frozen_diagnostic, normalized_question=canonical, owned_changes=owned_changes)
            return None
        diagnostic.update(path='closed_view_default_projection', normalized_question=canonical,
                          view=parsed['view'], parameters=params, default_order_added=default_order,
                          owned_changes=owned_changes)
        return ordinary
    except (ValueError, TypeError) as exc:
        diagnostic.update(natural_view_status='unsupported', natural_view_error=str(exc))
        return None


# F02 extension begins; frozen inherited functions above remain source-identical.
import json

FAMILY_ID = 'family_f02'
NEW_VIEW = 'ecs_tenant_zone_ip_alias'
NEW_COLUMNS = ['tenant_name', 'azone_name', 'vm_name', 'private_ips']
NEW_PROJECTION_SQL = [
    'CLOUD_VM_NOVA.tenantName AS tenant_name',
    'CLOUD_VM_NOVA.azoneName AS azone_name',
    'CLOUD_VM_NOVA.name AS vm_name',
    'CLOUD_VM_NOVA.privateIps AS private_ips',
]
NEW_SQL = 'SELECT ' + ', '.join(NEW_PROJECTION_SQL) + ' FROM CLOUD_VM_NOVA'
NEW_API = {
    'method': 'GET',
    'url': '/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000',
    'condition': {'constraint': [
        {'simple': {'name': 'logicalRegionName', 'value': '{{logicalRegionName}}',
                    'operator': 'equal'}} for _ in range(3)]},
}
# Preserve both inherited functions and their original globals/semantics.
_INHERITED_MATERIALIZE = _materialize_batch3
_INHERITED_GROUND = _ground_batch3_parameters
_INHERITED_NATURAL_PREPARE = prepare_natural_candidate
_B3_SPECS['F02']['shapes'][tuple(NEW_COLUMNS)] = {'none': [('logicalRegionName',)]}
VIEWS[NEW_VIEW] = ('F02', NEW_COLUMNS, 'none', None)


def quote_tokens(text):
    """One lexical scan: JSON double quotes decode exactly once; raw pairs stay raw."""
    if type(text) is not str:
        raise ValueError('question_text_required')
    if any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f or 0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise ValueError('question_control_or_invalid_unicode')
    decoder = json.JSONDecoder()
    pairs = {"'": "'", '“': '”', '‘': '’', '「': '」'}
    tokens, pos = [], 0
    while pos < len(text):
        opening = text[pos]
        if opening == '"':
            try:
                value, end = decoder.raw_decode(text, pos)
            except ValueError as exc:
                raise ValueError('invalid_JSON_quoted_literal') from exc
        elif opening in pairs:
            last = text.find(pairs[opening], pos + 1)
            if last < 0:
                raise ValueError('unclosed_raw_quoted_literal')
            value, end = text[pos + 1:last], last + 1
        elif opening in {'”', '’', '」'}:
            raise ValueError('unmatched_quote_closer')
        else:
            pos += 1
            continue
        if type(value) is not str or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError('decoded_control_or_invalid_unicode')
        tokens.append({'start': pos, 'end': end, 'value': value})
        pos = end
    return tuple(tokens)


def _new_parameters(item, parsed):
    if type(item) is not dict or item.get('id') != FAMILY_ID or item.get('family_id') != 'F02':
        raise ValueError('selected_F02_item_required')
    if type(parsed) is not dict:
        raise ValueError('parameters_object_required')
    if set(parsed) == {'view', 'filters', 'required_filters'}:
        if parsed['view'] != NEW_VIEW:
            raise ValueError('new_view_required')
        config = view_parameters(item, parsed)
    elif set(parsed) == {'scope', 'projection', 'order', 'filters', 'required_filters'}:
        config = copy.deepcopy(parsed)
    else:
        raise ValueError('closed_new_or_inherited_parameter_schema_required')
    if config['scope'] != 'filtered' or config['projection'] != NEW_COLUMNS or config['order'] != 'none':
        raise ValueError('fixed_alias_projection_region_scope_no_order_required')
    filters, required = config['filters'], config['required_filters']
    if type(filters) is not dict or set(filters) != {'logicalRegionName'}:
        raise ValueError('exact_region_filter_required')
    if type(required) is not list or required != ['logicalRegionName']:
        raise ValueError('exact_required_filters_required')
    value = filters['logicalRegionName']
    if (type(value) is not str or not value or value != value.strip() or '{{' in value or '}}' in value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError('nonempty_original_region_string_required')
    return config


def _new_materialize(item, config):
    ordinary = copy.deepcopy(item)
    for key in ('family_id', 'parameter_contract', 'default_params', 'params', 'family_parameters'):
        ordinary.pop(key, None)
    api = copy.deepcopy(NEW_API)
    for predicate in api['condition']['constraint']:
        predicate['simple']['value'] = config['filters']['logicalRegionName']
    ordinary.update(resources=['VM_NOVA'], api_call=api, sql=NEW_SQL)
    return ordinary


def _new_literal(question, tokens, value):
    choices = [re.escape(question[t['start']:t['end']]) for t in tokens if t['value'] == value]
    atom = r'A-Za-z0-9_@./:#%+\-'
    if re.fullmatch('[' + atom + ']+', value):
        choices.append(re.escape(value) + '(?![' + atom + '])')
    if not choices:
        raise ValueError('region_not_present_as_complete_original_literal')
    return '(?-i:(?:' + '|'.join(dict.fromkeys(choices)) + '))'


def _new_explicit_projection(question, tokens):
    markers = [m for m in re.finditer(
        r'(?:仅|只)?\s*(?:依次|按顺序)?\s*(?:输出|返回|显示|展示)(?:的)?(?:字段|列)?\s*(?:为|是|:|：)?\s*'
        r'|(?:字段|列)\s*(?:为|是|:|：|包括|包含)\s*', question)
        if not any(t['start'] <= m.start() < t['end'] for t in tokens)]
    if not markers:
        return question, False
    if len(markers) != 1:
        raise ValueError('single_explicit_projection_required')
    marker = markers[0]
    tail = question[marker.end():].strip().rstrip('。.;；!?！？ ')
    aliases = {
        'tenant_name': 'tenant_name', 'tenantName': 'tenant_name', '租户': 'tenant_name', '租户名称': 'tenant_name',
        'azone_name': 'azone_name', 'azoneName': 'azone_name', '可用区': 'azone_name', '可用区名称': 'azone_name',
        'vm_name': 'vm_name', 'name': 'vm_name', '实例名': 'vm_name', '实例名称': 'vm_name', '虚拟机名': 'vm_name',
        'private_ips': 'private_ips', 'privateIps': 'private_ips', 'IP': 'private_ips', 'IP地址': 'private_ips',
        '私网IP': 'private_ips', '私有IP': 'private_ips',
    }
    fields = re.split(r'\s*(?:、|,|，|和|与|及)\s*', tail)
    lookup = {key.casefold(): value for key, value in aliases.items()}
    if [lookup.get(field.casefold()) for field in fields] != NEW_COLUMNS:
        raise ValueError('fixed_explicit_alias_column_order_required')
    return question[:marker.start()].rstrip('，,、;； '), True


def _new_ground(question, config):
    tokens = quote_tokens(question)
    value = config['filters']['logicalRegionName']
    literal = _new_literal(question, tokens, value)
    # Match whole original text; no residual deletion can hide extra predicates,
    # ranking, grouping, pagination requests, extra outputs or additional parents.
    role = r'(?:logicalRegionName|区域|地区|地域|region)'
    operand = r'\s*(?:(?:等于|为|是|=|:|：)\s*)?' + literal
    region = r'(?:' + role + operand + '|' + literal + r'\s*(?:区域|地区|地域))'
    ecs = r'(?:(?<![A-Za-z0-9_])(?:ECS|VM_NOVA)(?![A-Za-z0-9_])|虚拟机|云主机)'
    name = r'(?:实例名(?:称)?|虚拟机名(?:称)?|名称)'
    ip = r'(?:(?:私网|私有)?IP(?:地址)?)'
    fields = name + r'\s*[和与及、]\s*' + ip
    tenant_zone = r'(?:各(?:个)?租户\s*(?:在|和|与|及|、)?\s*各(?:个)?(?:可用区|AZ)|每(?:个)?租户\s*(?:在)?\s*每(?:个)?(?:可用区|AZ))'
    prefix = r'\s*(?:(?:请帮我|帮我|麻烦|请)\s*)?(?:(?:查询|查看|查找|列出|查一下|看一下|获取)\s*)?'
    end = r'\s*[。.!！?？]*\s*'
    text, explicit = _new_explicit_projection(question, tokens)
    natural = [
        region + r'\s*(?:下|中|内|里|的)?\s*' + tenant_zone + r'\s*(?:中|内)?的?\s*' + ecs + r'\s*' + fields,
        region + r'\s*(?:下|中|内|里|的)?\s*' + ecs + r'\s*(?:在|于)?\s*' + tenant_zone + r'\s*(?:中|内)?的?\s*' + fields,
        r'按\s*(?:租户\s*[和与及、]\s*(?:可用区|AZ)|(?:可用区|AZ)\s*[和与及、]\s*租户)\s*(?:列出|查看|查询)\s*' + region + r'\s*(?:下|中|内|的)?\s*' + ecs + r'\s*' + fields,
    ]
    if explicit:
        natural.append(region + r'\s*(?:下|中|内|里|的)?\s*(?:所有|全部)?\s*' + ecs + r'\s*(?:实例|明细|清单|列表)?')
    if not re.fullmatch(prefix + '(?:' + '|'.join(natural) + ')' + end, text, re.I):
        raise ValueError('complete_original_region_tenant_zone_detail_evidence_required')
    return {'view': NEW_VIEW, 'filters': copy.deepcopy(config['filters']), 'columns': NEW_COLUMNS[:],
            'explicit_projection': explicit, 'scope': 'filtered', 'grain': 'VM records; no GROUP BY',
            'quoted_token_spans': [[t['start'], t['end']] for t in tokens],
            'source_api_sql_and_repeated_predicates_preserved': True}


def _materialize_batch3(item, parameters):
    if type(parameters) is dict and parameters.get('projection') == NEW_COLUMNS:
        return _new_materialize(item, _new_parameters(item, parameters))
    return _INHERITED_MATERIALIZE(item, parameters)


def _ground_batch3_parameters(question, item, parameters):
    if type(parameters) is dict and parameters.get('projection') == NEW_COLUMNS:
        return _new_ground(question, _new_parameters(item, parameters))
    return _INHERITED_GROUND(question, item, parameters)


def prepare_natural_candidate(question, item, parsed, frozen_prepare, diagnostics=None):
    if type(parsed) is dict and parsed.get('view') == NEW_VIEW:
        return prepare_candidate(question, item, parsed, diagnostics)
    return _INHERITED_NATURAL_PREPARE(question, item, parsed, frozen_prepare, diagnostics)


def materialize_candidate(item, parsed):
    """Structure only. prepare_candidate must ground original question for execution."""
    try:
        if type(parsed) is dict and parsed.get('view') == NEW_VIEW:
            return _new_materialize(item, _new_parameters(item, parsed))
        return _materialize_batch3(item, view_parameters(item, parsed) if 'view' in parsed else parsed)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def prepare_candidate(question, item, parsed, diagnostics=None):
    """F02 unified local boundary, preserving inherited explicit and natural paths."""
    diagnostic = diagnostics if diagnostics is not None else {}
    try:
        if type(item) is not dict or item.get('id') != FAMILY_ID or item.get('family_id') != 'F02':
            raise ValueError('selected_F02_item_required')
        is_new = type(parsed) is dict and (parsed.get('view') == NEW_VIEW or parsed.get('projection') == NEW_COLUMNS)
        if not is_new:
            if type(parsed) is dict and 'view' in parsed:
                return _INHERITED_NATURAL_PREPARE(question, item, parsed, _prepare_batch3_candidate, diagnostic)
            return _prepare_batch3_candidate(question, item, parsed, diagnostic)
        config = _new_parameters(item, parsed)
        evidence = _new_ground(question, config)
        ordinary = _new_materialize(item, config)
        diagnostic.update(family_status='materialized', family_id='F02', view=NEW_VIEW,
                          parameters=copy.deepcopy(parsed), contract_evidence=evidence)
        return ordinary
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        diagnostic.update(family_status='invalid_or_ungrounded_parameters', family_error=str(exc))
        return None
