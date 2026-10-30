"""R3: exact source contract, dynamic namespace, trusted B capture boundary.

No historical resource contents or hashes participate in runtime eligibility.
Only trusted host code may configure the capture reader. This module validates
captured requests/pages and relations; it cannot authenticate arbitrary JSON as
an HTTP response or supply B's missing typed-count execution integration.
"""
import copy
import hashlib
import json

RESULT_COLUMNS = ['gaussdb_count', 'middleware_count', 'obs_bucket_count']
TEMPLATE_SHA256 = 'e604b32516b5807a283d245fd8cc69b33d6cbb73a53c0b71e210c2f73e1b8c0b'
SQL_SHA256 = '878d97545d32894c8db5ebde9a3a4d651ed54961b96f3d50076d0eda36e32440'
FIELDS = {'AZONE': ('id', 'logicalRegionId', 'logicalRegionName'),
          'MIDDLEWARE': ('id', 'logicalRegionId')}
API_ROLES = (('GAUSSDB_INSTANCE', True), ('MIDDLEWARE', False),
             ('OBS_BUCKET', True), ('AZONE', True))
RESOURCES = ['GAUSSDB_INSTANCE', 'MIDDLEWARE', 'OBS_BUCKET', 'AZONE']


def _reject(diagnostics, reason):
    if diagnostics is not None:
        diagnostics.update(status='rejected', reason=reason)
    return None


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _project_rows(ci, records):
    if not isinstance(records, list):
        return None
    keys = FIELDS[ci]
    projected = []
    for record in records:
        if not isinstance(record, dict):
            return None
        values = [record.get(key) for key in keys]
        if any(not isinstance(v, str) or not v or v != v.strip() for v in values):
            return None
        try:
            for value in values:
                value.encode('utf-8')
        except UnicodeError:
            return None
        projected.append(dict(zip(keys, values)))
    return sorted(projected, key=lambda row: tuple(row[key] for key in keys))


def _global_relation(azones, middleware):
    """Check the whole supplied directory, before any requested-name filtering."""
    if not azones:
        return None, 'empty_global_directory'
    name_to_ids, id_to_names = {}, {}
    for row in azones:
        name_to_ids.setdefault(row['logicalRegionName'], set()).add(row['logicalRegionId'])
        id_to_names.setdefault(row['logicalRegionId'], set()).add(row['logicalRegionName'])
    if any(len(ids) != 1 for ids in name_to_ids.values()):
        return None, 'global_name_has_multiple_ids'
    if any(len(names) != 1 for names in id_to_names.values()):
        return None, 'global_id_has_multiple_names'
    if any(row['logicalRegionId'] not in id_to_names for row in middleware):
        return None, 'unresolved_global_middleware_region_id'
    return name_to_ids, None


