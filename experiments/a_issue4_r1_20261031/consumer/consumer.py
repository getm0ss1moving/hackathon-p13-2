"""Offline 298 consumer. Only the externally pinned provider decides PORT policy.

Raw HTTP/source/isolation claims are B assertions, never established by a hash.
No fetching, model, official executor mutation or address-to-EIP ownership guess.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
PROTOCOL = 'tenant-vm-eip-host-consumer-r2'
LEGACY_SHA = '1e750166c9c6040ae0f5c2caf5407605476e29f05bf450c6b90b6a6a18ab15c4'
CODEC_SHA = '0d3e9663ede6b55ba465066a84bfaa37c8c8ece2f22e10fa57affa5a78c0113e'
PORT_COLUMNS = ('id', 'devId', 'logicalRegionName')
NULLABLE = {'VM_NOVA': {'name', 'tenantName', 'privateIps', 'floatingIp', 'hostId', 'resId'},
            'HOST': {'name', 'ipAddress'}, 'FLOATING_IPS': {'portId', 'floatingIpAddress', 'isInternal'}}
FOREIGN_KEYS = {'VM_NOVA': {'hostId', 'resId'}, 'HOST': set(), 'FLOATING_IPS': {'portId'}}
LIMIT = 4096


class ConsumerError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def encoded(value):
    def native_json(item, active):
        kind = type(item)
        if item is None or kind in (str, bool, int):
            return
        if kind is float:
            if not math.isfinite(item):
                raise ValueError('nonfinite float')
            return
        if kind not in (dict, list):
            raise ValueError('only native JSON objects/arrays/scalars are permitted')
        identity = id(item)
        if identity in active:
            raise ValueError('cyclic JSON container')
        active.add(identity)
        if kind is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('JSON object keys must be native strings')
            children = item.values()
        else:
            children = item
        for child in children:
            native_json(child, active)
        active.remove(identity)
    try:
        native_json(value, set())
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                          allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ConsumerError('invalid_json', 'finite UTF-8 JSON required') from exc


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def blank(value):
    return value is None or (type(value) is str and not value.strip())


def text(value):
    if type(value) is not str or blank(value) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ConsumerError('identity_or_scope_failure', 'nonblank exact control-free UTF-8 text required')
    encoded(value)
    return value


def _module(path, sha, name):
    path = Path(path)
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ConsumerError('source_pin_failure', 'pinned source is unavailable') from exc
    if path.is_symlink() or actual != sha:
        raise ConsumerError('source_pin_failure', 'source bytes differ from external pin')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy():
    return _module(ROOT / 'legacy_vm_eip_host.py', LEGACY_SHA, '_tenant_legacy_r2')


def provider(provider_root=None):
    pin = json.loads((ROOT / 'PROVIDER_LOCK.json').read_text())
    if pin.get('status') != 'FROZEN_PROVIDER_INTERFACE':
        raise ConsumerError('provider_pending', 'provider frozen interface has not been received')
    root = (Path(provider_root) if provider_root is not None else ROOT / pin['provider_root']).resolve()
    module = _module(root / 'shared_policy.py', pin['source_sha256'], '_tenant_shared_provider_r2')
    if module.VERSION != pin['version'] or module.PORT_BATCH_PROTOCOL != pin['protocol']:
        raise ConsumerError('source_pin_failure', 'provider version/protocol differs from external pin')
    return module, {**pin, 'resolved_root': str(root)}


def build_tenant_view(params):
    m = legacy()
    try:
        plan = m.build(params)
    except m.Unsupported as exc:
        raise ConsumerError('invalid_params', str(exc)) from exc
    for value in params.values():
        text(value)
    if plan['transport_diagnostic']['status'] == 'blocked_core_length':
        raise ConsumerError('request_too_large', 'expanded legacy API+SQL exceeds4096 UTF-8 bytes; no truncation')
    plan = deepcopy(plan)
    plan.update(protocol=PROTOCOL, default_enabled=False, runtime_adopted=False,
                full_original_question_certified=False,
                receipt_protocol='capture + raw_receipts; PORT context first, optionally all generated scoped batches',
                port_duplicate_policy='external pinned provider only',
                selection_receipt='optional VM_NOVA_SELECTION actual tenant query; omission does not prove tenant API-selection obligation')
    plan['tenant_selection_request'] = _request('VM_NOVA', {k: v for k, v in params.items() if k != 'view'})
    return plan


def _request(ci, equal, in_field=None, keys=None):
    constraints = [{'simple': {'name': k, 'value': text(v), 'operator': 'equal'}} for k, v in sorted(equal.items())]
    if in_field is not None:
        if not keys:
            raise ConsumerError('scope_failure', 'empty IN must never become a broad request')
        constraints.append({'simple': {'name': in_field, 'value': list(keys), 'operator': 'in'}})
    for item in constraints[1:]:
        item['logOp'] = 'and'
    result = {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=1000', 'autoPagination': True}
    if constraints:
        result['condition'] = {'constraint': constraints}
    if len(encoded(result)) > LIMIT:
        raise ConsumerError('request_too_large', 'literal request exceeds4096 UTF-8 bytes; no truncation')
    return result


def plan_tenant_port_batches(params, vm_context):
    build_tenant_view(params)
    groups = {}
    for row in vm_context:
        if row.get('tenantName') != params['tenantName']:
            continue
        if 'logicalRegionName' in params and row.get('logicalRegionName') != params['logicalRegionName']:
            continue
        if not blank(row.get('resId')):
            groups.setdefault(text(row['logicalRegionName']), set()).add(text(row['resId']))
    batches = []
    for region, keys in sorted(groups.items()):
        batch = []
        for key in sorted(keys):
            proposed = batch + [key]
            try:
                if len(proposed) > 100:
                    raise ConsumerError('request_too_large', 'batch count limit')
                _request('PORT', {'logicalRegionName': region}, 'devId', proposed)
            except ConsumerError:
                if not batch:
                    raise
                batches.append(_request('PORT', {'logicalRegionName': region}, 'devId', batch))
                batch, proposed = [], [key]
                _request('PORT', {'logicalRegionName': region}, 'devId', proposed)
            batch = proposed
        if batch:
            batches.append(_request('PORT', {'logicalRegionName': region}, 'devId', batch))
    return batches


def _capture(evidence):
    if type(evidence) is not dict or set(evidence) != {'capture', 'raw_receipts', 'question_text'}:
        raise ConsumerError('evidence_failure', 'closed capture/raw_receipts/full question_text evidence required')
    capture = evidence['capture']
    if (type(capture) is not dict or set(capture) != {'capture_id', 'source_ref', 'schema_ref', 'origin', 'isolation'}
            or capture['origin'] not in ('synthetic', 'B_verified_native')
            or capture['isolation'] not in ('immutable_snapshot', 'best_effort_non_atomic')):
        raise ConsumerError('capture_failure', 'explicit current capture origin and isolation required')
    for key in ('capture_id', 'source_ref', 'schema_ref'):
        text(capture[key])
    if 'question_text' in evidence:
        if type(evidence['question_text']) is not str or not evidence['question_text'].strip():
            raise ConsumerError('evidence_failure', 'question_text must retain the full nonblank original text')
        encoded(evidence['question_text'])
    encoded(evidence)
    return capture


def _state(item):
    if type(item) is not dict or item.get('ok') is not True or item.get('success', True) is not True:
        raise ConsumerError('receipt_failure', 'successful actual receipt required')
    error = item.get('error')
    if not (error is None or error is False or type(error) is str and error == ''):
        raise ConsumerError('receipt_failure', 'declared request error')
    if type(item.get('http_status')) is not int or not 200 <= item['http_status'] < 300:
        raise ConsumerError('receipt_failure', 'actual HTTP 2xx required; derived is not HTTP')
    for key in ('httpStatus', 'status_code', 'statusCode', 'http_status_code', 'httpStatusCode'):
        if key in item and (type(item[key]) is not int or not 200 <= item[key] < 300):
            raise ConsumerError('receipt_failure', 'contradictory HTTP state')
    if 'status' in item and not (type(item['status']) is int and 200 <= item['status'] < 300
                                 or type(item['status']) is str and item['status'] in ('ok', 'success')):
        raise ConsumerError('receipt_failure', 'contradictory or unknown receipt status')
    if (item.get('receipt_kind', 'raw_http') != 'raw_http'
            or any(k in item for k in ('source_raw_receipt_sha256', 'source_projection_sha256', 'canonical_receipt', 'canonical_receipts'))):
        raise ConsumerError('derived_as_raw', 'derived projection cannot establish HTTP receipt')


def page_request(request, index):
    out = deepcopy(request)
    url = urlsplit(out['url'])
    pairs = parse_qsl(url.query, keep_blank_values=True)
    if len([k for k, _ in pairs if k == 'pageNo']) != 1:
        raise ConsumerError('request_failure', 'one pageNo required')
    out['url'] = urlunsplit((url.scheme, url.netloc, url.path,
                            urlencode([(k, str(index) if k == 'pageNo' else v) for k, v in pairs]), url.fragment))
    return out


def _raw_pages(receipt, request, capture):
    _state(receipt)
    if receipt.get('capture_id') != capture['capture_id']:
        raise ConsumerError('capture_failure', 'receipt capture identity changed')
    text(receipt.get('receipt_id'))
    if encoded(receipt.get('request')) != encoded(request):
        raise ConsumerError('request_failure', 'actual request/scope/operator changed')
    text(receipt.get('schema_source'))
    pages = receipt.get('pages')
    if type(pages) is not list or not pages:
        raise ConsumerError('pagination_failure', 'complete bound actual pages required')
    rows, total = [], None
    for index, page in enumerate(pages, 1):
        _state(page)
        if 'capture_id' in page and page['capture_id'] != capture['capture_id']:
            raise ConsumerError('capture_failure', 'page capture identity contradicts current capture')
        number, count, size, t = page.get('pageNo', page.get('currentPage')), page.get('totalPageNo'), page.get('pageSize'), page.get('totalNum')
        if 'currentPage' in page and (type(page['currentPage']) is not int or page['currentPage'] != number):
            raise ConsumerError('pagination_failure', 'contradictory page number')
        if type(number) is not int or number != index or type(count) is not int or type(size) is not int or size != 1000 or type(t) is not int or t < 0:
            raise ConsumerError('pagination_failure', 'invalid pagination metadata')
        if total is None:
            total = t
        if total != t or count != (t + 999) // 1000 and not (t == 0 and count == 1):
            raise ConsumerError('pagination_failure', 'unstable population')
        if encoded(page.get('request')) != encoded(page_request(request, index)):
            raise ConsumerError('request_failure', 'page actual request changed')
        batch = page.get('objList')
        if type(batch) is not list or any(type(row) is not dict for row in batch) or len(batch) != min(1000, max(0, t - len(rows))):
            raise ConsumerError('pagination_failure', 'missing/extra rows')
        rows.extend(batch)
    if len(rows) != total or len(pages) != max(1, (total + 999) // 1000):
        raise ConsumerError('pagination_failure', 'missing/extra pages')
    return rows


def _field_state(row, field):
    if field not in row:
        return 'missing'
    value = row[field]
    if value is None:
        return 'null'
    if value == '':
        return 'empty_string'
    if type(value) is str and not value.strip():
        return 'whitespace'
    return 'present'


def _collect_role(ci, receipt, request, columns, capture):
    raw_rows = _raw_pages(receipt, request, capture)
    schema = receipt.get('schema')
    if receipt.get('schema_verified') is not True or type(schema) is not list or any(type(k) is not str for k in schema) or len(schema) != len(set(schema)) or not set(columns) <= set(schema):
        raise ConsumerError('schema_failure', ci + ': actual schema required, including zero rows')
    equals = {}
    for item in request.get('condition', {}).get('constraint', []):
        s = item['simple']
        if s['operator'] != 'equal' or item.get('logOp', 'and') != 'and':
            raise ConsumerError('scope_failure', 'non-PORT role scope is closed equal')
        equals[s['name']] = s['value']
    rows, seen, states, missing, normalized = [], set(), [], {}, {}
    nullable = (NULLABLE[ci] & set(columns)) - set(equals)
    for raw in raw_rows:
        if any(k not in raw for k in columns if k not in nullable):
            raise ConsumerError('schema_failure', ci + ': required role field missing')
        identity = text(raw.get('id'))
        text(raw.get('logicalRegionName'))
        if identity in seen:
            raise ConsumerError('duplicate_identity', ci + ': repeated identity prohibited')
        seen.add(identity)
        if any(k not in raw or encoded(raw[k]) != encoded(v) for k, v in equals.items()):
            raise ConsumerError('scope_failure', ci + ': row outside exact actual request')
        row = {k: deepcopy(raw.get(k)) for k in columns}
        field_states = {k: _field_state(raw, k) for k in columns}
        for key, value in row.items():
            if key == 'isInternal' and ci == 'FLOATING_IPS' and type(value) is bool:
                row[key] = 'true' if value else 'false'
            elif value is not None and type(value) is not str:
                raise ConsumerError('schema_failure', ci + '.' + key + ': unexpected native type')
            if key not in raw:
                missing[key] = missing.get(key, 0) + 1
            if key in FOREIGN_KEYS[ci] and blank(value):
                if value is not None:
                    normalized[key] = normalized.get(key, 0) + 1
                row[key] = None
        states.append({'id': identity, 'fields': field_states})
        rows.append(row)
    canonical = {'receipt_kind': 'derived_validated_projection_not_HTTP', 'raw_receipt_sha256': digest(receipt),
                 'raw_total_num': len(raw_rows), 'raw_observation_count': len(raw_rows), 'canonical_object_count': len(rows),
                 'duplicate_observation_count': 0, 'canonical_projection_sha256': digest(rows), 'schema_source': receipt['schema_source'],
                 'missing_nullable_observations': missing, 'blank_normalized_observations': normalized, 'field_states': states}
    return {'rows': rows, 'columns': list(columns), 'canonical_receipt': canonical}


def _legacy_derived(projection, expected):
    rows, source_sha, pages = projection['rows'], digest(projection['canonical_receipt']), []
    for index in range(max(1, (len(rows) + 999) // 1000)):
        pages.append({'ok': True, 'pageNo': index + 1, 'pageSize': 1000, 'totalNum': len(rows),
                      'totalPageNo': (len(rows) + 999) // 1000, 'objList': deepcopy(rows[index * 1000:(index + 1) * 1000]),
                      'receipt_kind': 'derived_validated_projection_not_HTTP', 'source_projection_sha256': source_sha})
    return {'ok': True, 'request': deepcopy(expected), 'schema_verified': True, 'schema': list(projection['columns']), 'pages': pages,
            'receipt_kind': 'derived_validated_projection_not_HTTP', 'source_projection_sha256': source_sha}


def _port_projection(module, batches, requests, capture):
    pairs = []
    for receipt, request in zip(batches, requests):
        _raw_pages(receipt, request, capture)
        pairs.append({'request': deepcopy(request), 'receipt': deepcopy(receipt)})
    try:
        prepared = module.collect_port_batches(pairs)
        result = module.recheck_port_batches(prepared)
        if encoded(result) != encoded(prepared):
            raise ConsumerError('port_provider_failure', 'provider recheck returned a different projection')
        if result['protocol'] != 'a-port-batches-v1' or result['resource'] != 'PORT' or tuple(result['columns']) != PORT_COLUMNS:
            raise ConsumerError('port_provider_failure', 'provider protocol or projection schema drift')
        if encoded(result['raw_receipts']) != encoded(batches):
            raise ConsumerError('port_provider_failure', 'provider raw receipts changed')
        typed = result['typed_port_table']
        if (typed.get('table') != 'CLOUD_PORT' or tuple(typed.get('columns', ())) != PORT_COLUMNS
                or typed.get('types') != {f: 'TEXT' for f in PORT_COLUMNS}
                or encoded(typed.get('rows')) != encoded(result['rows'])):
            raise ConsumerError('port_provider_failure', 'provider typed table differs from checked projection')
        if len(batches) > 1:
            context = module.collect_port_batches([pairs[0]])
            for pair in pairs[1:]:
                scoped = module.collect_port_batches([pair])
                predicates = pair['request']['condition']['constraint']
                region, keys = predicates[0]['simple']['value'], predicates[1]['simple']['value']
                expected = [r for r in context['rows'] if r['logicalRegionName'] == region and r['devId'] in keys]
                if encoded(sorted(scoped['rows'], key=lambda r: r['id'])) != encoded(sorted(expected, key=lambda r: r['id'])):
                    raise ConsumerError('port_scope_recall_gap', 'scoped PORT response differs from same complete context')
            if encoded(sorted(result['rows'], key=lambda r: r['id'])) != encoded(sorted(context['rows'], key=lambda r: r['id'])):
                raise ConsumerError('port_scope_drift', 'PORT scoped union differs from complete context')
    except module.Unsupported as exc:
        raise ConsumerError('port_provider_failure', str(exc)) from exc
    return result


def prepare_tenant_view(params, evidence, *, provider_root=None):
    plan, capture, m = build_tenant_view(params), _capture(evidence), legacy()
    schemas = m.schema_for(params['view'])
    raw = evidence['raw_receipts']
    if type(raw) is not dict or set(raw) - (set(schemas) | {'VM_NOVA_SELECTION'}) or not set(schemas) <= set(raw):
        raise ConsumerError('evidence_failure', 'exact view resources plus optional actual VM selection required')
    calls, projections, actual_receipts = dict(zip(schemas, plan['api_call'])), {}, []
    for ci in schemas:
        if ci == 'PORT':
            continue
        projections[ci] = _collect_role(ci, raw[ci], calls[ci], schemas[ci], capture)
        actual_receipts.append(raw[ci])
    selected = [v for v in projections['VM_NOVA']['rows'] if v['tenantName'] == params['tenantName']]
    selection_proven = params['view'] == 'native_ip_host_rows'
    if 'VM_NOVA_SELECTION' in raw:
        selection_call = plan['tenant_selection_request']
        selection = _collect_role('VM_NOVA', raw['VM_NOVA_SELECTION'], selection_call, schemas['VM_NOVA'], capture)
        if encoded(sorted(selection['rows'], key=lambda r: r['id'])) != encoded(sorted(selected, key=lambda r: r['id'])):
            raise ConsumerError('selection_drift', 'actual tenant query differs from same full VM context')
        selected_ids = {r['id'] for r in selected}
        context_states = [s for s in projections['VM_NOVA']['canonical_receipt']['field_states'] if s['id'] in selected_ids]
        if encoded(sorted(context_states, key=lambda s: s['id'])) != encoded(sorted(selection['canonical_receipt']['field_states'], key=lambda s: s['id'])):
            raise ConsumerError('selection_drift', 'tenant selection and context disagree on field presence/null state')
        actual_receipts.append(raw['VM_NOVA_SELECTION'])
        projections['VM_NOVA_SELECTION'] = selection
        selection_proven = True
    port_pin, provider_prepared = None, None
    if 'PORT' in schemas:
        module, port_pin = provider(provider_root)
        batches = raw['PORT'] if type(raw['PORT']) is list else [raw['PORT']]
        scoped = plan_tenant_port_batches(params, projections['VM_NOVA']['rows'])
        if len(batches) not in {1, 1 + len(scoped)}:
            raise ConsumerError('evidence_failure', 'PORT needs context alone, or context plus all generated scope batches')
        requests = [calls['PORT']] + (scoped if len(batches) > 1 else [])
        provider_prepared = _port_projection(module, batches, requests, capture)
        projections['PORT'] = provider_prepared
        actual_receipts.extend(batches)
        plan['port_actual_requests'] = deepcopy(requests)
        plan['port_scoped_batch_set_executed'] = len(batches) > 1
    ids = [text(r.get('receipt_id')) for r in actual_receipts]
    if len(ids) != len(set(ids)):
        raise ConsumerError('capture_failure', 'every actual request requires a unique receipt identity')
    derived = {ci: _legacy_derived(projections[ci], calls[ci]) for ci in schemas}
    try:
        tables, diagnostics = m.prepare(params, derived)
    except m.Unsupported as exc:
        raise ConsumerError('relationship_failure', str(exc)) from exc
    typed = {'CLOUD_' + ci: {'columns': list(fields), 'types': {f: 'TEXT' for f in fields},
                            'collations': {f: 'BINARY' for f in fields}, 'rows': deepcopy(tables['CLOUD_' + ci])}
             for ci, fields in schemas.items()}
    if provider_prepared is not None:
        source_table = provider_prepared['typed_port_table']
        if encoded(source_table['rows']) != encoded(tables['CLOUD_PORT']):
            raise ConsumerError('port_provider_failure', 'legacy validation changed provider canonical PORT rows')
        typed['CLOUD_PORT'] = {k: deepcopy(source_table[k]) for k in ('columns', 'types', 'rows')}
        typed['CLOUD_PORT']['collations'] = {f: 'BINARY' for f in source_table['columns']}
    codec = _module(ROOT / 'address_codec_r1.py', CODEC_SHA, '_tenant_frozen_address_codec')
    raw_states = {s['id']: s['fields'] for s in projections['VM_NOVA']['canonical_receipt']['field_states']}
    ip_states = [{'vm_id': v['id'], 'selected': v['tenantName'] == params['tenantName'],
                  'raw_field_state': raw_states[v['id']]['privateIps'],
                  **codec.decode(v['privateIps'], present=raw_states[v['id']]['privateIps'] != 'missing')}
                 for v in projections['VM_NOVA']['rows']]
    diagnostics = deepcopy(diagnostics)
    diagnostics.update(full_eip_objects_binding_complete=False, business_complete=False, full_original_question_certified=False,
                       runtime_adopted=False, actual_tenant_selection_receipt_proven=selection_proven,
                       capture_isolation_asserted_by_B=capture['isolation'], native_capture_authenticated_by_consumer=False,
                       private_ip_states=ip_states,
                       selected_unknown_private_ip_vm_count=sum(s['selected'] and s['status'] != 'decoded' for s in ip_states),
                       port_policy_ref=deepcopy(port_pin), source_authentication='B external obligation; marker/hash is not authentication')
    input_evidence = {'params': deepcopy(params), 'evidence': deepcopy(evidence),
                      'provider_root': port_pin['resolved_root'] if port_pin else None}
    return {'protocol': PROTOCOL, 'status': 'ready_for_typed_sql', 'plan': plan, 'typed_tables': typed,
            'raw_receipts': deepcopy(raw), 'canonical_receipts': {ci: deepcopy(p['canonical_receipt']) for ci, p in projections.items()},
            'provider_prepared': deepcopy(provider_prepared), 'derived_validator_inputs': derived,
            'input_evidence': input_evidence, 'input_evidence_sha256': digest(input_evidence),
            'typed_projection_sha256': digest(typed), 'diagnostics': diagnostics, 'default_enabled': False, 'B_loader_pairing': 'pending'}


def recheck_tenant_prepared(prepared):
    if type(prepared) is not dict or prepared.get('protocol') != PROTOCOL or prepared.get('status') != 'ready_for_typed_sql':
        raise ConsumerError('prepared_failure', 'current consumer preparation required')
    encoded(prepared)
    source = prepared.get('input_evidence')
    if type(source) is not dict or set(source) != {'params', 'evidence', 'provider_root'} or digest(source) != prepared.get('input_evidence_sha256'):
        raise ConsumerError('prepared_failure', 'retained input evidence changed')
    fresh = prepare_tenant_view(source['params'], source['evidence'], provider_root=source['provider_root'])
    if encoded(fresh) != encoded(prepared):
        raise ConsumerError('prepared_failure', 'recomputed raw/derived/typed/plan/diagnostics differ')
    return fresh


def execute_tenant_prepared(prepared):
    checked = recheck_tenant_prepared(prepared)
    conn = sqlite3.connect(':memory:')
    try:
        for table, schema in checked['typed_tables'].items():
            conn.execute('CREATE TABLE ' + table + ' (' + ','.join('"' + f + '" TEXT COLLATE BINARY' for f in schema['columns']) + ')')
            conn.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in schema['columns']) + ')',
                             [[row[f] for f in schema['columns']] for row in schema['rows']])
        cur = conn.execute(checked['plan']['sql'])
        columns = [c[0] for c in cur.description]
        if columns != checked['plan']['output_columns']:
            raise ConsumerError('output_failure', 'legacy output schema differs')
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    diagnostics = deepcopy(checked['diagnostics'])
    requested = {'vm_name': 'vm_id', 'private_ips_raw': 'vm_id', 'native_floating_ip_raw': 'vm_id', 'host_name': 'host_id', 'host_ip': 'host_id'}
    if checked['plan']['view'] == 'known_port_eip_host_rows':
        requested.update(eip_address='eip_id', eip_internal_role_raw='eip_id')
    diagnostics['requested_display_unknown_counts'] = {f: len({r[i] for r in rows if r[i] is not None and blank(r[f])}) for f, i in requested.items()}
    diagnostics['requested_display_values_complete'] = not any(diagnostics['requested_display_unknown_counts'].values())
    return {'ok': True, 'columns': columns, 'rows': rows, 'diagnostics': diagnostics,
            'full_original_question_certified': False, 'runtime_adopted': False}


def evaluate_tenant_view(params, evidence, *, provider_root=None):
    try:
        return execute_tenant_prepared(prepare_tenant_view(params, evidence, provider_root=provider_root))
    except ConsumerError as exc:
        return {'ok': False, 'rows': None, 'error': {'code': exc.code, 'message': str(exc), 'details': deepcopy(exc.details)},
                'full_original_question_certified': False}
