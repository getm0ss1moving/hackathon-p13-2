"""纯函数候选：按区域内租户资源数量选最大租户，再展开完整明细。

不负责问句路由、网络、表装载或官方执行；B必须先完成preflight及typed schema门禁。
"""
from urllib.parse import urlencode
from copy import deepcopy
import json
import unicodedata
import hashlib
import sqlite3

FAMILY_ID = 'A_ISSUE3_RANKED_TENANT_DETAILS'
REVISION = 'R2'
PROJECTION_CONTRACT = 'tenant-identity-projection-v2'
# Explicit, versioned Unicode whitespace set, including Python legacy C0 separators.
# Nonblank identity values are never stripped or otherwise rewritten.
TENANT_WHITESPACE_CODEPOINTS = (9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)
TENANT_WHITESPACE = frozenset(chr(c) for c in TENANT_WHITESPACE_CODEPOINTS)

def is_unknown_tenant_identity(value):
    return value is None or (isinstance(value, str) and all(c in TENANT_WHITESPACE for c in value))

def _compact_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))

def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

def check_envelope_budget(payload, *, boundary='B_final_envelope', byte_limit=4096):
    """Measure the supplied actual JSON envelope, not raw question length."""
    size = _compact_bytes(payload)
    return {'status': 'blocked' if size > byte_limit else 'within_local_byte_budget',
            'reason': 'utf8_json_budget_exceeded' if size > byte_limit else None,
            'boundary': boundary, 'measured_bytes': size, 'limit_bytes': byte_limit}

SCHEMAS = {
    'VM_NOVA': ['id', 'tenantId', 'tenantName', 'logicalRegionName', 'name', 'ipAddress', 'privateIps', 'floatingIp'],
    'VOLUME': ['id', 'tenantId', 'tenantName', 'logicalRegionName', 'name', 'size', 'status'],
    'R_VOLUME_MOUNTON_VM': ['id', 'vmId', 'volumeId'],
}
PARAMETER_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['logicalRegionName', 'metric', 'tie_policy', 'unknown_tenant_policy'],
    'properties': {
        'logicalRegionName': {'type': 'string', 'minLength': 1},
        'metric': {'enum': ['vm_count', 'volume_count']},
        'tie_policy': {'enum': ['all_ties']},
        'unknown_tenant_policy': {'enum': ['reject', 'exclude_with_diagnostic']},
    },
}


