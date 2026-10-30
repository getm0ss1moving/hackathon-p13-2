"""Isolated closed candidates. No network, database, model or legacy-ID routing."""
from copy import deepcopy
import json
import re

F10 = 'family_f10'
F17 = 'family_f17_safe'
FILTER_ORDER = ('logicalRegionName', 'azoneName', 'vendorName')
HOST_COLUMNS = {
    'vcpu_allocation_rate': ['name', 'ipAddress', 'allocatedVcpuCores', 'totalVcpuCores', 'allocation_rate'],
    'remaining_memory_mb': ['name', 'ipAddress', 'totalVmemoryMB', 'allocatedVmemoryMB', 'remaining_memory'],
}
POOL_COLUMNS = {
    'az_usage': ['azoneName', 'total_capacity', 'free_capacity', 'used_capacity', 'usage_rate'],
    'vendor_capacity': ['vendorName', 'total_capacity', 'free_capacity'],
}
HOST_SELECT = {
    'vcpu_allocation_rate': 'name, ipAddress, allocatedVcpuCores, totalVcpuCores, CAST(allocatedVcpuCores AS FLOAT) / totalVcpuCores AS allocation_rate',
    'remaining_memory_mb': 'name, ipAddress, totalVmemoryMB, allocatedVmemoryMB, totalVmemoryMB - allocatedVmemoryMB AS remaining_memory',
}
HOST_SORT_KEY = {'vcpu_allocation_rate': 'allocation_rate', 'remaining_memory_mb': 'remaining_memory'}
POOL_SQL = {
    'az_usage': 'SELECT azoneName, SUM(totalCapacityGB) AS total_capacity, SUM(freeCapacityGB) AS free_capacity, (SUM(totalCapacityGB) - SUM(freeCapacityGB)) AS used_capacity, ROUND((SUM(totalCapacityGB) - SUM(freeCapacityGB)) * 100.0 / SUM(totalCapacityGB), 2) AS usage_rate FROM CLOUD_STORAGE_POOL GROUP BY azoneName',
    'vendor_capacity': 'SELECT vendorName, SUM(totalCapacityGB) AS total_capacity, SUM(freeCapacityGB) AS free_capacity FROM CLOUD_STORAGE_POOL GROUP BY vendorName',
}
_ROLE = re.compile(
    r'(?P<region>逻辑区域|区域|(?<![A-Za-z0-9_])(?:logicalRegionName|region)(?![A-Za-z0-9_]))'
    r'|(?P<az>可用区|(?<![A-Za-z0-9_])(?:azoneName|AZ)(?![A-Za-z0-9_]))'
    r'|(?P<vendor>供应商|厂商|(?<![A-Za-z0-9_])vendorName(?![A-Za-z0-9_]))', re.I)
