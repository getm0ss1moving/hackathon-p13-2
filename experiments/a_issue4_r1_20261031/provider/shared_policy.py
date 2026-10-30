"""A shared, offline receipt/projection policy. No network or question routing.

Raw HTTP assertions are supplied by B. Validation proves their local consistency,
not authenticity, snapshot isolation, or business authority.
"""
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

VERSION = 'a-shared-policy-issue4-v1'
PORT_IGNORED_AUDIT_FIELDS = frozenset({'last_Modified', 'last_update_date'})
PORT_BATCH_PROTOCOL = 'a-port-batches-v1'
PORT_BATCH_COLUMNS = ('id', 'devId', 'logicalRegionName')


class Unsupported(ValueError):
    pass


def encoded(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError) as exc:
        raise Unsupported('finite UTF-8 JSON required') from exc


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def blank(value):
    return value is None or (type(value) is str and not value.strip())


def text(value):
    if type(value) is not str or blank(value):
        raise Unsupported('nonblank exact text required')
    encoded(value)
    return value


def state_ok(value):
    if type(value) is not dict or value.get('ok') is not True:
        raise Unsupported('successful request receipt required')
    if 'success' in value and value['success'] is not True:
        raise Unsupported('contradictory success state')
    if 'error' in value and not (value['error'] is None or value['error'] is False
                                or type(value['error']) is str and value['error'] == ''):
        raise Unsupported('request error')
    for key in ('http_status', 'httpStatus', 'status_code', 'statusCode',
                'http_status_code', 'httpStatusCode'):
        if key in value and (type(value[key]) is not int or not 200 <= value[key] < 300):
            raise Unsupported('HTTP failure or unknown HTTP state')
    if 'status' in value and not (type(value['status']) is int and 200 <= value['status'] < 300
                                 or type(value['status']) is str and value['status'] in ('ok', 'success')):
        raise Unsupported('unknown receipt status')


def page_request(request, number):
    call = deepcopy(request)
    u = urlsplit(call['url'])
    query = parse_qsl(u.query, keep_blank_values=True)
    if len([1 for k, _ in query if k == 'pageNo']) != 1:
        raise Unsupported('one pageNo parameter required')
    call['url'] = urlunsplit((u.scheme, u.netloc, u.path,
                             urlencode([(k, str(number) if k == 'pageNo' else v) for k, v in query]), u.fragment))
    return call


def equal_filters(request):
    condition = request.get('condition', {})
    result = {}
    for item in condition.get('constraint', []):
        simple = item.get('simple', {})
        if simple.get('operator') != 'equal' or not isinstance(simple.get('name'), str):
            raise Unsupported('only flat equal scope supported')
        key, value = simple['name'], simple.get('value')
        if key in result or item.get('logOp', 'and') != 'and':
            raise Unsupported('ambiguous equal scope')
        result[key] = value
    return result


def _business_signature(raw, columns):
    """One exact PORT equivalence rule, shared within and across batches."""
    ignored = PORT_IGNORED_AUDIT_FIELDS - set(columns)
    return digest({k: v for k, v in raw.items() if k not in ignored})


def collect(resource, receipt, request, columns, *, nullable=(), blank_to_null=(), numeric=()):
    """Legacy equal-only entry point; behavior and output contract unchanged."""
    return _collect(resource, receipt, request, columns, nullable=nullable,
                    blank_to_null=blank_to_null, numeric=numeric)


