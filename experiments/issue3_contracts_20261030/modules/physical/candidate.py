"""Pure local NEXT_N28 extension; no IO, model, routing or SDK mutation.

The current native physical CIs have no nonempty schema evidence. Materializing
this isolated candidate does not enable the profile in production.
"""
import json
import sqlite3

FAMILY_ID = 'NEXT_N28'
PROFILE_ID = 'physical_network_and_virtual_firewall_counts'
RESOURCES = ('S_Switch', 'S_Router', 'VFW')
TABLES = {'S_Switch': 'SYS_Switch', 'S_Router': 'SYS_Router', 'VFW': 'CLOUD_VFW'}
LABELS = {'S_Switch': 'switch', 'S_Router': 'router', 'VFW': 'vfw'}
PAGE_SIZE = 10000
MAX_REQUEST_BYTES = 4096
REQUIRED_COLUMNS = {'id': 'TEXT', 'logicalRegionName': 'TEXT'}
RELEASE_BLOCKERS = (
    'S_Switch_nonempty_native_id_and_logicalRegionName_schema_unverified',
    'S_Router_nonempty_native_id_and_logicalRegionName_schema_unverified',
    'B_must_supply_validated_complete_pages_and_real_zero_row_preparation',
    'official_executor_empty_placeholder_count_is_not_a_valid_zero',
    'C_business_count_and_pagination_gates_remain',
)


def parameters_for_region(region):
    """Convenience for callers that already resolved the explicit region role."""
    return {'resource_set': list(RESOURCES), 'group': 'none',
            'layout': 'labeled_rows', 'metric': 'count_rows',
            'filters': {'logicalRegionName': region},
            'required_filters': ['logicalRegionName']}


def build(params):
    """Materialize the one reviewed extension tuple into ordinary API+SQL.

    Unknown keys/roles/metrics are rejected. No entity defaults are supplied.
    Existing NEXT_N28 five tuples are owned by their original helper.
    """
    keys = {'resource_set', 'group', 'layout', 'metric', 'filters', 'required_filters'}
    if not isinstance(params, dict) or set(params) != keys:
        raise ValueError('closed_parameter_schema_required')
    if (params['resource_set'] != list(RESOURCES) or params['group'] != 'none'
            or params['layout'] != 'labeled_rows' or params['metric'] != 'count_rows'):
        raise ValueError('unreviewed_resource_role_group_layout_or_metric')
    filters = params['filters']
    if (not isinstance(filters, dict) or set(filters) != {'logicalRegionName'}
            or params['required_filters'] != ['logicalRegionName']):
        raise ValueError('one_explicit_equal_logical_region_required')
    region = filters['logicalRegionName']
    if (not isinstance(region, str) or not region or region.strip() != region
            or any(ord(c) < 32 for c in region) or '{{' in region or '}}' in region):
        raise ValueError('literal_nonempty_region_required')
    calls = []
    for ci in RESOURCES:
        call = {'method': 'GET',
                'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=10000',
                'condition': {'constraint': [{'simple': {
                    'name': 'logicalRegionName', 'value': region, 'operator': 'equal'}}]}}
        if len(json.dumps(call, ensure_ascii=False, separators=(',', ':')).encode()) > MAX_REQUEST_BYTES:
            raise ValueError('request_exceeds_4096_bytes')
        calls.append(call)
    branches = ["SELECT '" + LABELS[ci] + "' AS device_type, COUNT(*) AS total FROM " + TABLES[ci]
                for ci in RESOURCES]
    return {'id': 'family_next_n28_physical_vfw_candidate',
            'name': 'independent_physical_and_virtual_firewall_counts', 'family_id': FAMILY_ID,
            'profile_id': PROFILE_ID, 'resources': list(RESOURCES),
            'api_call': calls, 'sql': ' UNION ALL '.join(branches),
            'output_columns': ['device_type', 'total'],
            'output_grain': 'one labeled row for each independently fetched resource CI',
            'required_schema': {ci: dict(REQUIRED_COLUMNS) for ci in RESOURCES},
            'status': 'isolated_candidate_blocked_native_schema',
            'release_blockers': list(RELEASE_BLOCKERS)}


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('invalid_' + name)
    return value


