"""最新版仅两处修改，数值函数保留最初版语义；旧ratio1测试已留档。"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
from evaluator import _vals_equal


class EvaluatorRevisionTests(unittest.TestCase):
    def test_original_hundredfold_comparison_is_unchanged_in_latest_revision(self):
        for left, right in [(1, 100), (2, 200), (100, 1), (200, 2)]:
            with self.subTest(left=left, right=right):
                self.assertTrue(_vals_equal(left, right))

    def test_exact_values_match_and_old_relative_rule_remains(self):
        for left, right in [(1, 1), (2, 2)]:
            with self.subTest(left=left, right=right):
                self.assertTrue(_vals_equal(left, right))
        self.assertFalse(_vals_equal(100, 105))
        self.assertFalse(_vals_equal(105, 100))

    def test_values_clearly_outside_relative_tolerance_are_rejected(self):
        self.assertFalse(_vals_equal(100, 112))
        self.assertFalse(_vals_equal(112, 100))

    def test_existing_absolute_and_null_rules_remain(self):
        self.assertTrue(_vals_equal(0, 0.005))
        self.assertTrue(_vals_equal(None, None))
        self.assertFalse(_vals_equal(None, 0))
