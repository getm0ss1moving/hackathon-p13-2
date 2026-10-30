"""Stdlib synthetic controls only; no native data, network or model calls.

Expected membership pairs are hand-authored. The fake transport's substring
selection is deliberately weaker than exact membership, and never an oracle for
expected SQL results. Run only when the user elects to run terminal tests.
"""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'address'))
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = PACKAGE / 'address'
spec = importlib.util.spec_from_file_location('address_membership_candidate', ROOT / 'candidate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
MISSING = object()


def params(filters=None, policy='known_only_with_diagnostic'):
    f = {'logicalRegionName': 'region-A', 'status': 'ACTIVE'} if filters is None else filters
    return {'profile': 'fixed_address_member_vm_rows', 'filters': f, 'required_filters': sorted(f),
            'address_codec': 'at_or_scalar_v1', 'unknown_policy': policy}


def eip(identity, fixed='x9', region='region-A', address='public-opaque'):
    row = {'id': identity, 'logicalRegionName': region, 'status': 'ACTIVE', 'floatingIpAddress': address}
    if fixed is not MISSING:
        row['fixedIpAddress'] = fixed
    return row


def vm(identity, raw='@x9@y8@', region='region-A', name='same-name'):
    row = {'id': identity, 'logicalRegionName': region, 'name': name}
    if raw is not MISSING:
        row['privateIps'] = raw
    return row


def receipt(ci, request, rows, role, rid, capture='synthetic-capture'):
    total = len(rows)
    batches = [rows[n:n + 1000] for n in range(0, total, 1000)] or [[]]
    return {'ok': True, 'http_status': 200, 'role': role, 'receipt_id': rid, 'capture_id': capture,
            'request': deepcopy(request), 'schema': list(m.SCHEMA[ci]), 'schema_verified': True,
            'pages': [{'ok': True, 'http_status': 200, 'pageNo': n, 'pageSize': 1000,
                       'totalNum': total, 'totalPageNo': (total + 999) // 1000,
                       'objList': deepcopy(batch)} for n, batch in enumerate(batches, 1)]}


def evidence(p, eips, vms, candidates=None):
    plan = m.plan_followups(p, eips)
    out = {'capture': {'capture_id': 'synthetic-capture', 'source_ref': 'synthetic-v1',
                       'schema_ref': 'synthetic-schema-v1', 'isolation': 'immutable_snapshot',
                       'origin': 'synthetic'},
           'eip': receipt('FLOATING_IPS', m.build(p)['eip_request'], eips, 'selected_eips', 'receipt-eip'),
           'vm_context': [], 'vm_candidates': []}
    for n, desc in enumerate(plan['context_requests']):
        rows = [v for v in vms if v['logicalRegionName'] == desc['region']]
        out['vm_context'].append(receipt('VM_NOVA', desc['request'], rows, desc['role'], 'context-' + str(n)))
    for n, desc in enumerate(plan['candidate_requests']):
        if candidates is None:
            rows = [v for v in vms if v['logicalRegionName'] == desc['region']
                    and isinstance(v.get('privateIps'), str) and desc['needle'] in v['privateIps']]
        else:
            rows = candidates.get((desc['region'], desc['fixed_token']), [])
        item = receipt('VM_NOVA', desc['request'], rows, desc['role'], 'candidate-' + str(n))
        item['lookup_id'] = desc['lookup_id']
        out['vm_candidates'].append(item)
    return out


class MembershipControls(unittest.TestCase):
    def run_rows(self, eips, vms, p=None, candidates=None):
        p = params() if p is None else p
        return m.execute_local(p, evidence(p, eips, vms, candidates))

    def blocked(self, code, p, data):
        out = m.evaluate(p, data)
        self.assertFalse(out['ok'])
        self.assertIsNone(out['rows'])
        self.assertEqual(out['error']['code'], code)
        self.assertFalse(out['full_original_question_certified'])

    def test_native_at_scalar_ipv6_raw_and_duplicates(self):
        raw = '@x9@2001:DB8::a@x9@'
        out = self.run_rows([eip('e-1'), eip('e-2', '2001:DB8::a')], [vm('v-1', raw)])
        self.assertEqual([(r['eip_id'], r['vm_id']) for r in out['rows']], [('e-1', 'v-1'), ('e-2', 'v-1')])
        self.assertEqual([r['private_ips_raw'] for r in out['rows']], [raw, raw])
        self.assertEqual(out['diagnostics']['duplicate_member_tokens_removed'], 1)
        self.assertFalse(out['diagnostics']['full_eip_binding_complete'])
        self.assertFalse(out['full_original_question_certified'])
        self.assertEqual(m.decode('opaque-other')['tokens'], ['opaque-other'])

    def test_substring_case_and_different_ipv6_spelling_do_not_match(self):
        out = self.run_rows([eip('e-1', 'x9'), eip('e-2', '2001:db8::a')],
                            [vm('v-1', '@prefix-x9-suffix@X9@2001:DB8::a@')],
                            candidates={('region-A', 'x9'): [vm('v-1', '@prefix-x9-suffix@X9@2001:DB8::a@')],
                                        ('region-A', '2001:db8::a'): [vm('v-1', '@prefix-x9-suffix@X9@2001:DB8::a@')]})
        self.assertEqual([r['vm_id'] for r in out['rows']], [None, None])
        self.assertEqual([r['known_matching_vm_count'] for r in out['rows']], [0, 0])

    def test_multi_eip_vm_fanout_is_identity_based(self):
        out = self.run_rows([eip('e-1'), eip('e-2')], [vm('v-1'), vm('v-2', 'x9')])
        self.assertEqual([(r['eip_id'], r['vm_id']) for r in out['rows']],
                         [('e-1', 'v-1'), ('e-1', 'v-2'), ('e-2', 'v-1'), ('e-2', 'v-2')])
        self.assertTrue(all(r['known_matching_vm_count'] == 2 for r in out['rows']))
        self.assertTrue(all(r['membership_status'] == 'multiple_address_member_candidates' for r in out['rows']))

    def test_same_token_different_regions_never_crosses(self):
        p = params({'status': 'ACTIVE'})
        out = self.run_rows([eip('e-1'), eip('e-2', region='region-B')],
                            [vm('v-1'), vm('v-2', region='region-B')], p)
        self.assertEqual([(r['eip_id'], r['vm_id']) for r in out['rows']], [('e-1', 'v-1'), ('e-2', 'v-2')])

    def test_unknowns_are_retained_and_distinguished(self):
        vms = [vm('known'), vm('missing', MISSING), vm('null', None), vm('empty', ''),
               vm('space', '  '), vm('malformed', '@x9@@'), vm('unproven-json', '["x9"]')]
        out = self.run_rows([eip('e-1'), eip('e-2', MISSING), eip('e-3', ''), eip('e-4', '@x9@')], vms)
        self.assertEqual(len(out['rows']), 4)
        self.assertEqual(out['rows'][0]['vm_id'], 'known')
        self.assertEqual(out['rows'][0]['membership_status'], 'known_candidates_population_incomplete')
        self.assertEqual([r['membership_status'] for r in out['rows'][1:]], ['unknown_fixed_address'] * 3)
        d = out['diagnostics']
        self.assertEqual(d['unknown_VM_address_rows'], 6)
        self.assertEqual(d['unknown_fixed_EIP_rows'], 3)
        self.assertFalse(d['membership_population_complete_in_declared_receipts'])
        states = {r['vm_id']: r for r in d['vm_address_states']}
        self.assertFalse(states['missing']['private_ips_present'])
        self.assertEqual(states['null']['status'], 'unknown_null')
        self.assertEqual(states['empty']['status'], 'unknown_empty')
        self.assertEqual(states['space']['status'], 'unknown_whitespace')

    def test_reject_policy_returns_failure_not_empty(self):
        p = params(policy='reject')
        self.blocked('unknown_population', p, evidence(p, [eip('e-1')], [vm('unknown', MISSING)]))

    def test_complete_empty_parents_typed_columns_and_no_followups(self):
        p = params()
        data = evidence(p, [], [])
        self.assertEqual(data['vm_context'], [])
        self.assertEqual(data['vm_candidates'], [])
        out = m.execute_local(p, data)
        self.assertEqual(out['rows'], [])
        self.assertEqual(out['columns'], list(m.OUTPUT))
        self.assertEqual(out['diagnostics']['selected_eip_count'], 0)
        self.assertFalse(out['full_original_question_certified'])

    def test_unknown_fixed_still_requires_region_context(self):
        p = params()
        data = evidence(p, [eip('e-1', None)], [vm('v-1', MISSING)])
        self.assertEqual(len(data['vm_context']), 1)
        self.assertEqual(data['vm_candidates'], [])
        data['vm_context'] = []
        self.blocked('evidence_failure', p, data)

    def test_parser_unproven_or_malformed_encodings_do_not_guess(self):
        for raw in ('["x9"]', '{"ip":"x9"}', 'x9,y8', 'x9;y8', '@x9', 'x9@', '@@', '@x9@@y8@', '@\n@'):
            with self.subTest(raw=raw):
                self.assertEqual(m.decode(raw)['status'], 'unsupported_or_malformed_codec')
                self.assertEqual(m.decode(raw)['tokens'], [])
        self.assertEqual(m.decode(42)['status'], 'unsupported_native_type')
        for codec in ('csv_exact_v1', 'json_string_array_v1', 'scalar_v1'):
            p = params(); p['address_codec'] = codec
            with self.subTest(codec=codec), self.assertRaises(m.Blocked) as cm:
                m.build(p)
            self.assertEqual(cm.exception.code, 'unsupported_codec')

    def test_opaque_no_value_whitelist_trim_or_number_conversion(self):
        for token in ('new-unseen-token', '000001', '图形-Δ', "quote'X", ' space preserved ', '2001:DB8::f', 'prefix{{opaque}}tail'):
            with self.subTest(token=token):
                out = self.run_rows([eip('e-1', token)], [vm('v-1', '@' + token + '@')])
                self.assertEqual(out['rows'][0]['vm_id'], 'v-1')
                self.assertEqual(out['rows'][0]['fixed_ip'], token)
                self.assertEqual(out['rows'][0]['private_ips_raw'], '@' + token + '@')

    def test_like_wildcard_candidate_false_positive_is_removed(self):
        vms = [vm('v-exact', '@a_b@'), vm('v-extra', '@axb@')]
        out = self.run_rows([eip('e-1', 'a_b')], vms, candidates={('region-A', 'a_b'): vms})
        self.assertEqual([r['vm_id'] for r in out['rows']], ['v-exact'])

    def test_literal_dependency_operator_and_filter_contract(self):
        p = params()
        first = m.build(p)['eip_request']
        self.assertEqual(first['condition']['constraint'], [
            {'simple': {'name': 'logicalRegionName', 'value': 'region-A', 'operator': 'equal'}},
            {'simple': {'name': 'status', 'value': 'ACTIVE', 'operator': 'equal'}, 'logOp': 'and'}])
        plan = m.plan_followups(p, [eip('e-1'), eip('e-2')])
        self.assertEqual(len(plan['candidate_requests']), 1)
        self.assertEqual(plan['candidate_requests'][0]['eip_ids'], ['e-1', 'e-2'])
        self.assertEqual(plan['candidate_requests'][0]['request']['condition']['constraint'][1],
                         {'simple': {'name': 'privateIps', 'value': 'x9', 'operator': 'contain'}, 'logOp': 'and'})
        for replacement in ('in', 'equal'):
            data = evidence(p, [eip('e-1')], [vm('v-1')])
            data['vm_candidates'][0]['request']['condition']['constraint'][1]['simple']['operator'] = replacement
            self.blocked('request_drift', p, data)

    def test_candidate_recall_is_checked_per_token_not_global_union(self):
        p = params()
        data = evidence(p, [eip('e-x', 'x9'), eip('e-y', 'y8')], [vm('v-1')])
        data['vm_candidates'][0]['pages'][0].update(totalNum=0, totalPageNo=0, objList=[])
        self.blocked('candidate_recall_gap', p, data)

    def test_source_role_lookup_request_and_schema_drift(self):
        p = params(); base = evidence(p, [eip('e-1')], [vm('v-1')])
        mutations = [
            ('capture_failure', lambda d: d['vm_context'][0].update(capture_id='older')),
            ('capture_failure', lambda d: d['vm_context'][0].update(role='other')),
            ('capture_failure', lambda d: d['vm_candidates'][0].update(lookup_id='other')),
            ('capture_failure', lambda d: d['vm_context'][0].update(receipt_id='receipt-eip')),
            ('request_drift', lambda d: d['eip']['request'].update(autoPagination=False)),
            ('request_drift', lambda d: d['eip']['request'].update(autoPagination=1)),
            ('schema_failure', lambda d: d['vm_context'][0].update(schema=[])),
            ('schema_failure', lambda d: d['eip'].update(schema_verified=False)),
            ('scope_drift', lambda d: d['eip']['pages'][0]['objList'][0].update(status='OTHER')),
            ('context_drift', lambda d: d['vm_candidates'][0]['pages'][0]['objList'][0].update(privateIps='x9')),
        ]
        for code, mutate in mutations:
            with self.subTest(code=code, mutation=mutate):
                data = deepcopy(base); mutate(data); self.blocked(code, p, data)

    def test_failure_pagination_and_sparse_type_gates(self):
        p = params(); base = evidence(p, [eip('e-1')], [vm('v-1')])
        mutations = [
            ('receipt_failure', lambda d: d['eip'].update(ok=False)),
            ('receipt_failure', lambda d: d['eip'].update(http_status=500)),
            ('receipt_failure', lambda d: d['eip']['pages'][0].update(success=False)),
            ('receipt_failure', lambda d: d['eip']['pages'][0].update(error='backend failed')),
            ('receipt_failure', lambda d: d['eip']['pages'][0].pop('http_status')),
            ('pagination_failure', lambda d: d['eip']['pages'][0].update(totalNum=2)),
            ('pagination_failure', lambda d: d['eip']['pages'][0].update(pageNo=True)),
            ('pagination_failure', lambda d: d['eip']['pages'].clear()),
            ('schema_failure', lambda d: d['eip']['pages'][0]['objList'][0].pop('id')),
            ('schema_failure', lambda d: d['vm_context'][0]['pages'][0]['objList'][0].update(privateIps=['x9'])),
        ]
        for code, mutate in mutations:
            with self.subTest(code=code, mutation=mutate):
                data = deepcopy(base); mutate(data); self.blocked(code, p, data)

    def test_duplicate_ids_same_page_and_across_pages_fail(self):
        p = params()
        data = evidence(p, [eip('e-1')], [vm('v-1')])
        page = data['vm_context'][0]['pages'][0]
        page['objList'].append(deepcopy(page['objList'][0])); page['totalNum'] = 2
        self.blocked('duplicate_identity', p, data)
        data = evidence(p, [eip('e-' + str(n)) for n in range(1001)], [])
        data['eip']['pages'][1]['objList'][0]['id'] = 'e-0'
        self.blocked('duplicate_identity', p, data)

    def test_real_multi_page_shape_and_missing_page(self):
        p = params(); eips = [eip('e-' + str(n)) for n in range(1001)]
        data = evidence(p, eips, [vm('v-1')])
        out = m.execute_local(p, data)
        self.assertEqual(len(out['rows']), 1001)
        self.assertEqual(out['diagnostics']['selected_eip_count'], 1001)
        data['eip']['pages'].pop()
        self.blocked('pagination_failure', p, data)

    def test_best_effort_capture_keeps_matches_without_snapshot_claim(self):
        p = params(); data = evidence(p, [eip('e-1')], [vm('v-1')])
        data['capture']['isolation'] = 'best_effort_non_atomic'
        out = m.execute_local(p, data)
        self.assertEqual(out['rows'][0]['vm_id'], 'v-1')
        self.assertEqual(out['rows'][0]['membership_status'], 'known_candidates_non_atomic_capture')
        self.assertFalse(out['diagnostics']['membership_snapshot_complete_under_B_assertions'])
        self.assertFalse(out['diagnostics']['native_execution_verified_by_module'])

    def test_prepared_rows_digest_diagnostics_and_marker_tampering(self):
        p = params(); prepared = m.prepare(p, evidence(p, [eip('e-1')], [vm('v-1')]))
        mutations = [lambda d: d['tables']['A_VM_ADDRESS_MEMBERS'].clear(),
                     lambda d: d['tables']['A_EIP_MEMBER_STATE'][0].update(known_matching_vm_count=True),
                     lambda d: d['diagnostics'].update(full_eip_binding_complete=True),
                     lambda d: d.update(evidence_sha256='invalid'),
                     lambda d: d.pop('input_evidence')]
        for mutate in mutations:
            data = deepcopy(prepared); mutate(data)
            with self.assertRaises(m.Blocked) as cm:
                m.execute_prepared(data)
            self.assertEqual(cm.exception.code, 'prepared_drift')
        # Recomputed digest does not bypass request validation. Nor is a digest authentication.
        data = deepcopy(prepared)
        data['input_evidence']['evidence']['eip']['request']['method'] = 'POST'
        data['evidence_sha256'] = hashlib.sha256(m.encoded(data['input_evidence'])).hexdigest()
        with self.assertRaises(m.Blocked) as cm:
            m.execute_prepared(data)
        self.assertEqual(cm.exception.code, 'request_drift')

    def test_order_permutation_cannot_change_business_pairs(self):
        p = params()
        parents = [eip('e-z', 'y8'), eip('e-a', 'x9')]
        machines = [vm('v-z'), vm('v-a', '@y8@')]
        expected = [('e-a', 'v-z'), ('e-z', 'v-a'), ('e-z', 'v-z')]
        for es, vs in ((parents, machines), (list(reversed(parents)), list(reversed(machines)))):
            out = m.execute_local(p, evidence(p, es, vs))
            self.assertEqual([(r['eip_id'], r['vm_id']) for r in out['rows']], expected)

    def test_required_fixed_filter_and_unknown_identity_are_not_invented(self):
        p = params({'fixedIpAddress': 'x9'})
        data = evidence(p, [eip('e-1')], [vm('v-1')])
        out = m.execute_local(p, data)
        self.assertEqual(out['rows'][0]['fixed_ip'], 'x9')
        data['eip']['pages'][0]['objList'][0]['fixedIpAddress'] = 'other'
        self.blocked('scope_drift', p, data)
        p = params(); data = evidence(p, [eip('e-1')], [vm('v-1')])
        data['vm_context'][0]['pages'][0]['objList'][0]['id'] = ''
        self.blocked('invalid_text', p, data)

    def test_invalid_utf8_and_nonfinite_json_are_controlled_failures(self):
        p = params(); data = evidence(p, [eip('e-1')], [vm('v-1')])
        data['vm_context'][0]['pages'][0]['objList'][0]['privateIps'] = '\ud800'
        self.blocked('invalid_json', p, data)
        data = evidence(p, [eip('e-1')], [vm('v-1')])
        data['eip']['unused_metadata'] = float('nan')
        self.blocked('invalid_json', p, data)

    def test_no_default_scope_and_no_silent_transport_truncation(self):
        for f in ({}, {'tenantName': 'tenant-A'}):
            with self.assertRaises(m.Blocked):
                m.build(params(f))
        p = params(); p['required_filters'] = ['logicalRegionName']
        with self.assertRaises(m.Blocked) as cm:
            m.build(p)
        self.assertEqual(cm.exception.code, 'scope_drift')
        p = params({'logicalRegionName': '界' * 2000})
        with self.assertRaises(m.Blocked) as cm:
            m.build(p)
        self.assertEqual(cm.exception.code, 'request_too_large')
        self.assertGreater(cm.exception.details['measured_bytes'], 4096)


if __name__ == '__main__':
    unittest.main(verbosity=2)