def _exact_template_contract(template):
    if not isinstance(template, dict) or template.get('family_id'):
        return False
    if template.get('resources') != RESOURCES or not isinstance(template.get('sql'), str):
        return False
    calls = template.get('api_call')
    if not isinstance(calls, list) or len(calls) != len(API_ROLES):
        return False
    for call, (ci, scoped) in zip(calls, API_ROLES):
        expected = {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=10000'}
        if scoped:
            expected['condition'] = {'constraint': [{'simple': {
                'name': 'logicalRegionName', 'value': '{{logicalRegionName}}', 'operator': 'equal'}}]}
        if call != expected:
            return False
    try:
        return (hashlib.sha256(template['sql'].encode()).hexdigest() == SQL_SHA256
                and _digest(template) == TEMPLATE_SHA256)
    except (TypeError, ValueError, UnicodeError):
        return False


def _nonempty_string(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _validated_capture(capture, execution_id, diagnostics=None):
    """Validate pages captured by configured trusted B code, not model JSON.

    snapshot_id must come from B's verified source snapshot/read isolation. A
    newly invented UUID or complete=true cannot establish this property. The
    host must withhold the capture when it cannot establish source consistency.
    """
    if not isinstance(capture, dict) or capture.get('execution_id') != execution_id:
        return _reject(diagnostics, 'capture_execution_id_mismatch')
    snapshot_id = capture.get('snapshot_id')
    if not _nonempty_string(snapshot_id):
        return _reject(diagnostics, 'trusted_source_snapshot_required')
    reads = capture.get('reads')
    if not isinstance(reads, dict) or set(reads) != set(FIELDS):
        return _reject(diagnostics, 'complete_global_namespace_reads_required')
    records, receipts = {}, {}
    for ci, fields in FIELDS.items():
        read = reads[ci]
        if not isinstance(read, dict):
            return _reject(diagnostics, 'invalid_read_capture')
        expected_request = {'method': 'GET', 'ci': ci, 'endpoint': 'instances', 'constraints': []}
        if read.get('request') != expected_request:
            return _reject(diagnostics, 'global_unfiltered_CI_request_required')
        schema = read.get('schema')
        if (not isinstance(schema, list) or any(not isinstance(c, str) for c in schema)
                or not set(fields) <= set(schema)):
            return _reject(diagnostics, 'required_namespace_schema_unavailable')
        pages = read.get('pages')
        if not isinstance(pages, list) or not pages:
            return _reject(diagnostics, 'missing_namespace_pages')
        rows, totals = [], None
        for index, page in enumerate(pages, 1):
            if not isinstance(page, dict) or page.get('http_status') != 200 or type(page.get('http_status')) is not int:
                return _reject(diagnostics, 'namespace_HTTP_failure')
            if page.get('snapshot_id') != snapshot_id:
                return _reject(diagnostics, 'source_snapshot_drift')
            if type(page.get('request_page')) is not int or page['request_page'] != index:
                return _reject(diagnostics, 'duplicate_missing_or_out_of_order_page')
            body = page.get('body')
            if not isinstance(body, dict) or ('success' in body and body['success'] is not True) or body.get('error'):
                return _reject(diagnostics, 'namespace_response_failure')
            batch = body.get('objList')
            if not isinstance(batch, list):
                return _reject(diagnostics, 'namespace_objList_missing')
            total, count, size, current = (body.get(k) for k in ('totalNum', 'totalPageNo', 'pageSize', 'currentPage'))
            if not (_integer(total) and _integer(count) and _integer(size, 1) and type(current) is int and current == index):
                return _reject(diagnostics, 'invalid_namespace_pagination_metadata')
            if page.get('request') != dict(expected_request, pageNo=index, pageSize=size):
                return _reject(diagnostics, 'namespace_page_request_scope_drift')
            expected_count = (total + size - 1) // size
            if (total == 0 and count not in (0, 1)) or (total > 0 and count != expected_count):
                return _reject(diagnostics, 'inconsistent_namespace_total_pages')
            state = (total, count, size)
            if totals is not None and totals != state:
                return _reject(diagnostics, 'namespace_page_total_drift')
            totals = state
            expected_length = min(size, max(0, total - (index - 1) * size))
            if len(batch) != expected_length:
                return _reject(diagnostics, 'namespace_short_or_oversized_page')
            rows.extend(batch)
        total, count, size = totals
        if len(pages) != max(1, count) or len(rows) != total:
            return _reject(diagnostics, 'incomplete_namespace_pages')
        projected = _project_rows(ci, rows)
        if projected is None:
            return _reject(diagnostics, 'invalid_namespace_fields')
        records[ci] = projected
        receipts[ci] = {'row_count': total, 'pages': len(pages), 'projection_sha256': _digest(projected)}
    names, reason = _global_relation(records['AZONE'], records['MIDDLEWARE'])
    if reason:
        return _reject(diagnostics, reason)
    return {'snapshot_id': snapshot_id, 'records': records, 'receipts': receipts, 'names': names}


def make_region_count_binder(trusted_capture_reader):
    """Configure in trusted B host code, never from question/model parameters.

    The callback obtains captures from B's actual controlled execution inputs.
    It must not re-label caller JSON/flags as trusted. No reader is supplied by
    this candidate; absent B integration is an explicit blocker. This is a trust
    boundary, not cryptographic authentication of arbitrary Python callbacks.
    """
    if not callable(trusted_capture_reader):
        raise ValueError('B_trusted_execution_capture_reader_required')

    def bind(template, params, execution_id, diagnostics=None):
        if not _exact_template_contract(template):
            return _reject(diagnostics, 'template_contract_or_fingerprint_mismatch')
        if not isinstance(params, dict) or set(params) != {'logicalRegionName'}:
            return _reject(diagnostics, 'missing_or_extra_parameters')
        region = params['logicalRegionName']
        if not _nonempty_string(region):
            return _reject(diagnostics, 'invalid_explicit_region')
        if not _nonempty_string(execution_id):
            return _reject(diagnostics, 'trusted_execution_id_required')
        try:
            capture = trusted_capture_reader(execution_id)
        except Exception:
            return _reject(diagnostics, 'trusted_B_capture_unavailable')
        valid = _validated_capture(capture, execution_id, diagnostics)
        if valid is None:
            return None
        if region not in valid['names']:
            return _reject(diagnostics, 'requested_region_not_in_current_namespace')
        selected = [row for row in valid['records']['AZONE'] if row['logicalRegionName'] == region]
        proof = {
            'version': 'rb196-current-execution-namespace-v1',
            'execution_id': execution_id, 'snapshot_id': valid['snapshot_id'],
            'global_projection_sha256': {ci: info['projection_sha256'] for ci, info in valid['receipts'].items()},
            'selected_azone_projection_sha256': _digest(selected),
            'namespace_capture_validated': True,
            'actual_SQL_inputs_validated': False,
            'count_data_validated': False,
        }
        item = copy.deepcopy(template)
        for call, (_, scoped) in zip(item['api_call'], API_ROLES):
            if scoped:
                call['condition']['constraint'][0]['simple']['value'] = region
        item['_expected_result_columns'] = list(RESULT_COLUMNS)
        item['_namespace_execution_requirement'] = proof
        if diagnostics is not None:
            diagnostics.update(status='bound_requires_B_execution_input_check_and_typed_count',
                               reason='current_complete_namespace_validated')
        return item
    return bind


def check_execution_namespace(bound_item, execution_id, snapshot_id, actual_namespace_tables, diagnostics=None):
    """Check B's actual SQL input lists against this run's dynamic commitment.

    B must call this with its own actual input tables and verified snapshot ID,
    before typed SQL loading. This only covers AZONE and MIDDLEWARE namespace
    inputs; it does not certify GaussDB/OBS reads, empty COUNT, or SQL results.
    """
    if not _nonempty_string(execution_id) or not _nonempty_string(snapshot_id):
        return _reject(diagnostics, 'trusted_execution_and_source_snapshot_required')
    if not isinstance(bound_item, dict):
        return _reject(diagnostics, 'missing_bound_item')
    proof = bound_item.get('_namespace_execution_requirement')
    if not isinstance(proof, dict) or proof.get('version') != 'rb196-current-execution-namespace-v1':
        return _reject(diagnostics, 'missing_current_execution_requirement')
    if proof.get('execution_id') != execution_id or proof.get('snapshot_id') != snapshot_id:
        return _reject(diagnostics, 'execution_or_source_snapshot_mismatch')
    fingerprints = proof.get('global_projection_sha256')
    hashes = list(fingerprints.values()) if isinstance(fingerprints, dict) else []
    hashes.append(proof.get('selected_azone_projection_sha256'))
    if (not isinstance(fingerprints, dict) or set(fingerprints) != set(FIELDS)
            or any(not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h) for h in hashes)):
        return _reject(diagnostics, 'invalid_dynamic_execution_commitment')
    if not isinstance(actual_namespace_tables, dict) or set(actual_namespace_tables) != set(FIELDS):
        return _reject(diagnostics, 'actual_namespace_tables_required')
    actual = {ci: _project_rows(ci, rows) for ci, rows in actual_namespace_tables.items()}
    if any(rows is None for rows in actual.values()):
        return _reject(diagnostics, 'actual_namespace_fields_unavailable')
    if (_digest(actual['MIDDLEWARE']) != proof['global_projection_sha256']['MIDDLEWARE']
            or _digest(actual['AZONE']) != proof['selected_azone_projection_sha256']):
        return _reject(diagnostics, 'namespace_input_drift_since_capture')
    if diagnostics is not None:
        diagnostics.update(status='namespace_inputs_bound_for_this_execution_only',
                           reason='count_response_schema_and_empty_validation_still_required')
    return True


