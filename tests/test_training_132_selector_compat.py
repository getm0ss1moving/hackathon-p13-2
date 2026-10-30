"""仅合成132式额外元数据兼容控制；不代表实际132源码/运行验收。"""
import copy
import unittest

import runbook_matcher as matcher
from test_training_selector_cards import F02_BASE, F19_BASE, family_fixture


class SelectorMetadataCompatibilityTests(unittest.TestCase):
    def test_f02_natural_view_metadata_keeps_verified_core_pairs_visible(self):
        original = family_fixture('F02')
        expected = matcher._format_runbook_list([original])
        # natural_views的实际Schema尚未交付。本控制只要求额外描述元数据
        # 不影响旧profiles；不按这些合成键物化或宣称新view已获支持。
        for metadata in [[], {'synthetic_new_view': {'columns': ['unverified_alias']}},
                         [{'view': 'synthetic_new_view', 'columns': ['unverified_alias']}]]:
            item = copy.deepcopy(original)
            item['parameter_contract']['natural_views'] = metadata
            before = copy.deepcopy(item)
            with self.subTest(metadata=metadata):
                card = matcher._format_runbook_list([item])
                self.assertEqual(card, expected)
                self.assertEqual(card.count('←全部等值筛选('), 7)
                self.assertNotIn('unverified_alias', card)
                self.assertNotIn('synthetic_new_view', card)
                self.assertEqual(item, before)

    def test_extension_does_not_certify_an_invalid_core_profile(self):
        item = family_fixture('F02')
        item['parameter_contract']['natural_views'] = []
        item['parameter_contract']['profiles'][0]['filters'] = ['unknown_field']
        self.assertEqual(matcher._format_runbook_list([item]), F02_BASE)

    def test_other_unknown_contract_keys_remain_rejected(self):
        item = family_fixture('F02')
        item['parameter_contract'].update(natural_views=[], unreviewed_semantics={})
        self.assertEqual(matcher._format_runbook_list([item]), F02_BASE)

    def test_extension_is_limited_to_the_documented_f02_family(self):
        item = family_fixture('F19')
        item['parameter_contract']['natural_views'] = []
        self.assertEqual(matcher._format_runbook_list([item]), F19_BASE)


if __name__ == '__main__':
    unittest.main()