def _validate(params):
    if not isinstance(params, dict):
        raise ValueError('params must be an object')
    required = set(PARAMETER_SCHEMA['required'])
    if set(params) != required:
        raise ValueError('missing or unsupported parameter; all policies must be explicit')
    if not isinstance(params['logicalRegionName'], str) or not params['logicalRegionName'].strip():
        raise ValueError('logicalRegionName must be a nonempty string')
    if any(unicodedata.category(ch) == 'Cc' for ch in params['logicalRegionName']):
        raise ValueError('logicalRegionName contains a control character')
    for key in ('metric', 'tie_policy', 'unknown_tenant_policy'):
        if params[key] not in PARAMETER_SCHEMA['properties'][key]['enum']:
            raise ValueError('unsupported '+key)


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def _materialize(params):
    """SQL MUST consume preflight's validated projected tables, never raw API rows.

    Only structured capability parameters; no question, source-id or entity routing.
    """
    _validate(params)
    region = params['logicalRegionName']
    sql_region = _literal(region)
    metric = params['metric']
    cis = ['VOLUME'] if metric == 'volume_count' else ['VM_NOVA', 'VOLUME', 'R_VOLUME_MOUNTON_VM']
    api = []
    for ci in cis:
        endpoint = 'relations' if ci.startswith('R_') else 'instances'
        call = {'method': 'GET', 'url': '/rest/hackthon/db/'+endpoint+'/'+ci+'?'+urlencode({'pageNo': 1, 'pageSize': 1000})}
        if endpoint == 'instances':
            call['condition'] = {'constraint': [{'simple': {'name': 'logicalRegionName', 'value': region, 'operator': 'equal'}}]}
        api.append(call)
    source = 'CLOUD_VM_NOVA' if metric == 'vm_count' else 'CLOUD_VOLUME'
    prefix = f'''WITH scoped AS (
 SELECT * FROM {source} WHERE logicalRegionName={sql_region}
), tenant_counts AS (
 SELECT tenantId, COUNT(DISTINCT id) AS resource_count
 FROM scoped WHERE tenantId IS NOT NULL GROUP BY tenantId
), winners AS (
 SELECT tenantId, resource_count FROM tenant_counts
 WHERE resource_count=(SELECT MAX(resource_count) FROM tenant_counts)
)'''
    if metric == 'volume_count':
        columns = ['tenant_id', 'tenant_name', 'resource_count', 'volume_id', 'volume_name', 'volume_size_raw', 'volume_status']
        sql = prefix + '''
SELECT w.tenantId AS tenant_id, d.tenantName AS tenant_name, w.resource_count,
 d.id AS volume_id, d.name AS volume_name, d.size AS volume_size_raw, d.status AS volume_status
FROM winners w JOIN scoped d ON d.tenantId=w.tenantId
ORDER BY w.tenantId,d.id'''
        grain = 'one row per volume id belonging to each maximal known tenant identity'
    else:
        columns = ['tenant_id', 'tenant_name', 'resource_count', 'vm_id', 'vm_name', 'ip_address', 'private_ips', 'floating_ip', 'referenced_volume_id', 'volume_id', 'volume_name', 'volume_size_raw', 'volume_status', 'mount_status']
        sql = prefix + f''', mounts AS (
 SELECT DISTINCT vmId, volumeId FROM R_VOLUME_MOUNTON_VM
), scoped_volumes AS (
 SELECT * FROM CLOUD_VOLUME WHERE logicalRegionName={sql_region}
)
SELECT w.tenantId AS tenant_id, d.tenantName AS tenant_name, w.resource_count,
 d.id AS vm_id,d.name AS vm_name,d.ipAddress AS ip_address,d.privateIps AS private_ips,d.floatingIp AS floating_ip,
 m.volumeId AS referenced_volume_id,v.id AS volume_id,v.name AS volume_name,
 v.size AS volume_size_raw,v.status AS volume_status,
 CASE WHEN m.vmId IS NULL THEN 'no_mount' WHEN v.id IS NULL THEN 'unresolved_volume' ELSE 'resolved' END AS mount_status
FROM winners w JOIN scoped d ON d.tenantId=w.tenantId
LEFT JOIN mounts m ON m.vmId=d.id
LEFT JOIN scoped_volumes v ON v.id=m.volumeId
ORDER BY w.tenantId,d.id,m.volumeId'''
        grain = 'one row per winning tenant id x vm id x distinct referenced volume id; no-mount VM retains one null-volume row'
    transport_bytes = _compact_bytes({'api_call': api, 'sql': sql})
    result = {
        'id': FAMILY_ID, 'view': metric, 'resources': cis, 'api_call': api, 'sql': sql,
        'parameter_schema': deepcopy(PARAMETER_SCHEMA), 'params': dict(params),
        'output_columns': columns, 'grain': grain,
        'required_schema': {ci: list(SCHEMAS[ci]) for ci in cis},
        'status': 'isolated_candidate_policy_conditional' if transport_bytes <= 4096 else 'blocked_transport_budget',
        'transport_bytes': transport_bytes, 'transport_byte_limit': 4096,
        'requires_preflight': True, 'requires_typed_empty_schema': True,
        'requires_validated_tables': True, 'projection_contract': PROJECTION_CONTRACT, 'revision': REVISION,
        'blocked_reason': ({'code': 'expanded_api_sql_exceeds_local_budget', 'boundary': 'expanded_api_call+sql',
                            'measured_bytes': transport_bytes, 'limit_bytes': 4096} if transport_bytes > 4096 else None),
        'needs_C': ['accept all tied maximal tenant identities', 'accept tenantId identity namespace',
                    'accept explicit treatment of resources lacking tenantId', 'accept raw capacity/native IP output semantics'],
    }
    result['byte_boundaries'] = {
        'encoding': 'UTF-8 compact JSON ensure_ascii=False',
        'expanded_wire_bytes': transport_bytes, 'wire_boundary': 'api_call+sql only',
        'expanded_wire_limit_bytes': 4096,
        'static_api_sql_template_bytes': None, 'static_template_measurement': 'compact api_call+sql using {{logicalRegionName}}, not a published static item or expanded wire',
        'full_plan_bytes': 0, 'full_plan_limit_bytes': None,
        'full_plan_role': 'local metadata, not an approved B wire envelope; measure actual final B envelope separately',
        'formal_depth4_gate': 'pending official algorithm and actual transport validation',
    }
    for _ in range(4):
        result['byte_boundaries']['full_plan_bytes'] = _compact_bytes(result)
    return result


def build(params):
    """Materialize the structured family and measure static/expanded boundaries separately."""
    result = _materialize(params)
    static_params = dict(params)
    static_params['logicalRegionName'] = '{{logicalRegionName}}'
    result['byte_boundaries']['static_api_sql_template_bytes'] = _materialize(static_params)['transport_bytes']
    for _ in range(4):
        result['byte_boundaries']['full_plan_bytes'] = _compact_bytes(result)
    return result


