"""原评分器的空结果/未作答/错误区别；没有网络和真实题目。"""
import unittest
from evaluator import evaluate_case


class BlankContractTests(unittest.TestCase):
    def setUp(self):
        self.case = {'case_id': 'SYNTHETIC', 'question': '合成查询', 'sql': 'SELECT name FROM synthetic',
                     'api_call': {'method': 'GET', 'url': '/synthetic'},
                     'answer': {'columns': ['name'], 'rows': [], 'row_count': 0}}
        self.output = {'matched_runbook': 'synthetic', 'api_call': self.case['api_call'],
                       'sql': self.case['sql'], 'result': self.case['answer'], 'error': None}

    def test_valid_empty_answer_receives_five(self):
        self.assertEqual(evaluate_case(self.case, self.output, 0)['score'], 5)

    def test_missing_match_receives_zero_even_when_reference_is_empty(self):
        self.assertEqual(evaluate_case(self.case, dict(self.output, matched_runbook=None), 0)['score'], 0)

    def test_forced_empty_is_wrong_when_reference_has_rows(self):
        self.case['answer'] = {'columns': ['name'], 'rows': [{'name': 'synthetic_value'}], 'row_count': 1}
        self.assertEqual(evaluate_case(self.case, self.output, 0)['score'], -1)

    def test_zero_count_is_a_row_and_does_not_equal_blank(self):
        self.case['sql'] = 'SELECT COUNT(*) AS total FROM synthetic'
        self.case['answer'] = {'columns': ['total'], 'rows': [{'total': 0}], 'row_count': 1}
        self.assertEqual(evaluate_case(self.case, dict(self.output, sql=self.case['sql'], result=self.case['answer']), 0)['score'], 5)
        self.assertEqual(evaluate_case(self.case, self.output, 0)['score'], -1)

    def test_execution_error_does_not_become_a_valid_empty_answer(self):
        self.assertEqual(evaluate_case(self.case, dict(self.output, error='synthetic failed request'), 0)['score'], -1)


if __name__ == '__main__': unittest.main()
