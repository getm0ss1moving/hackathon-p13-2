"""合成实体替换和参数边界，不读取白盒或封存集合。"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as matcher


class MultiwordProductTests(unittest.TestCase):
    def extract(self, question):
        values = {}
        matcher._auto_fill_params(question, values, ["productName", "logicalRegionName", "tenantName"])
        return values

    def test_synthetic_models_preserve_all_words(self):
        for value in ["Orion Rack X9", "Vendor Pro 880", "Chip R2-XL/A", "Model +900"]:
            with self.subTest(value=value):
                self.assertEqual(self.extract(f"查询型号为{value}的服务器数量")["productName"], value)

    def test_chinese_following_conditions_do_not_enter_model(self):
        result = self.extract("查询型号Model R 7在区域region_train8下的服务器")
        self.assertEqual(result["productName"], "Model R 7")
        self.assertEqual(result["logicalRegionName"], "region_train8")

    def test_punctuation_ends_model(self):
        self.assertEqual(self.extract("型号Model A 12，按区域统计")["productName"], "Model A 12")

    def test_explicit_quoted_chinese_name(self):
        self.assertEqual(self.extract('型号为“星际 Model 7”的设备')["productName"], "星际 Model 7")

    def test_conflicting_models_are_not_chosen(self):
        self.assertNotIn("productName", self.extract("型号Model A 1或型号Model B 2的设备"))

    def test_other_fields_do_not_expand_to_multiple_words(self):
        result = self.extract("查询租户tenant_alpha在区域region_beta下的服务器")
        self.assertEqual(result["tenantName"], "tenant_alpha")
        self.assertEqual(result["logicalRegionName"], "region_beta")

    def test_no_prefix_before_another_explicit_field(self):
        result = self.extract("productName=Model X tenantName=tenant_alpha")
        self.assertNotIn("productName", result)
        self.assertEqual(result["tenantName"], "tenant_alpha")

    def test_terminal_explicit_field_and_single_word(self):
        self.assertEqual(self.extract("productName=Model X 12")["productName"], "Model X 12")
        self.assertEqual(self.extract("型号Model9的服务器")["productName"], "Model9")


if __name__ == "__main__":
    unittest.main()
