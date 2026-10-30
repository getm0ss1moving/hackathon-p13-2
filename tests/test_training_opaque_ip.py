"""IP角色明确时保留脱敏原文；无题号、模型或网络。"""
import unittest

import runbook_matcher as m


class OpaqueIPTests(unittest.TestCase):
    def test_deictic_or_explicit_ip_role_grounds_original_value(self):
        cases = [('opaque_alpha这个IP是哪台弹性IP', 'opaque_alpha'),
                 ('ip-alpha_2这个IP绑定哪台ECS', 'ip-alpha_2'),
                 ('IP地址为token_beta，查询绑定信息', 'token_beta'),
                 ('IP="address with spaces"，查询归属', 'address with spaces'),
                 ('“opaque_alpha”这个IP的归属', 'opaque_alpha'),
                 ('10.2.3.4这个IP归属哪台ECS', '10.2.3.4')]
        for question, value in cases:
            with self.subTest(question=question):
                parsed = {}
                m._auto_fill_params(question, parsed, ['fixedIpAddress'])
                self.assertEqual(parsed, {'fixedIpAddress': value})
                self.assertEqual(m._ground_params(question, parsed, {}), parsed)

    def test_no_ip_role_or_multiple_opaque_values_is_not_guessed(self):
        for question in ['查询实例opaque_alpha的信息', '返回name和IP列表',
                         'opaque_alpha这个IP和opaque_beta这个IP的归属',
                         'IP为opaque_alpha或者IP为opaque_beta', 'IP不是opaque_alpha',
                         'IP为opaque_alpha，IP为opaque_beta', '查询实例"IP为opaque_alpha"的信息']:
            with self.subTest(question=question):
                self.assertIsNone(m._explicit_ip_literal(question, 'fixedIpAddress'))

    def test_explicit_opposite_role_or_negation_cannot_reenter_legacy_ipv4_fallback(self):
        for question in ['浮动IP为10.2.3.4', 'IP不是10.2.3.4', 'IP为10.2.3.4或者IP为10.2.3.5']:
            with self.subTest(question=question):
                values = {}
                m._auto_fill_params(question, values, ['fixedIpAddress'])
                self.assertEqual(values, {})

    def test_explicit_floating_ip_does_not_fill_fixed_ip_role(self):
        self.assertIsNone(m._explicit_ip_literal('浮动IP为opaque_alpha', 'fixedIpAddress'))
        self.assertIsNone(m._explicit_ip_literal('弹性IP为opaque_alpha', 'fixedIpAddress'))

    def test_repeated_same_binding_and_entity_contents_do_not_create_extra_predicates(self):
        self.assertEqual(m._explicit_ip_literal('opaque_OR_alpha这个IP，IP为opaque_OR_alpha', 'fixedIpAddress'), 'opaque_OR_alpha')
        self.assertEqual(m._explicit_ip_literal('IP为"opaque_OR_alpha"', 'privateIps'), 'opaque_OR_alpha')


if __name__ == '__main__':
    unittest.main()
