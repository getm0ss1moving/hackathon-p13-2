"""前置名字、漏值和资源词边界的正反控制；不读用例或参考。"""
import json
import unittest
from unittest.mock import patch

from a160_fixtures import family_item
import runbook_matcher as m


class MissingParameterRecoveryTests(unittest.TestCase):
    def test_single_resource_request_excludes_unrelated_single_table_API_only(self):
        pool = {'sql': 'SELECT COUNT(*) AS count FROM CLOUD_STORAGE_POOL',
                'api_call': {'url': '/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000'}}
        self.assertEqual(m._candidate_unavailable_resource('查询租户tenant_alpha下ECS IP列表', pool)['resource'], 'VM_NOVA')
        self.assertIsNone(m._candidate_unavailable_resource('查询存储池数量', pool))
        multi = dict(pool, api_call=[pool['api_call'], {'url': '/rest/hackthon/db/instances/VM_NOVA'}])
        self.assertIsNone(m._candidate_unavailable_resource('查询ECS IP列表', multi))
        self.assertIsNone(m._candidate_unavailable_resource('查询ECS及存储池数量', pool))

    def test_cluster_name_before_role_is_filled_in_original_namespace(self):
        item = {'api_call': {'url': '/rest/hackthon/db/instances/CLUSTER', 'condition': {
            'constraint': [{'simple': {'name': 'name', 'value': '{{name}}'}}]}}}
        for question, expected in [('cluster_alpha集群下的宿主机', 'cluster_alpha'),
                                   ('"cluster with spaces"集群的虚拟机', 'cluster with spaces'),
                                   ('查询集群名称为"cluster_alpha"的宿主机', 'cluster_alpha')]:
            values = {}
            m._auto_fill_params(question, values, ['name'], item)
            self.assertEqual(values, {'name': expected})

    def test_negated_or_multiple_cluster_names_are_not_guessed(self):
        for question in ['不是cluster_alpha集群', 'cluster_alpha集群或者cluster_beta集群',
                         'cluster_alpha集群和cluster_beta集群', '查询名称为"cluster_alpha集群"的宿主机']:
            self.assertIsNone(m._preposed_cluster_name(question))

    def match(self, question, parameters):
        details = {}
        with patch.object(m, 'llm_ask', return_value=json.dumps(parameters)), \
                patch.object(m, '_get_table_schemas', return_value='synthetic'), \
                patch.object(m, '_refine_sql', side_effect=lambda q, sql, *a, **k: sql):
            ordinary = m._match_closed_view_candidate(question, family_item('F02'), details)
        return ordinary, details

    def test_bare_ecs_role_misparsed_as_name_is_repaired_only_by_full_question_proof(self):
        params = {'view': 'ecs_cluster_zone', 'filters': {'name': 'ECSvm_alpha'}, 'required_filters': ['name']}
        result, details = self.match('查询ECSvm_alpha属于哪个集群、哪个可用区', params)
        self.assertIsNotNone(result, details)
        self.assertEqual(result['sql'], 'SELECT name, clusterName, azoneName FROM CLOUD_VM_NOVA')
        self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'], 'vm_alpha')
        self.assertIn('parameter_recovery', details)

    def test_explicitly_named_ecs_prefix_is_kept_as_entity_content(self):
        params = {'view': 'ecs_cluster_zone', 'filters': {'name': 'ECSvm_alpha'}, 'required_filters': ['name']}
        result, details = self.match('查询ECS名称为"ECSvm_alpha"属于哪个集群、哪个可用区', params)
        self.assertIsNotNone(result, details)
        self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'], 'ECSvm_alpha')
        wrong = dict(params, filters={'name': 'vm_alpha'})
        result, _ = self.match('查询ECS名称为"ECSvm_alpha"属于哪个集群、哪个可用区', wrong)
        self.assertIsNone(result)

    def test_missing_tenant_and_required_slot_are_completed_from_explicit_role(self):
        params = {'view': 'ecs_ip_tenant', 'filters': {'tenantName': None, 'logicalRegionName': 'region_alpha',
                   'azoneName': 'zone_alpha'}, 'required_filters': ['logicalRegionName', 'azoneName']}
        question = '查询租户tenant_alpha在区域region_alpha可用区zone_alpha中的ECS IP列表'
        result, details = self.match(question, params)
        self.assertIsNotNone(result, details)
        self.assertEqual(result['sql'], 'SELECT name, privateIps, status FROM CLOUD_VM_NOVA')
        actual = {e['simple']['name']: e['simple']['value'] for e in result['api_call']['condition']['constraint']}
        self.assertEqual(actual, {'tenantName': 'tenant_alpha', 'logicalRegionName': 'region_alpha', 'azoneName': 'zone_alpha'})

    def test_nonempty_conflicting_entity_extra_obligation_and_disjunction_still_reject(self):
        params = {'view': 'ecs_filtered_list', 'filters': {'tenantName': 'wrong_tenant', 'logicalRegionName': 'region_alpha',
                  'azoneName': 'zone_alpha'}, 'required_filters': ['tenantName', 'logicalRegionName', 'azoneName']}
        q = '查询租户tenant_alpha在区域region_alpha可用区zone_alpha中的ECS IP列表'
        self.assertIsNone(self.match(q, params)[0])
        params['filters']['tenantName'] = None
        for question in [q + '，并输出secretMetric', q + '或者租户tenant_beta']:
            self.assertIsNone(self.match(question, params)[0])


if __name__ == '__main__':
    unittest.main()
