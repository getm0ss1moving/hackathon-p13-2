"""显式枚举仅对齐同CI同字段已观察到的大小写，不改实体名称。"""
import unittest
from unittest.mock import patch

import runbook_matcher as m


class SchemaEnumCaseTests(unittest.TestCase):
    def setUp(self):
        self.item = {'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000',
                     'condition': {'constraint': [{'simple': {'name': 'hypervisorType', 'value': '{{hypervisorType}}', 'operator': 'equal'}}]}}}

    def test_explicit_hypervisor_value_uses_native_enum_case(self):
        with patch.dict(m._schema_values, {'HOST': {'hypervisorType': ['unknown', 'kvm']}}):
            rules = {}
            m._auto_fill_params('查询KVM虚拟化类型的宿主机', rules, ['hypervisorType'], self.item)
            final = m._ground_params('查询KVM虚拟化类型的宿主机', rules, self.item)
            self.assertEqual(final, {'hypervisorType': 'kvm'})
            self.assertTrue(m._fill_params(self.item, final, '查询KVM虚拟化类型的宿主机'))
            self.assertEqual(self.item['api_call']['condition']['constraint'][0]['simple']['value'], 'kvm')

    def test_documented_code_works_when_samples_omit_it_without_inventing_a_filter(self):
        with patch.dict(m._schema_values, {'HOST': {'hypervisorType': ['unknown']}, 'VM_NOVA': {'hypervisorType': ['kvm']}}):
            self.assertEqual(m._ground_params('查询宿主机数量', {'hypervisorType': 'kvm'}, self.item), {})
            self.assertEqual(m._canonical_enum(self.item, 'hypervisorType', 'KVM'), 'kvm')
            self.assertEqual(m._canonical_enum(self.item, 'hypervisorType', 'FutureType'), 'FutureType')

    def test_instance_name_with_same_letters_is_preserved(self):
        named = {'api_call': {'url': '/rest/hackthon/db/instances/HOST',
                  'condition': {'constraint': [{'simple': {'name': 'name', 'value': '{{name}}'}}]}}}
        self.assertEqual(m._ground_params('宿主机名称为KVM', {'name': 'KVM'}, named), {'name': 'KVM'})


if __name__ == '__main__':
    unittest.main()
