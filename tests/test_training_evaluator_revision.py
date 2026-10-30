"""数值相等性修订回归；仅合成数值，不读取题库或调用模型。"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
from evaluator import _vals_equal


class EvaluatorRevisionTests(unittest.TestCase):
    def test_hundredfold_errors_are_rejected_in_both_directions(self):
        for left, right in [(1, 100), (2, 200), (100, 1), (200, 2)]:
            with self.subTest(left=left, right=right):
                self.assertFalse(_vals_equal(left, right))

    def test_equal_and_close_numeric_values_match(self):
        for left, right in [(1, 1), (2, 2), (100, 105), (105, 100)]:
            with self.subTest(left=left, right=right):
                self.assertTrue(_vals_equal(left, right))

    def test_values_clearly_outside_relative_tolerance_are_rejected(self):
        self.assertFalse(_vals_equal(100, 112))
        self.assertFalse(_vals_equal(112, 100))

    def test_existing_absolute_and_null_rules_remain(self):
        self.assertTrue(_vals_equal(0, 0.005))
        self.assertTrue(_vals_equal(None, None))
        self.assertFalse(_vals_equal(None, 0))
