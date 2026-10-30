"""配对探针的合成范围、冻结、预算与记录测试；不读取封存，不访问网络。"""

from contextlib import redirect_stdout
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
import train_prompt_probe as probe


def fixture():
    cases = [{"case_id": f"SYNTH-{index:03}", "question": f"合成训练问题{index}"} for index in range(150)]
    manifest = {"split_id": "whitebox_150_50_v1", "train_sha256": "a" * 64,
                "train_history_sha256": "b" * 64}
    sources = {name: "c" * 64 for name in probe.HISTORICAL_SOURCES}
    parent = {"type": "training_plan", "scope": "train_only", "split_id": manifest["split_id"],
              "record_format": 2, "case_count": 150, "repeats": 1,
              "case_order": "fixed train file order", "training_sha256": manifest["train_sha256"],
              "split_manifest_sha256": "d" * 64, "source_sha256": sources,
              "feature_flags": dict(probe.V2_FLAGS), "model": "synthetic-model",
              "base_url": "https://example.invalid", "max_output_tokens": 1024, "sdk_max_retries": 0}
    resume = {"type": "resume_plan", "scope": "train_only_resume", "parent_sha256": "e" * 64,
              **{key: copy.deepcopy(parent[key]) for key in (
                  "source_sha256", "training_sha256", "feature_flags", "model", "base_url",
                  "max_output_tokens", "sdk_max_retries")},
              "case_ids": [case["case_id"] for case in cases[147:]], "case_count": 3}
    history = []
    for index, case in enumerate(cases):
        matching = {"reason": "matched", "sql_before_refine": "SELECT name FROM CLOUD_VM_NOVA",
                    "sql_after_refine": "SELECT name FROM CLOUD_VM_NOVA"}
        if index % 3 == 0:
            matching["projection_contract"] = {"reject": True, "reason": "synthetic_missing_column"}
        history.append({"type": "case", "case_index": index + 1, **case,
                        "api_call": {"method": "GET", "url": "/rest/hackthon/db/instances/VM_NOVA",
                                     "condition": {"constraint": [{"simple": {"name": "name", "value": "synthetic-vm"}}]}},
                        "matched_runbook": "synthetic_template", "score_without_time_penalty": 5,
                        "diagnostics": {"matching": matching, "llm_calls": [{"stage": "refine", "status": "ok"}]}})

    def rows(plan, records, status):
        output = [plan]
        for record in records:
            output.extend([{"type": "request", "case_id": record["case_id"], "stage": "refine", "status": "ok",
                            "requested_model": "synthetic-model", "response_model": "synthetic-model"}, record])
        output.append({"type": "summary", "status": status, "completed_cases": len(records),
                       "generation_requests": len(records), "model_identity_mismatches": []})
        return output
    return manifest, cases, rows(parent, history[:147], "incomplete"), rows(resume, history[147:], "complete"), history


