"""Explicit x86 architecture rows with distinct resource, host and BMC roles."""
import sqlite3
import shared_policy as policy

FAMILY_ID = 'family_x86_server_role_rows'
COLUMNS = ('id', 'logicalRegionName', 'cpuArch', 'name', 'ipAddress', 'hostName', 'hostIpAddress', 'hostType')
OUTPUT = ('server_id', 'server_name', 'cpu_arch', 'bmc_ip_address', 'host_name', 'host_ip_address', 'host_type')


def build(params):
    if type(params) is not dict or set(params) != {'logicalRegionName'}:
        raise policy.Unsupported('one explicit logicalRegionName required')
    region = policy.text(params['logicalRegionName'])
    if any(ord(c) < 32 or ord(c) == 127 for c in region):
        raise policy.Unsupported('control-free region required')
    call = {'method': 'GET', 'url': '/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=1000',
            'autoPagination': True, 'condition': {'constraint': [
                {'simple': {'name': 'logicalRegionName', 'value': region, 'operator': 'equal'}},
                {'simple': {'name': 'cpuArch', 'value': 'x86', 'operator': 'equal'}, 'logOp': 'and'}]}}
    r = "'" + region.replace("'", "''") + "'"
    sql = ('SELECT id AS server_id,name AS server_name,cpuArch AS cpu_arch,ipAddress AS bmc_ip_address,'
           'hostName AS host_name,hostIpAddress AS host_ip_address,hostType AS host_type '
           'FROM SYS_X86Server WHERE logicalRegionName=' + r + " AND cpuArch='x86' ORDER BY id")
    n = len(policy.encoded({'api_call': [call], 'sql': sql}))
    if n > 4096:
        raise policy.Unsupported('expanded API SQL exceeds local budget')
    return {'id': FAMILY_ID, 'family_id': FAMILY_ID, 'resources': ['S_X86Server'], 'api_call': [call],
            'sql': sql, 'output_columns': list(OUTPUT), 'required_schema': list(COLUMNS),
            'default_enabled': False, 'expanded_core_bytes': n,
            'role_boundary': 'name is resource display; ipAddress is BMC, never hostIpAddress fallback',
            'optional_host_role_authority': 'raw separately labeled fields only; business display equivalence unresolved'}


def execute_local(params, receipt):
    plan = build(params)
    prepared = policy.collect('S_X86Server', receipt, plan['api_call'][0], COLUMNS,
                              nullable={'ipAddress', 'hostName', 'hostIpAddress', 'hostType'},
                              blank_to_null={'ipAddress', 'hostName', 'hostIpAddress', 'hostType'})
    conn = sqlite3.connect(':memory:')
    try:
        conn.execute('CREATE TABLE SYS_X86Server (' + ','.join('"'+k+'" TEXT' for k in COLUMNS) + ')')
        conn.executemany('INSERT INTO SYS_X86Server VALUES (' + ','.join('?' for _ in COLUMNS) + ')',
                         [[r[k] for k in COLUMNS] for r in prepared['rows']])
        cur = conn.execute(plan['sql'])
        rows = [dict(zip(OUTPUT, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    return {'columns': list(OUTPUT), 'rows': rows,
            'diagnostics': {'unknown_values': {k: sum(policy.blank(r[k]) for r in prepared['rows'])
                                              for k in ('ipAddress', 'hostName', 'hostIpAddress', 'hostType')},
                            'architecture_source': 'cpuArch exact native x86, never CI class name',
                            'full_answer': False, 'role_authority_for_generic_IP_output': False},
            'receipt_evidence': {'raw': prepared['raw_receipt'], 'canonical': prepared['canonical_receipt']},
            'default_enabled': False}
