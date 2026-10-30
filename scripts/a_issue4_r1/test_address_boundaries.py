"""Owner offline checks with hand-built receipts, independent of main test helpers.

This is a second construction, not an independent reviewer or native integration.
Network/socket and child-process entrypoints are blocked during execution.
"""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'address'))
import ast
from copy import deepcopy
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import unittest
import urllib.request

ROOT = PACKAGE / 'address'
NETWORK_ATTEMPTS = []


def forbidden(*args, **kwargs):
    NETWORK_ATTEMPTS.append('network_or_child_process')
    raise AssertionError('offline validation forbids network and child processes')


socket.socket = forbidden
socket.create_connection = forbidden
http.client.HTTPConnection.connect = forbidden
http.client.HTTPSConnection.connect = forbidden
urllib.request.urlopen = forbidden
subprocess.Popen = forbidden
subprocess.run = forbidden

spec = importlib.util.spec_from_file_location('boundary_candidate', ROOT / 'candidate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
REAL_CONNECT = sqlite3.connect


def memory_only(database, *args, **kwargs):
    if database != ':memory:':
        raise AssertionError('only in-memory SQLite permitted')
    return REAL_CONNECT(database, *args, **kwargs)


m.sqlite3.connect = memory_only
REGION = 'independent-region'
PARAMS = {'profile': 'fixed_address_member_vm_rows',
          'filters': {'status': 'BOUND', 'logicalRegionName': REGION},
          'required_filters': ['status', 'logicalRegionName'],
          'address_codec': 'at_or_scalar_v1', 'unknown_policy': 'known_only_with_diagnostic'}


def query(ci, pairs):
    constraints = []
    for n, (name, value, operator) in enumerate(pairs):
        item = {'simple': {'name': name, 'value': value, 'operator': operator}}
        if n:
            item['logOp'] = 'and'
        constraints.append(item)
    return {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=1000',
            'autoPagination': True, 'condition': {'constraint': constraints}}


def parent(identity, fixed):
    return {'id': identity, 'logicalRegionName': REGION, 'status': 'BOUND',
            'fixedIpAddress': fixed, 'floatingIpAddress': 'public-' + identity}


def machine(identity, raw):
    return {'id': identity, 'logicalRegionName': REGION, 'name': 'duplicate-display-name', 'privateIps': raw}


def envelope(ci, role, rid, request, rows):
    # Independent declared schemas: no candidate.SCHEMA/build/plan_followups calls.
    schema = (['id', 'logicalRegionName', 'status', 'fixedIpAddress', 'floatingIpAddress']
              if ci == 'FLOATING_IPS' else ['id', 'logicalRegionName', 'name', 'privateIps'])
    return {'ok': True, 'http_status': 200, 'capture_id': 'independent-capture',
            'role': role, 'receipt_id': rid, 'request': deepcopy(request),
            'schema': schema, 'schema_verified': True,
            'pages': [{'ok': True, 'http_status': 200, 'pageNo': 1, 'pageSize': 1000,
                       'totalNum': len(rows), 'totalPageNo': 1 if rows else 0, 'objList': deepcopy(rows)}]}


def fixture(parents, machines, candidate_rows_by_token, context=True):
    eip_request = query('FLOATING_IPS', [('logicalRegionName', REGION, 'equal'), ('status', 'BOUND', 'equal')])
    out = {'capture': {'capture_id': 'independent-capture', 'source_ref': 'independent-synthetic-v1',
                       'schema_ref': 'hand-declared-schema-v1', 'isolation': 'immutable_snapshot', 'origin': 'synthetic'},
           'eip': envelope('FLOATING_IPS', 'selected_eips', 'eip', eip_request, parents),
           'vm_context': [], 'vm_candidates': []}
    if context:
        out['vm_context'] = [envelope('VM_NOVA', 'vm_region_context', 'context',
                                     query('VM_NOVA', [('logicalRegionName', REGION, 'equal')]), machines)]
    for n, (token, rows) in enumerate(sorted(candidate_rows_by_token.items())):
        request = query('VM_NOVA', [('logicalRegionName', REGION, 'equal'), ('privateIps', token, 'contain')])
        item = envelope('VM_NOVA', 'vm_contain_candidates', 'lookup-' + str(n), request, rows)
        raw = json.dumps([REGION, token], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        item['lookup_id'] = hashlib.sha256(raw).hexdigest()
        out['vm_candidates'].append(item)
    return out


class IndependentBoundaries(unittest.TestCase):
    def setUp(self):
        self.parents = [parent('e-1', 'ab'), parent('e-2', 'a'), parent('e-3', None), parent('e-4', 'AB')]
        missing = {'id': 'v-3', 'logicalRegionName': REGION, 'name': 'duplicate-display-name'}
        self.machines = [machine('v-1', '@ab@def@ab@'), machine('v-2', '@xab@'), missing,
                         machine('v-4', None), machine('v-5', ''), machine('v-6', '  '),
                         machine('v-7', '@ab@@'), machine('v-8', '["ab"]')]
        supersets = [self.machines[i] for i in (0, 1, 6, 7)]
        self.data = fixture(self.parents, self.machines, {'AB': supersets, 'a': supersets, 'ab': supersets})

    def tearDown(self):
        self.assertEqual(NETWORK_ATTEMPTS, [])

    def test_all_sources_compile_and_candidate_imports_are_closed_stdlib(self):
        for path in [ROOT / 'candidate.py', *sorted((ROOT / 'scripts').glob('*.py'))]:
            source = path.read_text(encoding='utf-8')
            tree = ast.parse(source, filename=str(path))
            compile(tree, str(path), 'exec')
            if path.name == 'candidate.py':
                imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
                imports |= {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
                self.assertEqual(imports, {'copy', 'hashlib', 'json', 'sqlite3'})
                dynamic = {node.func.id for node in ast.walk(tree)
                           if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                           and node.func.id in {'__import__', 'eval', 'exec'}}
                self.assertEqual(dynamic, set())

    def test_hand_built_receipts_have_exact_expected_pairs_raw_unknowns(self):
        self.assertEqual(m.build(PARAMS)['eip_request'], self.data['eip']['request'])
        out = m.execute_local(PARAMS, self.data)
        self.assertEqual([(r['eip_id'], r['vm_id']) for r in out['rows']],
                         [('e-1', 'v-1'), ('e-2', None), ('e-3', None), ('e-4', None)])
        self.assertEqual(out['rows'][0]['private_ips_raw'], '@ab@def@ab@')
        self.assertEqual(out['diagnostics']['unknown_VM_address_rows'], 6)
        self.assertEqual(out['diagnostics']['unknown_fixed_EIP_rows'], 1)
        self.assertEqual(out['diagnostics']['duplicate_member_tokens_removed'], 1)
        self.assertFalse(out['diagnostics']['full_eip_binding_complete'])
        self.assertFalse(out['full_original_question_certified'])

    def test_one_lookup_omission_cannot_be_hidden_by_other_lookup(self):
        target = self.data['vm_candidates'][2]['pages'][0]
        target['objList'] = target['objList'][1:]
        target['totalNum'] -= 1
        out = m.evaluate(PARAMS, self.data)
        self.assertFalse(out['ok'])
        self.assertIsNone(out['rows'])
        self.assertEqual(out['error']['code'], 'candidate_recall_gap')
        self.assertEqual(out['error']['details']['missing_vm_ids'], ['v-1'])

    def test_complete_nonmember_is_not_a_substring_match_or_ownership_claim(self):
        v = machine('v-only', '@ab@')
        data = fixture([parent('e-only', 'a')], [v], {'a': [v]})
        out = m.execute_local(PARAMS, data)
        self.assertEqual(len(out['rows']), 1)
        self.assertIsNone(out['rows'][0]['vm_id'])
        self.assertEqual(out['rows'][0]['known_matching_vm_count'], 0)
        self.assertEqual(out['rows'][0]['membership_status'], 'no_address_member_in_declared_snapshot')
        self.assertFalse(out['diagnostics']['full_eip_binding_complete'])

    def test_percent_wildcard_and_unicode_are_exact_tokens(self):
        exact, extra = machine('v-exact', '@地址%_x@'), machine('v-extra', '@地址ABCyx@')
        data = fixture([parent('e-only', '地址%_x')], [exact, extra], {'地址%_x': [exact, extra]})
        out = m.execute_local(PARAMS, data)
        self.assertEqual([(r['eip_id'], r['vm_id']) for r in out['rows']], [('e-only', 'v-exact')])
        self.assertEqual(out['rows'][0]['private_ips_raw'], '@地址%_x@')

    def test_native_type_failure_does_not_become_unknown_or_empty_success(self):
        self.data['vm_context'][0]['pages'][0]['objList'][0]['privateIps'] = 0
        out = m.evaluate(PARAMS, self.data)
        self.assertFalse(out['ok'])
        self.assertIsNone(out['rows'])
        self.assertEqual(out['error']['code'], 'schema_failure')

    def test_no_parent_creates_true_typed_zero_tables(self):
        traces = []
        def traced(database, *args, **kwargs):
            conn = memory_only(database, *args, **kwargs)
            conn.set_trace_callback(traces.append)
            return conn
        m.sqlite3.connect = traced
        try:
            out = m.execute_local(PARAMS, fixture([], [], {}, context=False))
        finally:
            m.sqlite3.connect = memory_only
        self.assertEqual(out['rows'], [])
        creates = [t for t in traces if t.startswith('CREATE TABLE')]
        self.assertEqual(len(creates), 4)
        self.assertTrue(all('TEXT COLLATE BINARY' in t for t in creates))
        self.assertTrue(any('"known_matching_vm_count" INTEGER' in t for t in creates))
        self.assertFalse(any('_empty' in t for t in traces))
        self.assertFalse(out['full_original_question_certified'])

    def test_failure_and_non_atomic_capture_are_not_complete_success(self):
        failed = fixture([], [], {}, context=False)
        failed['eip']['http_status'] = 503
        out = m.evaluate(PARAMS, failed)
        self.assertFalse(out['ok'])
        self.assertIsNone(out['rows'])
        self.assertEqual(out['error']['code'], 'receipt_failure')
        v = machine('v-only', '@ab@')
        data = fixture([parent('e-only', 'ab')], [v], {'ab': [v]})
        data['capture']['isolation'] = 'best_effort_non_atomic'
        out = m.execute_local(PARAMS, data)
        self.assertEqual(out['rows'][0]['vm_id'], 'v-only')
        self.assertEqual(out['rows'][0]['membership_status'], 'known_candidates_non_atomic_capture')
        self.assertFalse(out['diagnostics']['membership_snapshot_complete_under_B_assertions'])
        self.assertFalse(out['diagnostics']['native_execution_verified_by_module'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
