"""Closed independent COUNT family, to insert into the existing B matcher.

No retrieval, model, SQL executor, old-ID routing or runtime template expansion.
Only the five reviewed resource/group/layout combinations are accepted.
"""
import re


_N28_RESOURCES = {
    'VM_NOVA': ('CLOUD_VM_NOVA', 'ECS'),
    'VOLUME': ('CLOUD_VOLUME', 'Volume'),
    'ROUTER': ('CLOUD_ROUTER', 'VPC'),
    'S_Switch': ('SYS_Switch', 'switch'),
    'S_Router': ('SYS_Router', 'router'),
    'ELB': ('CLOUD_ELB', None),
}
_N28_LAYOUTS = {
    ('VM_NOVA', 'VOLUME', 'ROUTER'): {'none': 'labeled_rows', 'vdcName': 'labeled_rows'},
    ('S_Switch', 'S_Router'): {'none': 'labeled_rows'},
    ('ROUTER',): {'vdcName': 'single_grouped'},
    ('ELB',): {'none': 'single_scalar'},
}


def materialize_count_family(item, parameters):
    """Return ordinary fully materialized api_call+sql, without changing SDK."""
    if not isinstance(item, dict) or item.get('family_id') != 'NEXT_N28':
        raise ValueError('unknown_count_family')
    keys = {'resource_set', 'group', 'layout', 'metric', 'filters', 'required_filters'}
    if not isinstance(parameters, dict) or set(parameters) != keys:
        raise ValueError('closed_count_parameter_schema_required')
    resources = parameters['resource_set']
    if not isinstance(resources, list) or not all(isinstance(x, str) for x in resources):
        raise ValueError('ordered_resource_list_required')
    group, layout = parameters['group'], parameters['layout']
    if not isinstance(group, str) or not isinstance(layout, str):
        raise ValueError('group_and_layout_strings_required')
    if _N28_LAYOUTS.get(tuple(resources), {}).get(group) != layout:
        raise ValueError('unreviewed_resource_group_layout_combination')
    if parameters['metric'] != 'count_rows':
        raise ValueError('only_count_star_supported')
    filters = parameters['filters']
    if (not isinstance(filters, dict) or set(filters) != {'logicalRegionName'}
            or parameters['required_filters'] != ['logicalRegionName']):
        raise ValueError('one_complete_equal_region_required')
    region = filters['logicalRegionName']
    if (not isinstance(region, str) or not region.strip() or '{{' in region
            or '}}' in region or '\n' in region or '\r' in region):
        raise ValueError('literal_nonempty_region_required')
    physical = resources[0].startswith('S_')
    label_column, count_column = ('device_type', 'total') if physical else ('type', 'count')
    calls, branches = [], []
    for ci in resources:
        table, label = _N28_RESOURCES[ci]
        calls.append({'method': 'GET',
                      'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=10000',
                      'condition': {'constraint': [{'simple': {
                          'name': 'logicalRegionName', 'value': region, 'operator': 'equal'}}]}})
        columns = []
        if layout == 'labeled_rows':
            columns.append("'" + label + "' AS " + label_column)
        if group == 'vdcName':
            columns.append('vdcName')
        columns.append('COUNT(*) AS ' + count_column)
        branch = 'SELECT ' + ', '.join(columns) + ' FROM ' + table
        if group == 'vdcName':
            branch += ' GROUP BY vdcName'
        branches.append(branch)
    # This is a fresh ordinary SDK item: metadata is never interpreted by SDK.
    return {'id': item.get('id', 'family_next_n28'),
            'name': 'independent_resource_row_counts', 'resources': list(resources),
            'api_call': calls if len(calls) > 1 else calls[0],
            'sql': ' UNION ALL '.join(branches)}


def _n28_mask(text, spans):
    chars = list(text)
    for start, end in spans:
        chars[start:end] = ' ' * (end - start)
    return ''.join(chars)


