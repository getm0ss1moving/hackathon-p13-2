"""仅合成训练成员、模型替身和网络guard；不读取封存或调用真实模型。"""

from contextlib import ExitStack, redirect_stdout, redirect_stderr
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import train_live


def fixture():
    cases = [{"case_id": f"SYNTH-{index:03}", "question": f"合成训练问题{index}"} for index in range(150)]
    history = [{**case, "score_without_time_penalty": 0 if index % 2 == 0 else 5}
               for index, case in enumerate(cases)]
    manifest = {"split_id": "whitebox_150_50_v1", "train_sha256": "d" * 64,
                "train_history_sha256": "d" * 64, "sealed_test_sha256": "d" * 64,
                "source_dataset_sha256": "d" * 64}
    return manifest, cases, history


class SubsetTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for owner, name in [(requests.Session, "request"), (httpx.Client, "send")]:
            self.stack.enter_context(patch.object(owner, name, side_effect=AssertionError("禁止真实网络")))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.manifest, self.cases, self.history = fixture()

    def test_default_full150_is_unchanged(self):
        cases, scope, phase = train_live.select_cases(self.cases, None, None)
        self.assertEqual((cases, scope, phase), (self.cases, "train_only", "full_training"))
        self.assertEqual((len(cases), 3 * len(cases), 5 * len(cases)), (150, 450, 750))

    def test_subset_order_is_original_training_order(self):
        cases, scope, phase = train_live.select_cases(self.cases, ["SYNTH-003", "SYNTH-000"], "failure_probe")
        self.assertEqual([case["case_id"] for case in cases], ["SYNTH-000", "SYNTH-003"])
        self.assertEqual((scope, phase), ("train_subset", "failure_probe"))

    def test_invalid_unknown_empty_duplicate_oversized_and_unlabeled_scope_stop(self):
        for ids, phase in [([], "failure_probe"), ([""], "failure_probe"), (["  "], "failure_probe"),
                           (["OUTSIDE"], "failure_probe"), (["SYNTH-000", "SYNTH-000"], "failure_probe"),
                           ([f"SYNTH-{i:03}" for i in range(151)], "failure_probe"),
                           (["SYNTH-000"], None), (None, "failure_probe"), (["SYNTH-000"], "unknown")]:
            with self.subTest(ids=ids, phase=phase), self.assertRaises(ValueError):
                train_live.select_cases(self.cases, ids, phase)

    def test_regression_requires_historical_five_but_new_failure_labels_allow_old_five(self):
        passed = [self.cases[1], self.cases[3]]
        metadata = train_live.phase_metadata(passed, self.history, "passed_regression")
        self.assertEqual(metadata["v2_full_quality_members"], ["SYNTH-001", "SYNTH-003"])
        with self.assertRaises(ValueError):
            train_live.phase_metadata([self.cases[0]], self.history, "passed_regression")
        metadata = train_live.phase_metadata([self.cases[1]], self.history, "failure_probe")
        self.assertEqual(metadata["case_quality"], [{"case_id": "SYNTH-001", "v2_quality": 5}])
        self.assertIn("later-discovered", metadata["membership_policy"])

    def test_phase_requires_complete_matching_history(self):
        for history in [self.history[:-1], self.history[:149] + [self.history[0]],
                        [self.history[0] | {"question": "wrong"}] + self.history[1:]]:
            with self.assertRaises(ValueError):
                train_live.phase_metadata([self.cases[0]], history, "failure_probe")

    def fake_runtime(self, stack, *, requests_per_case=2, after_sdk=None, wrong_response=False, extra_body_override="match"):
        state = SimpleNamespace(events=[], sdk_calls=0, system_calls=0, closed=False, request_options=[])
        matcher = SimpleNamespace(DEEPSEEK_API_KEY="synthetic-key", DEEPSEEK_MODEL="synthetic-model",
                                  DEEPSEEK_BASE_URL="https://example.invalid", _llm_client=None,
                                  __file__=str(train_live.HERE / "implementation/runbook_matcher.py"),
                                  get_llm_events=lambda: copy.deepcopy(state.events))

        def create(**options):
            state.sdk_calls += 1
            state.request_options.append(copy.deepcopy(options))
            if after_sdk:
                after_sdk(state)
            return SimpleNamespace(model="wrong-model" if wrong_response else options["model"])

        client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                 close=lambda: setattr(state, "closed", True))

        def ask(prompt, stage="unknown"):
            if len(state.events) >= int(os.environ["RUNBOOK_MAX_LLM_CALLS"]):
                raise RuntimeError("synthetic budget exhausted")
            event = {"stage": stage, "status": "error", "seconds": 0.01,
                     "prompt_tokens": 5, "completion_tokens": 2,
                     "thinking_mode": os.environ["RUNBOOK_THINKING_MODE"]}
            state.events.append(event)
            options = {"model": matcher.DEEPSEEK_MODEL, "max_tokens": 1024}
            if extra_body_override != "match":
                options["extra_body"] = extra_body_override
            elif os.environ["RUNBOOK_THINKING_MODE"] == "disabled":
                options["extra_body"] = {"thinking": {"type": "disabled"}}
            matcher._llm_client.chat.completions.create(**options)
            event["status"] = "ok"
            return "synthetic response"

        matcher.llm_ask = ask

        class System:
            initialization_metrics = {"index_seconds": 0, "schema_warm_seconds": 0}

            def __init__(self):
                matcher._llm_client = client

            def query(self, question):
                state.system_calls += 1
                for _ in range(requests_per_case):
                    matcher.llm_ask("synthetic prompt", stage="refine")
                return {"matched_runbook": "synthetic", "api_call": {"method": "GET", "url": "/synthetic"},
                        "sql": "SELECT 1", "result": {"columns": ["count"], "rows": [{"count": 1}], "row_count": 1},
                        "diagnostics": {}, "error": None}

        def score(case, output, elapsed):
            return {"case_id": case["case_id"], "elapsed": elapsed, "score": 5, "reason": "synthetic"}

        stack.enter_context(patch.dict(sys.modules, {
            "runbook_matcher": matcher, "runbook_system": SimpleNamespace(RunbookQuerySystem=System,
                __file__=str(train_live.HERE / "implementation/runbook_system.py")),
            "runbook_retriever": SimpleNamespace(__file__=str(train_live.HERE / "implementation/runbook_retriever.py")),
            "runbook_executor": SimpleNamespace(__file__=str(train_live.HERE / "implementation/runbook_executor.py")),
            "runbook_items": SimpleNamespace(RUNBOOK_ITEMS=[{}] * 200,
                __file__=str(train_live.HERE / "implementation/runbook_items.py")),
            "evaluator": SimpleNamespace(evaluate_case=score,
                __file__=str(train_live.HERE / "implementation/evaluator.py"))}))
        return state

    def fake_inputs(self, stack, digest_function=None):
        native_read, native_exists = Path.read_text, Path.exists

        def read(path, *args, **kwargs):
            if path.name == "baseline_manifest.json":
                return json.dumps({"readonly_files":{"implementation/runbook_items.py":"d" * 64}})
            if path.name in {"sealed_test.json", "CMDB用例集-白盒200.json"}:
                raise AssertionError("不能读取封存或原200题")
            return native_read(path, *args, **kwargs)

        def reference(manifest, all_cases, selected, phase):
            metadata = train_live.phase_metadata(selected, self.history, phase)
            metadata["file_sha256"] = {name: "d" * 64 for name in train_live.V2_HISTORY_FILES}
            return metadata

        stack.enter_context(patch.object(train_live, "load_training", return_value=(self.manifest, self.cases, self.history)))
        stack.enter_context(patch.object(train_live, "subset_history", side_effect=reference))
        stack.enter_context(patch.object(train_live, "sha", side_effect=digest_function or (lambda path: "d" * 64)))
        stack.enter_context(patch.object(train_live.subprocess, "check_output", return_value="synthetic-base\n"))
        stack.enter_context(patch.object(Path, "read_text", read))
        stack.enter_context(patch.object(Path, "exists", lambda path: False if path.name == ".env.local" else native_exists(path)))

    def preflight(self, args):
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(train_live.main(args), 0)
        return json.loads(stream.getvalue())

    def test_full_and_subset_preflight_feature_flags_and_budget(self):
        with ExitStack() as stack:
            self.fake_inputs(stack)
            state = self.fake_runtime(stack)
            full = self.preflight([])
            self.assertEqual((full["scope"], full["case_count"], full["max_requests"]), ("train_only", 150, 450))
            self.assertEqual(full["feature_flags"]["RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES"], "0")
            args = ["--case-id", "SYNTH-002", "--case-id", "SYNTH-000", "--phase", "failure_probe",
                    "--candidate-flags", "--refine-contract-prompt", "--independent-aggregates"]
            plan = self.preflight(args)
            self.assertEqual((plan["scope"], plan["phase"], plan["case_count"], plan["max_requests"]),
                             ("train_subset", "failure_probe", 2, 6))
            self.assertEqual(plan["case_ids"], ["SYNTH-000", "SYNTH-002"])
            self.assertEqual(plan["feature_flags"]["RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES"], "1")
            self.assertEqual(plan["feature_flags"]["RUNBOOK_REFINE_CONTRACT_PROMPT"], "1")
            self.assertIn("scripts/train_prompt_probe.py", plan["source_sha256"])
            self.assertEqual(set(plan["phase_reference"]["file_sha256"]), set(train_live.V2_HISTORY_FILES))
            self.assertNotIn("synthetic-key", json.dumps(plan))
            self.assertEqual((state.sdk_calls, state.system_calls), (0, 0))

    def test_cli_cannot_add_arbitrary_case_file_or_unfrozen_members(self):
        for args in [["--case-file", "/synthetic/other.json"], ["--case-id", "OUTSIDE", "--phase", "failure_probe"],
                     ["--case-id", ""], ["--case-id", "SYNTH-000", "--phase", "passed_regression"]]:
            with self.subTest(args=args), ExitStack() as stack:
                self.fake_inputs(stack)
                state = self.fake_runtime(stack)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    train_live.main(args)
                self.assertEqual((state.sdk_calls, state.system_calls), (0, 0))

    def run_fixture(self, stack, args, *, requests_per_case=2, after_sdk=None, wrong_response=False, mutate_plan=None,
                    digest_function=None, extra_body_override="match"):
        self.fake_inputs(stack, digest_function)
        state = self.fake_runtime(stack, requests_per_case=requests_per_case, after_sdk=after_sdk,
                                  wrong_response=wrong_response, extra_body_override=extra_body_override)
        plan = self.preflight(args)
        if mutate_plan:
            mutate_plan(plan)
        folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        expected, output = folder / "plan.json", folder / "output.jsonl"
        expected.write_text(json.dumps(plan))
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = train_live.main(args + ["--run", "--expected-plan", str(expected), "--output", str(output)])
        return code, [json.loads(line) for line in output.read_text().splitlines()], state

    def test_explicit_fifty_validation_is_separate_and_bounded(self):
        validation = [{'case_id': f'VALID-{i}', 'question': f'合成验证问题{i}'} for i in range(50)]
        args = ['--sealed-validation-freeze', str(train_live.HERE/'reports/synthetic_validation_freeze.json')]
        with ExitStack() as stack:
            stack.enter_context(patch('validation_data.load_sealed_validation', return_value=validation))
            code, rows, state = self.run_fixture(stack, args)
        self.assertEqual(code, 0)
        self.assertEqual(rows[0]['type'], 'validation_plan')
        self.assertEqual(rows[-1]['scope'], 'sealed50_validation')
        self.assertTrue(rows[-1]['holdout_evaluated'])
        self.assertEqual((rows[-1]['completed_cases'], rows[-1]['max_requests'], state.sdk_calls), (50, 150, 100))
        self.assertTrue(all(row['training_case_index'] is None for row in rows if row['type'] == 'case'))

    def test_explicit_full200_keeps_original_scope_and_caps_calls_at450(self):
        _, training, _ = fixture()
        full = training + [{'case_id': f'VALID-{i}', 'question': f'合成验证问题{i}'} for i in range(50)]
        with ExitStack() as stack:
            stack.enter_context(patch('validation_data.load_explicit_whitebox200', return_value=full))
            code, rows, state = self.run_fixture(stack, ['--whitebox200'])
        self.assertEqual(code, 0)
        self.assertEqual(rows[0]['type'], 'validation_plan')
        self.assertEqual(rows[-1]['scope'], 'whitebox200_explicit')
        self.assertEqual(rows[0]['case_order'], 'original whitebox file order')
        self.assertTrue(rows[-1]['holdout_evaluated'])
        self.assertEqual((rows[-1]['completed_cases'], rows[-1]['max_requests'], state.sdk_calls), (200, 450, 400))
        self.assertEqual(sum(row['training_case_index'] is None for row in rows if row['type'] == 'case'), 50)

    def test_validation_resume_runs_only_unrequested33_with99_budget(self):
        validation = [{'case_id': f'VALID-{i}', 'question': f'合成验证问题{i}'} for i in range(50)]
        evidence = {'completed_prefix': 17, 'files_sha256': {}, 'manual_retry': False}
        args = ['--sealed-validation-freeze', str(train_live.HERE/'reports/synthetic_freeze.json'),
                '--validation-resume', str(train_live.HERE/'reports/synthetic_parent')]
        with ExitStack() as stack:
            stack.enter_context(patch('validation_data.load_sealed_validation', return_value=validation))
            stack.enter_context(patch('validation_resume.remaining_validation', return_value=(validation[17:], evidence)))
            code, rows, state = self.run_fixture(stack, args)
        cases = [row for row in rows if row['type'] == 'case']
        self.assertEqual(code, 0)
        self.assertEqual(rows[-1]['scope'], 'sealed50_resume')
        self.assertEqual((rows[-1]['completed_cases'], rows[-1]['max_requests'], state.sdk_calls), (33, 99, 66))
        self.assertEqual([r['case_id'] for r in cases], [r['case_id'] for r in validation[17:]])
        self.assertTrue(all(r['training_case_index'] is None for r in cases))

    def test_default_training_never_loads_full_whitebox(self):
        with ExitStack() as stack:
            self.fake_inputs(stack);self.fake_runtime(stack)
            loader = stack.enter_context(patch('validation_data.load_explicit_whitebox200', side_effect=AssertionError('默认不可读全200')))
            plan = self.preflight([])
        loader.assert_not_called()
        self.assertEqual(plan['scope'], 'train_only')
        self.assertEqual(plan['case_count'], 150)

    def test_full200_rejects_mixed_scopes_before_loading_questions(self):
        for extra in [['--case-id', 'SYNTH-001', '--phase', 'failure_probe'],
                      ['--sealed-validation-freeze', 'unused.json']]:
            with self.subTest(extra=extra), ExitStack() as stack:
                self.fake_inputs(stack);self.fake_runtime(stack)
                loader = stack.enter_context(patch('validation_data.load_explicit_whitebox200'))
                with self.assertRaises(SystemExit): self.preflight(['--whitebox200', *extra])
                loader.assert_not_called()

    def test_recovery_candidates_default_off_and_explicit_flags_are_frozen(self):
        with ExitStack() as stack:
            self.fake_inputs(stack);self.fake_runtime(stack)
            default = self.preflight([])
            enabled = self.preflight(['--preserve-sparse-nulls', '--bind-deploy-node-region'])
        for name in ['RUNBOOK_PRESERVE_SPARSE_NULLS', 'RUNBOOK_BIND_DEPLOY_NODE_REGION']:
            self.assertEqual(default['feature_flags'][name], '0')
            self.assertEqual(enabled['feature_flags'][name], '1')

    def test_subset_run_summary_request_members_and_original_indices(self):
        args = ["--case-id", "SYNTH-003", "--case-id", "SYNTH-001", "--phase", "passed_regression"]
        with ExitStack() as stack:
            code, rows, state = self.run_fixture(stack, args)
        summary = rows[-1]
        self.assertEqual(code, 0)
        self.assertEqual((summary["scope"], summary["phase"], summary["planned_cases"], summary["max_score"]),
                         ("train_subset", "passed_regression", 2, 10))
        self.assertEqual((summary["max_requests"], summary["generation_requests"]), (6, 4))
        self.assertEqual(summary["status"], "complete")
        cases = [row for row in rows if row["type"] == "case"]
        self.assertEqual([row["case_id"] for row in cases], ["SYNTH-001", "SYNTH-003"])
        self.assertEqual([row["training_case_index"] for row in cases], [2, 4])
        self.assertEqual([row["case_index"] for row in cases], [1, 2])
        self.assertTrue(all(row["case_id"] in summary["case_ids"] for row in rows if row["type"] == "request"))
        self.assertEqual((state.sdk_calls, state.system_calls, state.closed), (4, 2, True))

    def test_phase_membership_and_plan_drift_stop_before_model(self):
        args = ["--case-id", "SYNTH-000", "--phase", "failure_probe"]
        for mutate in [lambda plan: plan.update(case_ids=["OUTSIDE"]), lambda plan: plan.update(phase="passed_regression"),
                       lambda plan: plan.update(max_requests=4),
                       lambda plan: plan["feature_flags"].update(RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES="1")]:
            with self.subTest(mutate=mutate), ExitStack() as stack:
                with self.assertRaises(SystemExit) as error:
                    self.run_fixture(stack, args, mutate_plan=mutate)
                self.assertEqual(error.exception.code, 2)

    def test_scope_budget_counts_failed_attempt_and_stops_without_retry(self):
        args = ["--case-id", "SYNTH-000", "--phase", "failure_probe"]
        with ExitStack() as stack:
            code, rows, state = self.run_fixture(stack, args, requests_per_case=4)
        self.assertEqual((code, state.sdk_calls), (1, 3))
        self.assertEqual((rows[-1]["status"], rows[-1]["generation_requests"], rows[-1]["max_requests"]), ("incomplete", 3, 3))

    def test_flag_and_history_drift_and_model_identity_stop_requests(self):
        args = ["--case-id", "SYNTH-000", "--phase", "failure_probe", "--independent-aggregates"]
        with ExitStack() as stack:
            code, rows, state = self.run_fixture(stack, args,
                                                 after_sdk=lambda state: os.environ.update(RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES="0"))
        self.assertEqual((code, state.sdk_calls, rows[-1]["status"]), (1, 1, "incomplete"))
        changed = {"value": False}
        with ExitStack() as stack:
            code, rows, state = self.run_fixture(stack, args, after_sdk=lambda state: changed.update(value=True),
                                                 digest_function=lambda path: "e" * 64 if changed["value"] and path.name == train_live.V2_HISTORY_FILES[0] else "d" * 64)
        self.assertEqual((code, state.sdk_calls, rows[-1]["status"]), (1, 1, "incomplete"))
        with ExitStack() as stack:
            code, rows, state = self.run_fixture(stack, args, wrong_response=True)
        self.assertEqual((code, state.sdk_calls, len(rows[-1]["model_identity_mismatches"])), (1, 1, 1))

    def test_thinking_modes_are_explicit_in_plan_and_match_actual_request(self):
        for mode in ["provider_default", "disabled"]:
            with self.subTest(mode=mode), ExitStack() as stack:
                args = ["--case-id", "SYNTH-000", "--phase", "failure_probe", "--thinking-mode", mode]
                code, rows, state = self.run_fixture(stack, args)
                plan = rows[0]
                expected = {"thinking": {"type": "disabled"}} if mode == "disabled" else None
                self.assertEqual((code, state.sdk_calls), (0, 2))
                self.assertEqual(plan["thinking_mode"], mode)
                self.assertEqual(plan["feature_flags"]["RUNBOOK_THINKING_MODE"], mode)
                self.assertEqual(plan["thinking_extra_body"], expected)
                self.assertTrue(all(options.get("extra_body") == expected for options in state.request_options))
                if mode == "provider_default":
                    self.assertTrue(all("extra_body" not in options for options in state.request_options))
                self.assertTrue(all(row["thinking_mode"] == mode for row in rows if row["type"] == "request"))
                self.assertEqual(rows[-1]["thinking_mode"], mode)

    def test_thinking_body_mismatch_stops_before_sdk_send(self):
        for mode, body in [("provider_default", {"thinking": {"type": "disabled"}}),
                           ("disabled", None), ("disabled", {"thinking": {"type": "disabled"}, "extra": True})]:
            with self.subTest(mode=mode, body=body), ExitStack() as stack:
                code, rows, state = self.run_fixture(stack,
                    ["--case-id", "SYNTH-000", "--phase", "failure_probe", "--thinking-mode", mode],
                    extra_body_override=body)
                self.assertEqual((code, state.sdk_calls, rows[-1]["status"]), (1, 0, "incomplete"))

    def test_thinking_mode_drift_is_frozen_before_next_request(self):
        with ExitStack() as stack:
            code, rows, state = self.run_fixture(stack,
                ["--case-id", "SYNTH-000", "--phase", "failure_probe", "--thinking-mode", "disabled"],
                after_sdk=lambda state: os.environ.update(RUNBOOK_THINKING_MODE="provider_default"))
        self.assertEqual((code, state.sdk_calls, rows[-1]["status"]), (1, 1, "incomplete"))

    def test_thinking_default_full150_and_invalid_or_changed_mode_are_rejected(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"RUNBOOK_THINKING_MODE": "disabled"}))
            self.fake_inputs(stack)
            state = self.fake_runtime(stack)
            plan = self.preflight([])
            self.assertEqual((plan["case_count"], plan["max_requests"], plan["thinking_mode"]), (150, 450, "disabled"))
            self.assertEqual(plan["thinking_extra_body"], {"thinking": {"type": "disabled"}})
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                train_live.main(["--thinking-mode", "unsupported"])
            self.assertEqual(state.sdk_calls, 0)
        with ExitStack() as stack, self.assertRaises(SystemExit):
            self.run_fixture(stack, ["--case-id", "SYNTH-000", "--phase", "failure_probe"],
                             mutate_plan=lambda plan: plan.update(thinking_mode="provider_default"))


if __name__ == "__main__":
    unittest.main()
