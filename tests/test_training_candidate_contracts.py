"""候选能力边界与模型null的原文合同恢复；不按题号或实体路由。"""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from a160_fixtures import family_item
import runbook_matcher as m


class CandidateContractTests(unittest.TestCase):
    def test_architecture_request_excludes_only_family_without_that_attribute(self):
        family = family_item('F11_CORE')
        for question in ['区域region_alpha下物理服务器CPU架构类型统计',
                         '区域region_beta按cpuArch统计服务器数量']:
            self.assertEqual(m._candidate_attribute_conflict(question, family)['field'], 'cpuArch')
        self.assertIsNone(m._candidate_attribute_conflict('物理服务器CPU架构类型统计', {'id': 'synthetic_arch'}))

    def test_quoted_or_labeled_entity_contents_are_not_requested_output_columns(self):
        family = family_item('F11_CORE')
        for question in ['型号为"CPU架构"的服务器各区域数量', '型号为cpuArch的服务器各区域数量',
                         '区域region_cpuArch下物理服务器各厂商数量', '型号model_alpha的服务器数量及分布']:
            with self.subTest(question=question):
                self.assertIsNone(m._candidate_attribute_conflict(question, family))

    def test_model_selects_from_remaining_candidates_without_extra_calls(self):
        family = family_item('F11_CORE')
        ordinary = {'id': 'synthetic_arch', 'name': 'architecture statistics', 'examples': [],
                    'sql': 'SELECT cpuArch,COUNT(*) AS count FROM SYS_X86Server GROUP BY cpuArch',
                    'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000',
                                 'condition': {'constraint': [{'simple': {'name': 'logicalRegionName',
                                                            'value': '{{logicalRegionName}}', 'operator': 'equal'}}]}}}
        retriever = SimpleNamespace(retrieve=lambda q: [SimpleNamespace(id=family['id']), SimpleNamespace(id=ordinary['id'])])
        diagnostics = {}
        with patch.dict(os.environ, {'RUNBOOK_RULE_ONLY_FILL': '1'}), \
                patch.dict(m._schema_columns, {'S_X86Server': ['id', 'logicalRegionName', 'cpuArch']}), \
                patch.object(m, 'llm_ask', return_value='1'), \
                patch.object(m, '_get_table_schemas', return_value='synthetic'), \
                patch.object(m, '_refine_sql', side_effect=lambda q, sql, *a, **k: sql):
            result = m.match_runbook('查询区域region_alpha下物理服务器CPU架构类型统计',
                                     [family, ordinary], retriever, diagnostics)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(result['id'], ordinary['id'])
        self.assertEqual(diagnostics['selection']['offered_ids'], [ordinary['id']])
        self.assertEqual(diagnostics['candidate_contract_exclusions'][0]['id'], family['id'])

    def fill(self, question, answer='null'):
        diagnostics = {}
        with patch.object(m, 'llm_ask', return_value=answer), \
                patch.object(m, '_get_table_schemas', return_value='synthetic'), \
                patch.object(m, '_refine_sql', side_effect=lambda q, sql, *a, **k: sql):
            result = m._match_a160_candidate(question, family_item('F26'), diagnostics)
        return result, diagnostics

    def test_null_is_recovered_only_when_original_question_has_one_complete_contract(self):
        result, diagnostics = self.fill('查询虚拟防火墙firewall_alpha的基本信息')
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(result['sql'], 'SELECT name, status FROM CLOUD_VFW')
        self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'], 'firewall_alpha')
        self.assertIn('family_null_recovery', diagnostics)

    def test_null_does_not_discard_unknown_obligations_or_invent_missing_entities(self):
        for question in ['查询虚拟防火墙基本信息', '查询虚拟防火墙firewall_alpha的基本信息及绑定云硬盘',
                         '查询虚拟防火墙名称为alpha或者名称为beta的基本信息',
                         '查询虚拟防火墙firewall_alpha的基本信息，输出secretMetric']:
            with self.subTest(question=question):
                result, diagnostics = self.fill(question)
                self.assertIsNone(result)
                self.assertNotIn('family_null_recovery', diagnostics)

    def test_non_null_wrong_entities_are_rejected_without_rewriting(self):
        result, diagnostics = self.fill('查询虚拟防火墙firewall_alpha的基本信息',
                                        '{"view":"rows","filters":{"name":"wrong_entity"},"required_filters":["name"]}')
        self.assertIsNone(result)
        self.assertNotIn('family_null_recovery', diagnostics)


if __name__ == '__main__':
    unittest.main()