def preflight(params, responses, schema_contracts=None, *, synthetic=False):
    """Validate complete page receipts and return local typed rows.

    Each receipt is {ok, request:{resource,logicalRegionName,pageNo,pageSize},
    payload:{objList,totalNum,totalPageNo,currentPage,pageSize}, snapshot_id?}.
    Explicit success is mandatory; absent/malformed/failed/truncated data cannot
    become []. A multi-page resource additionally requires a common nonempty
    snapshot_id. Empty resources require an external typed schema contract.
    Synthetic contracts are accepted only with the explicit synthetic flag.
    This function never claims production-ready status.
    """
    plan = build(params)
    if not isinstance(responses, dict) or set(responses) != set(RESOURCES):
        raise ValueError('all_three_resource_receipts_required')
    schema_contracts = {} if schema_contracts is None else schema_contracts
    if not isinstance(schema_contracts, dict) or not set(schema_contracts) <= set(RESOURCES):
        raise ValueError('invalid_schema_contracts')
    region = params['filters']['logicalRegionName']
    tables, schemas = {}, {}
    for ci in RESOURCES:
        receipts = responses[ci]
        if not isinstance(receipts, list) or not receipts:
            raise ValueError(ci + ':missing_pages')
        totals, page_totals, seen_pages, snapshot_ids, rows = set(), set(), [], set(), []
        for receipt in receipts:
            if not isinstance(receipt, dict) or receipt.get('ok') is not True:
                raise ValueError(ci + ':request_failed_or_success_unproven')
            request = receipt.get('request')
            payload = receipt.get('payload')
            if not isinstance(request, dict) or not isinstance(payload, dict):
                raise ValueError(ci + ':missing_request_or_payload')
            page_no = _integer(request.get('pageNo'), 'pageNo', 1)
            if request != {'resource': ci, 'logicalRegionName': region,
                           'pageNo': page_no, 'pageSize': PAGE_SIZE}:
                raise ValueError(ci + ':scope_or_request_mismatch')
            obj = payload.get('objList')
            if not isinstance(obj, list):
                raise ValueError(ci + ':missing_or_invalid_objList')
            total = _integer(payload.get('totalNum'), 'totalNum')
            pages = _integer(payload.get('totalPageNo'), 'totalPageNo')
            current = _integer(payload.get('currentPage'), 'currentPage', 1)
            size = _integer(payload.get('pageSize'), 'pageSize', 1)
            if current != page_no or size != PAGE_SIZE or len(obj) > PAGE_SIZE:
                raise ValueError(ci + ':page_metadata_mismatch')
            expected_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            if pages not in ({0, 1} if total == 0 else {expected_pages}):
                raise ValueError(ci + ':inconsistent_total_pages')
            expected_length = min(PAGE_SIZE, max(0, total - (page_no - 1) * PAGE_SIZE))
            if len(obj) != expected_length:
                raise ValueError(ci + ':truncated_or_irregular_page')
            totals.add(total); page_totals.add(pages); seen_pages.append(page_no)
            snapshot = receipt.get('snapshot_id')
            if snapshot is not None and (not isinstance(snapshot, str) or not snapshot.strip()):
                raise ValueError(ci + ':invalid_snapshot_id')
            snapshot_ids.add(snapshot)
            rows.extend(obj)
        if len(totals) != 1 or len(page_totals) != 1:
            raise ValueError(ci + ':changed_totals')
        total = next(iter(totals))
        expected_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if seen_pages != list(range(1, expected_count + 1)):
            raise ValueError(ci + ':missing_duplicate_or_out_of_order_pages')
        if expected_count > 1 and (len(snapshot_ids) != 1 or not next(iter(snapshot_ids))):
            raise ValueError(ci + ':multi_page_snapshot_required')
        if len(rows) != total:
            raise ValueError(ci + ':truncated_or_excess_rows')
        identities = set()
        for row in rows:
            if not isinstance(row, dict) or not set(REQUIRED_COLUMNS) <= set(row):
                raise ValueError(ci + ':required_native_columns_missing')
            identity = row['id']
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError(ci + ':missing_identity')
            if identity in identities:
                raise ValueError(ci + ':duplicate_identity')
            identities.add(identity)
            if row['logicalRegionName'] != region:
                raise ValueError(ci + ':record_scope_mismatch')
        if not rows:
            contract = schema_contracts.get(ci)
            if (not isinstance(contract, dict) or contract.get('columns') != REQUIRED_COLUMNS
                    or contract.get('evidence') not in {'synthetic', 'official_verified_nonempty'}):
                raise ValueError(ci + ':empty_resource_schema_unproven')
            if contract['evidence'] == 'synthetic' and synthetic is not True:
                raise ValueError(ci + ':synthetic_schema_forbidden_in_real_mode')
            if contract['evidence'] == 'official_verified_nonempty':
                source_hash = contract.get('source_sha256')
                if (not isinstance(source_hash, str) or len(source_hash) != 64
                        or any(c not in '0123456789abcdef' for c in source_hash)):
                    raise ValueError(ci + ':schema_source_hash_required')
        tables[TABLES[ci]] = [{key: row[key] for key in REQUIRED_COLUMNS} for row in rows]
        schemas[TABLES[ci]] = dict(REQUIRED_COLUMNS)
    return {'status': 'ready_for_local_sql_only', 'tables': tables,
            'schemas': schemas, 'sql': plan['sql'], 'output_columns': plan['output_columns'],
            'release_blockers': list(RELEASE_BLOCKERS), 'synthetic': synthetic is True}


def execute_local(params, responses, schema_contracts=None, *, synthetic=False):
    """Offline verification only. True empty tables receive zero inserted rows."""
    prepared = preflight(params, responses, schema_contracts, synthetic=synthetic)
    with sqlite3.connect(':memory:') as conn:
        for table, columns in prepared['schemas'].items():
            conn.execute('CREATE TABLE "' + table + '" (id TEXT, logicalRegionName TEXT)')
            conn.executemany('INSERT INTO "' + table + '" VALUES (?, ?)',
                             [(r['id'], r['logicalRegionName']) for r in prepared['tables'][table]])
        return [list(row) for row in conn.execute(prepared['sql']).fetchall()]
