"""Pure batch4 business contracts; no model, service, SDK extension or executor."""
import copy
import itertools
import re


SPECS = {
    'F26': {'ci': 'VFW', 'table': 'CLOUD_VFW',
            'filters': ['name', 'logicalRegionName', 'vdcName', 'status'],
            'views': {'rows': ['name', 'status'], 'count': ['vdcName', 'count']}},
    'F16': {'ci': 'STORAGE_POOL', 'table': 'CLOUD_STORAGE_POOL',
            'filters': ['name', 'azoneName', 'logicalRegionName'],
            'views': {'capacity_detail': ['name', 'totalCapacityGB', 'freeCapacityGB', 'provisionedCapacityGB',
                                          'used_capacity', 'usage_rate', 'over_subscription_ratio'],
                      'usage_list': ['name', 'totalCapacityGB', 'freeCapacityGB', 'used_capacity', 'usage_rate']}},
    'F11_CORE': {'ci': 'S_X86Server', 'table': 'SYS_X86Server',
                 'filters': ['logicalRegionName', 'productName', 'manufacturer'],
                 'views': {'region_count': ['logicalRegionName', 'count'], 'manufacturer_count': ['manufacturer', 'count']}},
}

EXPRESSIONS = {
    'used_capacity': '(totalCapacityGB - freeCapacityGB) AS used_capacity',
    'usage_rate': 'ROUND((totalCapacityGB - freeCapacityGB) * 100.0 / totalCapacityGB, 2) AS usage_rate',
    'over_subscription_ratio': 'ROUND(provisionedCapacityGB * 100.0 / totalCapacityGB, 2) AS over_subscription_ratio',
    'count': 'COUNT(*) AS count',
}

ROLES = {
    'name': ['名称', '名字', 'name'], 'logicalRegionName': ['logicalRegionName', '区域', '地域', '地区', 'region'],
    'azoneName': ['azoneName', '可用区', 'AZ'], 'vdcName': ['vdcName', 'VDC名称', 'VDC'],
    'status': ['status', '状态'], 'productName': ['productName', '产品型号', '产品名称', '产品名', '型号'],
    'manufacturer': ['manufacturer', '制造商', '厂商', '厂家'],
}

COLUMN_LABELS = {
    'name': ['name', '名称', '名字'], 'status': ['status', '状态'], 'vdcName': ['vdcName', 'VDC名称', 'VDC'],
    'count': ['count', '数量', '计数'], 'logicalRegionName': ['logicalRegionName', '区域', '地域'],
    'manufacturer': ['manufacturer', '厂商', '制造商', '厂家'], 'totalCapacityGB': ['totalCapacityGB', '总容量'],
    'freeCapacityGB': ['freeCapacityGB', '可用容量'], 'provisionedCapacityGB': ['provisionedCapacityGB', '预配置容量', '预分配容量'],
    'used_capacity': ['used_capacity', '已用容量'], 'usage_rate': ['usage_rate', '使用率'],
    'over_subscription_ratio': ['over_subscription_ratio', '超配比'],
}

RESOURCE = {
    'F26': r'(?:(?<![A-Za-z0-9_])VFW(?![A-Za-z0-9_])|虚拟防火墙)',
    'F16': r'(?:(?<![A-Za-z0-9_])STORAGE_POOL(?![A-Za-z0-9_])|存储池)',
    'F11_CORE': r'(?:(?<![A-Za-z0-9_])S_X86Server(?![A-Za-z0-9_])|物理服务器|服务器)',
}


