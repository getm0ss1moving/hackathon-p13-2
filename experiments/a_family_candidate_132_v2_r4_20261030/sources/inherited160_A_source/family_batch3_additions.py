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