class FakeMatcher:
    class ModelOutputError(ValueError):
        pass

    DEEPSEEK_MODEL = "synthetic-model"
    DEEPSEEK_BASE_URL = "https://example.invalid"

    def __init__(self, failure=None, response_model=None):
        self._llm_client, self.events, self.sdk_calls = None, [], 0
        self.failure, self.response_model = failure, response_model or self.DEEPSEEK_MODEL
        self.seen_flags, self.closed = [], False

    def get_llm_events(self):
        return copy.deepcopy(self.events)

    def _warm_schema_cache(self):
        pass

    def _get_table_schemas(self, sql):
        return "synthetic schema"

    def get_llm(self):
        if self._llm_client is None:
            self._llm_client = SimpleNamespace(max_retries=0, close=lambda: setattr(self, "closed", True),
                                             chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))
        return self._llm_client

    def create(self, **kwargs):
        self.sdk_calls += 1
        self.seen_flags.append(os.environ.get(probe.PROMPT_FLAG))
        if self.failure == "timeout":
            raise TimeoutError("synthetic timeout; must not be logged")
        if self.failure == "unknown":
            raise ValueError("synthetic unknown error")
        return SimpleNamespace(model=self.response_model, usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
                               choices=[SimpleNamespace(finish_reason="length" if self.failure == "length" else "stop",
                                                        message=SimpleNamespace(content="SELECT name FROM CLOUD_VM_NOVA"))])

    def llm_ask(self, prompt, stage="unknown"):
        event = {"stage": stage, "status": "error", "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.01}
        self.events.append(event)
        response = self.get_llm().chat.completions.create(model=self.DEEPSEEK_MODEL, max_tokens=1024, stream=False)
        event.update(prompt_tokens=response.usage.prompt_tokens, completion_tokens=response.usage.completion_tokens)
        if response.choices[0].finish_reason == "length":
            raise self.ModelOutputError("synthetic truncated response")
        event["status"] = "ok"
        return response.choices[0].message.content

    def _refine_sql(self, question, sql, schemas, diagnostics):
        diagnostics.update(refine_prompt_policy=os.environ[probe.PROMPT_FLAG],
                           projection_contract={"reject": False, "reason": "synthetic_preserved"})
        try:
            return self.llm_ask("synthetic prompt", stage="refine")
        except Exception:
            return sql  # 真实matcher也吞掉精调异常；runner必须外层发现并停止。


class ProbeTests(unittest.TestCase):
    def setUp(self):
        for owner, name in [(requests.Session, "request"), (httpx.Client, "send")]:
            context = patch.object(owner, name, side_effect=AssertionError("合成测试禁止网络"))
            context.start()
            self.addCleanup(context.stop)
        context = patch.dict(os.environ, {}, clear=True)
        context.start()
        self.addCleanup(context.stop)

    def validate(self, data):
        manifest, cases, parent, resume, _ = data
        return probe.validate_history(manifest, cases, parent, resume, "e" * 64, "d" * 64)

    def selected(self, count=1):
        _, cases, _, _, history = fixture()
        ids = [case["case_id"] for case in cases[:count]]
        return probe.select_inputs(cases, history, ids, ())

    def small_plan(self, selected):
        return {"type": "prompt_probe_plan", "scope": "train_only_paired_refine",
                "case_ids": [item["input"]["case_id"] for item in selected], "max_requests": 2 * len(selected),
                "selected_inputs": [{"case_id": item["input"]["case_id"], "input_sha256": item["input_sha256"]}
                                    for item in selected],
                "variants": {"original": "0", "candidate": "1"},
                "model": "synthetic-model", "base_url": "https://example.invalid"}

    def run_synthetic(self, matcher=None, check=None, execute=None):
        selected = self.selected()
        plan, rows, executed = self.small_plan(selected), [], []
        matcher = matcher or FakeMatcher()

        def execute_default(item):
            executed.append(copy.deepcopy(item))
            return {"result": {"columns": ["name"], "rows": [{"name": "synthetic-vm"}], "row_count": 1}, "error": None}

        executor = SimpleNamespace(_cache={"stale": []}, execute=execute or execute_default)
        code = probe.run_probe(plan, selected, matcher, executor,
                               lambda case, output, elapsed: {"score": 5, "elapsed": elapsed}, rows.append,
                               check or (lambda variant: None))
        return code, rows, matcher, executed

    def test_full_fixed_training_history_and_source_link(self):
        parent, records = self.validate(fixture())
        self.assertEqual(len(records), 150)
        self.assertEqual(parent["feature_flags"], probe.V2_FLAGS)

    def test_scope_training_hash_source_and_request_drift_rejected(self):
        mutations = [
            lambda d: d[2][0].update(training_sha256="f" * 64),
            lambda d: d[2][0].update(scope="other"),
            lambda d: d[3][0].update(parent_sha256="f" * 64),
            lambda d: d[3][0]["source_sha256"].update({"training_data.py": "f" * 64}),
            lambda d: d[3][0]["case_ids"].reverse(),
            lambda d: d[2][2].update(case_index=2),
            lambda d: d[2][1].update(case_id="OUTSIDE-TRAINING"),
            lambda d: d[2][1].update(response_model="wrong-model"),
            lambda d: d[2][2]["diagnostics"]["llm_calls"].clear(),
            lambda d: d[3][-1].update(status="incomplete"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = copy.deepcopy(fixture())
                mutate(data)
                with self.assertRaises(ValueError):
                    self.validate(data)

    def test_selected_ids_are_fixed_and_ordered_without_score_replacement(self):
        _, cases, _, _, history = fixture()
        ids = (cases[7]["case_id"], cases[0]["case_id"])
        history[7]["score_without_time_penalty"] = -1
        result = probe.select_inputs(cases, history, ids, ())
        self.assertEqual([item["input"]["case_id"] for item in result], [cases[0]["case_id"], cases[7]["case_id"]])
        for item in result:
            self.assertEqual(item["input_sha256"], probe.digest(item["input"]))
        for bad in [("OUTSIDE-TRAINING",), (ids[0], ids[0]), tuple(case["case_id"] for case in cases[:17])]:
            with self.assertRaises(ValueError):
                probe.select_inputs(cases, history, bad, ())

    def test_missing_accepted_input_or_unique_refine_stops(self):
        _, cases, _, _, history = fixture()
        history[0]["diagnostics"]["matching"].pop("sql_before_refine")
        with self.assertRaises(ValueError):
            probe.select_inputs(cases, history, (cases[0]["case_id"],), ())

    def test_only_prompt_and_train_runner_may_differ_from_historical_source(self):
        historical = {name: "a" * 64 for name in probe.HISTORICAL_SOURCES}
        current = historical | {"implementation/runbook_matcher.py": "b" * 64, "train_live.py": "b" * 64}
        probe.validate_current_sources(historical, current)
        for name in set(probe.HISTORICAL_SOURCES) - {"implementation/runbook_matcher.py", "train_live.py"}:
            with self.subTest(name=name), self.assertRaises(ValueError):
                probe.validate_current_sources(historical, current | {name: "c" * 64})

    def test_preflight_prints_plan_without_runtime_or_network(self):
        selected = self.selected()
        plan = self.small_plan(selected)
        output = io.StringIO()
        with patch.object(probe, "prepare", return_value=(plan, selected, {"DEEPSEEK_API_KEY": "never-print-this"})), redirect_stdout(output):
            self.assertEqual(probe.main([]), 0)
        self.assertEqual(json.loads(output.getvalue()), plan)
        self.assertNotIn("never-print-this", output.getvalue())

    def test_run_requires_matching_plan_and_new_output_before_runtime(self):
        selected = self.selected()
        plan = self.small_plan(selected)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            path.write_text(json.dumps(plan | {"max_requests": 31}))
            arguments = [["--run"], ["--expected-plan", str(path)],
                         ["--run", "--expected-plan", str(path), "--output", str(Path(folder) / "new.jsonl")]]
            for args in arguments:
                with self.subTest(args=args), patch.object(probe, "prepare", return_value=(plan, selected, {})), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exc:
                    probe.main(args)
                self.assertEqual(exc.exception.code, 2)

    def test_budget_never_exceeds_32_and_failed_attempts_are_counted(self):
        budget = probe.RequestBudget(32)
        self.assertEqual([budget.take() for _ in range(32)], list(range(1, 33)))
        with self.assertRaises(RuntimeError):
            budget.take()
        self.assertEqual(budget.used, 32)
        for maximum in [0, 33, True, 2.0]:
            with self.assertRaises(ValueError):
                probe.RequestBudget(maximum)

    def test_pair_has_two_identical_inputs_and_complete_trace(self):
        code, rows, matcher, executed = self.run_synthetic()
        self.assertEqual(code, 0)
        self.assertEqual(matcher.seen_flags, ["0", "1"])
        self.assertEqual(len(executed), 2)
        self.assertEqual(executed[0], executed[1])
        self.assertTrue(matcher.closed)
        requests_rows = [row for row in rows if row["type"] == "request"]
        arms = [row for row in rows if row["type"] == "arm"]
        self.assertEqual([row["request_index"] for row in requests_rows], [1, 2])
        for row in requests_rows:
            for field in ["raw_proposal", "response_model", "requested_model", "prompt_tokens", "completion_tokens", "input_sha256"]:
                self.assertIn(field, row)
        self.assertTrue(all(arm["contracts"] and arm["execution"] and arm["untimed_score"] for arm in arms))
        self.assertEqual(rows[-1]["status"], "complete")
        self.assertEqual(rows[-1]["completed_pairs"], 1)
        self.assertEqual(rows[-1]["generation_requests"], 2)

    def test_full_16_case_budget_closes_exactly_32_refine_records(self):
        _, cases, _, _, history = fixture()
        selected = probe.select_inputs(cases, history, [case["case_id"] for case in cases[:12]],
                                       [case["case_id"] for case in cases[12:16]])
        plan, rows, matcher = self.small_plan(selected), [], FakeMatcher()
        executor = SimpleNamespace(_cache={}, execute=lambda item: {"result": None, "error": None})
        self.assertEqual(probe.run_probe(plan, selected, matcher, executor,
                                        lambda *args: {"score": 5}, rows.append, lambda variant: None), 0)
        self.assertEqual(matcher.sdk_calls, 32)
        self.assertEqual(len([row for row in rows if row["type"] == "request"]), 32)
        self.assertEqual(len([row for row in rows if row["type"] == "arm"]), 32)
        self.assertEqual(len([row for row in rows if row["type"] == "pair"]), 16)
        self.assertEqual(rows[-1]["status"], "complete")

    def test_real_refine_function_and_event_capture_with_synthetic_sdk(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
        import runbook_matcher as matcher
        selected, rows, fake_sdk = self.selected(), [], FakeMatcher()
        plan = self.small_plan(selected)
        client = SimpleNamespace(max_retries=0, close=lambda: None,
                                 chat=SimpleNamespace(completions=SimpleNamespace(create=fake_sdk.create)))

        def get_client():
            matcher._llm_client = client
            return client

        executor = SimpleNamespace(_cache={}, execute=lambda item: {"result": None, "error": None})
        with patch.object(matcher, "DEEPSEEK_MODEL", plan["model"]), \
                patch.object(matcher, "DEEPSEEK_BASE_URL", plan["base_url"]), \
                patch.object(matcher, "_llm_client", None), patch.object(matcher, "_llm_events", []), \
                patch.object(matcher, "_schema_columns", {"VM_NOVA": ["name"]}), \
                patch.object(matcher, "get_llm", side_effect=get_client), \
                patch.object(matcher, "_warm_schema_cache"), patch.object(matcher, "_get_table_schemas", return_value="synthetic schema"), \
                patch.dict(os.environ, dict(probe.V2_FLAGS) | {"RUNBOOK_MAX_LLM_CALLS": "2", "RUNBOOK_MAX_OUTPUT_TOKENS": "1024"}):
            self.assertEqual(probe.run_probe(plan, selected, matcher, executor,
                                            lambda *args: {"score": 5}, rows.append, lambda variant: None), 0)
        self.assertEqual(fake_sdk.seen_flags, ["0", "1"])
        arms = [row for row in rows if row["type"] == "arm"]
        self.assertEqual([row["contracts"]["refine_prompt_policy"] for row in arms],
                         ["original", "preserve_output_contract"])
        self.assertTrue(all(row["contracts"]["projection_contract"]["reason"] == "columns_preserved" for row in arms))

    def test_timeout_and_model_mismatch_stop_after_first_attempt(self):
        for matcher in [FakeMatcher("timeout"), FakeMatcher("unknown"), FakeMatcher(response_model="wrong-model")]:
            with self.subTest(failure=matcher.failure, model=matcher.response_model):
                code, rows, matcher, executed = self.run_synthetic(matcher)
                self.assertEqual(code, 1)
                self.assertEqual(matcher.sdk_calls, 1)
                self.assertEqual(executed, [])
                self.assertEqual(rows[-1]["status"], "incomplete")
                self.assertEqual(rows[-1]["generation_requests"], 1)
                self.assertEqual(rows[-1]["failed_events"], 1)
                self.assertEqual(rows[-1]["completed_pairs"], 0)
                self.assertEqual(len([row for row in rows if row["type"] == "arm"]), 1)
                self.assertNotIn("synthetic timeout; must not be logged", json.dumps(rows))

    def test_known_bad_model_output_falls_back_without_retry_and_finishes_pair(self):
        code, rows, matcher, executed = self.run_synthetic(FakeMatcher("length"))
        self.assertEqual((code, matcher.sdk_calls, len(executed)), (0, 2, 2))
        arms = [row for row in rows if row["type"] == "arm"]
        self.assertTrue(all(arm["proposal_status"] == "invalid_model_output_fallback" for arm in arms))
        self.assertTrue(all(arm["sql_after_refine"] == arm["sql_before_refine"] for arm in arms))
        self.assertEqual(rows[-1]["status"], "complete")
        self.assertEqual(rows[-1]["failed_model_outputs"], 2)
        self.assertEqual(rows[-1]["transport_errors"], 0)
        self.assertEqual(rows[-1]["prompt_tokens"], 24)
        self.assertEqual(rows[-1]["completion_tokens"], 10)

    def test_drift_after_response_keeps_raw_and_prevents_execution(self):
        matcher = FakeMatcher()

        def check(variant):
            if matcher.sdk_calls:
                raise RuntimeError("synthetic source drift")

        code, rows, matcher, executed = self.run_synthetic(matcher, check)
        self.assertEqual((code, matcher.sdk_calls, executed), (1, 1, []))
        request = next(row for row in rows if row["type"] == "request")
        self.assertEqual(request["raw_proposal"], "SELECT name FROM CLOUD_VM_NOVA")
        self.assertEqual(rows[-1]["status"], "incomplete")

    def test_drift_before_any_request_stops_with_zero_budget(self):
        def check(variant):
            raise RuntimeError("synthetic training drift")
        code, rows, matcher, executed = self.run_synthetic(check=check)
        self.assertEqual((code, matcher.sdk_calls, executed), (1, 0, []))
        self.assertEqual(rows[-1]["generation_requests"], 0)
        self.assertEqual(rows[-1]["status"], "incomplete")

    def test_frozen_checks_real_hash_and_environment_contract_before_network(self):
        root, split = Path("/synthetic/B"), Path("/synthetic/train")
        hashes = {root / "train_prompt_probe.py": "runner", split / "train.json": "training",
                  split / "train_history.jsonl": "training-history", split / "manifest.json": "manifest",
                  root / "experiments/parent.jsonl": "parent"}
        config = {"DEEPSEEK_API_KEY": "synthetic-secret", "DEEPSEEK_MODEL": "synthetic-model",
                  "DEEPSEEK_BASE_URL": "https://example.invalid"}
        plan = {"source_sha256": {"train_prompt_probe.py": "runner"}, "training_sha256": "training",
                "training_history_sha256": "training-history", "split_manifest_sha256": "manifest",
                "history_sha256": {"parent.jsonl": "parent"}, "feature_flags": dict(probe.V2_FLAGS),
                "variants": {"original": "0", "candidate": "1"}, "max_requests": 32, "timeout_seconds": 60.0,
                "model": "synthetic-model", "base_url": "https://example.invalid"}
        environment = dict(probe.V2_FLAGS) | config | {probe.PROMPT_FLAG: "0", "RUNBOOK_MAX_LLM_CALLS": "32",
                                                     "RUNBOOK_MAX_OUTPUT_TOKENS": "1024", "RUNBOOK_LLM_TIMEOUT": "60.0"}
        with patch.object(probe, "HERE", root), patch.object(probe, "SPLIT", split), \
                patch.object(probe, "sha", side_effect=lambda path: hashes[path]), \
                patch.object(probe, "read_local_config", return_value=config), patch.dict(os.environ, environment, clear=True):
            probe.frozen(plan, "original", config)
            for path in hashes:
                previous = hashes[path]
                hashes[path] = "drifted"
                with self.subTest(path=path), self.assertRaises(RuntimeError):
                    probe.frozen(plan, "original", config)
                hashes[path] = previous
            for name in environment:
                with self.subTest(variable=name), patch.dict(os.environ, {name: "drifted"}), self.assertRaises(RuntimeError):
                    probe.frozen(plan, "original", config)
            with patch.object(probe, "read_local_config", return_value=config | {"DEEPSEEK_API_KEY": "changed"}), self.assertRaises(RuntimeError):
                probe.frozen(plan, "original", config)

    def test_input_mutation_cannot_change_both_arms_from_frozen_plan(self):
        selected = self.selected()
        plan = self.small_plan(selected)
        selected[0]["input"]["sql_before_refine"] = "SELECT other FROM CLOUD_VM_NOVA"
        selected[0]["input_sha256"] = probe.digest(selected[0]["input"])
        with self.assertRaises(ValueError):
            probe.run_probe(plan, selected, FakeMatcher(), None, None, lambda row: None, lambda variant: None)

    def test_execution_failure_never_becomes_completed_pair(self):
        code, rows, matcher, _ = self.run_synthetic(execute=lambda item: {"error": "synthetic SQL error", "result": None})
        self.assertEqual((code, matcher.sdk_calls), (1, 1))
        arm = next(row for row in rows if row["type"] == "arm")
        self.assertEqual(arm["status"], "incomplete")
        self.assertEqual(arm["execution"]["error"], "synthetic SQL error")
        self.assertEqual(rows[-1]["completed_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
