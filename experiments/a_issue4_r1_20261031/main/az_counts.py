"""Partial AZ population diagnostic: independent VM/VOLUME and unknown ROUTER.

ROUTER has no source AZ column. The local NULL is an explicit derived unknown
marker, never advertised as source schema or authoritative deployment mapping.
"""
import sqlite3
import shared_policy as policy

FAMILY_ID = 'family_az_resource_population_diagnostic'
SCHEMA = {'VM_NOVA': ('id', 'logicalRegionName', 'azoneName'),
          'VOLUME': ('id', 'logicalRegionName', 'azoneName'),
          'ROUTER': ('id', 'logicalRegionName'),
          'AZONE': ('id', 'logicalRegionName', 'name')}
OUTPUT = ('azone_name', 'row_kind', 'known_ecs_count', 'known_volume_count', 'known_vpc_count',
          'ecs_count_if_complete', 'volume_count_if_complete', 'vpc_count_if_complete')


def build(params):
    if type(params) is not dict or set(params) != {'logicalRegionName'}:
        raise policy.Unsupported('one explicit logicalRegionName required')
    region = policy.text(params['logicalRegionName'])
    if any(ord(c) < 32 or ord(c) == 127 for c in region):
        raise policy.Unsupported('control-free region required')
    calls = [{'method': 'GET', 'url': '/rest/hackthon/db/instances/'+ci+'?pageNo=1&pageSize=1000',
              'autoPagination': True, 'condition': {'constraint': [
                  {'simple': {'name': 'logicalRegionName', 'value': region, 'operator': 'equal'}}]}}
             for ci in SCHEMA]
    r = "'" + region.replace("'", "''") + "'"
    sql = f'''WITH
v AS (SELECT azoneName d,COUNT(*) n FROM CLOUD_VM_NOVA WHERE logicalRegionName={r} GROUP BY azoneName),
w AS (SELECT azoneName d,COUNT(*) n FROM CLOUD_VOLUME WHERE logicalRegionName={r} GROUP BY azoneName),
c AS (SELECT COUNT(*) n FROM CLOUD_ROUTER WHERE logicalRegionName={r}),
d AS (SELECT name d FROM CLOUD_AZONE WHERE logicalRegionName={r} UNION SELECT d FROM v UNION SELECT d FROM w
 UNION SELECT NULL WHERE (SELECT n FROM c)>0),
u AS (SELECT COALESCE((SELECT n FROM v WHERE d IS NULL),0) v,COALESCE((SELECT n FROM w WHERE d IS NULL),0) w)
SELECT d.d AS azone_name,CASE WHEN d.d IS NULL THEN 'unknown_az' ELSE 'known_az_name' END AS row_kind,
 COALESCE(v.n,0) AS known_ecs_count,COALESCE(w.n,0) AS known_volume_count,
 CASE WHEN d.d IS NULL THEN c.n ELSE 0 END AS known_vpc_count,
 CASE WHEN d.d IS NOT NULL AND u.v=0 THEN COALESCE(v.n,0) END AS ecs_count_if_complete,
 CASE WHEN d.d IS NOT NULL AND u.w=0 THEN COALESCE(w.n,0) END AS volume_count_if_complete,
 CASE WHEN d.d IS NOT NULL AND c.n=0 THEN 0 END AS vpc_count_if_complete
FROM d CROSS JOIN c CROSS JOIN u LEFT JOIN v ON v.d IS d.d LEFT JOIN w ON w.d IS d.d
ORDER BY d.d IS NOT NULL,d.d'''
    n = len(policy.encoded({'api_call': calls, 'sql': sql}))
    if n > 4096:
        raise policy.Unsupported('expanded API SQL exceeds local budget')
    return {'id': FAMILY_ID, 'family_id': FAMILY_ID, 'api_call': calls, 'sql': sql,
            'resources': list(SCHEMA), 'output_columns': list(OUTPUT), 'required_schema': SCHEMA,
            'full_requested_operation_supported': False, 'default_enabled': False,
            'expanded_core_bytes': n, 'group_domain': 'region AZONE names UNION observed VM/VOLUME AZ names UNION explicit NULL unknown',
            'derived_unknown_policy': 'every ROUTER contributes once to unknown AZ; no source azoneName column added'}


def execute_local(params, receipts):
    plan = build(params)
    if type(receipts) is not dict or set(receipts) != set(SCHEMA):
        raise policy.Unsupported('all four bound populations required')
    prepared = {}
    for (ci, cols), call in zip(SCHEMA.items(), plan['api_call']):
        optional = {'azoneName'} if ci == 'VM_NOVA' else set()
        prepared[ci] = policy.collect(ci, receipts[ci], call, cols, nullable=optional,
                                      blank_to_null={'azoneName'} if 'azoneName' in cols else set())
    if any(policy.blank(r['name']) for r in prepared['AZONE']['rows']):
        raise policy.Unsupported('AZ catalog name domain unproven')
    conn = sqlite3.connect(':memory:')
    try:
        for ci, p in prepared.items():
            fields = SCHEMA[ci]
            conn.execute('CREATE TABLE CLOUD_' + ci + ' (' + ','.join('"'+k+'" TEXT' for k in fields) + ')')
            conn.executemany('INSERT INTO CLOUD_' + ci + ' VALUES (' + ','.join('?' for _ in fields) + ')',
                             [[r[k] for k in fields] for r in p['rows']])
        cur = conn.execute(plan['sql'])
        rows = [dict(zip(OUTPUT, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    unknown = {ci: sum(r['azoneName'] is None for r in prepared[ci]['rows']) for ci in ('VM_NOVA', 'VOLUME')}
    unknown['ROUTER'] = len(prepared['ROUTER']['rows'])
    catalog = {r['name'] for r in prepared['AZONE']['rows']}
    out_of_catalog = {ci: sum(r['azoneName'] is not None and r['azoneName'] not in catalog for r in prepared[ci]['rows'])
                      for ci in ('VM_NOVA', 'VOLUME')}
    return {'columns': list(OUTPUT), 'rows': rows,
            'diagnostics': {'unknown_az_object_counts': unknown, 'observed_names_outside_AZ_catalog': out_of_catalog,
                            'full_answer': False, 'full_requested_operation_supported': False,
                            'deployment_AZ_business_authority': 'unresolved',
                            'count_meaning': 'known_* in NULL row is unknown-assignment population, never a real AZ',
                            'independent_population_sizes': {ci: len(p['rows']) for ci, p in prepared.items()}},
            'receipt_evidence': {ci: {'raw': p['raw_receipt'], 'canonical': p['canonical_receipt']} for ci, p in prepared.items()},
            'default_enabled': False}
