"""枚举只接受已知语义映射或真实目录值；全部合成字段样例。"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m


def item(ci="HOST", field="status"):
    return {"api_call": {"url": "/rest/hackthon/db/instances/"+ci, "condition": {"constraint": [
        {"simple": {"name": field, "value": "{{"+field+"}}"}}]}}}


class EnumLabelTests(unittest.TestCase):
    def setUp(self):
        context = patch.dict(os.environ, {"RUNBOOK_GROUND_ENUM_LABELS": "1"})
        context.start()
        self.addCleanup(context.stop)
        context = patch.object(m, "_schema_values", {"HOST": {"status": ["normal", "fault"]}, "VOLUME": {"bootable": [True, False]}})
        context.start()
        self.addCleanup(context.stop)

    def test_untranslated_label_does_not_become_api_value(self):
        details = {}
        self.assertEqual(m._ground_params("运行中的主机", {"status": "运行中"}, item(), details), {})
        self.assertEqual(details["unmapped_enum_labels"][0]["resource"], "HOST")

    def test_known_semantics_translate(self):
        self.assertEqual(m._ground_params("正常的主机", {"status": "正常"}, item()), {"status": "normal"})

    def test_observed_chinese_catalog_value_is_allowed(self):
        with patch.object(m, "_schema_values", {"HOST": {"status": ["检修", "在用"]}}):
            self.assertEqual(m._ground_params("状态为检修", {"status": "检修"}, item()), {"status": "检修"})

    def test_explicit_ascii_state_is_not_rejected(self):
        self.assertEqual(m._ground_params("status=CUSTOM_STATE", {"status": "CUSTOM_STATE"}, item()), {"status": "custom_state"})

    def test_false_boolean_stays_false(self):
        self.assertEqual(m._ground_params("不可启动的磁盘", {"bootable": False}, item("VOLUME", "bootable")), {"bootable": False})

    def test_conflicting_labels_are_not_chosen(self):
        self.assertEqual(m._ground_params("状态正常或故障", {"status": "正常或故障"}, item()), {})

    def test_disabled_flag_preserves_previous_behavior(self):
        with patch.dict(os.environ, {"RUNBOOK_GROUND_ENUM_LABELS": "0"}):
            self.assertEqual(m._ground_params("运行中", {"status": "运行中"}, item()), {"status": "运行中"})


if __name__ == "__main__":
    unittest.main()