_RESOURCE = {
    F10: r'宿主机|(?<![A-Za-z0-9_])(?:CLOUD_HOST|HOST)(?![A-Za-z0-9_])',
    F17: r'云存储池|存储池|(?<![A-Za-z0-9_])(?:CLOUD_STORAGE_POOL|STORAGE_POOL)(?![A-Za-z0-9_])',
}
_METRICS = {
    'vcpu_allocation_rate': r'(?:v\s*cpu|虚拟CPU|CPU)(?:的)?(?:已)?分配(?:比率|比例|占比|率)|v\s*cpu\s+allocation\s+(?:rate|ratio)',
    'remaining_memory_mb': r'内存(?:的)?(?:剩余(?:量|容量)?|余量)|(?:剩余|可用)(?:的)?内存(?:量|容量)?|remaining\s+memory',
}
_GROUPS = {
    'azoneName': r'(?:按照|根据|各个|每个|按|以|各|每)\s*(?:可用区|(?<![A-Za-z0-9_])(?:azoneName|AZ)(?![A-Za-z0-9_]))(?:\s*分组)?',
    'vendorName': r'(?:按照|根据|各个|每个|按|以|各|每)\s*(?:供应商|厂商|(?<![A-Za-z0-9_])vendorName(?![A-Za-z0-9_]))(?:\s*分组)?',
}
_FIELD_ALIASES = {
    'name': ['name', '主机名', '宿主机名', '宿主机名称', '名称'],
    'ipAddress': ['ipAddress', 'IP', 'IP地址', '宿主机IP'],
    'allocatedVcpuCores': ['allocatedVcpuCores', '已分配vCPU', '已分配vCPU核数'],
    'totalVcpuCores': ['totalVcpuCores', 'vCPU总量', 'vCPU总核数'],
    'allocation_rate': ['allocation_rate', 'vCPU分配率', '分配率'],
    'totalVmemoryMB': ['totalVmemoryMB', '内存总量', '总内存'],
    'allocatedVmemoryMB': ['allocatedVmemoryMB', '已分配内存'],
    'remaining_memory': ['remaining_memory', '剩余内存', '内存剩余量'],
    'azoneName': ['azoneName', '可用区', 'AZ'],
    'vendorName': ['vendorName', '厂商', '供应商'],
    'total_capacity': ['total_capacity', '总容量'],
    'free_capacity': ['free_capacity', '可用容量', '空闲容量'],
    'used_capacity': ['used_capacity', '已用容量'],
    'usage_rate': ['usage_rate', '使用率'],
}
_ALIAS_TO_FIELD = {re.sub(r'\s+', '', a).lower(): f for f, aliases in _FIELD_ALIASES.items() for a in aliases}
_GENERIC = (
    r'帮我查询|帮我查一下|帮忙查询|查询一下|请帮我|帮我|帮忙|请|查一下|看一下|查询|查看|统计|列出|展示|显示|返回|输出|'
    r'当前|目前|所有|全部|分别|分组|排名|列表|情况|信息|的|下|中|内|和|以及|及|与|并且|且|并|\bAND\b'
)


class ContractError(ValueError):
    """Internal diagnostic only; never serialize as a business answer."""


def _consume(text, pattern):
    found = list(re.finditer(pattern, text, re.I))
    for m in reversed(found):
        text = text[:m.start()] + ' ' * (m.end() - m.start()) + text[m.end():]
    return text, found


def _quoted_ranges(text):
    ranges = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] in ('"', "'", '“', '‘'):
            _, end = _quoted_value(text, cursor)
            ranges.append((cursor, end))
            cursor = end
        else:
            cursor += 1
    return ranges


def _projection(question):
    quoted = _quoted_ranges(question)
    markers = [m for m in re.finditer(r'(输出|返回|显示|列出)(?:的)?(?:字段|列)?(?:为|是|:|：)?\s*', question)
               if not any(start < m.end() and m.start() < end for start, end in quoted)]
    for m in reversed(markers):
        tail = question[m.end():].strip().rstrip('。.;；!?！？ ')
        parts = re.split(r'\s*(?:、|,|，|和|以及|及)\s*', tail)
        if parts and re.sub(r'\s+', '', parts[0]).lower() in _ALIAS_TO_FIELD:
            try:
                fields = [_ALIAS_TO_FIELD[re.sub(r'\s+', '', p).lower()] for p in parts]
            except KeyError as exc:
                raise ContractError('unsupported_explicit_projection') from exc
            if len(fields) != len(set(fields)):
                raise ContractError('duplicate_projection')
            return question[:m.start()], fields
        if m.group(1) in ('输出', '返回'):
            raise ContractError('unrecognized_explicit_output')
    return question, None


def _quoted_value(text, start):
    pairs = {'"': '"', "'": "'", '“': '”', '‘': '’'}
    if start >= len(text) or text[start] not in pairs:
        return None
    opener, close = text[start], pairs[text[start]]
    if opener == '"':
        try:
            value, length = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(value, str):
                return value, start + length
        except (ValueError, json.JSONDecodeError):
            pass
    end = text.find(close, start + 1)
    if end < 0:
        raise ContractError('unclosed_entity_quote')
    return text[start + 1:end], end + 1


