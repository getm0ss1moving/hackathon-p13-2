"""Owner synthetic tests; real pinned provider only, no provider mocks/receipts.

All fixtures explicitly synthetic. Network and subprocess access blocked in this
process. Expected rows/counts are authored, not inferred from a membership join.
"""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'consumer'))
import ast
from copy import deepcopy
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
import urllib.request

ROOT = PACKAGE / 'consumer'
ATTEMPTS = []
def no_network(*args, **kwargs):
    ATTEMPTS.append('forbidden_io')
    raise AssertionError('network/subprocess not permitted in offline tests')
socket.socket = no_network
socket.create_connection = no_network
http.client.HTTPConnection.connect = no_network
http.client.HTTPSConnection.connect = no_network
urllib.request.urlopen = no_network
subprocess.Popen = no_network
subprocess.run = no_network
spec = importlib.util.spec_from_file_location('tenant_consumer_under_test', ROOT / 'consumer.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
BASE = json.loads((ROOT / 'evidence/port-interface-counterexample.json').read_text())
CAPTURE = {'capture_id': 'consumer-synthetic-capture', 'source_ref': 'review-counterexample-synthetic',
           'schema_ref': 'review-synthetic-schema', 'origin': 'synthetic', 'isolation': 'immutable_snapshot'}


def params(view='known_port_eip_host_rows', region=True):
    p = {'view': view, 'tenantName': 'tenant'}
    if region:
        p['logicalRegionName'] = 'review-region'
    return p


def receipt(ci, request, rows, rid, schema):
    batches = [rows[n:n + 1000] for n in range(0, len(rows), 1000)] or [[]]
    return {'ok': True, 'http_status': 200, 'capture_id': CAPTURE['capture_id'], 'receipt_id': rid,
            'receipt_kind': 'raw_http', 'request': deepcopy(request), 'schema_verified': True,
            'schema_source': 'synthetic-independent-schema', 'schema': list(schema),
            'pages': [{'ok': True, 'http_status': 200, 'pageNo': n, 'pageSize': 1000,
                       'totalNum': len(rows), 'totalPageNo': (len(rows) + 999) // 1000,
                       'request': c.page_request(request, n), 'receipt_kind': 'raw_http',
                       'objList': deepcopy(batch)} for n, batch in enumerate(batches, 1)]}


def fixture(p=None):
    p = params() if p is None else p
    legacy = c.legacy(); plan = legacy.build(p); schemas = legacy.schema_for(p['view'])
    raw = {}
    for ci, request in zip(schemas, plan['api_call']):
        original = BASE['minimal_raw_receipts'][ci]
        rows = [deepcopy(row) for page in original['pages'] for row in page['objList']]
        raw[ci] = receipt(ci, request, rows, 'raw-' + ci, schemas[ci])
    return {'capture': deepcopy(CAPTURE), 'raw_receipts': raw,
            'question_text': '查询租户tenant的ECS私有IP列表、关联弹性IP列表和所属宿主机列表'}


def rows(data, ci):
    envelope = data['raw_receipts'][ci]
    if type(envelope) is list:
        envelope = envelope[0]
    return [row for page in envelope['pages'] for row in page['objList']]


def replace_rows(data, ci, values):
    env = data['raw_receipts'][ci]
    data['raw_receipts'][ci] = receipt(ci, env['request'], values, env['receipt_id'], env['schema'])


def add_scoped(p, data):
    context = data['raw_receipts']['PORT']
    requests = c.plan_tenant_port_batches(p, rows(data, 'VM_NOVA'))
    batches = [context]
    for n, request in enumerate(requests):
        cond = request['condition']['constraint']
        region, keys = cond[0]['simple']['value'], cond[1]['simple']['value']
        selected = [r for r in rows(data, 'PORT') if r['logicalRegionName'] == region and r.get('devId') in keys]
        batches.append(receipt('PORT', request, selected, 'scoped-' + str(n), context['schema']))
    data['raw_receipts']['PORT'] = batches
    return data


class ConsumerTests(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(ATTEMPTS, [])

    def run_view(self, data=None, p=None):
        p = params() if p is None else p
        data = fixture(p) if data is None else data
        prepared = c.prepare_tenant_view(p, data)
        self.assertEqual(c.encoded(prepared), c.encoded(c.recheck_tenant_prepared(prepared)))
        return prepared, c.execute_tenant_prepared(prepared)

    def blocked(self, data, code, p=None):
        out = c.evaluate_tenant_view(params() if p is None else p, data)
        self.assertFalse(out['ok']); self.assertIsNone(out['rows'])
        self.assertEqual(out['error']['code'], code)
        self.assertFalse(out['full_original_question_certified'])

    def test_sources_compile_and_legacy_views_params_sql_columns_unchanged(self):
        for path in [ROOT / 'consumer.py', ROOT / 'legacy_vm_eip_host.py', ROOT / 'address_codec_r1.py', Path(__file__)]:
            compile(ast.parse(path.read_text(), filename=str(path)), str(path), 'exec')
        for view in ('native_ip_host_rows', 'known_port_eip_host_rows'):
            for region in (False, True):
                p = params(view, region)
                old, new = c.legacy().build(p), c.build_tenant_view(p)
                for key in ('family_id', 'view', 'resources', 'api_call', 'sql', 'output_columns'):
                    self.assertEqual(old[key], new[key])
        self.assertEqual(hashlib.sha256((ROOT / 'legacy_vm_eip_host.py').read_bytes()).hexdigest(), BASE['legacy_source_sha256'])

    def test_review_minimal_raw2_to1_actual_provider_and_exact_known_row(self):
        data = fixture(); original = deepcopy(data)
        prep, out = self.run_view(data)
        self.assertEqual(data, original)
        self.assertEqual(len(prep['typed_tables']['CLOUD_PORT']['rows']), 1)
        self.assertEqual(len(rows(data, 'PORT')), 2)
        self.assertEqual(out['rows'], BASE['observed']['review_only_manual_derived_wrapper']['rows'])
        self.assertFalse(out['diagnostics']['actual_tenant_selection_receipt_proven'])
        self.assertFalse(out['diagnostics']['full_eip_objects_binding_complete'])
        self.assertFalse(out['full_original_question_certified'])
        self.assertEqual(prep['input_evidence']['evidence']['question_text'], original['question_text'])

    def test_sparse_private_ip_is_preserved_unknown_not_old_row_schema_failure(self):
        data = fixture(); rows(data, 'VM_NOVA')[0].pop('privateIps')
        prep, out = self.run_view(data)
        self.assertNotIn('privateIps', rows(prep['input_evidence']['evidence'], 'VM_NOVA')[0])
        self.assertIsNone(out['rows'][0]['private_ips_raw'])
        self.assertEqual(out['diagnostics']['private_ip_states'][0]['status'], 'unknown_missing')
        self.assertEqual(out['diagnostics']['selected_unknown_private_ip_vm_count'], 1)
        self.assertEqual(prep['canonical_receipts']['VM_NOVA']['missing_nullable_observations']['privateIps'], 1)

    def test_null_empty_whitespace_malformed_ip_states_stay_distinct(self):
        for value, status in [(None, 'unknown_null'), ('', 'unknown_empty'), ('  ', 'unknown_whitespace'), ('@token@@', 'unsupported_or_malformed_codec')]:
            with self.subTest(value=value):
                data = fixture(); rows(data, 'VM_NOVA')[0]['privateIps'] = value
                _, out = self.run_view(data)
                self.assertEqual(out['rows'][0]['private_ips_raw'], value)
                self.assertEqual(out['diagnostics']['private_ip_states'][0]['status'], status)
                self.assertEqual(out['diagnostics']['selected_unknown_private_ip_vm_count'], 1)

    def test_raw_codec_never_drives_eip_binding(self):
        data = fixture(); rows(data, 'VM_NOVA')[0]['privateIps'] = '@unrelated@FE80::AB@unrelated@'
        _, out = self.run_view(data)
        self.assertEqual(out['rows'][0]['private_ips_raw'], '@unrelated@FE80::AB@unrelated@')
        self.assertEqual(out['rows'][0]['eip_id'], 'eip')
        self.assertEqual(out['rows'][0]['eip_link_status'], 'known_port_link_only')
        self.assertFalse(out['diagnostics']['full_eip_objects_binding_complete'])

    def test_eip_bool_and_raw_string_roles_are_not_forced_through_text_port_policy(self):
        for value, expected in [(False, 'false'), (True, 'true'), ('False', 'False'), ('external-unseen', 'external-unseen'), (None, None)]:
            with self.subTest(value=value):
                data = fixture(); rows(data, 'FLOATING_IPS')[0]['isInternal'] = value
                _, out = self.run_view(data)
                self.assertEqual(out['rows'][0]['eip_internal_role_raw'], expected)
                self.assertEqual(rows(data, 'FLOATING_IPS')[0]['isInternal'], value)

    def test_two_eips_keep_roles_and_identity_without_fanout_diagnostic_inflation(self):
        data = fixture(); second = deepcopy(rows(data, 'FLOATING_IPS')[0]); second.update(id='eip2', isInternal=True)
        replace_rows(data, 'FLOATING_IPS', rows(data, 'FLOATING_IPS') + [second])
        _, out = self.run_view(data)
        self.assertEqual([(r['eip_id'], r['eip_internal_role_raw']) for r in out['rows']], [('eip', 'false'), ('eip2', 'true')])
        self.assertEqual(out['diagnostics']['selected_vm_count'], 1)
        self.assertEqual(out['diagnostics']['requested_display_unknown_counts']['native_floating_ip_raw'], 1)

    def test_missing_blank_and_dangling_host_references_retain_vm(self):
        for mode in ('missing', 'null', 'empty', 'dangling'):
            data = fixture(); vm = rows(data, 'VM_NOVA')[0]
            if mode == 'missing': vm.pop('hostId')
            else: vm['hostId'] = {'null': None, 'empty': '', 'dangling': 'not-a-host'}[mode]
            _, out = self.run_view(data)
            self.assertEqual(out['rows'][0]['vm_id'], 'vm')
            self.assertIsNone(out['rows'][0]['host_id'])
            self.assertEqual(out['rows'][0]['host_link_status'], 'unresolved_host_reference' if mode == 'dangling' else 'unknown_host_reference')

    def test_cross_tenant_endpoint_collision_is_not_hidden_by_parent_filter(self):
        data = fixture(); other = deepcopy(rows(data, 'VM_NOVA')[0]); other.update(id='other-vm', tenantName='other-tenant')
        replace_rows(data, 'VM_NOVA', rows(data, 'VM_NOVA') + [other])
        self.blocked(data, 'relationship_failure')

    def test_same_names_and_private_ip_do_not_create_ownership_edges(self):
        data = fixture(); other = deepcopy(rows(data, 'VM_NOVA')[0]); other.update(id='vm2', resId='res2')
        replace_rows(data, 'VM_NOVA', rows(data, 'VM_NOVA') + [other])
        _, out = self.run_view(data)
        self.assertEqual([(r['vm_id'], r['eip_id']) for r in out['rows']], [('vm', 'eip'), ('vm2', None)])
        self.assertEqual(out['rows'][1]['eip_link_status'], 'no_known_binding')
        self.assertFalse(out['diagnostics']['full_eip_objects_binding_complete'])

    def test_unknown_vm_endpoint_port_and_eip_orphans_remain_diagnostics(self):
        for value in (None, '', 'dangling-port'):
            data = fixture(); rows(data, 'FLOATING_IPS')[0]['portId'] = value
            _, out = self.run_view(data)
            self.assertIsNone(out['rows'][0]['eip_id'])
            self.assertEqual(out['diagnostics']['eips_missing_or_dangling_port_count'], 1)
        data = fixture(); rows(data, 'VM_NOVA')[0].pop('resId')
        _, out = self.run_view(data)
        self.assertEqual(out['diagnostics']['unknown_vm_res_id_count'], 1)
        self.assertEqual(out['diagnostics']['eips_unattributed_vm_count'], 1)

    def test_port_unknown_dev_id_is_provider_nullable_not_guessed(self):
        data = fixture()
        for row in rows(data, 'PORT'):row['devId'] = None
        prep, out = self.run_view(data)
        self.assertIsNone(prep['typed_tables']['CLOUD_PORT']['rows'][0]['devId'])
        self.assertEqual(out['diagnostics']['ports_unattributed_vm_count'], 1)
        self.assertIsNone(out['rows'][0]['eip_id'])

    def test_schema_is_needed_for_sparse_and_empty_rows(self):
        for ci, field in [('VM_NOVA', 'privateIps'), ('HOST', 'name'), ('FLOATING_IPS', 'isInternal')]:
            data = fixture(); data['raw_receipts'][ci]['schema'].remove(field)
            self.blocked(data, 'schema_failure')
        data = fixture(); rows(data, 'VM_NOVA')[0].pop('id')
        self.blocked(data, 'schema_failure')

    def test_non_port_duplicate_identity_is_rejected_even_identical(self):
        for ci in ('VM_NOVA', 'HOST', 'FLOATING_IPS'):
            data = fixture(); replace_rows(data, ci, rows(data, ci) * 2)
            self.blocked(data, 'duplicate_identity')

    def test_provider_rejects_unprojected_business_and_presence_conflict(self):
        for first, second in [(1, True), (1, 1.0), ('a', 'b')]:
            data = fixture(); a, b = rows(data, 'PORT'); a['unprojected-business'] = first; b['unprojected-business'] = second
            self.blocked(data, 'port_provider_failure')
        data = fixture(); rows(data, 'PORT')[1]['unprojected-business'] = None
        self.blocked(data, 'port_provider_failure')

    def test_missing_failure_partial_pages_never_turn_into_empty_success(self):
        mutations = [lambda d: d['raw_receipts']['VM_NOVA'].update(http_status=500),
                     lambda d: d['raw_receipts']['VM_NOVA']['pages'][0].update(ok=False),
                     lambda d: d['raw_receipts']['VM_NOVA']['pages'][0].update(totalNum=2),
                     lambda d: d['raw_receipts']['VM_NOVA']['pages'].clear()]
        for mutate in mutations:
            data = fixture(); mutate(data)
            out = c.evaluate_tenant_view(params(), data)
            self.assertFalse(out['ok']); self.assertIsNone(out['rows'])

    def test_capture_receipt_id_actual_request_and_page_binding(self):
        mutations = [('capture_failure', lambda d: d['raw_receipts']['HOST'].update(capture_id='old')),
                     ('capture_failure', lambda d: d['raw_receipts']['HOST'].update(receipt_id='raw-VM_NOVA')),
                     ('request_failure', lambda d: d['raw_receipts']['VM_NOVA']['request'].update(autoPagination=1)),
                     ('request_failure', lambda d: d['raw_receipts']['VM_NOVA']['pages'][0]['request'].update(method='POST'))]
        for code, mutate in mutations:
            data = fixture(); mutate(data); self.blocked(data, code)

    def test_derived_pages_with_forged200_cannot_be_raw(self):
        data = fixture()
        data['raw_receipts']['VM_NOVA']['pages'][0].update(receipt_kind='derived_validated_projection_not_HTTP', http_status=200)
        self.blocked(data, 'derived_as_raw')
        data = fixture(); data['raw_receipts']['PORT'].update(source_raw_receipt_sha256='marker', http_status=200)
        self.blocked(data, 'derived_as_raw')

    def test_derived_legacy_inputs_are_marked_without_http_status(self):
        prep, _ = self.run_view()
        for env in prep['derived_validator_inputs'].values():
            self.assertEqual(env['receipt_kind'], 'derived_validated_projection_not_HTTP')
            self.assertNotIn('http_status', env)
            for page in env['pages']:
                self.assertEqual(page['receipt_kind'], 'derived_validated_projection_not_HTTP')
                self.assertNotIn('http_status', page)
        self.assertEqual(prep['raw_receipts'], prep['input_evidence']['evidence']['raw_receipts'])

    def test_recheck_recomputes_every_derived_component_not_ready_or_digest(self):
        prepared, _ = self.run_view()
        mutations = [lambda p: p['typed_tables']['CLOUD_PORT']['rows'].clear(),
                     lambda p: p['diagnostics'].update(business_complete=True),
                     lambda p: p['canonical_receipts']['PORT'].clear(),
                     lambda p: p['derived_validator_inputs']['PORT']['pages'][0]['objList'].clear(),
                     lambda p: p['provider_prepared']['rows'].clear(),
                     lambda p: p['plan'].update(sql='SELECT 1')]
        for mutate in mutations:
            changed = deepcopy(prepared); mutate(changed)
            changed['typed_projection_sha256'] = c.digest(changed['typed_tables'])
            with self.assertRaises(c.ConsumerError) as ctx:c.recheck_tenant_prepared(changed)
            self.assertEqual(ctx.exception.code, 'prepared_failure')

    def test_recomputed_input_digest_does_not_hide_source_request_failure(self):
        prepared, _ = self.run_view()
        raw = prepared['input_evidence']['evidence']['raw_receipts']['HOST']
        raw['request']['method'] = 'POST'
        prepared['input_evidence_sha256'] = c.digest(prepared['input_evidence'])
        with self.assertRaises(c.ConsumerError) as ctx:c.recheck_tenant_prepared(prepared)
        self.assertEqual(ctx.exception.code, 'request_failure')

    def test_external_provider_source_pin_checked_before_import(self):
        module, pin = c.provider()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'shared_policy.py'; path.write_text('raise RuntimeError("must not import")\n')
            with self.assertRaises(c.ConsumerError) as ctx:c.provider(d)
            self.assertEqual(ctx.exception.code, 'source_pin_failure')

    def test_actual_in_scoped_batches_cross_provider_consumer(self):
        p = params(); data = add_scoped(p, fixture(p))
        self.assertEqual(data['raw_receipts']['PORT'][1]['request']['condition']['constraint'][1]['simple'],
                         {'name': 'devId', 'value': ['res'], 'operator': 'in'})
        prep, out = self.run_view(data, p)
        self.assertEqual(len(out['rows']), 1)
        self.assertEqual(len(prep['provider_prepared']['raw_receipts']), 2)
        self.assertEqual([r['pages'][0]['totalNum'] for r in prep['provider_prepared']['raw_receipts']], [2, 2])
        self.assertEqual(len(prep['typed_tables']['CLOUD_PORT']['rows']), 1)
        self.assertTrue(prep['plan']['port_scoped_batch_set_executed'])

    def test_scoped_omission_cannot_be_repaired_from_full_context_silently(self):
        data = add_scoped(params(), fixture())
        env = data['raw_receipts']['PORT'][1]
        env['pages'][0].update(objList=[], totalNum=0, totalPageNo=0)
        self.blocked(data, 'port_scope_recall_gap')

    def test_cross_batch_business_conflict_is_decided_by_actual_provider(self):
        data = add_scoped(params(), fixture())
        for r in data['raw_receipts']['PORT'][1]['pages'][0]['objList']:r['unprojected-business'] = 'drift'
        self.blocked(data, 'port_provider_failure')
        data = fixture(); vm2 = deepcopy(rows(data, 'VM_NOVA')[0]);vm2.update(id='vm2',resId='res2')
        replace_rows(data, 'VM_NOVA', rows(data, 'VM_NOVA') + [vm2]);add_scoped(params(),data)
        for r in data['raw_receipts']['PORT'][1]['pages'][0]['objList']:r['devId'] = 'res2'
        self.blocked(data, 'port_provider_failure')

    def test_multi_in_batches_preserve_each_raw_population_and_no_context_fallback(self):
        p = params(); data = fixture(); vms=[];ports=[]
        for n in range(101):
            v=deepcopy(rows(data,'VM_NOVA')[0]);v.update(id='v'+str(n),resId='res-'+str(n));vms.append(v)
            ports.append({'id':'p'+str(n),'devId':'res-'+str(n),'logicalRegionName':'review-region'})
        replace_rows(data,'VM_NOVA',vms);replace_rows(data,'PORT',ports)
        rows(data,'FLOATING_IPS')[0]['portId']='p0';add_scoped(p,data)
        prep,out=self.run_view(data,p)
        self.assertEqual(len(out['rows']),101)
        self.assertEqual([r['pages'][0]['totalNum'] for r in prep['provider_prepared']['raw_receipts']],[101,100,1])
        self.assertEqual(len(prep['typed_tables']['CLOUD_PORT']['rows']),101)
        data['raw_receipts']['PORT'].pop()
        self.blocked(data,'evidence_failure',p)

    def test_no_endpoint_keys_never_create_empty_in_or_unfiltered_dependency(self):
        data=fixture();rows(data,'VM_NOVA')[0]['resId']=None
        self.assertEqual(c.plan_tenant_port_batches(params(),rows(data,'VM_NOVA')),[])
        prep,out=self.run_view(data)
        self.assertEqual(len(prep['plan']['port_actual_requests']),1)
        self.assertFalse(prep['plan']['port_scoped_batch_set_executed'])
        self.assertIsNone(out['rows'][0]['eip_id'])

    def test_actual_tenant_selection_receipt_paired_to_complete_context(self):
        p=params();data=fixture()
        query=c._request('VM_NOVA',{'tenantName':'tenant','logicalRegionName':'review-region'})
        data['raw_receipts']['VM_NOVA_SELECTION']=receipt('VM_NOVA',query,rows(data,'VM_NOVA'),'tenant-selection',data['raw_receipts']['VM_NOVA']['schema'])
        _,out=self.run_view(data,p)
        self.assertTrue(out['diagnostics']['actual_tenant_selection_receipt_proven'])
        data['raw_receipts']['VM_NOVA_SELECTION']['pages'][0].update(objList=[],totalNum=0,totalPageNo=0)
        self.blocked(data,'selection_drift',p)

    def test_best_effort_isolation_and_display_unknowns_do_not_certify_full_answer(self):
        data=fixture();data['capture']['isolation']='best_effort_non_atomic'
        _,out=self.run_view(data)
        self.assertEqual(out['diagnostics']['capture_isolation_asserted_by_B'],'best_effort_non_atomic')
        self.assertFalse(out['diagnostics']['native_capture_authenticated_by_consumer'])
        self.assertFalse(out['diagnostics']['business_complete'])
        self.assertFalse(out['full_original_question_certified'])

    def test_zero_populations_create_declared_true_empty_tables_and_columns(self):
        data=fixture()
        for ci in list(data['raw_receipts']):replace_rows(data,ci,[])
        prep,out=self.run_view(data)
        self.assertEqual(out['rows'],[])
        self.assertEqual(out['columns'],c.legacy().build(params())['output_columns'])
        self.assertEqual(set(prep['typed_tables']),{'CLOUD_VM_NOVA','CLOUD_HOST','CLOUD_PORT','CLOUD_FLOATING_IPS'})
        self.assertTrue(all(table['rows']==[] for table in prep['typed_tables'].values()))
        self.assertTrue(all('_empty' not in table['columns'] for table in prep['typed_tables'].values()))

    def test_native_view_is_independent_of_port_and_preserves_host_unknown(self):
        p=params('native_ip_host_rows');data=fixture(p);rows(data,'VM_NOVA')[0].pop('privateIps')
        prep,out=self.run_view(data,p)
        self.assertIsNone(prep['provider_prepared'])
        self.assertNotIn('PORT',prep['canonical_receipts'])
        self.assertIsNone(out['rows'][0]['private_ips_raw'])
        self.assertTrue(out['diagnostics']['actual_tenant_selection_receipt_proven'])
        self.assertFalse(out['diagnostics']['full_eip_objects_binding_complete'])

    def test_nontext_roles_invalid_utf8_and_unknown_parameters_fail_closed(self):
        for ci,key,value in [('VM_NOVA','privateIps',['token']),('HOST','name',1),('FLOATING_IPS','isInternal',0)]:
            data=fixture();rows(data,ci)[0][key]=value;self.blocked(data,'schema_failure')
        data=fixture();rows(data,'VM_NOVA')[0]['privateIps']='\ud800';self.blocked(data,'invalid_json')
        p=params();p['case_id']='forbidden'
        with self.assertRaises(c.ConsumerError):c.build_tenant_view(p)

    def test_opaque_literals_remain_full_and_long_requests_do_not_truncate(self):
        p=params();p['tenantName']="租户-'opaque-0000"
        data=fixture(p);rows(data,'VM_NOVA')[0]['tenantName']=p['tenantName']
        _,out=self.run_view(data,p)
        self.assertEqual(out['rows'][0]['vm_id'],'vm')
        self.assertIn(p['tenantName'].replace("'","''"),c.build_tenant_view(p)['sql'])
        p['tenantName']='界'*2000
        with self.assertRaises(c.ConsumerError) as ctx:c.build_tenant_view(p)
        self.assertEqual(ctx.exception.code,'request_too_large')

    def test_full_original_question_with_newlines_is_retained_exactly(self):
        data=fixture();data['question_text']='完整原文：查询租户tenant\n私有IP、关联EIP及宿主机，保留全部条件。'
        prep,_=self.run_view(data)
        self.assertEqual(prep['input_evidence']['evidence']['question_text'],data['question_text'])

    def test_port_raw_duplicate_across_pages_keeps_original_population(self):
        data=fixture();ports=[{'id':'port','devId':'res','logicalRegionName':'review-region'}]
        ports += [{'id':'other-'+str(n),'devId':None,'logicalRegionName':'review-region'} for n in range(999)]
        ports.append({'id':'port','devId':'res','logicalRegionName':'review-region','last_Modified':'later'})
        replace_rows(data,'PORT',ports)
        prep,out=self.run_view(data)
        self.assertEqual(len(prep['raw_receipts']['PORT']['pages']),2)
        self.assertEqual(prep['raw_receipts']['PORT']['pages'][0]['totalNum'],1001)
        self.assertEqual(len(prep['typed_tables']['CLOUD_PORT']['rows']),1000)
        self.assertEqual(prep['derived_validator_inputs']['PORT']['pages'][0]['totalNum'],1000)
        self.assertEqual([(r['vm_id'],r['eip_id']) for r in out['rows']],[('vm','eip')])

    def test_selection_missing_and_null_states_cannot_silently_drift(self):
        p=params();data=fixture();rows(data,'VM_NOVA')[0].pop('privateIps')
        query=c.build_tenant_view(p)['tenant_selection_request']
        source=deepcopy(rows(data,'VM_NOVA'));source[0]['privateIps']=None
        data['raw_receipts']['VM_NOVA_SELECTION']=receipt('VM_NOVA',query,source,'selection',data['raw_receipts']['VM_NOVA']['schema'])
        self.blocked(data,'selection_drift',p)

    def test_raw_status_contradictions_are_not_ignored(self):
        for value in ('failed','unknown',False,500):
            data=fixture();data['raw_receipts']['VM_NOVA']['status']=value
            self.blocked(data,'receipt_failure')

    def test_projection_source_markers_still_reject_after_kind_is_removed(self):
        for key in ('source_projection_sha256','canonical_receipt','canonical_receipts'):
            data=fixture();data['raw_receipts']['HOST'][key]={}
            data['raw_receipts']['HOST'].pop('receipt_kind',None)
            self.blocked(data,'derived_as_raw')

    def test_full_original_question_is_required_not_reconstructed_from_params(self):
        data=fixture();data.pop('question_text')
        self.blocked(data,'evidence_failure')

    def test_page_capture_contradiction_is_rejected(self):
        data=fixture();data['raw_receipts']['HOST']['pages'][0]['capture_id']='other-capture'
        self.blocked(data,'capture_failure')

    def test_type_exact_recheck_rejects_bool_int_and_int_float_aliases(self):
        prepared,_=self.run_view()
        changes=[lambda p:p['diagnostics'].update(selected_vm_count=True),
                 lambda p:p['diagnostics'].update(selected_vm_count=1.0),
                 lambda p:p['canonical_receipts']['PORT'].update(canonical_object_count=True),
                 lambda p:p['provider_prepared']['canonical_receipt'].update(canonical_object_count=True)]
        for change in changes:
            altered=deepcopy(prepared);change(altered)
            altered['input_evidence_sha256']=c.digest(altered['input_evidence'])
            altered['typed_projection_sha256']=c.digest(altered['typed_tables'])
            with self.assertRaises(c.ConsumerError) as ctx:c.recheck_tenant_prepared(altered)
            self.assertEqual(ctx.exception.code,'prepared_failure')

    def test_invalid_json_is_rejected_in_recheck_and_raw_input(self):
        prepared,_=self.run_view()
        cyclic=[];cyclic.append(cyclic)
        for bad in (float('nan'),float('inf'),('tuple-is-not-JSON',),{1:'non-string-key'},cyclic):
            changed=deepcopy(prepared);changed['diagnostics']['invalid-extra']=bad
            with self.assertRaises(c.ConsumerError) as ctx:c.recheck_tenant_prepared(changed)
            self.assertEqual(ctx.exception.code,'invalid_json')
        data=fixture();data['raw_receipts']['HOST']['extra-unprojected']=(1,2)
        self.blocked(data,'invalid_json')

    def test_global_views_still_reject_cross_region_host_and_eip_edges(self):
        p=params(region=False);data=fixture(p);rows(data,'HOST')[0]['logicalRegionName']='other-region'
        self.blocked(data,'relationship_failure',p)
        data=fixture(p);rows(data,'FLOATING_IPS')[0]['logicalRegionName']='other-region'
        self.blocked(data,'relationship_failure',p)


if __name__=='__main__':unittest.main(verbosity=2)
