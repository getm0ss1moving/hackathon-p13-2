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
