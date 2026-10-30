"""A已证区域名称→ID绑定：完整响应、单解及失败停止，不猜测区域ID。"""
import copy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runbook_matcher as m
import runbook_system as system


class LogicalRegionScopeTests(unittest.TestCase):
    def setUp(self):
        self.item = {'id': 'synthetic_cloud_service', 'name': 'synthetic service counts', 'examples': [],
                     'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/S_CloudService?pageNo=1&pageSize=10000'},
                     'sql': 'SELECT indexName,COUNT(*) AS instance_count FROM SYS_CloudService GROUP BY indexName'}
        context = patch.dict(m._schema_columns, {'AZONE': ['id', 'logicalRegionName', 'logicalRegionId'],
                                                'S_CloudService': ['id', 'logicalRegionId', 'indexName']})
        context.start()
        self.addCleanup(context.stop)

    def payload(self, ids):
        rows = [{'id': 'az_' + str(i), 'logicalRegionName': 'region_alpha', 'logicalRegionId': value}
                for i, value in enumerate(ids)]
        return {'objList': rows, 'totalNum': len(rows), 'totalPageNo': int(bool(rows)),
                'currentPage': 1, 'pageSize': 1000}

    def session(self, payload):
        client = SimpleNamespace()
        client.get = unittest.mock.Mock(return_value=SimpleNamespace(status_code=200, json=lambda: payload))
        client.mount = lambda *a, **k: None
        client.close = lambda: None
        return client

    def resolve(self, ids, item=None):
        item = copy.deepcopy(item or self.item)
        client = self.session(self.payload(ids))
        with patch.object(system.requests, 'Session', return_value=client):
            evidence = m._resolve_logical_region_scope(item, {'logicalRegionName': 'region_alpha'})
        self.assertEqual(client.get.call_count, 1)
        self.assertIn('/instances/AZONE?', client.get.call_args.args[0])
        return item, evidence

    def test_unique_id_from_multiple_catalog_rows_is_bound_without_changing_sql(self):
        original = copy.deepcopy(self.item)
        item, evidence = self.resolve(['canonical_alpha', 'canonical_alpha'])
        self.assertTrue(evidence['valid'], evidence)
        self.assertEqual(evidence['status'], 'resolved')
        self.assertEqual(item['sql'], original['sql'])
        self.assertEqual(item['api_call']['condition']['constraint'][0]['simple'],
                         {'name': 'logicalRegionId', 'value': 'canonical_alpha', 'operator': 'equal'})

    def test_same_reviewed_region_namespace_binds_deployment_nodes(self):
        item = copy.deepcopy(self.item)
        item['api_call']['url'] = item['api_call']['url'].replace('S_CloudService', 'S_DeployNode')
        item['sql'] = 'SELECT hostClass,COUNT(*) AS count FROM SYS_DeployNode GROUP BY hostClass'
        with patch.dict(os.environ, {'RUNBOOK_BIND_DEPLOY_NODE_REGION': '1'}), \
                patch.dict(m._schema_columns, {'S_DeployNode': ['id', 'logicalRegionId', 'hostClass']}):
            result, evidence = self.resolve(['canonical_alpha'], item)
        self.assertTrue(evidence['valid'], evidence)
        self.assertEqual(evidence['target_field'], 'S_DeployNode.logicalRegionId')
        self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'], 'canonical_alpha')

    def test_deployment_node_candidate_is_off_without_explicit_flag(self):
        item = copy.deepcopy(self.item)
        item['api_call']['url'] = item['api_call']['url'].replace('S_CloudService', 'S_DeployNode')
        item['sql'] = 'SELECT hostClass,COUNT(*) AS count FROM SYS_DeployNode GROUP BY hostClass'
        with patch.dict(os.environ, {'RUNBOOK_BIND_DEPLOY_NODE_REGION': '0'}):
            self.assertIsNone(m._resolve_logical_region_scope(item, {'logicalRegionName': 'region_alpha'}))

    def test_unknown_ambiguous_and_missing_ids_leave_target_unbound(self):
        for ids, status in [([], 'unknown'), (['one', 'two'], 'ambiguous'), ([None], 'incomplete'), ([''], 'incomplete')]:
            with self.subTest(ids=ids):
                item, evidence = self.resolve(ids)
                self.assertFalse(evidence['valid'])
                self.assertEqual(evidence['status'], status)
                self.assertFalse(evidence['target_query_permitted'])
                self.assertEqual(item, self.item)

    def test_existing_predicates_are_preserved_and_conflicting_id_is_rejected(self):
        item = copy.deepcopy(self.item)
        predicate = {'simple': {'name': 'logicalRegionId', 'value': 'other', 'operator': 'equal'}}
        item['api_call']['condition'] = {'constraint': [predicate]}
        actual, evidence = self.resolve(['canonical_alpha'], item)
        self.assertFalse(evidence['valid'])
        self.assertEqual(evidence['reason'], 'conflicting_existing_region_filter')
        self.assertEqual(actual, item)

    def test_transport_and_error_envelopes_are_never_an_empty_success(self):
        payloads = [dict(self.payload([]), error='failure'), {'objList': []},
                    dict(self.payload([]), totalNum=1), dict(self.payload([]), success=False)]
        for payload in payloads:
            item = copy.deepcopy(self.item)
            with self.subTest(payload=payload), patch.object(system.requests, 'Session', return_value=self.session(payload)):
                evidence = m._resolve_logical_region_scope(item, {'logicalRegionName': 'region_alpha'})
                self.assertEqual(evidence['status'], 'error')
                self.assertFalse(evidence['valid'])
                self.assertEqual(item, self.item)
        with patch.object(system, '_execute_bounded_api', side_effect=RuntimeError('synthetic transport failure')):
            evidence = m._resolve_logical_region_scope(copy.deepcopy(self.item), {'logicalRegionName': 'region_alpha'})
        self.assertEqual(evidence['status'], 'error')

    def test_unknown_region_stops_before_target_execute_and_refinement(self):
        query = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        query.items = [copy.deepcopy(self.item)]
        query.retriever = SimpleNamespace(retrieve=lambda q: [SimpleNamespace(id=self.item['id'])])
        client = self.session(self.payload([]))
        with patch.object(system.requests, 'Session', return_value=client), \
                patch.object(m, 'llm_ask', return_value='1'), \
                patch.object(m, '_refine_sql') as refine, patch.object(system, 'execute') as execute:
            answer = query.query('查询区域region_alpha下各云服务的微服务实例数量')
        self.assertIsNone(answer['matched_runbook'])
        self.assertEqual(answer['diagnostics']['rejection']['reason'], 'unresolved_logical_region_scope')
        self.assertEqual(client.get.call_count, 1)
        self.assertIn('/instances/AZONE?', client.get.call_args.args[0])
        refine.assert_not_called()
        execute.assert_not_called()

    def test_other_ci_and_unsupported_or_or_url_conditions_are_not_generalized(self):
        for variant in ['other_ci', 'or', 'url']:
            item = copy.deepcopy(self.item)
            if variant == 'other_ci':
                item['api_call']['url'] = item['api_call']['url'].replace('S_CloudService', 'MIDDLEWARE')
            elif variant == 'or':
                item['api_call']['condition'] = {'constraint': [{'simple': {'name': 'id', 'value': 'a'}, 'logOp': 'or'}]}
            else:
                item['api_call']['url'] += '&condition=unreviewed'
            with self.subTest(variant=variant), patch.object(system, '_execute_bounded_api') as lookup:
                evidence = m._resolve_logical_region_scope(item, {'logicalRegionName': 'region_alpha'})
                self.assertTrue(evidence is None or not evidence['valid'])
                lookup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
