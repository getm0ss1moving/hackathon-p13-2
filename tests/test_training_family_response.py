"""模型格式包裹不能丢失合法合同，额外文本和冲突JSON仍需拒绝。"""
import json
import unittest
from unittest.mock import patch

from a160_fixtures import family_item
import runbook_matcher as matcher


FENCE = chr(96) * 3


class FamilyResponseTests(unittest.TestCase):
    def test_bare_or_single_json_fence_preserves_values(self):
        parameters = {"view": "ecs_creation_time", "filters": {"name": "vm_alpha"},
                      "required_filters": ["name"]}
        bare = json.dumps(parameters)
        for answer in [bare, " \n" + bare + "\n ", FENCE + "json\n" + bare + "\n" + FENCE,
                       FENCE + "\n" + bare + "\n" + FENCE, FENCE + "JSON\r\n" + bare + "\r\n" + FENCE]:
            with self.subTest(answer=answer):
                self.assertEqual(matcher._parse_family_response(answer), parameters)
        self.assertIsNone(matcher._parse_family_response(FENCE + "json\nnull\n" + FENCE))

    def test_multiple_objects_prose_unknown_fences_and_non_objects_are_rejected(self):
        for answer in ['说明：{"filters":{}}', '{} {}', '[]', '42', '"{}"',
                       FENCE + 'python\n{}\n' + FENCE,
                       FENCE + 'json\n{}\n' + FENCE + '\n额外说明',
                       FENCE + 'json\n{}\n' + FENCE + '\n' + FENCE + 'json\n{}\n' + FENCE,
                       FENCE + 'json\n{}', None, {}]:
            with self.subTest(answer=answer), self.assertRaises((ValueError, TypeError)):
                matcher._parse_family_response(answer)

    def test_duplicate_keys_and_nonfinite_values_are_rejected(self):
        for answer in ['{"view":"a","view":"b"}', '{"view":"a","view":"a"}',
                       '{"filters":{"name":"alpha","name":"beta"}}',
                       '{"top_k":NaN}', '{"top_k":Infinity}', '{"top_k":-Infinity}']:
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                matcher._parse_family_response(answer)

    def match(self, question, parameters):
        diagnostics = {}
        answer = FENCE + 'json\n' + json.dumps(parameters) + '\n' + FENCE
        with patch.object(matcher, 'llm_ask', return_value=answer), \
                patch.object(matcher, '_get_table_schemas', return_value='synthetic'), \
                patch.object(matcher, '_refine_sql', side_effect=lambda q, sql, *a, **k: sql):
            result = matcher._match_closed_view_candidate(question, family_item('F02'), diagnostics)
        return result, diagnostics

    def test_fenced_family_response_materializes_original_contract(self):
        parameters = {'view': 'ecs_creation_time', 'filters': {'name': 'vm_alpha'}, 'required_filters': ['name']}
        result, detail = self.match('查询ECSvm_alpha的创建时间', parameters)
        self.assertIsNotNone(result, detail)
        self.assertEqual(result['sql'], 'SELECT name, createdAt FROM CLOUD_VM_NOVA')
        self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'], 'vm_alpha')

    def test_fence_never_relaxes_question_grounding_or_adds_obligations(self):
        parameters = {'view': 'ecs_creation_time', 'filters': {'name': 'vm_alpha'}, 'required_filters': ['name']}
        for question in ['查询ECSvm_beta的创建时间', '查询ECSvm_alpha的创建时间以及secretMetric']:
            with self.subTest(question=question):
                result, _ = self.match(question, parameters)
                self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
