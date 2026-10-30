"""用户合并版评分修订；仅合成输入及固定150标准答案自比，无模型/留出。"""
import ast
import hashlib
from pathlib import Path
import subprocess
import unittest

import evaluator
from training_data import load_training

ROOT = Path(__file__).resolve().parents[1]


def result(columns, rows, count=None):
    return {"columns": columns, "rows": rows, "row_count": len(rows) if count is None else count}


class AliasExtraColumnRevisionTests(unittest.TestCase):
    def test_renamed_columns_and_extra_values_can_match(self):
        standard = result(["original_name", "original_status"], [{"original_name": "alpha", "original_status": "active"}])
        renamed = result(["name", "state"], [{"name": "alpha", "state": "active"}])
        extended = result(["name", "state", "extra"], [{"name": "alpha", "state": "active", "extra": "ignored"}])
        self.assertEqual(evaluator._compare_answers(standard, renamed), (True, 1.0))
        self.assertEqual(evaluator._compare_answers(standard, extended), (True, 1.0))

    def test_equal_names_keep_existing_extra_column_behavior(self):
        standard = result(["name"], [{"name": "alpha"}])
        extended = result(["name", "extra"], [{"name": "alpha", "extra": "ignored"}])
        self.assertEqual(evaluator._compare_answers(standard, extended), (True, 1.0))

    def test_wrong_or_missing_values_never_receive_full_credit(self):
        standard = result(["a", "b"], [{"a": "alpha", "b": "active"}])
        for actual in [result(["x", "y", "z"], [{"x": "alpha", "y": "wrong", "z": "ignored"}]),
                       result(["x", "y", "z"], [{"x": "active", "y": "wrong", "z": "ignored"}]),
                       result(["x"], [{"x": "alpha"}]), result(["a"], [{"a": "alpha"}])]:
            with self.subTest(actual=actual):
                self.assertFalse(evaluator._compare_answers(standard, actual)[0])

    def test_duplicate_standard_values_cannot_reuse_one_system_value(self):
        self.assertFalse(evaluator._tuples_match(("alpha", "alpha"), ("alpha", "beta", "extra")))
        self.assertTrue(evaluator._tuples_match(("alpha", "alpha"), ("alpha", "alpha", "extra")))

    def test_equal_width_preserves_ordered_tuple_logic(self):
        self.assertFalse(evaluator._tuples_match(("alpha", "active"), ("active", "alpha")))
        self.assertFalse(evaluator._tuples_match(("alpha", "active"), ("alpha",)))

    def test_row_count_and_duplicate_row_mismatch_still_deduct(self):
        standard = result(["name"], [{"name": "alpha"}])
        wrong_count = result(["alias", "extra"], [{"alias": "alpha", "extra": "ignored"}], count=2)
        self.assertEqual(evaluator._compare_answers(standard, wrong_count), (False, 0.5))
        duplicate_standard = result(["name"], [{"name": "alpha"}, {"name": "alpha"}])
        one_match = result(["alias", "extra"], [{"alias": "alpha", "extra": "x"}, {"alias": "beta", "extra": "x"}])
        self.assertEqual(evaluator._compare_answers(duplicate_standard, one_match), (False, 0.5))

    def test_exactly_three_functions_differ_from_original_with_authorized_ratio1(self):
        source = subprocess.check_output(["git", "show", "d79c316:implementation/evaluator.py"], cwd=ROOT)
        original = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef)}
        revised = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse((ROOT / "implementation/evaluator.py").read_text()).body
                   if isinstance(node, ast.FunctionDef)}
        self.assertEqual(set(original), set(revised))
        self.assertEqual({name for name in original if original[name] != revised[name]}, {"_vals_equal", "_tuples_match", "_compare_answers"})
        self.assertEqual(hashlib.sha256((ROOT / "implementation/evaluator.py").read_bytes()).hexdigest(),
                         "f936c85a3490bc4d927c65736aa0860b6cc03c3141a540e896859909eb28808b")

    def test_numeric_fix_also_applies_inside_renamed_extra_column_fallback(self):
        standard = result(["expected"], [{"expected": 2}])
        hundredfold = result(["alias", "extra"], [{"alias": 200, "extra": "ignored"}])
        close = result(["alias", "extra"], [{"alias": 2.1, "extra": "ignored"}])
        self.assertFalse(evaluator._compare_answers(standard, hundredfold)[0])
        self.assertEqual(evaluator._compare_answers(standard, close), (True, 1.0))

    def test_original_and_revised_fixed_training_standard_self_comparisons_agree(self):
        source = subprocess.check_output(["git", "show", "d79c316:implementation/evaluator.py"], cwd=ROOT)
        original = {"__file__": str(ROOT / "implementation/evaluator.py"), "__name__": "original_scorer_control"}
        exec(compile(source, "original_d79c316.py", "exec"), original)
        _, train, _ = load_training()
        self.assertEqual(len(train), 150)
        for case in train:
            with self.subTest(case=case["case_id"]):
                answer = case.get("answer")
                before = original["_compare_answers"](answer, answer)
                after = evaluator._compare_answers(answer, answer)
                self.assertEqual(before, after)
                self.assertEqual(after, (True, 1.0))


if __name__ == "__main__":
    unittest.main()