def parse_count_request(question):
    """Finite full-consumption Chinese grammar; no LLM or template lookup.

    Supports one explicit equal-region role and implicit ordinary count/group
    phrases or a matching terminal raw-column projection. Unsupported compound
    requests fail closed, and must not be partially answered by this family.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError('question_required')
    role = r'(?:logicalRegionName|区域|地区|地域|(?<![A-Za-z0-9_])region(?![A-Za-z0-9_]))'
    literal = r'''(?:"(?P<dq>[^"\n]+)"|'(?P<sq>[^'\n]+)'|“(?P<cq>[^”\n]+)”|「(?P<jq>[^」\n]+)」|(?P<bare>[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*))'''
    equal = r'\s*(?:(?:等于|为|是|=|:|：)\s*)?'
    matches = []
    for pattern in [role + equal + literal, literal + r'\s*(?:(?:为|是|等于)\s*)?' + role]:
        for m in re.finditer(pattern, question, re.I):
            value = next(x for x in m.groupdict().values() if x is not None)
            matches.append((m.start(), m.end(), value))
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    owned, stop = [], -1
    for match in matches:
        if match[0] >= stop:
            owned.append(match)
            stop = match[1]
    if len(owned) != 1:
        raise ValueError('one_explicit_region_binding_required')
    remaining = _n28_mask(question, [(owned[0][0], owned[0][1])])

    # Projection is an obligation, never a replacement for resources/metric.
    column_match = re.search(r'(?:返回|输出|显示)(?:字段|列)?\s*(?:为|是|:|：)?\s*'
                             r'([A-Za-z_][A-Za-z0-9_]*(?:\s*[,，、]\s*[A-Za-z_][A-Za-z0-9_]*)*)'
                             r'\s*[。;；!?！？]*\s*$', remaining)
    columns = None
    if column_match:
        columns = re.split(r'\s*[,，、]\s*', column_match.group(1))
        remaining = _n28_mask(remaining, [column_match.span()])
    group_pattern = (r'(?:所有\s*VDC\s*中\s*)?(?:各个|每个|各)\s*VDC'
                     r'|按\s*VDC\s*(?:分组|分别统计|统计)?')
    groups = list(re.finditer(group_pattern, remaining, re.I))
    if len(groups) > 1:
        raise ValueError('repeated_group_obligation')
    group = 'vdcName' if groups else 'none'
    remaining = _n28_mask(remaining, [m.span() for m in groups])
    resource_pattern = (r'(?<![A-Za-z0-9_])(?:VM_NOVA|ECS|VOLUME|ROUTER|S_Switch|S_Router|ELB|VPC)'
                        r'(?![A-Za-z0-9_])|云硬盘|虚拟机|负载均衡器|物理交换机|物理路由器|交换机|路由器')
    aliases = {'vm_nova': 'VM_NOVA', 'ecs': 'VM_NOVA', '虚拟机': 'VM_NOVA',
               'volume': 'VOLUME', '云硬盘': 'VOLUME', 'router': 'ROUTER', 'vpc': 'ROUTER',
               's_switch': 'S_Switch', '交换机': 'S_Switch', '物理交换机': 'S_Switch', 's_router': 'S_Router',
               '路由器': 'S_Router', '物理路由器': 'S_Router', 'elb': 'ELB', '负载均衡器': 'ELB'}
    resource_matches = list(re.finditer(resource_pattern, remaining, re.I))
    resources = [aliases[m.group().casefold()] for m in resource_matches]
    remaining = _n28_mask(remaining, [m.span() for m in resource_matches])
    # Listing order is not an ORDER BY. Restore the frozen source branch order,
    # accepting a permutation only when every member appears exactly once.
    for reviewed in _N28_LAYOUTS:
        if len(resources) == len(reviewed) and set(resources) == set(reviewed):
            resources = list(reviewed)
            break
    layout = _N28_LAYOUTS.get(tuple(resources), {}).get(group)
    if layout is None:
        raise ValueError('unreviewed_resource_group_combination')
    physical = resources[0].startswith('S_')
    expected_columns = []
    if layout == 'labeled_rows':
        expected_columns.append('device_type' if physical else 'type')
    if group == 'vdcName':
        expected_columns.append('vdcName')
    expected_columns.append('total' if physical else 'count')
    if columns is not None and columns != expected_columns:
        raise ValueError('projection_order_or_alias_mismatch')
    # Count must be requested even when an explicit field is named "count".
    # Consume verb+metric before "计数" can match across 统[计数]量.
    counts = list(re.finditer(r'(?:统计\s*)?(?:记录计数|记录数|数量|总数|有多少(?:个|台|块)?|多少(?:个|台|块)?|计数)', remaining))
    if not counts:
        raise ValueError('count_intent_required')
    remaining = _n28_mask(remaining, [m.span() for m in counts])
    glue = r'请|帮我|一下|查询|查看|查找|统计|分别|各自|一共|当前|所有|全部|实例|的|在|下|中|内|并且|并|且|和|与|及'
    remaining = re.sub(glue, ' ', remaining)
    remaining = re.sub(r'[\s，,、。.:：;；!?！？()/]+', '', remaining)
    if remaining:
        raise ValueError('unsupported_or_unconsumed_request_clause')
    return {'resource_set': resources, 'group': group, 'layout': layout,
            'metric': 'count_rows', 'filters': {'logicalRegionName': owned[0][2]},
            'required_filters': ['logicalRegionName']}


def prepare_count_candidate(question, item, parsed, diagnostics=None):
    """B boundary: compare external parsed structure to full original request.

    Caller owns retrieval/model stages/refinement/official output. Unsupported
    language is distinct internally from an executed successful empty result.
    """
    try:
        ordinary = materialize_count_family(item, parsed)
        actual = parse_count_request(question)
        if actual != parsed:
            raise ValueError('complete_request_parameter_mismatch')
    except (ValueError, TypeError) as exc:
        if diagnostics is not None:
            diagnostics.update(status='unsupported_or_ungrounded', reason=str(exc))
        return None
    if diagnostics is not None:
        diagnostics.update(status='materialized', parameters=actual)
    return ordinary