def _collect(resource, receipt, request, columns, *, nullable=(), blank_to_null=(), numeric=(), port_scope=None):
    """Check full RAW pagination first; produce separate canonical receipt.

    Only PORT duplicate identities may collapse. Compare every source field except
    the two explicitly named audit timestamps, with presence and JSON types exact.
    Any requested audit field participates in equivalence. Other CIs reject even
    identical duplicates. Missing nullable values need actual schema declaration.
    """
    state_ok(receipt)
    encoded(receipt)
    if receipt.get('request') != request:
        raise Unsupported(resource + ': request binding mismatch')
    schema = receipt.get('schema')
    if (receipt.get('schema_verified') is not True or type(schema) is not list
            or any(type(k) is not str for k in schema) or len(set(schema)) != len(schema)
            or not set(columns) <= set(schema)):
        raise Unsupported(resource + ': actual verified schema required')
    text(receipt.get('schema_source'))
    if not set(nullable) <= set(columns) or not set(blank_to_null) <= set(columns):
        raise Unsupported('undeclared projection policy')
    pages = receipt.get('pages')
    if type(pages) is not list or not pages:
        raise Unsupported(resource + ': missing pages')
    page_sizes = [v for k, v in parse_qsl(urlsplit(request['url']).query) if k == 'pageSize']
    if len(page_sizes) != 1 or not page_sizes[0].isdigit():
        raise Unsupported('one integer pageSize required')
    expected_size = int(page_sizes[0])
    raw_rows, meta = [], None
    for index, page in enumerate(pages, 1):
        state_ok(page)
        number = page.get('pageNo', page.get('currentPage'))
        if ('pageNo' in page and 'currentPage' in page and page['pageNo'] != page['currentPage']):
            raise Unsupported('contradictory page number')
        total, size, count = (page.get(k) for k in ('totalNum', 'pageSize', 'totalPageNo'))
        if (any(type(x) is not int for x in (number, total, size, count)) or number != index
                or total < 0 or size != expected_size or size <= 0):
            raise Unsupported('invalid page metadata')
        expected_pages = max(1, (total + size - 1) // size)
        if (len(pages) != expected_pages or count != expected_pages and not (total == 0 and count == 0)
                or meta is not None and meta != (total, size, count)):
            raise Unsupported('incomplete or unstable pagination')
        meta = total, size, count
        if page.get('request') != page_request(request, index):
            raise Unsupported('unbound page request')
        batch = page.get('objList')
        if type(batch) is not list or len(batch) != min(size, max(0, total - len(raw_rows))):
            raise Unsupported('truncated or extra RAW page rows')
        if any(type(r) is not dict for r in batch):
            raise Unsupported('invalid row')
        raw_rows.extend(batch)
    # Deduplication happens only after the complete raw population is checked.
    rows, seen, business, sparse, normalized = [], {}, {}, {}, {}
    filters = equal_filters(request) if port_scope is None else None
    ignored = PORT_IGNORED_AUDIT_FIELDS - set(columns)
    for raw in raw_rows:
        if any(k not in raw for k in columns if k not in nullable):
            raise Unsupported(resource + ': missing identity/scope/required field')
        identity = text(raw.get('id'))
        wrong_filter = (any(raw.get(k) != v or k not in raw for k, v in filters.items()) if filters is not None
                        else any(k not in raw or type(raw[k]) is not str or
                                 (raw[k] != v if op == 'equal' else raw[k] not in v)
                                 for k, op, v in port_scope))
        if wrong_filter:
            raise Unsupported(resource + ': response filter mismatch')
        row = {k: deepcopy(raw.get(k)) for k in columns}
        for k, value in row.items():
            if value is not None and (type(value) not in (str, int, float) if k in numeric else type(value) is not str):
                raise Unsupported(resource + '.' + k + ': invalid source type')
            if k not in raw:
                sparse[k] = sparse.get(k, 0) + 1
            if k in blank_to_null and blank(value):
                if value is not None:
                    normalized[k] = normalized.get(k, 0) + 1
                row[k] = None
        # Missing key != explicit NULL; audit-only differences are the sole exception.
        signature = _business_signature(raw, columns)
        if identity in seen:
            if resource != 'PORT' or business[identity] != signature or seen[identity] != row:
                raise Unsupported(resource + ': conflicting or prohibited duplicate identity')
            continue
        seen[identity], business[identity] = row, signature
        rows.append(row)
    diagnostics = {
        'policy_version': VERSION, 'raw_receipt_sha256': digest(receipt),
        'raw_total_num': meta[0], 'raw_observation_count': len(raw_rows),
        'canonical_object_count': len(rows), 'duplicate_observation_count': len(raw_rows) - len(rows),
        'canonical_projection_sha256': digest(rows), 'schema_source': receipt['schema_source'],
        'missing_nullable_observations': sparse, 'blank_normalized_observations': normalized,
        'duplicate_policy': 'PORT all business source fields equal, audit timestamps excluded' if resource == 'PORT' else 'reject',
        'equivalence_fields': sorted(set().union(*(set(r) for r in raw_rows)) - ignored) if resource == 'PORT' else list(columns),
        'ignored_audit_fields': sorted(ignored) if resource == 'PORT' else [],
        'population_meaning': 'raw observations and canonical identities are separate; unique source population is not independently certified',
    }
    return {'resource': resource, 'raw_receipt': deepcopy(receipt), 'rows': rows,
            'canonical_receipt': diagnostics, 'columns': list(columns)}


def _port_scope(request):
    """Closed PORT request shapes only; retain and validate actual in lists."""
    if (type(request) is not dict or set(request) - {'method', 'url', 'autoPagination', 'condition'}
            or request.get('method') != 'GET' or request.get('autoPagination') is not True
            or type(request.get('url')) is not str):
        raise Unsupported('closed actual complete PORT request required')
    u = urlsplit(request['url'])
    pairs = parse_qsl(u.query, keep_blank_values=True)
    if (u.path != '/rest/hackthon/db/instances/PORT' or u.fragment
            or len(pairs) != 2 or {k for k, _ in pairs} != {'pageNo', 'pageSize'}
            or dict(pairs)['pageNo'] != '1' or not dict(pairs)['pageSize'].isdigit()
            or not 1 <= int(dict(pairs)['pageSize']) <= 1000):
        raise Unsupported('exact PORT endpoint and initial pagination required')
    condition = request.get('condition', {'constraint': []})
    if type(condition) is not dict or set(condition) != {'constraint'} or type(condition['constraint']) is not list:
        raise Unsupported('flat PORT AND constraints required')
    scopes, seen = [], set()
    for item in condition['constraint']:
        if (type(item) is not dict or set(item) - {'simple', 'logOp'} or 'simple' not in item
                or item.get('logOp', 'and') != 'and' or type(item['simple']) is not dict
                or set(item['simple']) != {'name', 'operator', 'value'}):
            raise Unsupported('only exact simple PORT AND clauses supported')
        k, op, value = (item['simple'][key] for key in ('name', 'operator', 'value'))
        if type(k) is not str or k not in ('logicalRegionName', 'devId') or k in seen:
            raise Unsupported('duplicate or unsupported PORT scope field')
        seen.add(k)
        if op == 'equal':
            text(value)
        elif k == 'devId' and op == 'in':
            if type(value) is not list or not value:
                raise Unsupported('devId in requires nonempty explicit native list')
            for token in value:
                text(token)
            if len(set(value)) != len(value):
                raise Unsupported('devId in values must be exact and unique')
        else:
            raise Unsupported('only region equal and devId equal/in supported')
        scopes.append((k, op, deepcopy(value)))
    return scopes


def _raw_http_assertions(receipt):
    """Reject derived inputs even with appended200; never create HTTP evidence."""
    state_ok(receipt)
    if (receipt.get('receipt_kind', 'raw_http') != 'raw_http'
            or 'source_raw_receipt_sha256' in receipt or 'canonical_receipt' in receipt
            or 'canonical_receipts' in receipt):
        raise Unsupported('PORT batches require original raw HTTP evidence, not a derived projection')
    keys = ('http_status', 'httpStatus', 'status_code', 'statusCode', 'http_status_code', 'httpStatusCode')
    if not any(k in receipt for k in keys) and not (type(receipt.get('status')) is int):
        raise Unsupported('actual integer HTTP2xx assertion required for each raw envelope/page')


def collect_port_batches(batches):
    """Prepare PORT-only scoped batches and reject cross-batch business conflicts.

    Each batch is exactly {'request': expected actual request, 'receipt': raw}.
    This creates typed local data and canonical metadata, never HTTP receipts.
    Other CI policies, including EIP bool roles, remain with their consumers.
    """
    if type(batches) is not list or not batches:
        raise Unsupported('nonempty list of complete raw PORT batches required')
    evidence = {'batches': deepcopy(batches)}
    encoded(evidence)
    per_batch, raw_receipts, rows, seen, signatures = [], [], [], {}, {}
    for batch in batches:
        if type(batch) is not dict or set(batch) != {'request', 'receipt'}:
            raise Unsupported('exact request/receipt batch pair required')
        request, receipt = batch['request'], batch['receipt']
        scopes = _port_scope(request)
        _raw_http_assertions(receipt)
        if type(receipt.get('pages')) is not list or not receipt['pages']:
            raise Unsupported('complete raw pages required')
        for page in receipt['pages']:
            _raw_http_assertions(page)
        p = _collect('PORT', receipt, request, PORT_BATCH_COLUMNS,
                     nullable={'devId'}, blank_to_null={'devId'}, port_scope=scopes)
        if any(blank(r['logicalRegionName']) for r in p['rows']):
            raise Unsupported('PORT native region must be nonblank even in global scope')
        # Canonical rows alone are insufficient cross-batch identity evidence.
        raw_signatures = {r['id']: _business_signature(r, PORT_BATCH_COLUMNS)
                          for page in receipt['pages'] for r in page['objList']}
        for row in p['rows']:
            identity = row['id']
            if identity in seen:
                if signatures[identity] != raw_signatures[identity] or seen[identity] != row:
                    raise Unsupported('PORT: conflicting duplicate identity across raw batches')
                continue
            signatures[identity], seen[identity] = raw_signatures[identity], row
            rows.append(deepcopy(row))
        per_batch.append(deepcopy(p['canonical_receipt']))
        raw_receipts.append(deepcopy(receipt))
    raw_count = sum(p['raw_observation_count'] for p in per_batch)
    batch_count = sum(p['canonical_object_count'] for p in per_batch)
    canonical = {
        'protocol': PORT_BATCH_PROTOCOL, 'batch_count': len(batches),
        'batch_raw_total_nums': [p['raw_total_num'] for p in per_batch],
        'raw_observation_count': raw_count, 'sum_batch_canonical_object_counts': batch_count,
        'canonical_object_count': len(rows),
        'within_batch_duplicate_observation_count': raw_count - batch_count,
        'cross_batch_duplicate_object_count': batch_count - len(rows),
        'duplicate_observation_count': raw_count - len(rows),
        'raw_receipt_set_sha256': digest(raw_receipts), 'canonical_projection_sha256': digest(rows),
        'batch_request_sha256': [digest(b['request']) for b in batches],
        'population_meaning': 'sum of separately scoped raw observations and union canonical identities; no single raw population total or global coverage claim',
        'scope_coverage_complete': False, 'business_authority_certified': False,
    }
    return {
        'protocol': PORT_BATCH_PROTOCOL, 'resource': 'PORT', 'columns': list(PORT_BATCH_COLUMNS),
        'rows': rows, 'raw_receipts': raw_receipts, 'canonical_receipts': per_batch,
        'canonical_receipt': canonical,
        'typed_port_table': {'table': 'CLOUD_PORT', 'columns': list(PORT_BATCH_COLUMNS),
                             'types': {k: 'TEXT' for k in PORT_BATCH_COLUMNS}, 'rows': deepcopy(rows)},
        'input_evidence': evidence, 'input_evidence_sha256': digest(evidence),
        'canonical_projection_sha256': digest(rows), 'default_enabled': False, 'full_answer': False,
    }


def recheck_port_batches(prepared):
    """Rebuild from retained actual raw batches; never trust ready/hash markers."""
    if type(prepared) is not dict or prepared.get('protocol') != PORT_BATCH_PROTOCOL:
        raise Unsupported('current PORT batch protocol required')
    evidence = prepared.get('input_evidence')
    if (type(evidence) is not dict or set(evidence) != {'batches'}
            or prepared.get('input_evidence_sha256') != digest(evidence)):
        raise Unsupported('actual PORT batch input evidence changed')
    fresh = collect_port_batches(evidence['batches'])
    if encoded(fresh) != encoded(prepared):
        raise Unsupported('PORT raw/canonical/typed projection or diagnostic changed')
    return fresh


def projected_pages(prepared, *, page_size=1000, page_number='pageNo', bound_request=None):
    """Derived local validator input. These are never labeled original HTTP pages."""
    rows = prepared['rows']
    count = max(1, (len(rows) + page_size - 1) // page_size)
    result = []
    for index in range(1, count + 1):
        p = {'ok': True, page_number: index, 'pageSize': page_size,
             'totalNum': len(rows), 'totalPageNo': count if rows else 0,
             'objList': deepcopy(rows[(index - 1) * page_size:index * page_size]),
             'receipt_kind': 'derived_validated_projection_not_HTTP',
             'source_raw_receipt_sha256': prepared['canonical_receipt']['raw_receipt_sha256']}
        if bound_request is not None:
            p['request'] = page_request(bound_request, index)
        result.append(p)
    return result