def materialize_batch4(item, parsed):
    family = item.get('family_id')
    if family not in SPECS or not isinstance(parsed, dict) or set(parsed) != {'view', 'filters', 'required_filters'}:
        raise ValueError('closed_batch4_schema_required')
    spec = SPECS[family]
    view = parsed['view']
    if not isinstance(view, str) or view not in spec['views']:
        raise ValueError('unsupported_view')
    filters, required = parsed['filters'], parsed['required_filters']
    if (not isinstance(filters, dict) or not filters or not isinstance(required, list)
            or any(not isinstance(k, str) for k in required) or len(set(required)) != len(required)
            or set(required) != set(filters) or set(filters) - set(spec['filters'])):
        raise ValueError('complete_nonempty_filter_contract_required')
    for field, value in filters.items():
        if not isinstance(value, str) or not value.strip() or '{{' in value or '}}' in value:
            raise ValueError('nonempty_original_text_required:' + field)
    columns = spec['views'][view]
    sql = 'SELECT ' + ', '.join(EXPRESSIONS.get(c, c) for c in columns) + ' FROM ' + spec['table']
    if family == 'F26' and view == 'count': sql += ' GROUP BY vdcName'
    if family == 'F11_CORE': sql += ' GROUP BY ' + columns[0]
    if family == 'F16' and view == 'usage_list': sql += ' ORDER BY usage_rate DESC'
    ordinary = copy.deepcopy(item)
    for key in ['family_id', 'parameter_contract', 'default_params']:
        ordinary.pop(key, None)
    ordinary['sql'] = sql
    ordinary['api_call'] = {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + spec['ci'] + '?pageNo=1&pageSize=10000',
                           'condition': {'constraint': [{'simple': {'name': field, 'value': filters[field], 'operator': 'equal'}}
                                                        for field in spec['filters'] if field in filters]}}
    return ordinary


def _quoted(text):
    return [m.span() for m in re.finditer(r'''"[^"\n]*"|'[^'\n]*'|“[^”\n]*”|「[^」\n]*」''', text)]


def _inside(span, spans): return any(a <= span[0] and span[1] <= b for a, b in spans)


def _mask(text, spans):
    chars = list(text)
    for a, b in spans: chars[a:b] = ' ' * (b - a)
    return ''.join(chars)


def _label(text):
    return r'(?<![A-Za-z0-9_])' + re.escape(text) + r'(?![A-Za-z0-9_])' if text.isascii() else re.escape(text)


def _literal(value, allow_bare=True):
    alternatives = [re.escape(a) + re.escape(value) + re.escape(b)
                    for a, b in [('"', '"'), ("'", "'"), ('“', '”'), ('「', '」')]]
    # Bare entities cannot swallow query operators. Quotes keep such names opaque.
    if allow_bare and not re.search(r'或者|或|不是|不等|不属于|排除|除了|剔除|包含|开头|大于|小于|不为|!=|<>|\|\||(?<![A-Za-z0-9_])(?:OR|AND|NOT)(?![A-Za-z0-9_])', value, re.I):
        alternatives.append(re.escape(value) + r'(?![A-Za-z0-9_@./:#%+\-])')
    return '(?-i:(?:' + '|'.join(alternatives) + '))'


