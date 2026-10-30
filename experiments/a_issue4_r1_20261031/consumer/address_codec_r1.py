"""Pure address membership contract. No network, model, official executor or PORT policy.

B supplies authenticated current receipts; structural checks here cannot establish
server authenticity, isolation, source authority or complete EIP ownership.
"""
from copy import deepcopy
import hashlib
import json
import sqlite3

PROFILE = 'fixed_address_member_vm_rows'
PROTOCOL = 'opaque-address-membership-r1.1'
CODEC = 'at_or_scalar_v1'
CODECS = (CODEC,)
LIMIT = 4096
SCHEMA = {
    'FLOATING_IPS': ('id', 'logicalRegionName', 'status', 'fixedIpAddress', 'floatingIpAddress'),
    'VM_NOVA': ('id', 'logicalRegionName', 'name', 'privateIps'),
}
OUTPUT = ('eip_id', 'eip_region', 'floating_ip', 'fixed_ip', 'vm_id', 'vm_name',
          'private_ips_raw', 'known_matching_vm_count', 'membership_status', 'relationship_evidence')
TABLE_SCHEMA = {
    'CLOUD_FLOATING_IPS': SCHEMA['FLOATING_IPS'],
    'CLOUD_VM_NOVA': SCHEMA['VM_NOVA'],
    'A_VM_ADDRESS_MEMBERS': ('vm_id', 'logical_region_name', 'address_token'),
    'A_EIP_MEMBER_STATE': ('eip_id', 'eip_region', 'known_matching_vm_count', 'membership_status'),
}
SQL = """SELECT e.id AS eip_id,e.logicalRegionName AS eip_region,
e.floatingIpAddress AS floating_ip,e.fixedIpAddress AS fixed_ip,
v.id AS vm_id,v.name AS vm_name,v.privateIps AS private_ips_raw,
s.known_matching_vm_count,s.membership_status,
'address_membership_candidate_only' AS relationship_evidence
FROM CLOUD_FLOATING_IPS e
JOIN A_EIP_MEMBER_STATE s ON s.eip_id=e.id AND s.eip_region=e.logicalRegionName
LEFT JOIN A_VM_ADDRESS_MEMBERS a ON a.address_token=e.fixedIpAddress AND a.logical_region_name=e.logicalRegionName
LEFT JOIN CLOUD_VM_NOVA v ON v.id=a.vm_id AND v.logicalRegionName=a.logical_region_name
ORDER BY e.logicalRegionName,e.id,v.id"""


