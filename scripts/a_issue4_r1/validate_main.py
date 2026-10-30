"""Replay synthetic contract checks only. No model, HTTP, dataset or evaluator."""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'main'))
from copy import deepcopy
import argparse
import json
from pathlib import Path
import traceback

import adapters
import az_counts
import server_rows
import shared_policy as policy

CHECKS = []


def check(name, actual, expected=True):
    CHECKS.append({'name': name, 'passed': actual == expected})
    if actual != expected:
        raise AssertionError(name + ': ' + repr(actual) + ' != ' + repr(expected))


def rejects(name, call):
    try:
        call()
    except ValueError:
        check(name, True)
    else:
        check(name, False)


def receipt(call, schema, rows):
    pages = []
    total = len(rows)
    size = int(call['url'].split('pageSize=')[1].split('&')[0])
    count = max(1, (total + size - 1) // size)
    for i in range(1, count + 1):
        pages.append({'ok': True, 'http_status': 200, 'pageNo': i, 'currentPage': i,
                      'pageSize': size, 'totalNum': total, 'totalPageNo': count if total else 0,
                      'request': policy.page_request(call, i), 'objList': deepcopy(rows[(i-1)*size:i*size])})
    return {'ok': True, 'http_status': 200, 'request': deepcopy(call),
            'schema_verified': True, 'schema_source': 'synthetic-declared-schema', 'schema': list(schema), 'pages': pages}


def inputs(name, params, rows):
    plan = adapters.build(name, params)
    schema = adapters.schemas(name, adapters.core(name), plan)
    return {ci: receipt(call, schema['ROUTER' if ci == 'ROUTER_SELECTION' else ci], rows.get(ci, []))
            for ci, call in zip(plan['receipt_resources'], plan['api_call'])}


VDC = {'profile': 'vdc_vm_volume_gaussdb_instance_counts', 'resource_set': ['VM_NOVA', 'VOLUME', 'GAUSSDB_INSTANCE'],
       'group': 'vdcName', 'layout': 'grouped_counts_wide', 'metric': 'count_rows',
       'filters': {'logicalRegionName': 'region-test'}, 'required_filters': ['logicalRegionName']}
TENANT = {'logicalRegionName': 'region-test', 'metric': 'vm_count', 'tie_policy': 'all_ties',
          'unknown_tenant_policy': 'exclude_with_diagnostic'}
POOL = {'logicalRegionName': 'region-test', 'tie_policy': 'all_ties', 'unknown_owner_policy': 'known_only',
        'unknown_size_policy': 'known_only'}
CLUSTER = {'profile': 'cluster_max_vm_host_running_details', 'filters': {'azoneName': 'zone-test'},
           'tie_policy': 'all_ties', 'unknown_rank_policy': 'known_only_with_diagnostic',
           'details_population': 'all_hosts_all_active_VMs'}
NETWORK = {'logicalRegionName': 'region-test', 'vdcName': 'vdc-test'}
NAMED = {'profile': 'named_vpc_subnet_eip_counts', 'filters': {'name': 'named-test', 'logicalRegionName': 'region-test'},
         'required_filters': ['name', 'logicalRegionName'], 'same_name_policy': 'all_matching_parent_ids'}


def row(identity, **kw):
    return {'id': identity, 'logicalRegionName': 'region-test', **kw}


def run():
    # Raw page population remains 1001 while PORT canonical population is 1000.
    call = {'method': 'GET', 'url': '/rest/hackthon/db/instances/PORT?pageNo=1&pageSize=1000', 'autoPagination': True}
    rs = [row('port-'+str(i), devId='vm-'+str(i), devNativeId=None) for i in range(1000)]
    rs.append({**rs[0], 'last_Modified': 'different'})
    raw = receipt(call, ('id', 'logicalRegionName', 'devId', 'devNativeId'), rs)
    before = deepcopy(raw)
    p = policy.collect('PORT', raw, call, ('id', 'logicalRegionName', 'devId', 'devNativeId'))
    check('PORT raw full pages kept', p['raw_receipt'] == before and raw == before)
    check('PORT dual population', (p['canonical_receipt']['raw_total_num'], len(p['rows']), p['canonical_receipt']['duplicate_observation_count']), (1001, 1000, 1))
    check('PORT duplicate across page boundary permitted only after raw completeness', len(raw['pages']), 2)
    derived = policy.projected_pages(p)
    check('derived count separately named', derived[0]['totalNum'] == 1000 and 'not_HTTP' in derived[0]['receipt_kind'])
    for label, mutate in [
        ('business endpoint conflict', lambda r: r['pages'][1]['objList'][0].update(devId='conflict')),
        ('nonprojected business conflict', lambda r: r['pages'][1]['objList'][0].update(futureBusinessField='conflict')),
        ('truncated raw page', lambda r: r['pages'][1]['objList'].clear()),
        ('changing total', lambda r: r['pages'][1].update(totalNum=1002)),
        ('HTTP failure', lambda r: r['pages'][1].update(statusCode=503)),
        ('contradictory success', lambda r: r.update(success=1)),
        ('missing actual schema', lambda r: r['schema'].remove('devId')),
        ('page request drift', lambda r: r['pages'][1]['request'].update(url=call['url'])),
        ('missing identity', lambda r: r['pages'][0]['objList'][0].pop('id')),
        ('unbound receipt', lambda r: r.pop('request')),
    ]:
        bad = deepcopy(raw); mutate(bad)
        rejects(label, lambda bad=bad: policy.collect('PORT', bad, call, ('id', 'logicalRegionName', 'devId', 'devNativeId')))
    rejects('other CI duplicate even if identical', lambda: policy.collect('ROUTER', raw, call, ('id', 'logicalRegionName', 'devId', 'devNativeId')))
    rejects('requested audit field cannot be ignored', lambda: policy.collect('PORT', raw, call, ('id', 'logicalRegionName', 'devId', 'devNativeId', 'last_Modified'), nullable={'last_Modified'}))

    data = {'VM_NOVA': [row('e1', vdcName='A'), row('e2'), row('e3', vdcName=' ')],
            'VOLUME': [row('v1', vdcName='B'), row('v2')],
            'GAUSSDB_INSTANCE': [row('g1', vdcName='C')]}
    raw = inputs('vdc_counts', VDC, data); before = deepcopy(raw)
    out = adapters.execute_local('vdc_counts', VDC, raw)
    by = {r['vdc_name']: r for r in out['rows']}
    check('independent full name-domain union', set(by), {None, 'A', 'B', 'C'})
    check('unknown bucket preserves population', by[None], {'vdc_name': None, 'ecs_count': 2, 'volume_count': 1, 'gaussdb_instance_count': 0})
    check('no input mutation sparse projection', raw, before)
    check('sparse grouping not complete owner answer', out['diagnostics']['full_answer'], False)
    check('Gauss instance never nodes', sum(r['gaussdb_instance_count'] for r in out['rows']), 1)
    for label, mutate in [('missing region strict', lambda r: r['VM_NOVA']['pages'][0]['objList'][0].pop('logicalRegionName')),
                          ('unknown schema not nullable proof', lambda r: r['VOLUME']['schema'].remove('vdcName')),
                          ('wrong explicit region', lambda r: r['VM_NOVA']['pages'][0]['objList'][0].update(logicalRegionName='wrong'))]:
        bad = deepcopy(raw); mutate(bad)
        rejects(label, lambda bad=bad: adapters.execute_local('vdc_counts', VDC, bad))
    check('verified all empty union gives no fabricated row', adapters.execute_local('vdc_counts', VDC, inputs('vdc_counts', VDC, {}))['rows'], [])

    vm = [row('e'+str(i), tenantId='A' if i < 3 else 'B', tenantName='display', name='vm',
              privateIps='encoded-[10.0.0.1,10.0.0.2]', ipAddress=None, floatingIp=None) for i in range(1, 5)]
    vm[0].pop('privateIps'); vm.append(row('e5', name='unknown'))
    volume = [row('v1', tenantId='A', tenantName='display', name='vol', size='10', status='in-use')]
    mount = [{'id': 'm1', 'vmId': 'e1', 'volumeId': 'v1'}, {'id': 'm2', 'vmId': 'e2', 'volumeId': 'v1'}]
    raw = inputs('tenant', TENANT, {'VM_NOVA': vm, 'VOLUME': volume, 'R_VOLUME_MOUNTON_VM': mount})
    out = adapters.execute_local('tenant', TENANT, raw)
    check('all tenant ties retained', {r['tenant_id'] for r in out['rows']}, {'A', 'B'})
    check('tenant unknown not real identity', out['diagnostics']['unknown_resource_count'], 1)
    check('unknown rank cannot certify global maximum', out['diagnostics']['scope_max_certified'], False)
    check('known lower-bound leader role', out['diagnostics']['answer_role'], 'known_lower_bound_leaders')
    check('raw multi-value IP encoding preserved', {r['private_ips'] for r in out['rows'] if r['private_ips']}, {'encoded-[10.0.0.1,10.0.0.2]'})
    check('missing IP diagnosed', out['diagnostics']['selected_unknown_private_ip_vm_count'], 1)
    reject_params = {**TENANT, 'unknown_tenant_policy': 'reject'}
    check('explicit reject policy remains compatible', adapters.execute_local('tenant', reject_params, inputs('tenant', reject_params, {'VM_NOVA': vm, 'VOLUME': volume, 'R_VOLUME_MOUNTON_VM': mount}))['status'], 'blocked')

    data = {'VOLUME': [row('v1', vdcId='A', vdcName='a', size='5', attachBackendId='p1'),
                       row('v2', vdcId='B', vdcName='b', size='5', attachBackendId='p1'),
                       row('v3', size='100', attachBackendId=None)],
            'STORAGE_POOL': [row('p1', poolName='pool', totalCapacityGB='100', freeCapacityGB='50', allocatedCapacityGB='50', provisionedCapacityGB='80')]}
    out = adapters.execute_local('ranked_pool', POOL, inputs('ranked_pool', POOL, data))
    check('pool all known capacity ties', {r['vdc_id'] for r in out['rows']}, {'A', 'B'})
    check('unknown capacity owner propagates to ranking', out['diagnostics']['scope_max_certified'], False)
    check('unknown owner capacity cannot become complete total', all(r['total_volume_size_if_complete_source_units'] is None for r in out['rows']))
    check('pool source units unconverted', {r['known_volume_size_source_units'] for r in out['rows']}, {'5'})
    check('unknown owner known capacity retained separately', out['diagnostics']['unknown_owner_known_size_source_units'], '100')
    data['VOLUME'][0].pop('size')
    out = adapters.execute_local('ranked_pool', POOL, inputs('ranked_pool', POOL, data))
    check('unknown size propagated', out['diagnostics']['unknown_size_volume_count'], 1)

    vms = [row('e'+str(i), name='vm', azoneName='zone-test', clusterId='c1' if i < 3 else 'c2', hostId='h1' if i < 3 else 'h2', status='active') for i in range(1, 5)]
    vms += [row('e5', name='vm', azoneName='zone-test', hostId='h1', status='active')]
    data = {'VM_NOVA': vms, 'CLUSTER': [row('c1', name='one'), row('c2', name='two')],
            'M_ClusterContainsPhyHost': [{'id': 'r1', 'source_Instance_Id': 'c1', 'target_Instance_Id': 'h1'}, {'id': 'r2', 'source_Instance_Id': 'c2', 'target_Instance_Id': 'h2'}],
            'HOST': [row('h1', name='host', totalVcpuCores=16), row('h2', name='host', totalVcpuCores=16)]}
    out = adapters.execute_local('cluster', CLUSTER, inputs('cluster', CLUSTER, data))
    check('cluster all rank ties', {r['cluster_id'] for r in out['rows']}, {'c1', 'c2'})
    check('host CPU independently summed once', {r['known_cluster_host_vcpu'] for r in out['rows']}, {16})
    check('unknown cluster rank remains partial', out['diagnostics']['scope_max_certified'], False)
    check('rank AZ filters not applied to global detail fetch', all('condition' not in c for c in adapters.build('cluster', CLUSTER)['api_call']))
    text_cpu = deepcopy(data); text_cpu['HOST'][0]['totalVcpuCores'] = '16'
    text_out = adapters.execute_local('cluster', CLUSTER, inputs('cluster', CLUSTER, text_cpu))
    check('text CPU remains unknown under native typed contract', all(r['complete_cluster_host_vcpu'] is None for r in text_out['rows'] if r['cluster_id'] == 'c1'))

    data = {'ROUTER': [row('r1', name='named-test', nativeId='nr1', vdcName='vdc-test'), row('r2', name='other', nativeId='nr2', vdcName=None)],
            'PORT': [row('p1', devNativeId='nr1', devId=None), row('p1', devNativeId='nr1', devId=None, last_update_date='later')],
            'R_PORT_IN_SUBNET': [{'id': 'l1', 'portId': 'p1', 'subnetId': 's1'}],
            'SUBNET': [row('s1', name='subnet', cidr='10/24')],
            'FLOATING_IPS': [row('f1', routerId='r1')]}
    out = adapters.execute_local('network', NETWORK, inputs('network', NETWORK, data))
    check('known VDC parent rows retained with unknown catalog', [r['vpc_id'] for r in out['rows']], ['r1'])
    check('unknown VDC parent diagnosed', out['diagnostics']['unknown_vdc_parent_rows'], 1)
    check('unknown parent never full-scope answer', out['diagnostics']['business_complete'], False)
    check('PORT no double child count', out['rows'][0]['resolved_subnet_count'], 1)
    check('raw duplicate population retained in adapter', out['receipt_evidence']['PORT']['canonical']['raw_total_num'], 2)

    data['ROUTER_SELECTION'] = [data['ROUTER'][0]]
    raw = inputs('named_vpc', NAMED, data)
    out = adapters.execute_local('named_vpc', NAMED, raw)
    check('named API actual name predicate', policy.equal_filters(adapters.build('named_vpc', NAMED)['api_call'][-1])['name'], 'named-test')
    check('named full catalog and selection both kept', set(out['receipt_evidence']), set(adapters.core('named_vpc').RESOURCES) | {'ROUTER_SELECTION'})
    check('named independent counts', (out['rows'][0]['resolved_subnet_count'], out['rows'][0]['known_eip_count']), (1, 1))
    bad = deepcopy(raw); bad['ROUTER_SELECTION'] = receipt(adapters.build('named_vpc', NAMED)['api_call'][-1], raw['ROUTER_SELECTION']['schema'], [])
    rejects('named selection/catalog drift blocks', lambda: adapters.execute_local('named_vpc', NAMED, bad))

    hdata = {k: v for k, v in data.items() if k in adapters.core('hierarchy').RESOURCES}
    hdata['VM_NOVA'] = []
    hp = {'view': 'parent_counts'}
    out = adapters.execute_local('hierarchy', hp, inputs('hierarchy', hp, hdata))
    check('hierarchy complete parent domain includes empty parent', {r['vpc_id'] for r in out['rows']}, {'r1', 'r2'})
    check('hierarchy PORT duplicate accepted consistently', out['receipt_evidence']['PORT']['canonical']['canonical_object_count'], 1)
    hp = {'view': 'hierarchy_rows'}
    out = adapters.execute_local('hierarchy', hp, inputs('hierarchy', hp, hdata))
    check('full hierarchy rows preserve empty parent', {r['vpc_id'] for r in out['rows']}, {'r1', 'r2'})

    cp = {'logicalRegionName': 'region-test'}
    data = {'VM_NOVA': [row('e1', vdcName='A', flavorId='f'), row('e2', vdcName='A', flavorId='f'), row('e3', flavorId='missing')],
            'FLAVOR': [row('f', vcpuSize='4')], 'VOLUME': [row('v1', vdcName='B', size='2.5'), row('v2', size='bad')],
            'GAUSSDB_NODE': [row('g1', vdcName='C')]}
    out = adapters.execute_local('capacity', cp, inputs('capacity', cp, data))
    by = {r['vdc_name']: r for r in out['rows']}
    check('capacity branch union', set(by), {None, 'A', 'B', 'C'})
    check('vCPU per VM, flavor dimension unique', by['A']['known_vcpu'], 8)
    check('unknown CPU never coerced zero total', by[None]['total_vcpu_if_complete'], None)
    check('unknown size never coerced zero total', by[None]['total_volume_size_if_complete'], None)
    check('Gauss nodes independent of instances', by['C']['gaussdb_node_count'], 1)

    sp = {'logicalRegionName': 'region-test'}
    call = server_rows.build(sp)['api_call'][0]
    sr = receipt(call, server_rows.COLUMNS, [row('s1', cpuArch='x86', name='resource-display', ipAddress='bmc-value', hostType='compute')])
    out = server_rows.execute_local(sp, sr)
    check('server resource/BMC/host roles distinct', (out['rows'][0]['server_name'], out['rows'][0]['bmc_ip_address'], out['rows'][0]['host_ip_address']), ('resource-display', 'bmc-value', None))
    check('server missing host IP explicit', out['diagnostics']['unknown_values']['hostIpAddress'], 1)
    bad = deepcopy(sr); bad['pages'][0]['objList'][0]['cpuArch'] = 'arm'
    rejects('CI class name never substitutes x86 architecture', lambda: server_rows.execute_local(sp, bad))
    check('server proven empty no placeholder', server_rows.execute_local(sp, receipt(call, server_rows.COLUMNS, []))['rows'], [])

    plan = az_counts.build(sp)
    data = {'VM_NOVA': [row('e1', azoneName='A'), row('e2')], 'VOLUME': [row('v1', azoneName='B')],
            'ROUTER': [row('r1')], 'AZONE': [row('a1', name='A'), row('a2', name='B'), row('a3', name='C')]}
    raw = {ci: receipt(call, az_counts.SCHEMA[ci], data[ci]) for ci, call in zip(plan['resources'], plan['api_call'])}
    out = az_counts.execute_local(sp, raw); by = {r['azone_name']: r for r in out['rows']}
    check('AZ full catalog plus observed plus unknown domain', set(by), {None, 'A', 'B', 'C'})
    check('VPC stays unknown AZ population', by[None]['known_vpc_count'], 1)
    check('VPC count not fabricated known zero', by['A']['vpc_count_if_complete'], None)
    check('ROUTER source schema has no invented AZ', 'azoneName' in plan['required_schema']['ROUTER'], False)
    check('AZ population conservation', (sum(r['known_ecs_count'] for r in out['rows']), sum(r['known_volume_count'] for r in out['rows']), sum(r['known_vpc_count'] for r in out['rows'])), (2, 1, 1))
    check('missing VM AZ prevents complete count', by['A']['ecs_count_if_complete'], None)
    check('known volume AZ count exact under local policy', by['B']['volume_count_if_complete'], 1)
    check('empty catalog AZ retained as zero bucket', by['C']['known_volume_count'], 0)
    check('partial AZ operation never full answer', out['diagnostics']['full_answer'], False)
    rejects('no default region', lambda: az_counts.build({}))
    rejects('long region not truncated', lambda: az_counts.build({'logicalRegionName': '界' * 3000}))

    # Compatible existing IDs and parameter validators; no runtime registry writes.
    for name, params in [('vdc_counts', VDC), ('tenant', TENANT), ('ranked_pool', POOL),
                         ('cluster', CLUSTER), ('network', NETWORK), ('hierarchy', {'view': 'hierarchy_rows'}),
                         ('named_vpc', NAMED), ('capacity', cp)]:
        m = adapters.core(name)
        original = m.prepare(params) if name == 'vdc_counts' else m.build(params)
        adapted = adapters.build(name, params)
        check(name + ' ID and output compatibility',
              (adapted.get('id'), adapted.get('family_id'), adapted['output_columns']),
              (original.get('id'), original.get('family_id'), original['output_columns']))
        check(name + ' original SQL and existing calls preserved',
              (adapted['sql'], adapted['api_call'][:len(original['api_call'])]),
              (original['sql'], original['api_call']))
        prepared = adapters.prepare_local(name, params, inputs(name, params, {}))
        check(name + ' typed empty tables retained', len(prepared['typed_tables']), len(original['resources']))
        check(name + ' typed preparation rechecks actual evidence', adapters.recheck_prepared(prepared) == prepared)
    typed_raw = inputs('cluster', CLUSTER, {'HOST': [row('h1', name='host', totalVcpuCores=16)]})
    prepared = adapters.prepare_local('cluster', CLUSTER, typed_raw)
    check('typed native CPU stays integer inside BLOB column',
          (prepared['typed_tables']['CLOUD_HOST']['types']['totalVcpuCores'], type(prepared['typed_tables']['CLOUD_HOST']['rows'][0]['totalVcpuCores']).__name__), ('BLOB', 'int'))
    changed = deepcopy(prepared); changed['typed_tables']['CLOUD_HOST']['rows'][0]['vcpu_known'] = 999
    changed['typed_projection_sha256'] = policy.digest(changed['typed_tables'])
    rejects('rehashed caller derived field tamper rejected', lambda: adapters.recheck_prepared(changed))
    all_unknown = {'VM_NOVA': [row('unknown', name='unknown')], 'VOLUME': [], 'R_VOLUME_MOUNTON_VM': []}
    prepared_unknown = adapters.prepare_local('tenant', TENANT, inputs('tenant', TENANT, all_unknown))
    check('typed preparation preserves unknown rank diagnostic',
          (prepared_unknown['diagnostics']['unknown_resource_count'], prepared_unknown['diagnostics']['scope_max_certified']), (1, False))
    out = adapters.execute_local('tenant', TENANT, inputs('tenant', TENANT, all_unknown))
    check('all unknown tenant has no fake winner', out['rows'], [])
    check('all unknown tenant remains unresolved', (out['diagnostics']['unknown_resource_count'], out['diagnostics']['scope_max_certified']), (1, False))
    for label, mutation in [('transport error no COUNT0', lambda r: r['VOLUME'].update(ok=False)),
                            ('placeholder row no COUNT1', lambda r: r['VOLUME']['pages'][0]['objList'][0].clear()),
                            ('nontext owner cannot become unknown', lambda r: r['VM_NOVA']['pages'][0]['objList'][0].update(vdcName=True))]:
        raw = inputs('vdc_counts', VDC, {'VM_NOVA': [row('e1', vdcName='A')], 'VOLUME': [row('v1', vdcName='A')], 'GAUSSDB_INSTANCE': []})
        mutation(raw)
        rejects(label, lambda raw=raw: adapters.execute_local('vdc_counts', VDC, raw))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    error = None
    try:
        run()
    except Exception:
        error = traceback.format_exc()
    report = {'status': 'PASS' if error is None and all(c['passed'] for c in CHECKS) else 'FAIL',
              'checks': len(CHECKS), 'passed': sum(c['passed'] for c in CHECKS), 'details': CHECKS,
              'error': error, 'synthetic_only': True, 'model_calls': 0, 'business_API_calls': 0,
              'old200_or_sealed50_read': False, 'native_business_SQL_runs': 0, 'default_enabled': False}
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'details'}, ensure_ascii=False))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