def _filters(text):
    found, spans = {}, []
    for match in _ROLE.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        if re.search(r'(?:按照|根据|各个|每个|按|以|各|每)\s*$', text[:match.start()]):
            continue
        field = {'region': 'logicalRegionName', 'az': 'azoneName', 'vendor': 'vendorName'}[match.lastgroup]
        start = match.end()
        if re.match(r'\s*(?:不等于|不是|不为|不包含|包含|大于|小于|排除|!=|<>|>=|<=|>|<|\b(?:not|like|contain|in)\b)', text[start:], re.I):
            raise ContractError('unsupported_filter_operator')
        bridge = re.match(r'\s*(?:(?:为|是|等于|=|:|：)\s*)?', text[start:])
        start += bridge.end()
        quoted = _quoted_value(text, start)
        if quoted:
            value, end = quoted
        else:
            token = re.match(r'[A-Za-z0-9_.@#:/+\-\u4e00-\u9fff]+', text[start:])
            if not token:
                raise ContractError('missing_filter_value')
            value = token.group()
            cuts = []
            for next_role in _ROLE.finditer(value):
                if next_role.start() > 0:
                    end_of_value = next_role.start()
                    connector = re.search(r'(?:以及|并且|或者|和|且|或|\bAND\b|\bOR\b)\s*$', value[:end_of_value], re.I)
                    cuts.append(connector.start() if connector else end_of_value)
                    break
            boundary = next((p for p in re.finditer(r'下|中|内|的', value) if p.start() > 0), None)
            if boundary:
                cuts.append(boundary.start())
            # Unquoted values end at an adjacent business phrase. Complex names
            # containing role/metric words must be quoted to remain opaque.
            content = re.search(r'内存|剩余内存|可用内存|宿主机|存储池|状态|租户|标签|阈值|(?<![A-Za-z0-9_])(?:vCPU|CLOUD_HOST|HOST|STORAGE_POOL|tenantName|status|vdcName|VDC)(?![A-Za-z0-9_])', value, re.I)
            if content and content.start() > 0:
                cuts.append(content.start())
            if cuts:
                value = value[:min(cuts)]
            if value in ('的', '下', '中', '内'):
                raise ContractError('missing_filter_value')
            if re.search(r'不等于|不是|不为|不包含|包含|排除|以外|之外|除外|或者|或', value):
                raise ContractError('ambiguous_unquoted_filter_operator')
            if any(p.start() > 0 for p in re.finditer(r'和|以及|且|并且', value)):
                raise ContractError('ambiguous_unquoted_multi_value')
            end = start + len(value)
        if not value or not value.strip() or value != value.strip():
            raise ContractError('empty_or_ambiguous_filter')
        if field in found:
            raise ContractError('repeated_filter_role')
        found[field] = value
        spans.append((match.start(), end))
    for start, end in reversed(spans):
        text = text[:start] + ' ' * (end - start) + text[end:]
    return text, found


def validate_parameters(family_id, parsed):
    if type(parsed) is not dict:
        raise ContractError('parameters_not_object')
    allowed = ({'metric', 'direction', 'top_k', 'filters', 'required_filters'} if family_id == F10
               else {'view', 'filters', 'required_filters'} if family_id == F17 else set())
    if not allowed or set(parsed) != allowed:
        raise ContractError('unknown_or_missing_parameter_keys')
    fs, required = parsed['filters'], parsed['required_filters']
    valid_fields = set(FILTER_ORDER[:2]) if family_id == F10 else set(FILTER_ORDER)
    if type(fs) is not dict or not fs or not set(fs) <= valid_fields:
        raise ContractError('unsupported_filters')
    for value in fs.values():
        if type(value) is not str or not value.strip() or value != value.strip() or '{{' in value or '}}' in value:
            raise ContractError('invalid_filter_value')
    if type(required) is not list or any(type(k) is not str for k in required):
        raise ContractError('invalid_required_filters')
    if len(required) != len(set(required)) or set(required) != set(fs):
        raise ContractError('required_filters_not_exact')
    if family_id == F10:
        if type(parsed['metric']) is not str or parsed['metric'] not in HOST_SELECT or parsed['direction'] != 'desc':
            raise ContractError('unsupported_rank_variant')
        if type(parsed['top_k']) is not int or not 1 <= parsed['top_k'] <= 2147483647:
            raise ContractError('invalid_top_k')
    elif type(parsed['view']) is not str or parsed['view'] not in POOL_SQL or 'logicalRegionName' not in fs:
        raise ContractError('unsupported_pool_view_or_missing_region')
    clean = deepcopy(parsed)
    clean['filters'] = {k: fs[k] for k in FILTER_ORDER if k in fs}
    clean['required_filters'] = [k for k in FILTER_ORDER if k in fs]
    return clean


