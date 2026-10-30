"""提示中的F18组合必须与审定合同一致；不调用模型或数据服务。"""
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m


def capture_schema(family):
    prompts = []
    def ask(prompt, stage):
        prompts.append(prompt)
        raise ValueError("offline capture")
    with patch.object(m, "llm_ask", side_effect=ask):
        m._match_family_candidate("合成结构检查", {"family_id": family})
    line = next(line for line in prompts[0].splitlines() if line.startswith("JSON Schema："))
    return json.loads(line.removeprefix("JSON Schema："))


class FamilySchemaTests(unittest.TestCase):
    def test_all_eight_pairs_match_the_four_reviewed_contracts(self):
        schema = capture_schema("F18")
        self.assertTrue({"group", "metrics"} <= set(schema["required"]))
        reviewed = {("flavorCode", "count"), ("engineVersion", "count"),
                    ("haMode", "count"), ("vdcName", "count_storage")}
        for group, metric in itertools.product(["flavorCode", "vdcName", "engineVersion", "haMode"], ["count", "count_storage"]):
            values = {"group": group, "metrics": metric}
            # 只穷举本次新增const/enum分支，不冒充完整JSON Schema验证器。
            branches = sum(all(values[k] in choice["enum"] if "enum" in choice else values[k] == choice["const"]
                               for k, choice in branch["properties"].items()) for branch in schema["oneOf"])
            with self.subTest(group=group, metrics=metric):
                self.assertEqual(branches, int((group, metric) in reviewed))

    def test_runtime_rejection_is_retained_for_illegal_pairs(self):
        for group, metric in [("flavorCode", "count_storage"), ("engineVersion", "count_storage"),
                              ("haMode", "count_storage"), ("vdcName", "count")]:
            params = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"},
                      "required_filters": ["logicalRegionName"], "group": group, "metrics": metric}
            with self.subTest(group=group, metrics=metric), self.assertRaisesRegex(ValueError, "unreviewed_metric_group"):
                m._materialize_family({"family_id": "F18"}, params)

    def test_other_families_do_not_receive_the_f18_constraint(self):
        f18_constraint = capture_schema("F18")["oneOf"]
        for family in ["F01", "F08", "F14", "F20", "F21"]:
            with self.subTest(family=family):
                schema = capture_schema(family)
                self.assertNotEqual(schema.get("oneOf"), f18_constraint)
                if family != "F01":
                    self.assertNotIn("oneOf", schema)


if __name__ == "__main__": unittest.main()