class Blocked(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def encoded(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError) as exc:
        raise Blocked('invalid_json', 'finite UTF-8 JSON required') from exc


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def opaque(value):
    if not isinstance(value, str) or blank(value) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise Blocked('invalid_text', 'nonblank control-free exact UTF-8 text required')
    encoded(value)
    return value


def checked(params):
    if (not isinstance(params, dict)
            or set(params) != {'profile', 'filters', 'required_filters', 'address_codec', 'unknown_policy'}
            or params['profile'] != PROFILE
            or params['unknown_policy'] not in ('reject', 'known_only_with_diagnostic')):
        raise Blocked('invalid_params', 'closed explicit membership profile and unknown policy required')
    if params['address_codec'] != CODEC:
        raise Blocked('unsupported_codec', 'only the source-evidenced at_or_scalar_v1 codec is supported')
    filters, required = params['filters'], params['required_filters']
    if (not isinstance(filters, dict) or not filters
            or set(filters) - {'logicalRegionName', 'status', 'fixedIpAddress'}):
        raise Blocked('invalid_params', 'nonempty exact EIP filters required; no default region/status')
    if (not isinstance(required, list) or any(not isinstance(k, str) for k in required)
            or len(required) != len(set(required)) or set(required) != set(filters)):
        raise Blocked('scope_drift', 'all supplied original filters must remain required')
    for value in filters.values():
        opaque(value)
    encoded(params)
    return deepcopy(params)


def predicate(field, value, operator='equal'):
    return {'simple': {'name': field, 'value': opaque(value), 'operator': operator}}


def request(ci, conditions):
    result = {'method': 'GET',
              'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=1000',
              'autoPagination': True, 'condition': {'constraint': deepcopy(conditions)}}
    for item in result['condition']['constraint'][1:]:
        item['logOp'] = 'and'
    size = len(encoded(result))
    if size > LIMIT:
        raise Blocked('request_too_large', 'literal request exceeds provisional compact UTF-8 limit; no truncation',
                      {'measured_bytes': size, 'limit_bytes': LIMIT})
    return result


def scalar_token(value):
    """No IP/number normalization or value whitelist. Reserve unproven delimiters."""
    opaque(value)
    if '@' in value or ',' in value or ';' in value or value.lstrip().startswith(('[', '{')):
        raise Blocked('unsupported_encoding', 'reserved or unproven address encoding')
    return value


def decode(raw, codec=CODEC, present=True):
    if codec != CODEC:
        raise Blocked('unsupported_codec', 'no automatic CSV, JSON or alternate codec support')
    result = {'status': None, 'tokens': [], 'duplicate_token_count': 0}
    if not present:
        result['status'] = 'unknown_missing'
    elif raw is None:
        result['status'] = 'unknown_null'
    elif raw == '':
        result['status'] = 'unknown_empty'
    elif isinstance(raw, str) and not raw.strip():
        result['status'] = 'unknown_whitespace'
    elif not isinstance(raw, str):
        result['status'] = 'unsupported_native_type'
    else:
        try:
            opaque(raw)
            if '@' in raw:
                if not (raw.startswith('@') and raw.endswith('@') and len(raw) > 2):
                    raise Blocked('unsupported_encoding', 'malformed at wrapper')
                values = raw[1:-1].split('@')
            else:
                values = [raw]
            for value in values:
                scalar_token(value)
            result.update(status='decoded', tokens=list(dict.fromkeys(values)),
                          duplicate_token_count=len(values) - len(set(values)))
        except Blocked:
            result['status'] = 'unsupported_or_malformed_codec'
    return result


def build(params):
    p = checked(params)
    return {
        'family_id': PROFILE, 'params': p,
        'eip_request': request('FLOATING_IPS', [predicate(k, v) for k, v in sorted(p['filters'].items())]),
        'sql': SQL, 'required_schema': deepcopy(SCHEMA),
        'typed_table_schema': deepcopy(TABLE_SCHEMA), 'output_columns': list(OUTPUT),
        'followup': 'plan_followups after verified complete EIP receipt; one literal contain request per distinct region/token plus same-region complete VM context',
        'operator_contract': 'native contain is a LIKE candidate superset, never exact membership; preserve actual operator and apply complete decoded token equality locally',
        'runtime_status': 'not_integrated_not_natively_verified',
        'official_executor_payload': False, 'full_eip_binding_complete': False,
    }


def _validate_rows(ci, rows, filters=None):
    if not isinstance(rows, list):
        raise Blocked('schema_failure', 'row list required')
    output, seen = [], set()
    for raw in rows:
        required = {'id', 'logicalRegionName'} | set(filters or {})
        if not isinstance(raw, dict) or not required <= set(raw):
            raise Blocked('schema_failure', ci + ': missing identity or required scope field')
        row = {k: deepcopy(raw[k]) for k in SCHEMA[ci] if k in raw}
        identity = opaque(row['id'])
        opaque(row['logicalRegionName'])
        if identity in seen:
            raise Blocked('duplicate_identity', ci + ': repeated object ID, even with identical projection')
        seen.add(identity)
        for value in row.values():
            if value is not None and not isinstance(value, str):
                raise Blocked('schema_failure', ci + ': declared native fields require text or NULL')
            if isinstance(value, str):
                encoded(value)
        for field, value in (filters or {}).items():
            if row[field] != value:
                raise Blocked('scope_drift', ci + ': actual row outside exact scope')
        output.append(row)
    return output


def _fixed_state(row):
    state = decode(row.get('fixedIpAddress'), present='fixedIpAddress' in row)
    if state['status'] == 'decoded' and '@' in row['fixedIpAddress']:
        state.update(status='unsupported_fixed_scalar_encoding', tokens=[], duplicate_token_count=0)
    return state


def _lookup_tokens(eips):
    out = {}
    for eip in eips:
        d = _fixed_state(eip)
        # fixedIpAddress is a scalar, never a wrapped or multi-token value.
        if d['status'] != 'decoded' or len(d['tokens']) != 1:
            continue
        out.setdefault((eip['logicalRegionName'], eip['fixedIpAddress']), []).append(eip['id'])
    return out


def plan_followups(params, eip_rows):
    p = checked(params)
    eips = _validate_rows('FLOATING_IPS', eip_rows, p['filters'])
    contexts = [{'role': 'vm_region_context', 'region': region,
                 'request': request('VM_NOVA', [predicate('logicalRegionName', region)])}
                for region in sorted({e['logicalRegionName'] for e in eips})]
    keys, lookups = _lookup_tokens(eips), []
    for (region, token), ids in sorted(keys.items()):
        lookups.append({'role': 'vm_contain_candidates',
                        'lookup_id': hashlib.sha256(encoded([region, token])).hexdigest(),
                        'region': region, 'fixed_token': token, 'needle': token, 'eip_ids': sorted(ids),
                        'request': request('VM_NOVA', [predicate('logicalRegionName', region),
                                                     predicate('privateIps', token, 'contain')])})
    return {'context_requests': contexts, 'candidate_requests': lookups,
            'unknown_fixed_eip_ids': sorted(e['id'] for e in eips
                                           if (e['logicalRegionName'], e.get('fixedIpAddress')) not in keys),
            'no_placeholders': True, 'no_in_for_encoded_privateIps': True, 'actually_executed': False}


def _success(item):
    if not isinstance(item, dict) or item.get('ok') is not True or item.get('success', True) is not True:
        raise Blocked('receipt_failure', 'failed or unknown success state')
    if item.get('error') not in (None, False, ''):
        raise Blocked('receipt_failure', 'declared error')
    if type(item.get('http_status')) is not int or not 200 <= item['http_status'] < 300:
        raise Blocked('receipt_failure', 'actual HTTP 2xx state required')
    for key in ('httpStatus', 'status_code', 'statusCode', 'http_status_code', 'httpStatusCode'):
        if key in item and (type(item[key]) is not int or not 200 <= item[key] < 300):
            raise Blocked('receipt_failure', 'contradictory HTTP state')


def _capture(evidence):
    if not isinstance(evidence, dict) or set(evidence) != {'capture', 'eip', 'vm_context', 'vm_candidates'}:
        raise Blocked('evidence_failure', 'exact staged receipt roles and capture descriptor required')
    capture = evidence['capture']
    if (not isinstance(capture, dict)
            or set(capture) != {'capture_id', 'source_ref', 'schema_ref', 'isolation', 'origin'}
            or capture['isolation'] not in ('immutable_snapshot', 'best_effort_non_atomic')
            or capture['origin'] not in ('synthetic', 'B_verified_native')):
        raise Blocked('capture_failure', 'closed B capture descriptor required')
    for key in ('capture_id', 'source_ref', 'schema_ref'):
        opaque(capture[key])
    return capture


def collect(ci, envelope, expected, role, capture):
    _success(envelope)
    if envelope.get('role') != role or envelope.get('capture_id') != capture['capture_id']:
        raise Blocked('capture_failure', 'role or current capture identity changed')
    opaque(envelope.get('receipt_id'))
    if not isinstance(envelope.get('request'), dict) or encoded(envelope['request']) != encoded(expected):
        raise Blocked('request_drift', 'actual request/operator/scope differs from literal plan')
    columns = envelope.get('schema')
    if (envelope.get('schema_verified') is not True or not isinstance(columns, list)
            or any(not isinstance(c, str) for c in columns) or len(columns) != len(set(columns))
            or not set(SCHEMA[ci]) <= set(columns)):
        raise Blocked('schema_failure', 'verified declared schema required even on zero rows')
    pages = envelope.get('pages')
    if not isinstance(pages, list) or not pages:
        raise Blocked('pagination_failure', 'actual complete pages required')
    rows, total = [], None
    for n, page in enumerate(pages, 1):
        _success(page)
        t, z, count = page.get('totalNum'), page.get('pageSize'), page.get('totalPageNo')
        if (type(page.get('pageNo')) is not int or page['pageNo'] != n or type(t) is not int or t < 0
                or type(z) is not int or z != 1000 or type(count) is not int):
            raise Blocked('pagination_failure', 'invalid actual pagination metadata')
        if total is None:
            total = t
        if total != t or (t and count != (t + 999) // 1000) or (not t and count not in (0, 1)):
            raise Blocked('pagination_failure', 'unstable or contradictory totals')
        batch = page.get('objList')
        if not isinstance(batch, list) or len(batch) != min(1000, max(t - len(rows), 0)):
            raise Blocked('pagination_failure', 'truncated or extra page')
        rows.extend(batch)
    if len(rows) != total or len(pages) != max(1, (total + 999) // 1000):
        raise Blocked('pagination_failure', 'missing or extra pages')
    equals = {c['simple']['name']: c['simple']['value']
              for c in expected['condition']['constraint'] if c['simple']['operator'] == 'equal'}
    return _validate_rows(ci, rows, equals)


def _prepare(params, evidence):
    p, capture = checked(params), _capture(evidence)
    eips = collect('FLOATING_IPS', evidence['eip'], build(p)['eip_request'], 'selected_eips', capture)
    plan = plan_followups(p, eips)
    if (not isinstance(evidence['vm_context'], list)
            or len(evidence['vm_context']) != len(plan['context_requests'])
            or not isinstance(evidence['vm_candidates'], list)
            or len(evidence['vm_candidates']) != len(plan['candidate_requests'])):
        raise Blocked('evidence_failure', 'every planned context and candidate receipt required')
    receipts = [evidence['eip']] + evidence['vm_context'] + evidence['vm_candidates']
    receipt_ids = [opaque(r.get('receipt_id')) if isinstance(r, dict) else opaque(None) for r in receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise Blocked('capture_failure', 'each request needs its own unambiguous receipt identity')
    contexts = []
    for envelope, desc in zip(evidence['vm_context'], plan['context_requests']):
        contexts += collect('VM_NOVA', envelope, desc['request'], desc['role'], capture)
    contexts = _validate_rows('VM_NOVA', contexts)
    directory = {v['id']: v for v in contexts}
    decoded = {v['id']: decode(v.get('privateIps'), present='privateIps' in v) for v in contexts}
    unknown_by_region = {r: sum(d['status'] != 'decoded' for i, d in decoded.items()
                                if directory[i]['logicalRegionName'] == r)
                         for r in sorted({e['logicalRegionName'] for e in eips})}
    selected_by_key, candidate_ids = {}, set()
    for envelope, desc in zip(evidence['vm_candidates'], plan['candidate_requests']):
        if not isinstance(envelope, dict) or envelope.get('lookup_id') != desc['lookup_id']:
            raise Blocked('capture_failure', 'per-token lookup identity changed')
        rows = collect('VM_NOVA', envelope, desc['request'], desc['role'], capture)
        selected = selected_by_key.setdefault((desc['region'], desc['fixed_token']), set())
        for vm in rows:
            if directory.get(vm['id']) != vm:
                raise Blocked('context_drift', 'candidate row absent or changed in same complete context')
            selected.add(vm['id'])
            candidate_ids.add(vm['id'])
    matches = {}
    for region, token in _lookup_tokens(eips):
        exact = {i for i, d in decoded.items()
                 if directory[i]['logicalRegionName'] == region and token in d['tokens']}
        if not exact <= selected_by_key.get((region, token), set()):
            raise Blocked('candidate_recall_gap', 'candidate response omitted an exact same-capture member',
                          {'region': region, 'fixed_token': token,
                           'missing_vm_ids': sorted(exact - selected_by_key.get((region, token), set()))})
        matches[(region, token)] = exact
    members = [{'vm_id': i, 'logical_region_name': directory[i]['logicalRegionName'], 'address_token': token}
               for i in sorted(candidate_ids) for token in decoded[i]['tokens']]
    states, unknown_eips = [], []
    for eip in eips:
        key = eip['logicalRegionName'], eip.get('fixedIpAddress')
        count = len(matches.get(key, set()))
        if key not in matches:
            status = 'unknown_fixed_address'
            unknown_eips.append(eip['id'])
        elif unknown_by_region[key[0]]:
            status = 'known_candidates_population_incomplete'
        elif capture['isolation'] != 'immutable_snapshot':
            status = 'known_candidates_non_atomic_capture'
        elif count > 1:
            status = 'multiple_address_member_candidates'
        elif count == 1:
            status = 'one_address_member_candidate'
        else:
            status = 'no_address_member_in_declared_snapshot'
        states.append({'eip_id': eip['id'], 'eip_region': key[0],
                       'known_matching_vm_count': count, 'membership_status': status})
    unknown_vm = sum(unknown_by_region.values())
    diag = {
        'selected_eip_count': len(eips), 'context_vm_count': len(contexts),
        'candidate_vm_count': len(candidate_ids), 'unknown_VM_address_rows': unknown_vm,
        'unknown_fixed_EIP_rows': len(unknown_eips), 'unknown_fixed_eip_ids': sorted(unknown_eips),
        'fixed_address_states': [{'eip_id': e['id'], 'fixed_ip_present': 'fixedIpAddress' in e,
                                  **_fixed_state(e)} for e in sorted(eips, key=lambda row: row['id'])],
        'unknown_address_by_region': unknown_by_region,
        'vm_address_states': [{'vm_id': i, 'region': directory[i]['logicalRegionName'],
                               'private_ips_present': 'privateIps' in directory[i], **decoded[i]}
                              for i in sorted(decoded)],
        'duplicate_member_tokens_removed': sum(d['duplicate_token_count'] for d in decoded.values()),
        'membership_population_complete_in_declared_receipts': not unknown_vm and not unknown_eips,
        'capture_isolation_asserted_by_B': capture['isolation'], 'capture_origin_asserted_by_B': capture['origin'],
        'membership_snapshot_complete_under_B_assertions': not unknown_vm and not unknown_eips
                                                            and capture['isolation'] == 'immutable_snapshot',
        'native_execution_verified_by_module': False, 'full_eip_binding_complete': False,
        'ownership_authority': 'not_established_by_address_membership',
        'source_authentication': 'external B obligation; ids, flags and digests cannot authenticate receipts',
        'C_official_empty_reference_policy': 'not_resolved_here',
    }
    if p['unknown_policy'] == 'reject' and (unknown_vm or unknown_eips):
        raise Blocked('unknown_population', 'unknown addresses under explicit reject policy', diag)
    tables = {'CLOUD_FLOATING_IPS': eips, 'CLOUD_VM_NOVA': contexts,
              'A_VM_ADDRESS_MEMBERS': members, 'A_EIP_MEMBER_STATE': states}
    return tables, diag


def prepare(params, evidence):
    tables, diag = _prepare(params, evidence)
    source = {'params': deepcopy(params), 'evidence': deepcopy(evidence)}
    return {'protocol': PROTOCOL, 'tables': tables, 'diagnostics': diag,
            'input_evidence': source, 'evidence_sha256': hashlib.sha256(encoded(source)).hexdigest()}


def execute_prepared(prepared):
    if not isinstance(prepared, dict) or prepared.get('protocol') != PROTOCOL:
        raise Blocked('prepared_drift', 'current checked prepared contract required')
    source = prepared.get('input_evidence')
    if (not isinstance(source, dict) or set(source) != {'params', 'evidence'}
            or prepared.get('evidence_sha256') != hashlib.sha256(encoded(source)).hexdigest()):
        raise Blocked('prepared_drift', 'retained input evidence and matching integrity digest required')
    tables, diag = _prepare(source['params'], source['evidence'])
    if encoded(prepared.get('tables')) != encoded(tables) or encoded(prepared.get('diagnostics')) != encoded(diag):
        raise Blocked('prepared_drift', 'prepared tables or diagnostics changed')
    conn = sqlite3.connect(':memory:')
    try:
        for name, columns in TABLE_SCHEMA.items():
            conn.execute('CREATE TABLE ' + name + ' (' + ','.join('"' + c + '" ' +
                         ('INTEGER' if c == 'known_matching_vm_count' else 'TEXT COLLATE BINARY')
                         for c in columns) + ')')
            conn.executemany('INSERT INTO ' + name + ' VALUES (' + ','.join('?' for _ in columns) + ')',
                             [[row.get(c) for c in columns] for row in tables[name]])
        cur = conn.execute(SQL)
        if tuple(c[0] for c in cur.description) != OUTPUT:
            raise AssertionError('output schema drift')
        rows = [dict(zip(OUTPUT, row)) for row in cur.fetchall()]
        # Count display unknowns by identity before membership fanout.
        diag['requested_display_unknown_counts'] = {
            'floating_ip': sum(blank(e.get('floatingIpAddress')) for e in tables['CLOUD_FLOATING_IPS']),
            'vm_name': sum(blank(v.get('name')) for v in tables['CLOUD_VM_NOVA']
                           if any(r['vm_id'] == v['id'] for r in rows)),
        }
        return {'ok': True, 'columns': list(OUTPUT), 'rows': rows, 'diagnostics': diag,
                'full_original_question_certified': False}
    finally:
        conn.close()


def execute_local(params, evidence):
    return execute_prepared(prepare(params, evidence))


def evaluate(params, evidence):
    """Controlled failures have rows=NULL, never a forged successful empty list."""
    try:
        return execute_local(params, evidence)
    except Blocked as exc:
        return {'ok': False, 'rows': None, 'columns': list(OUTPUT),
                'error': {'code': exc.code, 'message': str(exc), 'details': deepcopy(exc.details)},
                'full_original_question_certified': False}
