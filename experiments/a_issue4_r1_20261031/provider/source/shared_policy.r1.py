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


def collect(resource, receipt, request, columns, *, nullable=(), blank_to_null=(), numeric=()):
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
    filters = equal_filters(request)
    ignored = PORT_IGNORED_AUDIT_FIELDS - set(columns)
    for raw in raw_rows:
        if any(k not in raw for k in columns if k not in nullable):
            raise Unsupported(resource + ': missing identity/scope/required field')
        identity = text(raw.get('id'))
        if any(raw.get(k) != v or k not in raw for k, v in filters.items()):
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
        signature = digest({k: v for k, v in raw.items() if k not in ignored})
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
