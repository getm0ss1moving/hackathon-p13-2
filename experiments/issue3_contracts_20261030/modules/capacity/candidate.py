"""Isolated VDC-capacity materializer. No SDK, network, matcher, or evaluator imports."""
import json
import math
from decimal import Decimal, InvalidOperation

RESOURCES = ('VM_NOVA', 'FLAVOR', 'VOLUME', 'GAUSSDB_NODE')
REQUIRED_COLUMNS = {
    'VM_NOVA': ('id', 'logicalRegionName', 'vdcName', 'flavorId'),
    'FLAVOR': ('id', 'logicalRegionName', 'vcpuSize'),
    'VOLUME': ('id', 'logicalRegionName', 'vdcName', 'size'),
    'GAUSSDB_NODE': ('id', 'logicalRegionName', 'vdcName'),
}
OUTPUT_COLUMNS = ('vdc_name', 'known_vcpu', 'unknown_cpu_vm_count',
    'total_vcpu_if_complete', 'known_volume_size', 'unknown_volume_count',
    'total_volume_size_if_complete', 'gaussdb_node_count')

class Unsupported(ValueError):
    pass


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def _nonnegative_decimal(expr, integer=False):
    s = 'TRIM(CAST(' + expr + ' AS TEXT))'
    if integer:
        return f"({s}<>'' AND {s} NOT GLOB '*[^0-9]*')"
    return (f"({s}<>'' AND {s} NOT GLOB '*[^0-9.]*' AND "
            f"LENGTH({s})-LENGTH(REPLACE({s},'.',''))<=1 AND {s}<>'.')")


def build(params):
    """Return a fresh native api_call+SQL contract, never route from question text."""
    if not isinstance(params, dict) or set(params) - {'logicalRegionName'}:
        raise Unsupported('only explicit logicalRegionName is supported; additional obligations need another contract')
    region = params.get('logicalRegionName')
    if not isinstance(region, str) or not region.strip() or '\x00' in region:
        raise Unsupported('logicalRegionName must be an explicit nonempty string')
    r = _literal(region)
    cpu_valid = _nonnegative_decimal('f.vcpuSize', integer=True)
    vol_valid = _nonnegative_decimal('size')
    sql = f"""WITH
v AS (SELECT v.vdcName d,COUNT(*) n,
 SUM(CASE WHEN {cpu_valid} THEN CAST(f.vcpuSize AS INTEGER) ELSE 0 END) k,
 SUM(CASE WHEN {cpu_valid} THEN 0 ELSE 1 END) u
 FROM CLOUD_VM_NOVA v LEFT JOIN CLOUD_FLAVOR f
 ON v.flavorId=f.id AND v.logicalRegionName=f.logicalRegionName
 WHERE v.logicalRegionName={r} GROUP BY v.vdcName),
w AS (SELECT vdcName d,COUNT(*) n,
 SUM(CASE WHEN {vol_valid} THEN CAST(size AS REAL) ELSE 0 END) k,
 SUM(CASE WHEN {vol_valid} THEN 0 ELSE 1 END) u
 FROM CLOUD_VOLUME WHERE logicalRegionName={r} GROUP BY vdcName),
g AS (SELECT vdcName d,COUNT(*) n FROM CLOUD_GAUSSDB_NODE
 WHERE logicalRegionName={r} GROUP BY vdcName),
d AS (SELECT d FROM v UNION SELECT d FROM w UNION SELECT d FROM g)
SELECT d.d AS vdc_name,COALESCE(v.k,0) AS known_vcpu,
 COALESCE(v.u,0) AS unknown_cpu_vm_count,
 CASE WHEN COALESCE(v.u,0)=0 THEN COALESCE(v.k,0) END AS total_vcpu_if_complete,
 COALESCE(w.k,0) AS known_volume_size,COALESCE(w.u,0) AS unknown_volume_count,
 CASE WHEN COALESCE(w.u,0)=0 THEN COALESCE(w.k,0) END AS total_volume_size_if_complete,
 COALESCE(g.n,0) AS gaussdb_node_count
FROM d LEFT JOIN v ON d.d IS v.d LEFT JOIN w ON d.d IS w.d
LEFT JOIN g ON d.d IS g.d ORDER BY d.d IS NOT NULL,d.d"""
    api = [{'method': 'GET', 'url': f'/rest/hackthon/db/instances/{ci}?pageNo=1&pageSize=1000',
            'condition': {'constraint': [{'simple': {'name': 'logicalRegionName', 'value': region, 'operator': 'equal'}}]},
            'autoPagination': True} for ci in RESOURCES]
    out = {'id': 'A_ISSUE3_VDC_CAPACITY', 'resources': list(RESOURCES), 'api_call': api,
           'sql': sql, 'output_columns': list(OUTPUT_COLUMNS)}
    out['gates'] = ['B must validate complete pages and schema before SQL',
        'official empty-table loader produces _empty: unsupported until B supplies proven schema-preserving preparation',
        'source size units unconverted; GB/GiB equivalence requires C decision',
        'formal 4KB/depth policy and business acceptance remain external gates']
    out['serialized_plan_bytes'] = 0
    for _ in range(8):
        size = len(json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode())
        if size == out['serialized_plan_bytes']: break
        out['serialized_plan_bytes'] = size
    return out