def preflight(params, pages):
    """Validate complete raw pages before typed SQL loading; no service calls.

    Input {CI: [page envelope]}; each envelope has currentPage,pageSize,totalPageNo,totalNum,objList.
    Only whitespace/empty tenant IDs are normalized to NULL on NEW schema-projected
    row copies. Nonblank IDs remain exact. Input pages/rows are never mutated.
    Unknown count and SQL exclusion both derive from these same validated tables.

    """
    plan = build(params)
    if plan['status'] == 'blocked_transport_budget':
        return {'status': 'blocked', 'reason': 'transport_budget', 'transport_bytes': plan['transport_bytes'],
                'blocked_reason': plan['blocked_reason'], 'byte_boundaries': plan['byte_boundaries']}
    if not isinstance(pages, dict) or set(pages) != set(plan['resources']):
        return {'status': 'blocked', 'reason': 'missing_or_extra_resource_payload'}
    tables, errors = {}, []
    unknown_by_ci, normalized_by_ci = {}, {}
    for ci in plan['resources']:
        packets = pages[ci]
        if not isinstance(packets, list) or not packets:
            errors.append(ci+':missing_pages'); continue
        rows, metadata, seen_ids = [], None, set()
        for n, packet in enumerate(packets, 1):
            if not isinstance(packet, dict) or packet.get('error') or packet.get('success') is False:
                errors.append(ci+':request_failed'); continue
            if packet.get('ok') is not True:
                errors.append(ci+':unconfirmed_request_success'); continue
            keys = ['currentPage', 'pageSize', 'totalPageNo', 'totalNum', 'objList']
            if not all(k in packet for k in keys) or not isinstance(packet['objList'], list):
                errors.append(ci+':invalid_page_envelope'); continue
            nums = [packet[x] for x in keys[:-1]]
            if any(type(v) is not int for v in nums) or packet['pageSize'] <= 0 or packet['totalNum'] < 0 or packet['totalPageNo'] < 0:
                errors.append(ci+':invalid_page_metadata'); continue
            total_pages = max(1, packet['totalPageNo'])
            expected_pages = max(1, (packet['totalNum']+packet['pageSize']-1)//packet['pageSize'])
            if total_pages != expected_pages or packet['currentPage'] != n:
                errors.append(ci+':missing_or_out_of_order_page')
            current = (packet['pageSize'], packet['totalPageNo'], packet['totalNum'])
            if metadata is None: metadata = current
            elif metadata != current: errors.append(ci+':unstable_pagination')
            expected_size = min(packet['pageSize'], max(0, packet['totalNum']-(n-1)*packet['pageSize']))
            if len(packet['objList']) != expected_size:
                errors.append(ci+':truncated_or_oversized_page')
            for row in packet['objList']:
                if not isinstance(row, dict) or any(k not in row for k in SCHEMAS[ci]):
                    errors.append(ci+':missing_schema'); continue
                if not isinstance(row['id'], str) or not row['id'].strip() or row['id'] in seen_ids:
                    errors.append(ci+':invalid_or_duplicate_identity'); continue
                seen_ids.add(row['id'])
                if any(row[k] is not None and not isinstance(row[k], str) for k in SCHEMAS[ci]):
                    errors.append(ci+':non_text_source_field')
                if ci.startswith('R_'):
                    if any(not isinstance(row[k], str) or not row[k].strip() for k in ('vmId','volumeId')):
                        errors.append(ci+':missing_relation_endpoint')
                else:
                    if row['logicalRegionName'] != params['logicalRegionName']:
                        errors.append(ci+':scope_leak')
                    if row['tenantId'] is not None and not isinstance(row['tenantId'], str):
                        errors.append(ci+':invalid_tenant_identity')
                # Only copy validated schema fields; raw input is not a SQL loading contract.
                projected = {k: deepcopy(row[k]) for k in SCHEMAS[ci]}
                if not ci.startswith('R_') and is_unknown_tenant_identity(projected['tenantId']):
                    unknown_by_ci[ci] = unknown_by_ci.get(ci, 0) + 1
                    if projected['tenantId'] is not None:
                        normalized_by_ci[ci] = normalized_by_ci.get(ci, 0) + 1
                    projected['tenantId'] = None
                rows.append(projected)
        if metadata and len(packets) != max(1, metadata[1]): errors.append(ci+':incomplete_page_set')
        tables[ci] = rows
    if errors:
        return {'status': 'blocked', 'reason': 'invalid_or_incomplete_input', 'errors': sorted(set(errors))}
    ranked_ci = 'VM_NOVA' if params['metric'] == 'vm_count' else 'VOLUME'
    unknown_ids = [r['id'] for r in tables[ranked_ci] if r['tenantId'] is None]
    if unknown_ids and params['unknown_tenant_policy'] == 'reject':
        return {'status': 'blocked', 'reason': 'unknown_tenant_identity', 'unknown_resource_count': len(unknown_ids),
                'projection_contract': PROJECTION_CONTRACT, 'unknown_identity_count_by_ci': unknown_by_ci}
    unresolved = 0
    if params['metric'] == 'vm_count':
        vmids = {r['id'] for r in tables['VM_NOVA']}
        vids = {r['id'] for r in tables['VOLUME']}
        unresolved = len({(r['vmId'],r['volumeId']) for r in tables['R_VOLUME_MOUNTON_VM'] if r['vmId'] in vmids and r['volumeId'] not in vids})
    return {'status': 'ready_for_typed_sql', 'tables': tables, 'required_schema': plan['required_schema'],
            'projection_contract': PROJECTION_CONTRACT, 'requires_validated_tables': True,
            'projection_sha256': _fingerprint(tables), 'params_sha256': _fingerprint(params),
            'unknown_identity_count_by_ci': unknown_by_ci, 'normalized_blank_identity_count_by_ci': normalized_by_ci,
            'unknown_resource_count': len(unknown_ids), 'ranking_population': 'known_tenant_ids_only' if unknown_ids else 'complete_ranked_resource_population',
            'unresolved_mount_count': unresolved, 'complete_mount_details': unresolved == 0,
            'business_policy_accepted': False,
            'warning': 'SQL must load ONLY these validated projected table copies; raw input is unsupported. An official _empty placeholder or API failure must never be loaded as successful data. Typed empty tables are required.'}


def execute_prepared(params, prepared):
    """Pure local SQLite execution, enforcing the validated-projection loading path.

    This does not adopt or alter B/official execution. B may implement an equivalent
    checked typed loader, but loading raw rows instead is explicitly unsupported.
    """
    plan = build(params)
    if plan['status'] == 'blocked_transport_budget':
        return {'status': 'blocked', 'reason': 'transport_budget', 'blocked_reason': plan['blocked_reason']}
    if (not isinstance(prepared, dict) or prepared.get('status') != 'ready_for_typed_sql'
            or prepared.get('projection_contract') != PROJECTION_CONTRACT
            or prepared.get('requires_validated_tables') is not True
            or prepared.get('params_sha256') != _fingerprint(params)):
        return {'status': 'blocked', 'reason': 'requires_validated_projection'}
    tables = prepared.get('tables')
    if not isinstance(tables, dict) or set(tables) != set(plan['resources']):
        return {'status': 'blocked', 'reason': 'invalid_projection_tables'}
    if prepared.get('projection_sha256') != _fingerprint(tables):
        return {'status': 'blocked', 'reason': 'validated_projection_changed'}
    for ci, rows in tables.items():
        if not isinstance(rows, list):
            return {'status': 'blocked', 'reason': 'invalid_projection_rows'}
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(SCHEMAS[ci]):
                return {'status': 'blocked', 'reason': 'invalid_projection_schema'}
            if not ci.startswith('R_') and row['tenantId'] is not None and is_unknown_tenant_identity(row['tenantId']):
                return {'status': 'blocked', 'reason': 'raw_identity_not_canonical'}
    ranked_ci = 'VM_NOVA' if params['metric'] == 'vm_count' else 'VOLUME'
    unknown = sum(r['tenantId'] is None for r in tables[ranked_ci])
    if unknown != prepared.get('unknown_resource_count'):
        return {'status': 'blocked', 'reason': 'projection_diagnostics_mismatch'}
    if unknown and params['unknown_tenant_policy'] == 'reject':
        return {'status': 'blocked', 'reason': 'unknown_tenant_identity', 'unknown_resource_count': unknown}
    conn = sqlite3.connect(':memory:')
    try:
        for ci, rows in tables.items():
            table = ci if ci.startswith('R_') else 'CLOUD_'+ci
            columns = SCHEMAS[ci]
            conn.execute('CREATE TABLE '+table+' ('+','.join('"'+k+'" TEXT' for k in columns)+')')
            conn.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')',
                             [[r[k] for k in columns] for r in rows])
        cursor = conn.execute(plan['sql'])
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except sqlite3.DatabaseError as exc:
        return {'status': 'blocked', 'reason': 'local_sql_error', 'detail': str(exc)}
    finally:
        conn.close()
    keys = ['unknown_resource_count','ranking_population','unresolved_mount_count',
            'complete_mount_details','business_policy_accepted','projection_contract',
            'projection_sha256','unknown_identity_count_by_ci','normalized_blank_identity_count_by_ci']
    return {'status': 'local_sql_ok_policy_conditional', 'columns': columns, 'rows': rows,
            'diagnostics': {k: deepcopy(prepared[k]) for k in keys}, 'byte_boundaries': plan['byte_boundaries']}


def execute(params, pages):
    """Validate raw receipts then execute ONLY preflight's fresh projected tables."""
    prepared = preflight(params, pages)
    if prepared.get('status') != 'ready_for_typed_sql':
        return prepared
    return execute_prepared(params, prepared)
