"""Opt-in adapters for existing A families; original parameter shapes/IDs preserved.

Input is always shared_policy's exact bound raw receipt protocol. Legacy validator
inputs below are explicit DERIVED projection receipts, never original HTTP proof.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sqlite3

import shared_policy as policy

ROOT = Path(__file__).resolve().parent
NAMES = ('vdc_counts', 'tenant', 'ranked_pool', 'cluster', 'network', 'hierarchy', 'named_vpc', 'capacity')


def core(name):
    if name not in NAMES:
        raise policy.Unsupported('unsupported closed adapter family')
    spec = importlib.util.spec_from_file_location('_issue4_' + name, ROOT / 'core' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection_request(module, params):
    call = deepcopy(module.build(params)['api_call'][0])
    name = params['filters']['name']
    constraint = call.setdefault('condition', {}).setdefault('constraint', [])
    constraint.append({'simple': {'name': 'name', 'value': name, 'operator': 'equal'},
                       **({'logOp': 'and'} if constraint else {})})
    return call


def build(name, params):
    m = core(name)
    plan = m.prepare(params) if name == 'vdc_counts' else m.build(params)
    plan = deepcopy(plan)
    # Keep the full parent directory AND require actual named selection at HTTP.
    if name == 'named_vpc':
        plan['api_call'].append(selection_request(m, params))
        plan['receipt_resources'] = list(m.RESOURCES) + ['ROUTER_SELECTION']
    else:
        plan['receipt_resources'] = list(plan['resources'])
    plan['shared_policy'] = policy.VERSION
    plan['default_enabled'] = False
    plan['expanded_adapter_api_sql_bytes'] = len(policy.encoded({k: plan[k] for k in ('api_call', 'sql')}))
    plan['adapter_transport_status'] = ('within_local_core_bound' if plan['expanded_adapter_api_sql_bytes'] <= 4096 else 'blocked_core_length')
    plan['final_B_envelope_verified'] = False
    return plan


def schemas(name, m, plan):
    if name == 'vdc_counts':
        return {ci: list(m.COLUMNS) for ci in m.RESOURCES}
    if name == 'tenant':
        return {ci: m.SCHEMAS[ci] for ci in plan['resources']}
    if name == 'network':
        return m.COLUMNS
    if name == 'capacity':
        return m.REQUIRED_COLUMNS
    return m.SCHEMA


def optional_fields(name, ci, fields):
    # Identity, regional context, and relation endpoints remain strict unless an
    # existing family explicitly retains an unknown endpoint with a diagnostic.
    sparse = {
        'vdc_counts': {'vdcName'},
        'tenant': {'tenantId', 'tenantName', 'name', 'ipAddress', 'privateIps', 'floatingIp', 'size', 'status'},
        'ranked_pool': {'vdcId', 'vdcName', 'size', 'attachBackendId', 'poolName',
                        'totalCapacityGB', 'freeCapacityGB', 'allocatedCapacityGB', 'provisionedCapacityGB'},
        'cluster': {'azoneName', 'clusterId', 'hostId', 'status', 'totalVcpuCores',
                    'source_Instance_Id', 'target_Instance_Id'},
        'network': {'vdcName', 'devNativeId', 'portId', 'subnetId', 'routerId'},
        'hierarchy': {'nativeId', 'devNativeId', 'devId', 'portId', 'subnetId', 'resId', 'name', 'cidr'},
        'named_vpc': {'nativeId', 'devNativeId', 'portId', 'subnetId', 'routerId'},
        'capacity': {'vdcName', 'flavorId', 'size', 'vcpuSize'},
    }[name]
    return set(fields) & sparse


def project(name, params, receipts):
    m, plan = core(name), build(name, params)
    if plan['adapter_transport_status'] == 'blocked_core_length':
        raise policy.Unsupported('expanded adapter API+SQL exceeds local 4096 bound')
    if type(receipts) is not dict or set(receipts) != set(plan['receipt_resources']):
        raise policy.Unsupported('all exact bound resource receipts required')
    schema = schemas(name, m, plan)
    result = {}
    calls = plan['api_call']
    for i, ci in enumerate(plan['receipt_resources']):
        source = 'ROUTER' if ci == 'ROUTER_SELECTION' else ci
        fields = list(schema[source])
        nullable = optional_fields(name, source, fields)
        normalize = nullable & {'vdcName', 'vdcId', 'tenantId', 'azoneName', 'clusterId', 'hostId',
                                'source_Instance_Id', 'target_Instance_Id', 'nativeId', 'devNativeId',
                                'devId', 'portId', 'subnetId', 'routerId', 'resId', 'attachBackendId'}
        result[ci] = policy.collect(source, receipts[ci], calls[i], fields,
                                    nullable=nullable, blank_to_null=normalize,
                                    numeric=set(fields) & {'size', 'vcpuSize', 'totalVcpuCores'})
    if name == 'named_vpc':
        f = params['filters']
        catalog = [r for r in result['ROUTER']['rows'] if r['name'] == f['name']
                   and ('logicalRegionName' not in f or r['logicalRegionName'] == f['logicalRegionName'])]
        if sorted(catalog, key=lambda r: r['id']) != sorted(result['ROUTER_SELECTION']['rows'], key=lambda r: r['id']):
            raise policy.Unsupported('named HTTP selection and full parent catalog disagree')
    return m, plan, result


def legacy_inputs(name, m, plan, projections):
    """Translate only checked projections into legacy local-validator protocols."""
    result = {}
    for i, ci in enumerate(plan['resources']):
        p = projections[ci]
        request = plan['api_call'][i]
        pages = policy.projected_pages(p, page_number='currentPage' if name in ('tenant', 'ranked_pool', 'cluster', 'capacity') else 'pageNo',
                                       bound_request=request if name in ('ranked_pool', 'cluster') else None)
        if name in ('tenant', 'network'):
            result[ci] = pages
        elif name == 'vdc_counts':
            result[ci] = {'resource': ci, 'table': m.TABLES[ci], 'request': request,
                          'columns': p['columns'], 'schema_source': 'derived:' + p['canonical_receipt']['raw_receipt_sha256'], 'pages': pages}
        elif name in ('ranked_pool', 'cluster', 'capacity'):
            result[ci] = {'ok': True, 'status': 'ok', 'columns': p['columns'],
                          'schema_source': 'derived:' + p['canonical_receipt']['raw_receipt_sha256'], 'pages': pages}
        else:
            result[ci] = {'ok': True, 'request': request, 'schema': p['columns'],
                          'schema_verified': True, 'pages': pages,
                          'receipt_kind': 'derived_validated_projection_not_HTTP'}
    return result


def capacity_execute(m, params, inputs):
    tables = m.validate_pages(inputs, params)
    conn = sqlite3.connect(':memory:')
    try:
        for ci, rows in tables.items():
            fields = m.REQUIRED_COLUMNS[ci]
            conn.execute('CREATE TABLE CLOUD_' + ci + ' (' + ','.join('"'+k+'" TEXT' for k in fields) + ')')
            conn.executemany('INSERT INTO CLOUD_' + ci + ' VALUES (' + ','.join('?' for _ in fields) + ')',
                             [[r[k] for k in fields] for r in rows])
        cur = conn.execute(m.build(params)['sql'])
        cols = [c[0] for c in cur.description]
        if cols != list(m.OUTPUT_COLUMNS):
            raise AssertionError('capacity output contract drift')
        return {'columns': cols, 'rows': [dict(zip(cols, r)) for r in cur.fetchall()], 'diagnostics': {}}
    finally:
        conn.close()


def prepare_local(name, params, receipts):
    """A-side typed projection for B review. B loader/wire pairing stays pending.

    All derived columns come from the existing family's validator, not from a
    caller-supplied prepared flag. Original raw and canonical receipts both stay.
    """
    m, plan, projections = project(name, params, receipts)
    legacy = legacy_inputs(name, m, plan, projections)
    if name in ('vdc_counts', 'tenant', 'ranked_pool', 'cluster'):
        prepared = m.preflight(params, legacy)
        if prepared.get('status') == 'blocked':
            return prepared
        tables, diagnostics = prepared['tables'], prepared.get('diagnostics', {})
        if name == 'tenant':
            diagnostics = {k: deepcopy(prepared[k]) for k in (
                'unknown_resource_count', 'ranking_population', 'unresolved_mount_count',
                'complete_mount_details', 'unknown_identity_count_by_ci', 'normalized_blank_identity_count_by_ci')}
            diagnostics['scope_max_certified'] = diagnostics['unknown_resource_count'] == 0
        fields = (dict.fromkeys(m.RESOURCES, m.COLUMNS) if name == 'vdc_counts' else
                  {ci: m.SCHEMAS[ci] for ci in plan['resources']} if name == 'tenant' else m.PREPARED)
    elif name == 'capacity':
        tables, diagnostics, fields = m.validate_pages(legacy, params), {}, m.REQUIRED_COLUMNS
    elif name == 'network':
        tables, diagnostics = m.preflight(params, legacy)
        fields = m.COLUMNS
    elif name == 'hierarchy':
        tables, diagnostics = m.prepare(params, legacy)
        fields = m.SCHEMA
    else:
        prepared = m.prepare(params, legacy)
        tables, diagnostics, fields = prepared['tables'], prepared['diagnostics'], m.SCHEMA
    typed = {}
    for ci in plan['resources']:
        table = ci if ci.startswith(('R_', 'M_')) else 'CLOUD_' + ci
        rows = tables[table] if table in tables else tables[ci]
        columns = list(fields[ci])
        types = {k: 'TEXT' for k in columns}
        if name == 'ranked_pool' and ci == 'VOLUME':
            types['size_scaled'] = 'INTEGER'
        if name == 'cluster':
            for k in set(columns) & {'rank_eligible', 'is_running', 'status_known', 'host_graph_complete', 'vcpu_known'}:
                types[k] = 'INTEGER'
            if 'totalVcpuCores' in columns:
                types['totalVcpuCores'] = 'BLOB'
        typed[table] = {'columns': columns, 'types': types, 'rows': deepcopy(rows)}
    evidence = {'family': name, 'params': deepcopy(params), 'receipts': deepcopy(receipts)}
    diagnostics = deepcopy(diagnostics)
    diagnostics['full_answer'] = False
    diagnostics['business_policy_accepted'] = False
    return {'status': 'ready_for_typed_sql', 'plan': plan, 'typed_tables': typed,
            'diagnostics': diagnostics, 'raw_receipts': deepcopy(receipts),
            'canonical_receipts': {ci: p['canonical_receipt'] for ci, p in projections.items()},
            'input_evidence': evidence, 'input_evidence_sha256': policy.digest(evidence),
            'typed_projection_sha256': policy.digest(typed), 'default_enabled': False,
            'B_loader_pairing': 'pending', 'final_B_envelope_verified': False}


def recheck_prepared(prepared):
    """Return a freshly recomputed projection; a digest/ready flag alone is insufficient."""
    if type(prepared) is not dict or prepared.get('status') != 'ready_for_typed_sql':
        raise policy.Unsupported('validated preparation required')
    e = prepared.get('input_evidence')
    if type(e) is not dict or set(e) != {'family', 'params', 'receipts'} or policy.digest(e) != prepared.get('input_evidence_sha256'):
        raise policy.Unsupported('actual raw input evidence changed')
    fresh = prepare_local(e['family'], e['params'], e['receipts'])
    if fresh != prepared:
        raise policy.Unsupported('prepared plan/projection/diagnostics changed')
    return fresh


def execute_local(name, params, receipts):
    """Offline opt-in execution; every invocation rechecks its actual raw receipts."""
    m, plan, projections = project(name, params, receipts)
    inputs = legacy_inputs(name, m, plan, projections)
    if name == 'capacity':
        result = capacity_execute(m, params, inputs)
    elif name in ('tenant', 'ranked_pool'):
        result = m.execute(params, inputs)
    else:
        result = m.execute_local(params, inputs)
    if result.get('status') == 'blocked':
        return result
    result = deepcopy(result)
    d = result.setdefault('diagnostics', {})
    d['receipt_populations'] = {ci: deepcopy(p['canonical_receipt']) for ci, p in projections.items()}
    d['raw_receipt_set_sha256'] = policy.digest(receipts)
    d['unknown_vdc_rows_by_ci'] = {ci: sum(r.get('vdcName') is None for r in p['rows'])
                                    for ci, p in projections.items() if 'vdcName' in p['columns']}
    if name in ('tenant', 'ranked_pool', 'cluster'):
        if name == 'tenant':
            rank_complete = d['unknown_resource_count'] == 0
            detail_complete = d['complete_mount_details']
            selected = {r.get('vm_id') for r in result['rows'] if r.get('vm_id') is not None}
            d['selected_unknown_private_ip_vm_count'] = sum(r['id'] in selected and policy.blank(r['privateIps'])
                                                           for r in projections.get('VM_NOVA', {}).get('rows', []))
            detail_complete = detail_complete and d['selected_unknown_private_ip_vm_count'] == 0
        elif name == 'ranked_pool':
            rank_complete = bool(d['scope_max_certified'])
            detail_complete = bool(d['pool_link_complete'] and d['attribute_values_complete'])
            sizes = [m.scaled_size(r['size']) for r in projections['VOLUME']['rows'] if r['vdcId'] is None]
            scaled = sum(v for v in sizes if v is not None)
            whole, frac = divmod(scaled, m.SCALE)
            d['unknown_owner_known_size_source_units'] = str(whole) + ('.' + str(frac).zfill(6).rstrip('0') if frac else '')
            d['unknown_owner_unknown_size_volume_count'] = sum(v is None for v in sizes)
        else:
            rank_complete = bool(d['scope_max_certified'])
            winners = {r['cluster_id'] for r in result['rows']}
            detail_complete = all(d['selected_cluster_details'][cid]['running_vm_list_complete']
                                  and d['selected_cluster_details'][cid]['host_graph_complete'] for cid in winners)
            detail_complete = detail_complete and all(r['complete_cluster_host_vcpu'] is not None for r in result['rows'])
        d['ranking_complete'] = rank_complete
        d['scope_max_certified'] = rank_complete
        d['answer_role'] = 'known_lower_bound_leaders' if not rank_complete else 'local_snapshot_leaders'
        d['details_complete_under_local_policy'] = detail_complete
    if name == 'network':
        d['answer_role'] = 'known_scoped_parents_with_unknown_catalog_diagnostic'
    if name in ('vdc_counts', 'capacity'):
        d['answer_role'] = 'exact_observed_name_buckets_with_NULL_unknown_bucket'
        d['named_vdc_identity_complete'] = not any(d['unknown_vdc_rows_by_ci'].values())
    # Local calculation success never certifies full business authority or runtime adoption.
    d['full_answer'] = False
    d['business_policy_accepted'] = False
    d['raw_and_projection_receipts_distinct'] = True
    result['receipt_evidence'] = {ci: {'raw': p['raw_receipt'], 'canonical': p['canonical_receipt']}
                                  for ci, p in projections.items()}
    result['default_enabled'] = False
    result['runtime_adopted'] = False
    return result
