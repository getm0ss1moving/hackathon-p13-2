"""合成候选/评分/来源反例；只读取评分器代码，不读取任何题库或历史case。"""

from contextlib import ExitStack
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import Mock, patch

import httpx
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay_compat as c


ROOT = Path(__file__).resolve().parents[1]


class ReplayCompatTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(requests.Session, "request", side_effect=AssertionError("零网络")))
        self.stack.enter_context(patch.object(httpx.Client, "send", side_effect=AssertionError("零网络/模型")))
        self.active = ["before", "rb_052", "rb_086", "after"]
        self.old = ["before", "rb_054", "rb_052", "after"]
        self.current = ["before", "rb_052", "after"]

    def gate(self, selected="rb_052", recorded_index=None):
        return c.SelectionReplay(self.old, selected, self.active, c.APPROVED_ALIASES, recorded_index)

    def test_old_ordinal_is_recomputed_not_reused(self):
        gate = self.gate(recorded_index=3)
        proof = gate.observe(self.current)
        self.assertEqual((gate.old_index, gate.model_index()), (3, 2))
        self.assertEqual(self.current[2], "after")  # 直接复用旧3会误选after。
        self.assertEqual(proof["historical_selected_id"], "rb_052")
        self.assertEqual(proof["actual_candidate_ids"], self.current)

    def test_deleted_alias_selected_fill_and_refine_use_retained_item(self):
        gate = self.gate("rb_054", recorded_index=2)
        gate.observe(self.current)
        retained = {"id": "rb_052", "sql": "SELECT synthetic"}
        self.assertIs(gate.selected_item({"rb_052": retained}), retained)
        self.assertEqual((gate.model_index(), gate.proof["canonical_selected_id"]), (2, "rb_052"))

    def test_order_drift_blocks_before_any_per_case_get_or_candidate_query(self):
        for current in (["rb_052", "before", "after"], ["before", "rb_052"],
                        ["before", "rb_052", "after", "rb_086"], ["before", "rb_052", "rb_052", "after"]):
            with self.subTest(current=current):
                gate, sent = self.gate(), []
                with self.assertRaises(c.ReplayStop):
                    gate.observe(current)
                    gate.require_ready()
                    sent.append("historical baseline GET")
                self.assertEqual(sent, [])
                with self.assertRaises(c.ReplayStop):
                    gate.require_ready()

    def test_missing_preflight_forbids_api_and_model_stages(self):
        gate = self.gate()
        for operation in (gate.require_ready, gate.model_index, lambda: gate.selected_item({})):
            with self.assertRaises(c.ReplayStop):
                operation()

    def test_guard_checks_actual_query_retrieval_again_and_latches_drift(self):
        gate = self.gate()
        retrieve = Mock(side_effect=[[SimpleNamespace(id=value) for value in values]
                                     for values in (self.current, ["before", "after", "rb_052"], self.current)])
        wrapped = c.guard_retrieve(retrieve, lambda: gate)
        wrapped("synthetic preflight")
        gate.require_ready()
        with self.assertRaises(c.ReplayStop):
            wrapped("actual query")
        with self.assertRaises(c.ReplayStop):
            wrapped("cannot recover after failure")
        self.assertEqual(retrieve.call_count, 3)

    def test_refusal_zero_and_empty_candidate_case_are_explicit(self):
        gate = c.SelectionReplay([], None, self.active, c.APPROVED_ALIASES, recorded_index=0)
        gate.observe([])
        self.assertEqual(gate.model_index(), 0)
        with self.assertRaises(c.ReplayStop):
            gate.selected_item({})

    def test_unknown_deleted_id_selected_outside_and_conflicting_old_index_stop(self):
        for ids, selected, index in [(["unproved_deleted"], None, None),
                                     (self.old, "outside", None), (self.old, "rb_052", 2),
                                     (["before", "before"], None, None)]:
            with self.subTest(ids=ids, selected=selected), self.assertRaises(c.ReplayStop):
                c.SelectionReplay(ids, selected, self.active, c.APPROVED_ALIASES, index)

    def test_no_history_rewrite_and_returned_proof_is_independent(self):
        original = copy.deepcopy(self.old)
        gate = self.gate()
        proof = gate.observe(self.current)
        proof["historical_candidate_ids"].clear()
        self.assertEqual(self.old, original)
        self.assertEqual(gate.proof["historical_candidate_ids"], original)

    def library_fixture(self):
        items = [{"id": value} for value in ["rb_052", "rb_086"] + [f"synthetic_{i}" for i in range(196)]]
        for owner, alias in ((items[0], "rb_054"), (items[1], "rb_087")):
            owner["retrieval_aliases"] = [{"id": alias, "after_id": owner["id"],
                                          "examples": ["synthetic"], "description": "synthetic"}]
        return items

    def test_alias_provenance_is_only_exact_reviewed_a198(self):
        sources = {c.ITEMS: c.CURRENT_ITEMS, c.RETRIEVER: c.CURRENT_RETRIEVER}
        items = self.library_fixture()
        self.assertEqual(c.verified_library_aliases(items, sources), c.APPROVED_ALIASES)
        for mutation in (lambda values: values.pop(),
                         lambda values: values[0]["retrieval_aliases"][0].update(sql="SELECT 1"),
                         lambda values: values[0]["retrieval_aliases"][0].update(id="unproved_alias")):
            bad = copy.deepcopy(items)
            mutation(bad)
            with self.assertRaises(c.ReplayStop):
                c.verified_library_aliases(bad, sources)
        with self.assertRaises(c.ReplayStop):
            c.verified_library_aliases(items, sources | {c.RETRIEVER: "f" * 64})

    def test_source_chains_accept_only_exact_a_and_authorized_evaluator(self):
        old = {c.ITEMS: c.LEGACY_ITEMS, c.RETRIEVER: c.LEGACY_RETRIEVER, c.EVALUATOR: c.LEGACY_EVALUATOR,
               "implementation/runbook_executor.py": c.OFFICIAL_CURRENT["implementation/runbook_executor.py"],
               "output-server/synthetic.json": "a" * 64}
        new = old | {c.ITEMS: c.CURRENT_ITEMS, c.RETRIEVER: c.CURRENT_RETRIEVER, c.EVALUATOR: c.CURRENT_EVALUATOR}
        original = copy.deepcopy(old)
        proof = c.reconcile_sources(old, new)
        self.assertEqual(len(proof[c.ITEMS]["accepted_transitions"]), 2)
        self.assertEqual(len(proof[c.EVALUATOR]["accepted_transitions"]), 1)
        self.assertEqual(old, original)
        for key in ("implementation/runbook_executor.py", "output-server/synthetic.json"):
            with self.subTest(key=key), self.assertRaises(c.ReplayStop):
                c.reconcile_sources(old, new | {key: "b" * 64})

    def test_unknown_source_pair_reverse_or_missing_digest_is_not_approval(self):
        for old, new in [({c.ITEMS: c.INTEGRATED_ITEMS}, {c.ITEMS: "e" * 64}),
                         ({c.ITEMS: c.CURRENT_ITEMS}, {c.ITEMS: c.INTEGRATED_ITEMS}),
                         ({"implementation/runbook_matcher.py": "a" * 64}, {"implementation/runbook_matcher.py": "b" * 64}),
                         ({"training_data.py": "a" * 64}, {})]:
            with self.subTest(old=old), self.assertRaises(c.ReplayStop):
                c.reconcile_sources(old, new)

    def test_script_path_only_normalizes_current_lookup_keeps_historical_keys(self):
        old = {"training_data.py": "a" * 64, "run_whitebox.py": "b" * 64}
        proof = c.reconcile_sources(old, {"scripts/training_data.py": "a" * 64, "scripts/run_whitebox.py": "b" * 64})
        self.assertEqual(set(proof), set(old))
        self.assertEqual(proof["training_data.py"]["current_path"], "scripts/training_data.py")
        self.assertEqual(proof["training_data.py"]["accepted_transitions"], [])
        with self.assertRaises(c.ReplayStop):
            c.reconcile_sources(old, {"scripts/training_data.py": "d" * 64, "scripts/run_whitebox.py": "b" * 64})
        for bad in ("../training_data.py", "/training_data.py", "scripts//training_data.py", "scripts\\training_data.py"):
            with self.assertRaises(c.ReplayStop):
                c.current_source_path(bad)

    def test_official_executor_and_entrypoints_remain_exact(self):
        c.require_official_hashes(c.OFFICIAL_CURRENT)
        for key in c.OFFICIAL_CURRENT:
            with self.subTest(key=key), self.assertRaises(c.ReplayStop):
                c.require_official_hashes(c.OFFICIAL_CURRENT | {key: "0" * 64})


class ScorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "implementation/evaluator.py"
        # 本组专测历史original→ratio1回放合同，继续使用精确冻结的ratio1源码；
        # 最新别名版由test_training_evaluator_alias_revision独立验证，不能混称同一版本。
        import subprocess
        cls.source = subprocess.check_output([
            "git", "show", "e0f34ed42937203631eef0309964431c376cd179:implementation/evaluator.py"], cwd=ROOT)
        legacy, revised, cls.provenance = c.load_verified_scorers(cls.source, c.AUTHORIZED_REVISION, cls.path)
        cls.legacy, cls.revised = staticmethod(legacy), staticmethod(revised)

    def case_and_output(self, expected=2, actual=200):
        case = {"case_id": "SYNTHETIC", "question": "合成数值测试", "api_call": {}, "sql": "SELECT value FROM fixture",
                "answer": {"columns": ["value"], "rows": [{"value": expected}], "row_count": 1}}
        output = {"matched_runbook": "fixture", "api_call": {}, "sql": case["sql"], "error": None,
                  "result": {"columns": ["value"], "rows": [{"value": actual}], "row_count": 1}}
        return case, output

    def historical(self, case, score):
        return {"case_id": case["case_id"], "question": case["question"], "score_without_time_penalty": score}

    def test_pinned_original_and_revised_numeric_scores_are_separate(self):
        case, output = self.case_and_output()
        original_case, original_output = copy.deepcopy(case), copy.deepcopy(output)
        query = Mock(return_value=output)
        with patch("builtins.open", side_effect=AssertionError("评分不得读文件")):
            result = c.verify_legacy_then_rescore(case, output, self.historical(case, 5), self.legacy, self.revised, query)
        self.assertEqual((result["legacy_replay_actual"]["score"], result["revised_baseline"]["score"],
                          result["revised_candidate"]["score"]), (5, -1, -1))
        self.assertEqual(result["revised_delta"], 0)
        query.assert_called_once_with()
        self.assertEqual((case, output), (original_case, original_output))
        self.assertIn("no fresh model or latency", result["elapsed_policy"])

    def test_old_mismatch_stops_even_when_authorized_score_would_match_history(self):
        case, output = self.case_and_output()
        query, revised = Mock(return_value=output), Mock(wraps=self.revised)
        with self.assertRaises(c.ReplayStop):
            c.verify_legacy_then_rescore(case, output, self.historical(case, -1), self.legacy, revised, query)
        query.assert_not_called()
        revised.assert_not_called()

    def test_revised_tolerance_change_is_not_reported_as_candidate_improvement(self):
        case, output = self.case_and_output(expected=100, actual=109)
        result = c.verify_legacy_then_rescore(case, output, self.historical(case, -1), self.legacy, self.revised, lambda: output)
        self.assertEqual((result["legacy_historical_expected"], result["revised_baseline"]["score"], result["revised_delta"]), (-1, 5, 0))

    def test_source_or_authorization_extra_change_is_rejected(self):
        for source, revision in [(self.source + b"\n", c.AUTHORIZED_REVISION),
                                 (self.source, c.AUTHORIZED_REVISION | {"revision_id": "unapproved"}),
                                 (self.source, c.AUTHORIZED_REVISION | {"historical_results_rewritten": True})]:
            with self.subTest(revision=revision["revision_id"]), self.assertRaises(c.ReplayStop):
                c.load_verified_scorers(source, revision, self.path)

    def test_case_identity_score_and_preview_only_inputs_stop_before_candidate(self):
        case, output = self.case_and_output()
        history = self.historical(case, 5)
        bad_preview = copy.deepcopy(output)
        bad_preview["result"] = {"columns": ["value"], "rows_preview": [{"value": 200}], "row_count": 1}
        for baseline, record in [(output, history | {"case_id": "WRONG"}),
                                 (output, history | {"question": "WRONG"}),
                                 (output, history | {"score_without_time_penalty": True}),
                                 (output, history | {"score_without_time_penalty": float("nan")}),
                                 (bad_preview, history)]:
            query = Mock(return_value=output)
            with self.subTest(record=record), self.assertRaises(c.ReplayStop):
                c.verify_legacy_then_rescore(case, baseline, record, self.legacy, self.revised, query)
            query.assert_not_called()

    def test_rounded_elapsed_cannot_prove_original_timed_score(self):
        case, output = self.case_and_output(expected=2, actual=2)
        self.assertEqual((self.legacy(case, output, 4.0001)["score"], self.legacy(case, output, 4.00)["score"]), (4, 5))
        self.assertEqual((self.legacy(case, output, 6.0001)["score"], self.legacy(case, output, 6.00)["score"]), (2, 4))
        result = c.verify_legacy_then_rescore(case, output, self.historical(case, 5), self.legacy, self.revised, lambda: output)
        self.assertEqual((result["legacy_replay_actual"]["elapsed"], result["revised_baseline"]["elapsed"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
