"""猜空出口、原失败证据和未修改评分器的正反控制；不调用网络或模型。"""
import copy
import os
import unittest
from unittest.mock import patch

from evaluator import evaluate_case
import runbook_system as system


class EmptyAnswerFallbackTests(unittest.TestCase):
    def setUp(self):
        self.flags = patch.dict(os.environ, {"RUNBOOK_EMPTY_ANSWER_FALLBACK": "1"})
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.instance = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)

    def blank_case(self, *, filtered=False, nonempty=False):
        api = {"method": "GET", "url": "/synthetic"}
        if filtered:
            api["condition"] = {"constraint": [{"simple": {
                "name": "name", "value": "example", "operator": "equal"}}]}
        return {"case_id": "SYNTHETIC", "question": "合成问题", "api_call": api,
                "sql": "SELECT name FROM synthetic",
                "answer": {"columns": ["name"],
                           "rows": [{"name": "example"}] if nonempty else [],
                           "row_count": int(nonempty)}}

    def refusal(self):
        return {"question": "合成问题", "matched_runbook": None, "api_call": None,
                "sql": None, "result": None, "error": None,
                "diagnostics": {"rejection": {"stage": "matching", "reason": "resource_mismatch"}}}

    def test_default_is_enabled_and_records_a_guess(self):
        os.environ.pop("RUNBOOK_EMPTY_ANSWER_FALLBACK")
        output = system._apply_empty_answer_fallback(self.refusal())
        self.assertEqual(output["matched_runbook"], "empty_answer_fallback")
        self.assertEqual(output["result"], {"columns": ["value"], "rows": [], "row_count": 0})
        evidence = output["diagnostics"]["empty_answer_fallback"]
        self.assertTrue(evidence["answer_is_guess"])
        self.assertFalse(evidence["source_result_verified"])
        self.assertEqual(evidence["additional_model_requests"], 0)
        self.assertEqual(evidence["additional_http_requests"], 0)
        self.assertEqual(output["diagnostics"]["rejection"]["reason"], "resource_mismatch")

    def test_can_restore_abstention_for_a_control(self):
        output = self.refusal()
        with patch.dict(os.environ, {"RUNBOOK_EMPTY_ANSWER_FALLBACK": "0"}):
            self.assertIs(system._apply_empty_answer_fallback(output), output)
            self.assertIsNone(output["matched_runbook"])
            self.assertNotIn("empty_answer_fallback", output["diagnostics"])

    def test_normal_answers_including_count_zero_are_unchanged(self):
        for result in [self.blank_case()["answer"], self.blank_case(nonempty=True)["answer"],
                       {"columns": ["total"], "rows": [{"total": 0}], "row_count": 1}]:
            output = dict(self.refusal(), matched_runbook="real_selection", result=result)
            self.assertIs(system._apply_empty_answer_fallback(output), output)
            self.assertNotIn("empty_answer_fallback", output["diagnostics"])

    def test_original_execution_error_is_retained_as_evidence(self):
        output = dict(self.refusal(), matched_runbook="real_selection", sql="SELECT absent FROM synthetic",
                      error="no such column: absent", api_call=self.blank_case(filtered=True)["api_call"])
        guess = system._apply_empty_answer_fallback(output)
        evidence = guess["diagnostics"]["empty_answer_fallback"]
        self.assertEqual(evidence["original_error"], output["error"])
        self.assertEqual(evidence["original_sql"], output["sql"])
        self.assertEqual(evidence["original_matched_runbook"], "real_selection")
        self.assertEqual(guess["api_call"], output["api_call"])
        self.assertIsNone(guess["error"])

    def test_original_scorer_gives_five_only_for_matching_empty(self):
        guess = system._apply_empty_answer_fallback(self.refusal())
        self.assertEqual(evaluate_case(self.blank_case(), guess, 0)["score"], 5)
        self.assertEqual(evaluate_case(self.blank_case(nonempty=True), guess, 0)["score"], -1)

    def test_api_hard_gate_is_not_bypassed_by_fabricated_conditions(self):
        case = self.blank_case(filtered=True)
        guess = system._apply_empty_answer_fallback(self.refusal())
        self.assertIsNone(guess["api_call"])
        self.assertEqual(evaluate_case(case, guess, 0)["score"], 0)
        with_actual_api = system._apply_empty_answer_fallback(dict(self.refusal(), api_call=case["api_call"]))
        self.assertEqual(evaluate_case(case, with_actual_api, 0)["score"], 5)

    def test_query_no_match_adds_no_execution_or_model_request(self):
        self.instance.items, self.instance.retriever = [], object()
        with patch.object(system, "match_runbook", return_value=None) as match, \
                patch.object(system, "get_llm_events", return_value=[]), \
                patch.object(system, "execute") as execute, \
                patch.object(system, "_execute_bounded_api") as bounded:
            answer = self.instance.query("全新合成问题")
        match.assert_called_once()
        execute.assert_not_called()
        bounded.assert_not_called()
        self.assertEqual(answer["matched_runbook"], "empty_answer_fallback")

    def test_query_result_guard_still_rejects_before_empty_guess(self):
        self.instance.items, self.instance.retriever = [], object()
        item = {"name": "real_selection", "api_call": self.blank_case(filtered=True)["api_call"],
                "sql": "SELECT name FROM synthetic"}
        execution = {"sql": item["sql"], "result": {"columns": [], "rows": [], "row_count": 0}, "error": None}
        flags = {name: "0" for name in ["RUNBOOK_BOUNDED_API", "RUNBOOK_SG_RULE_SEMIJOIN",
                                        "RUNBOOK_TYPED_EMPTY_ROOT", "RUNBOOK_VERIFIED_EMPTY_ROOT"]}
        with patch.dict(os.environ, flags), patch.object(system, "match_runbook", return_value=item), \
                patch.object(system, "get_llm_events", return_value=[]), \
                patch.object(system, "execute", return_value=execution) as execute:
            answer = self.instance.query("合成查询")
        execute.assert_called_once_with(item)
        self.assertEqual(answer["diagnostics"]["rejection"]["reason"], "unverified_result_schema")
        self.assertEqual(answer["matched_runbook"], "empty_answer_fallback")
        self.assertEqual(answer["api_call"], item["api_call"])
        self.assertEqual(evaluate_case(self.blank_case(filtered=True), answer, 0)["score"], 5)

    def test_policy_does_not_intercept_budget_or_unhandled_exceptions(self):
        with patch.object(self.instance, "_query", side_effect=RuntimeError("budget exhausted")):
            with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
                self.instance.query("合成查询")

    def test_policy_does_not_depend_on_failure_reason_or_question(self):
        for reason in ["missing_parameters", "resource_mismatch", "unverified_api_condition", "invalid_family_parameters"]:
            output = self.refusal()
            output["question"] = "不同的合成问题" + reason
            output["diagnostics"]["rejection"]["reason"] = reason
            guess = system._apply_empty_answer_fallback(output)
            self.assertEqual(guess["result"]["row_count"], 0)
            self.assertEqual(guess["diagnostics"]["rejection"]["reason"], reason)


if __name__ == "__main__":
    unittest.main()