def validate_pages(data, params):
    """Fail closed; return rows only for successful complete schema-confirmed snapshots.

    Input per resource: status='ok', schema_source, columns, pages=[native page].
    This is an offline integration contract, not a replacement official executor.
    """
    plan = build(params)
    region = params['logicalRegionName']
    if not isinstance(data, dict) or set(data) != set(RESOURCES):
        raise Unsupported('all four resource snapshots are required')
    result = {}
    for ci in RESOURCES:
        snap = data[ci]
        if not isinstance(snap, dict) or snap.get('status') != 'ok':
            raise Unsupported(f'{ci}: request failed/unknown')
        if not isinstance(snap.get('schema_source'), str) or not snap['schema_source']:
            raise Unsupported(f'{ci}: schema provenance required')
        columns = snap.get('columns')
        if not isinstance(columns, (list, tuple)) or not all(isinstance(x,str) for x in columns) or not set(REQUIRED_COLUMNS[ci]) <= set(columns):
            raise Unsupported(f'{ci}: missing schema columns')
        pages = snap.get('pages')
        if not isinstance(pages, list) or not pages:
            raise Unsupported(f'{ci}: missing pages')
        first = pages[0]
        if not isinstance(first, dict):
            raise Unsupported(f'{ci}: invalid page')
        meta = [first.get(k) for k in ('totalNum', 'totalPageNo', 'pageSize')]
        if any(type(x) is not int for x in meta):
            raise Unsupported(f'{ci}: pagination metadata required')
        total, page_total, page_size = meta
        expected_pages=max(1, math.ceil(total/page_size)) if page_size>0 else -1
        empty_page_zero=(total==0 and page_total==0 and len(pages)==1)
        if total < 0 or page_size <= 0 or (not empty_page_zero and (page_total != expected_pages or len(pages) != page_total)):
            raise Unsupported(f'{ci}: incomplete/truncated pages')
        rows, seen = [], set()
        for index, page in enumerate(pages, 1):
            if not isinstance(page, dict) or type(page.get('currentPage')) is not int or page.get('currentPage') != index or [page.get(k) for k in ('totalNum','totalPageNo','pageSize')] != meta:
                raise Unsupported(f'{ci}: unstable/out-of-order pages')
            batch = page.get('objList')
            if not isinstance(batch, list) or len(batch) != min(page_size, max(0,total-(index-1)*page_size)):
                raise Unsupported(f'{ci}: missing/truncated objList')
            for row in batch:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
                    raise Unsupported(f'{ci}: missing identity')
                if row['id'] in seen:
                    raise Unsupported(f'{ci}: duplicate identity across snapshot')
                if row.get('logicalRegionName') != region:
                    raise Unsupported(f'{ci}: scope mismatch/missing region')
                seen.add(row['id']); rows.append(row)
        if rows and not set(REQUIRED_COLUMNS[ci]) <= set().union(*(set(x) for x in rows)):
            raise Unsupported(f'{ci}: claimed schema absent from payload')
        # Prevent SQLite overflow and garbage CAST; dirty/null values remain unknown in SQL.
        numeric = 'vcpuSize' if ci == 'FLAVOR' else 'size' if ci == 'VOLUME' else None
        if numeric:
            max_sum = Decimal(0)
            for row in rows:
                value = row.get(numeric)
                text = str(value).strip() if value is not None else ''
                valid = (bool(text) and all(c in '0123456789' for c in text)) if ci == 'FLAVOR' else (bool(text) and text != '.' and text.count('.')<=1 and all(c in '0123456789.' for c in text))
                if valid:
                    try: number = Decimal(text)
                    except InvalidOperation: raise Unsupported(f'{ci}: invalid numeric representation')
                    if number > Decimal('1e15'):
                        raise Unsupported(f'{ci}: numeric magnitude outside bounded contract')
                    max_sum += number
            if max_sum > Decimal('1e15'):
                raise Unsupported(f'{ci}: aggregate outside bounded contract')
        result[ci] = rows
    # VM multiplicity can repeat one flavor; bound actual CPU sum too.
    flavors={row['id']:row for row in result['FLAVOR']}
    cpu_sum=0
    for vm in result['VM_NOVA']:
        text=str(flavors.get(vm.get('flavorId'),{}).get('vcpuSize','')).strip()
        if text and all(c in '0123456789' for c in text): cpu_sum+=int(text)
    if cpu_sum>10**15: raise Unsupported('VM CPU aggregate outside bounded contract')
    return result