def ground_batch4(question, item, parsed):
    materialize_batch4(item, parsed)
    if not isinstance(question, str) or not question.strip(): raise ValueError('question_required')
    family, view = item['family_id'], parsed['view']
    spec, filters = SPECS[family], parsed['filters']
    text = question
    # Complete explicit output owns all column tokens and fixes their order.
    labels = {label: field for field, aliases in COLUMN_LABELS.items() for label in aliases}
    labels['COUNT(*) AS count'] = 'count'  # Exactly the reviewed output expression, not arbitrary SQL.
    canonical = {label.casefold(): field for label, field in labels.items()}
    field = '(?:' + '|'.join(_label(label) for label in sorted(labels, key=len, reverse=True)) + ')'
    intro = r'(?:只需|仅|只)?\s*(?:依次|按顺序)?\s*(?:(?:输出|返回|显示|展示)\s*(?:字段|列)?|(?:字段|列)\s*(?:为|是|:|：|包括|包含))\s*(?:为|是|:|：)?\s*'
    sorting = r'(?:按|按照)?\s*(?:使用率|usage_rate)\s*(?:降序(?:排序|排列)?|从高到低(?:排列|排序)?)'
    tail = r'(?=\s*' + (r'(?:[，,;；]\s*' + sorting + r')?' if family=='F16' and view=='usage_list' else '') + r'\s*[。;；!?！？]*\s*$)'
    projection = intro + field + r'(?:\s*(?:、|,|，|和|与|及|/)\s*' + field + r')*' + tail
    projections = [m for m in re.finditer(projection, text, re.I) if not _inside(m.span(), _quoted(text))]
    explicit = bool(projections)
    if len(projections) > 1: raise ValueError('single_explicit_projection_required')
    if explicit:
        p = projections[0]
        columns = [canonical[m.group().casefold()] for m in re.finditer(field, p.group(), re.I)]
        if columns != spec['views'][view]: raise ValueError('explicit_projection_mismatch')
        text = _mask(text, [p.span()])

    # Each declared filter owns one exact raw role/value span. Other conditions
    # cannot disappear: their text remains for complete residual checking.
    spans, values = [], {}
    # Entity fields own their complete evidence before status is interpreted.
    # JSON key order cannot let status words inside a name become predicates.
    for key, value in sorted(filters.items(), key=lambda pair: pair[0] == 'status'):
        aliases = ROLES[key]
        role = '(?:' + '|'.join(_label(a) for a in sorted(aliases, key=len, reverse=True)) + ')'
        # For attached ASCII role+entity, full exact value supplies the boundary.
        attached = '(?:' + '|'.join(r'(?<![A-Za-z0-9_])' + re.escape(a) for a in aliases if a.isascii()) + ')'
        literal = _literal(value)
        negative = r'不是|不等于|不为|不属于|!=|<>'
        if key == 'status': negative += r'|(?:(?:为|是|:|：)\s*)?非'
        # Look ahead *before* consuming spaces to prevent regex backtracking
        # from swallowing a negation as the operand instead of the operator.
        operator_guard = r'(?!\s*(?:' + negative + '))'
        implicit_post_literal = _literal(value, allow_bare=not (
            key == 'status' and re.match(r'(?:(?:为|是)\s*)?非', value)))
        scope_intro = r'(?:(?:它|它们)?\s*位于|范围限定|范围为|限定在)?\s*'
        patterns = [scope_intro + role + operator_guard + r'\s*(?:(?:等于|为|是|=|:|：)\s*)?' + literal,
                    implicit_post_literal + r'\s*(?:(?:为|是)\s*)?' + role,
                    literal + r'\s*(?:等于|=)\s*' + role,
                    implicit_post_literal + r'\s*[:：]\s*' + role]
        if any(a.isascii() for a in aliases): patterns.append(attached + operator_guard + literal)
        found = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.I):
                if not _inside(match.span(), _quoted(text)) and not _inside(match.span(), spans):
                    found.append(match.span())
        found = sorted(set(found), key=lambda s: (s[0], -(s[1]-s[0])))
        # Same occurrence may match a shorter role alias, not another operand.
        found = [s for i, s in enumerate(found) if not any(a <= s[0] and s[1] <= b for a,b in found[:i])]
        if not found and key == 'name' and family in {'F26', 'F16'}:
            resource = RESOURCE[family].replace('(?![A-Za-z0-9_])', '')
            pattern = resource + r'\s*(?P<entity>' + literal + ')'
            for match in re.finditer(pattern, text, re.I):
                if not _inside(match.span(), _quoted(text)): found.append(match.span('entity'))
        if len(found) != 1: raise ValueError('exact_single_filter_evidence_required:' + key)
        if any(max(a,c) < min(b,d) for a,b in found for c,d in spans):
            raise ValueError('filter_evidence_cannot_overlap:' + key)
        spans.extend(found); values[key] = value
    text = _mask(text, spans)
    resources = list(re.finditer(RESOURCE[family], text, re.I))
    if len(resources) != 1: raise ValueError('explicit_single_resource_required')
    text = _mask(text, [r.span() for r in resources])

    def consume(pattern):
        nonlocal text
        matches = list(re.finditer(pattern, text, re.I))
        text = _mask(text, [m.span() for m in matches])
        return bool(matches)
    group_prefix = r'(?:仅|只)?(?:各个|每个|各|(?:按|按照|以)\s*(?:各个|每个|各)?)\s*'
    group_suffix = r'\s*(?:为单位|为维度|分组)?'
    # No predicate operator is grammatical glue or a removable attribute token.
    if re.search(r'不是|不等于|不为|包含|开头|大于|小于|!=|<>|\|\||或者|或|(?<![A-Za-z0-9_])OR(?![A-Za-z0-9_])', text, re.I):
        raise ValueError('unsupported_predicate_or_disjunction')
    # Own the action before count nouns: 统计+数量 must not be split into
    # 统+计数+量. Only these views have an established count obligation.
    if family=='F11_CORE' or family=='F26' and view=='count': consume(r'统计')
    if family == 'F26':
        if view == 'rows':
            has_intent = consume(r'基本信息|基本情况|列表|清单|(?:名称|名字)\s*[和与及、]\s*状态|状态\s*[和与及、]\s*(?:名称|名字)')
        else:
            group = consume(group_prefix + r'(?:vdcName|VDC(?:名称)?)' + group_suffix)
            metric = consume(r'数量|个数|计数')
            has_intent = group and metric
    elif family == 'F11_CORE':
        if view == 'manufacturer_count':
            group = consume(group_prefix + r'(?:厂商|制造商|厂家|manufacturer)' + group_suffix)
        else:
            group = consume(group_prefix + r'(?:区域|地区|地域|logicalRegionName)' + group_suffix)
            if 'productName' in filters and re.search(r'分布', text): group = True
        metric = consume(r'数量|个数|计数')
        consume(r'及?分布情况|分布')
        has_intent = group and metric
    else:
        # Keep original per-record percent formulas; neither thresholds nor a
        # different order may be consumed as an output request.
        attrs = ['总容量', '可用容量', '已用容量', '使用率']
        if view == 'capacity_detail': attrs += ['预配置容量', '预分配容量', '超配比']
        if re.search(r'(?:' + '|'.join(attrs) + r')\s*(?:为|是|在|=|[<>])', text):
            raise ValueError('unsupported_capacity_predicate')
        usage_requested = bool(re.search(r'使用率', text))
        detail_requested = bool(re.search(r'容量(?:使用)?(?:情况|详情|明细)|超配比|预配置容量|预分配容量', text))
        if view == 'usage_list':
            consume(sorting)
            if detail_requested and not explicit: raise ValueError('capacity_detail_cannot_be_usage_list')
        consume(r'容量(?:使用)?(?:情况|详情|明细)|使用率列表|列表|清单')
        has_intent = detail_requested if view == 'capacity_detail' else usage_requested
        attribute_matches = list(re.finditer('|'.join(sorted(attrs,key=len,reverse=True)), text))
        if attribute_matches:
            text = _mask(text, [m.span() for m in attribute_matches])
    if not explicit and not has_intent: raise ValueError('view_intent_required')
    # Common request verbs only; no role, metric, operator or grouping words.
    text = re.sub(r'帮我(?:看看|查看|查询|查一下)|(?:我)?想(?:看看|查看|查询)|查一下|列一下|看看|我想看|请|帮我|查询|查看|列出|显示|返回|获取|它们|它|下|内|中|里|的|在|情况|并且|且|和|与|及|各|分别|所有|全部', ' ', text)
    text = re.sub(r'[\s，,、。;；:：!?！？()/]+', '', text)
    if text: raise ValueError('unsupported_or_unexpressed_clause')
    return {'family_id': family, 'view': view, 'filters': values, 'explicit_projection': explicit}


def prepare_batch4(question, item, parsed, diagnostics=None):
    try:
        ordinary = materialize_batch4(item, parsed)
        evidence = ground_batch4(question, item, parsed)
    except (ValueError, TypeError) as exc:
        if diagnostics is not None: diagnostics.update(status='unsupported', reason=str(exc))
        return None
    if diagnostics is not None: diagnostics.update(status='materialized', evidence=evidence)
    return ordinary