def infer_parameters(question, family_id):
    """Bounded natural-language contract check; no entity/example lookup."""
    if type(question) is not str or not question.strip():
        raise ContractError('empty_question')
    if family_id not in _RESOURCE:
        raise ContractError('unsupported_family')
    text, projection = _projection(question)
    text, filters = _filters(text)
    text, resources = _consume(text, _RESOURCE[family_id])
    if not resources:
        raise ContractError('resource_not_proven')
    if family_id == F10:
        metrics = []
        for metric, regex in _METRICS.items():
            text, hits = _consume(text, regex)
            if hits:
                metrics.append(metric)
        if len(metrics) != 1:
            raise ContractError('rank_metric_missing_or_conflicting')
        metric = metrics[0]
        numbers = []
        rank_patterns = [r'前\s*(\d+)\s*(?:台|个)?', r'\btop\s*(\d+)\s*(?:台|个)?',
            r'(?:最高|最大|最多|最低|最小|最少)(?:的)?\s*(\d+)\s*(?:台|个)',
            r'(?:最高|最大|最多|最低|最小|最少)(?:的)?\s*(一)\s*(?:台|个)']
        # Extract direction before the K pattern can consume a superlative.
        desc = bool(re.search(r'最高|最大|最多|降序|从高到低|从大到小', text))
        asc = bool(re.search(r'最低|最小|最少|升序|从低到高|从小到大', text))
        if desc and asc:
            raise ContractError('conflicting_sort_directions')
        if asc:
            raise ContractError('ascending_null_ranking_policy_not_supported')
        for pattern in rank_patterns:
            text, hits = _consume(text, pattern)
            numbers += [1 if m.group(1) == '一' else int(m.group(1)) for m in hits]
        if not numbers or len(set(numbers)) != 1:
            raise ContractError('top_k_missing_or_conflicting')
        text, _ = _consume(text, r'最高|最大|最多|最低|最小|最少|降序|升序|从高到低|从大到小|从低到高|从小到大')
        parsed = {'metric': metric, 'direction': 'desc', 'top_k': numbers[0],
            'filters': filters, 'required_filters': list(filters)}
        expected_columns = HOST_COLUMNS[metric]
    else:
        groups = []
        for group, regex in _GROUPS.items():
            text, hits = _consume(text, regex)
            if hits:
                groups.append(group)
        if len(groups) != 1:
            raise ContractError('pool_group_missing_or_conflicting')
        text, usage = _consume(text, r'容量使用(?:情况|统计)?|容量利用(?:情况|统计)?|使用率|usage_rate')
        text, total = _consume(text, r'总容量|容量总量|total_capacity')
        text, free = _consume(text, r'可用容量|空闲容量|剩余容量|free_capacity')
        text, used = _consume(text, r'已用容量|used_capacity')
        if groups[0] == 'azoneName' and (usage or projection == POOL_COLUMNS['az_usage']):
            view = 'az_usage'
        elif groups[0] == 'vendorName' and not usage and not used and (
                (total and free) or projection == POOL_COLUMNS['vendor_capacity']):
            view = 'vendor_capacity'
        else:
            raise ContractError('unsupported_pool_metric_group_pair')
        parsed = {'view': view, 'filters': filters, 'required_filters': list(filters)}
        expected_columns = POOL_COLUMNS[view]
    if projection is not None and projection != expected_columns:
        raise ContractError('projection_order_or_columns_mismatch')
    text, _ = _consume(text, _GENERIC)
    residue = re.sub(r'[\s，,。.;；:：、!?！？()（）]+', '', text)
    if residue:
        raise ContractError('unconsumed_request_semantics')
    return validate_parameters(family_id, parsed)


