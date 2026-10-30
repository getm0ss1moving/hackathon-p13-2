"""Named VPC independent counts; pure plans, receipt checks and synthetic SQLite.

No IO, native snapshot pinning, question/entity routing or official executor edits.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sqlite3

PROFILE = 'named_vpc_subnet_eip_counts'
PROTOCOL = 'named-vpc-counts-v1-source-rechecked'
SCHEMA = {
    'ROUTER': ('id', 'name', 'nativeId', 'logicalRegionName'),
    'PORT': ('id', 'devNativeId', 'logicalRegionName'),
    'R_PORT_IN_SUBNET': ('id', 'portId', 'subnetId'),
    'SUBNET': ('id', 'logicalRegionName'),
    'FLOATING_IPS': ('id', 'routerId', 'logicalRegionName'),
}
RESOURCES = tuple(SCHEMA)
TABLES = {r: r if r.startswith('R_') else 'CLOUD_' + r for r in RESOURCES}
OUTPUT_COLUMNS = ('vpc_id', 'vpc_name', 'logical_region_name',
                  'resolved_subnet_count', 'referenced_subnet_count',
                  'unresolved_subnet_count', 'known_eip_count')


class Unsupported(ValueError):
    pass


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def encoded(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Unsupported('input is not finite UTF-8 JSON') from exc


def params_checked(params):
    if not isinstance(params, dict) or set(params) != {
            'profile', 'filters', 'required_filters', 'same_name_policy'}:
        raise Unsupported('closed profile, filters, required_filters and same_name_policy required')
    filters = params['filters']
    if params['profile'] != PROFILE or not isinstance(filters, dict) or set(filters) not in (
            {'name'}, {'name', 'logicalRegionName'}):
        raise Unsupported('exact name and optional explicit logicalRegionName only')
    required = params['required_filters']
    if (not isinstance(required, list) or any(not isinstance(k, str) for k in required)
            or len(required) != len(set(required)) or set(required) != set(filters)):
        raise Unsupported('required_filters must preserve every supplied filter exactly once')
    if params['same_name_policy'] not in ('all_matching_parent_ids', 'reject_multiple_parent_ids'):
        raise Unsupported('explicit same-name identity policy required')
    if any(not isinstance(v, str) or blank(v) or any(ord(c) < 32 for c in v)
           for v in filters.values()):
        raise Unsupported('filters require exact nonblank text without ASCII controls')
    encoded(params)
    return deepcopy(params)


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def build(params):
    p = params_checked(params)
    filters = p['filters']
    clauses = ['name=' + literal(filters['name'])]
    if 'logicalRegionName' in filters:
        clauses.append('logicalRegionName=' + literal(filters['logicalRegionName']))
    sql = '''WITH p AS (SELECT * FROM CLOUD_ROUTER WHERE %s),
refs AS (SELECT DISTINCT p.id AS vpc_id,r.subnetId AS subnet_id
 FROM p JOIN CLOUD_PORT t ON t.devNativeId=p.nativeId AND t.logicalRegionName=p.logicalRegionName
 JOIN R_PORT_IN_SUBNET r ON r.portId=t.id WHERE r.subnetId IS NOT NULL),
sc AS (SELECT r.vpc_id,COUNT(*) AS referenced,
 SUM(CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END) AS resolved
 FROM refs r JOIN p ON p.id=r.vpc_id
 LEFT JOIN CLOUD_SUBNET s ON s.id=r.subnet_id AND s.logicalRegionName=p.logicalRegionName GROUP BY r.vpc_id),
ec AS (SELECT p.id AS vpc_id,COUNT(DISTINCT e.id) AS known_eip
 FROM p JOIN CLOUD_FLOATING_IPS e ON e.routerId=p.id AND e.logicalRegionName=p.logicalRegionName GROUP BY p.id)
SELECT p.id AS vpc_id,p.name AS vpc_name,p.logicalRegionName AS logical_region_name,
 COALESCE(sc.resolved,0) AS resolved_subnet_count,COALESCE(sc.referenced,0) AS referenced_subnet_count,
 COALESCE(sc.referenced,0)-COALESCE(sc.resolved,0) AS unresolved_subnet_count,
 COALESCE(ec.known_eip,0) AS known_eip_count
FROM p LEFT JOIN sc ON sc.vpc_id=p.id LEFT JOIN ec ON ec.vpc_id=p.id ORDER BY p.id''' % ' AND '.join(clauses)
    calls = []
    for resource in RESOURCES:
        kind = 'relations' if resource.startswith('R_') else 'instances'
        call = {'method': 'GET', 'url': '/rest/hackthon/db/%s/%s?pageNo=1&pageSize=1000' % (kind, resource),
                'autoPagination': True}
        if 'logicalRegionName' in filters and resource != 'R_PORT_IN_SUBNET':
            call['condition'] = {'constraint': [{'simple': {'name': 'logicalRegionName',
                                 'value': filters['logicalRegionName'], 'operator': 'equal'}}]}
        calls.append(call)
    core_bytes = len(encoded({'api_call': calls, 'sql': sql}))
    return {'family_id': PROFILE, 'api_call': calls, 'sql': sql,
            'resources': list(RESOURCES), 'output_columns': list(OUTPUT_COLUMNS),
            'input_schema': {TABLES[r]: list(SCHEMA[r]) for r in RESOURCES},
            'requires_prepared_inputs': True,
            'transport_diagnostic': {'boundary': 'compact sorted ensure_ascii=False UTF-8 api_call+sql',
                                    'measured_bytes': core_bytes, 'candidate_limit_bytes': 4096,
                                    'status': 'blocked_core_length' if core_bytes > 4096 else 'within_candidate_core_bound',
                                    'final_B_envelope_validated': False,
                                    'handling': 'Never truncate identifiers, scope or SQL. B must validate a supported encoding and its final transport envelope.'}}


def state_checked(value):
    if value.get('ok') is not True or ('success' in value and value['success'] is not True):
        raise Unsupported('failed, absent or contradictory success state')
    if 'error' in value:
        error = value['error']
        if not (error is None or error is False or (isinstance(error, str) and error == '')):
            raise Unsupported('declared error cannot be converted to success-empty')
    for key in ('http_status', 'httpStatus', 'status_code'):
        if key in value and (type(value[key]) is not int or not 200 <= value[key] < 300):
            raise Unsupported('declared HTTP state must be integer 2xx')


def collect(resource, envelope, expected):
    if not isinstance(envelope, dict):
        raise Unsupported('missing resource envelope')
    state_checked(envelope)
    if (not isinstance(envelope.get('request'), dict)
            or envelope['request'].get('autoPagination') is not True
            or envelope['request'] != expected):
        raise Unsupported('receipt is not bound to the exact complete catalog request')
    columns = envelope.get('schema')
    if (envelope.get('schema_verified') is not True or not isinstance(columns, list)
            or any(not isinstance(c, str) for c in columns)
            or not set(SCHEMA[resource]).issubset(columns)):
        raise Unsupported('verified typed schema required, including success-empty')
    pages = envelope.get('pages')
    if not isinstance(pages, list) or not pages:
        raise Unsupported('even zero rows require a successful zero-total page')
    rows, seen, total, size = [], set(), None, None
    for n, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            raise Unsupported('invalid page envelope')
        state_checked(page)
        t, z, np = page.get('totalNum'), page.get('pageSize'), page.get('totalPageNo')
        if (type(page.get('pageNo')) is not int or page['pageNo'] != n
                or type(t) is not int or t < 0 or type(z) is not int or z < 1 or type(np) is not int):
            raise Unsupported('invalid or out-of-order page metadata')
        if total is None:
            total, size = t, z
        if ((total, size) != (t, z) or (t > 0 and np != (t + z - 1) // z)
                or (t == 0 and np not in (0, 1))):
            raise Unsupported('unstable or inconsistent page totals')
        batch = page.get('objList')
        if not isinstance(batch, list) or len(batch) != min(z, max(t - len(rows), 0)):
            raise Unsupported('missing, extra or truncated page rows')
        for raw in batch:
            optional = {'routerId'} if resource == 'FLOATING_IPS' else set()
            if not isinstance(raw, dict) or any(k not in raw for k in SCHEMA[resource] if k not in optional):
                raise Unsupported('required identity, scope or join field is absent')
            row = {k: raw.get(k) for k in SCHEMA[resource]}
            encoded(row)
            identity = row['id']
            if not isinstance(identity, str) or blank(identity) or identity in seen:
                raise Unsupported('nonblank string object IDs must be unique across all CI pages')
            seen.add(identity)
            for key, value in row.items():
                if key == 'id':
                    continue
                if value is not None and not isinstance(value, str):
                    raise Unsupported('declared text columns require strings or NULL')
                if key in ('nativeId', 'devNativeId', 'portId', 'subnetId', 'routerId') and blank(value):
                    row[key] = None
            if 'logicalRegionName' in row:
                region = row['logicalRegionName']
                if blank(region):
                    raise Unsupported('region identity is unknown')
                if 'condition' in expected and region != expected['condition']['constraint'][0]['simple']['value']:
                    raise Unsupported('wrong-region response cannot establish complete scope')
            rows.append(row)
    if len(rows) != total or len(pages) != max(1, (total + size - 1) // size):
        raise Unsupported('incomplete page collection')
    return rows


def _prepare(params, receipts):
    p, plan = params_checked(params), build(params)
    if not isinstance(receipts, dict) or set(receipts) != set(RESOURCES):
        raise Unsupported('all five complete bound catalog receipts required')
    tables = {r: collect(r, receipts[r], call) for r, call in zip(RESOURCES, plan['api_call'])}
    routers = {r['id']: r for r in tables['ROUTER']}
    keys = {}
    for row in routers.values():
        if row['nativeId'] is not None:
            key = row['logicalRegionName'], row['nativeId']
            if key in keys:
                raise Unsupported('region/nativeId does not uniquely identify a VPC')
            keys[key] = row['id']
    f = p['filters']
    selected = [r for r in routers.values() if r['name'] == f['name']
                and ('logicalRegionName' not in f or r['logicalRegionName'] == f['logicalRegionName'])]
    if p['same_name_policy'] == 'reject_multiple_parent_ids' and len(selected) > 1:
        raise Unsupported('multiple exact-name parent IDs require explicit all-matching policy')
    selected_ids = {r['id'] for r in selected}
    ports = {r['id']: r for r in tables['PORT']}
    subnets = {r['id']: r for r in tables['SUBNET']}
    scoped_ports = {r['id'] for r in ports.values()
                    if keys.get((r['logicalRegionName'], r['devNativeId'])) in selected_ids}
    diagnostics = {
        'selected_parent_count': len(selected),
        'unknown_parent_name_count': sum(blank(r['name']) for r in routers.values()),
        'unknown_parent_native_id_count': sum(r['nativeId'] is None for r in routers.values()),
        'unknown_port_owner_count': sum(r['devNativeId'] is None for r in ports.values()),
        'orphan_relation_port_count': 0, 'selected_unknown_subnet_reference_count': 0,
        'unknown_eip_parent_count': 0, 'unresolved_eip_parent_count': 0,
        'trust_boundary': 'B assertions about current request, schema and complete pages; no authentication, atomic snapshot or official business certification',
        'full_business_acceptance': 'not_verified',
    }
    for rel in tables['R_PORT_IN_SUBNET']:
        port, subnet = ports.get(rel['portId']), subnets.get(rel['subnetId'])
        if port is None:
            diagnostics['orphan_relation_port_count'] += 1
        if port and subnet and port['logicalRegionName'] != subnet['logicalRegionName']:
            raise Unsupported('cross-region port/subnet edge')
        if rel['portId'] in scoped_ports and rel['subnetId'] is None:
            diagnostics['selected_unknown_subnet_reference_count'] += 1
    for eip in tables['FLOATING_IPS']:
        parent = routers.get(eip['routerId'])
        if eip['routerId'] is None:
            diagnostics['unknown_eip_parent_count'] += 1
        elif parent is None:
            diagnostics['unresolved_eip_parent_count'] += 1
        elif parent['logicalRegionName'] != eip['logicalRegionName']:
            raise Unsupported('cross-region EIP/VPC edge')
    return p, {TABLES[r]: tables[r] for r in RESOURCES}, diagnostics


def prepare(params, receipts):
    p, tables, diagnostics = _prepare(params, receipts)
    evidence = {'params': p, 'receipts': deepcopy(receipts)}
    return {'protocol': PROTOCOL, 'tables': tables, 'diagnostics': diagnostics,
            'input_evidence': evidence, 'evidence_sha256': hashlib.sha256(encoded(evidence)).hexdigest()}


def execute_prepared(prepared):
    if not isinstance(prepared, dict) or prepared.get('protocol') != PROTOCOL:
        raise Unsupported('current source-rechecked preparation protocol required')
    evidence = prepared.get('input_evidence')
    if not isinstance(evidence, dict) or set(evidence) != {'params', 'receipts'}:
        raise Unsupported('actual current receipt evidence required; a marker is insufficient')
    if prepared.get('evidence_sha256') != hashlib.sha256(encoded(evidence)).hexdigest():
        raise Unsupported('input evidence changed')
    p, tables, diagnostics = _prepare(evidence['params'], evidence['receipts'])
    if prepared.get('tables') != tables or prepared.get('diagnostics') != diagnostics:
        raise Unsupported('prepared projection or diagnostics changed')
    plan = build(p)
    conn = sqlite3.connect(':memory:')
    try:
        for resource in RESOURCES:
            table, columns = TABLES[resource], SCHEMA[resource]
            conn.execute('CREATE TABLE ' + table + ' (' + ','.join('"' + c + '" TEXT' for c in columns) + ')')
            conn.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in columns) + ')',
                             [[r[c] for c in columns] for r in tables[table]])
        cur = conn.execute(plan['sql'])
        if tuple(c[0] for c in cur.description) != OUTPUT_COLUMNS:
            raise AssertionError('output contract drift')
        rows = [dict(zip(OUTPUT_COLUMNS, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    diagnostics['selected_unresolved_subnet_count'] = sum(r['unresolved_subnet_count'] for r in rows)
    uncertain = ('unknown_parent_name_count', 'unknown_parent_native_id_count', 'unknown_port_owner_count',
                 'orphan_relation_port_count', 'selected_unknown_subnet_reference_count',
                 'unknown_eip_parent_count', 'unresolved_eip_parent_count', 'selected_unresolved_subnet_count')
    diagnostics['known_local_graph_complete'] = not any(diagnostics[k] for k in uncertain)
    diagnostics['result_status'] = ('complete_known_local_graph' if diagnostics['known_local_graph_complete']
                                    else 'partial_known_counts_cannot_answer_as_complete')
    diagnostics['transport_status'] = plan['transport_diagnostic']['status']
    diagnostics['final_B_envelope_validated'] = False
    diagnostics['empty_selection_meaning'] = 'zero selected VPC identities; no fabricated parent row or COUNT=1'
    return {'columns': list(OUTPUT_COLUMNS), 'rows': rows, 'diagnostics': diagnostics}


def execute_local(params, receipts):
    """Pure synthetic verifier, never a replacement official executor."""
    return execute_prepared(prepare(params, receipts))