def materialize_candidate(selected_item, parsed):
    """Return an ordinary item; caller must use prepare for question validation."""
    if type(selected_item) is not dict:
        raise ContractError('item_not_object')
    family_id = selected_item.get('id')
    config = validate_parameters(family_id, parsed)
    ci = 'HOST' if family_id == F10 else 'STORAGE_POOL'
    api = {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=10000',
        'condition': {'constraint': [{'simple': {'name': field, 'value': value, 'operator': 'equal'}}
            for field, value in config['filters'].items()]}}
    if family_id == F10:
        metric = config['metric']
        sql = ('SELECT ' + HOST_SELECT[metric] + ' FROM CLOUD_HOST ORDER BY ' + HOST_SORT_KEY[metric]
               + ' ' + config['direction'].upper() + ' LIMIT ' + str(config['top_k']))
    else:
        sql = POOL_SQL[config['view']]
    item = deepcopy(selected_item)
    for key in ('default_params', 'params', 'parameter_contract', 'family_parameters'):
        item.pop(key, None)
    item.update({'resources': [ci], 'api_call': api, 'sql': sql})
    return item


def prepare_single_table_candidate(question, selected_item, parsed, diagnostics=None):
    """B-facing boundary: ordinary item or None; diagnostics remain internal."""
    try:
        if type(selected_item) is not dict:
            raise ContractError('item_not_object')
        config = validate_parameters(selected_item.get('id'), parsed)
        from_question = infer_parameters(question, selected_item.get('id'))
        if config != from_question:
            raise ContractError('parsed_parameters_do_not_match_question')
        return materialize_candidate(selected_item, config)
    except (ContractError, TypeError, KeyError) as exc:
        if isinstance(diagnostics, dict):
            diagnostics.setdefault('single_table_candidate', []).append({'status': 'unsupported', 'reason': str(exc)})
        return None


def refined_contract_unchanged(prepared, refined):
    """Optional B post-refine gate; does not call or replace SQL refinement."""
    return (type(prepared) is dict and type(refined) is dict
        and all(prepared.get(k) == refined.get(k) for k in ('resources', 'api_call', 'sql')))


CANDIDATES = [
    {'id': F10, 'family_id': 'F10', 'name': '宿主机vCPU分配率与剩余内存排名',
     'description': 'HOST单表排名：vCPU分配率比值或剩余内存MB；两种受控指标降序与正整数TopK，明确区域/可用区AND条件，保留原五列、NULL和记录粒度。须由prepare物化。',
     'resources': ['HOST'], 'examples': ['查询区域内vCPU分配率最高的前若干台宿主机', '查询可用区内内存剩余量最大的前若干台宿主机'],
     'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000',
        'condition': {'constraint': [{'simple': {'name': 'logicalRegionName', 'value': '{{logicalRegionName}}', 'operator': 'equal'}}]}},
     'sql': 'SELECT ' + HOST_SELECT['vcpu_allocation_rate'] + ' FROM CLOUD_HOST ORDER BY allocation_rate DESC LIMIT 5'},
    {'id': F17, 'family_id': 'F17_SAFE', 'name': '存储池按可用区使用情况或厂商容量汇总',
     'description': 'STORAGE_POOL单表：各AZ总/空闲/已用/加权使用率，或各厂商总/可用容量。明确region及可选AZ/厂商AND；SUM后计算比例，不用allocated、不把协议当类型。须由prepare物化。',
     'resources': ['STORAGE_POOL'], 'examples': ['查询区域内各可用区的存储池容量使用情况', '查询区域内各厂商存储池总容量和可用容量'],
     'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000',
        'condition': {'constraint': [{'simple': {'name': 'logicalRegionName', 'value': '{{logicalRegionName}}', 'operator': 'equal'}}]}},
     'sql': POOL_SQL['az_usage']},
]
