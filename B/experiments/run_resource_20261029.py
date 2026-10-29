"""资源门禁固定诊断组；默认预检，--run 执行另行获准的本轮 24 次额度。"""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "implementation"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnostic_outcome(case_id, answer, untimed_score, scope):
    """验证预登记路径；选择器提前拒答不能证明空查找保护已执行。"""
    expected_match = scope["expected_match"][case_id]
    matched = bool(answer.get("matched_runbook"))
    matching = (answer.get("diagnostics") or {}).get("matching", {})
    reason = matching.get("reason")
    lookup = matching.get("resource_lookup") or {}
    if case_id in {"CMDB-036", "DEV-HOST-REPLACED"}:
        exercised = matched and reason == "matched" and lookup.get("valid") is True
    elif case_id == "DEV-NONEXISTENT-HOST":
        exercised = not matched and reason == "invalid_resource_lookup" and lookup.get("valid") is False
    elif not expected_match:
        exercised = not matched and reason == "resource_mismatch"
    else:
        exercised = matched and reason == "matched"
    return {"expected_match": expected_match, "match_expectation_observed": matched == expected_match,
            "expected_path_exercised": exercised,
            "diagnostic_passed": exercised and (untimed_score == 5 if expected_match else untimed_score == 0)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    plan_file = HERE / "experiments/resource_gate_20261029_plan.json"
    scope = json.loads(plan_file.read_text())
    if (type(scope.get("max_requests")) is not int or not 1 <= scope["max_requests"] <= 24
            or type(scope.get("max_output_tokens")) is not int or not 1 <= scope["max_output_tokens"] <= 1024
            or scope.get("sdk_max_retries") != 0 or scope.get("RUNBOOK_PRESERVE_TEMPLATE_COLUMNS") != "0"):
        parser.error("计划超出本轮调用边界或混入输出列实验")
    baseline = HERE / "experiments" / scope["baseline"]
    if sha(baseline) != scope["baseline_sha256"]:
        parser.error("固定基线记录哈希不一致")
    for line in (HERE / ".env.local").read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}:
            os.environ[name] = value
    if os.environ.get("DEEPSEEK_MODEL") != scope["model"] or os.environ.get("DEEPSEEK_BASE_URL") != scope["base_url"]:
        parser.error("模型配置与固定范围不一致")
    os.environ["RUNBOOK_MAX_LLM_CALLS"] = str(scope["max_requests"])
    os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"] = str(scope["max_output_tokens"])
    os.environ["RUNBOOK_PRESERVE_TEMPLATE_COLUMNS"] = scope["RUNBOOK_PRESERVE_TEMPLATE_COLUMNS"]
    import runbook_matcher as matcher
    from runbook_system import RunbookQuerySystem
    from evaluator import evaluate_case
    from run_whitebox import now, result_preview, peak_memory_mib

    test_file = HERE / "CMDB用例集-白盒200.json"
    all_cases = {c["case_id"]: c for c in json.loads(test_file.read_text())["cases"]}
    all_cases.update({c["case_id"]: c for c in scope["derived_cases"]})
    cases = [all_cases[cid] for cid in scope["case_order"]]
    baseline_plan = json.loads(baseline.read_text().splitlines()[0])
    if sha(test_file) != baseline_plan["dataset_sha256"]:
        parser.error("测试数据版本变化")
    for name in baseline_plan["source_sha256"]:
        expected = subprocess.check_output(["git", "show", scope["candidate_commit"] + ":B/implementation/" + name], cwd=HERE)
        if sha(HERE / "implementation" / name) != hashlib.sha256(expected).hexdigest():
            parser.error(f"源码与固定候选版本不同：{name}")
    for relative, expected in json.loads((HERE / "baseline_manifest.json").read_text())["readonly_files"].items():
        if sha(HERE / relative) != expected:
            parser.error(f"只读文件校验失败：{relative}")
    if matcher.get_llm_events():
        parser.error("需从新进程运行")
    plan = {"type": "plan", "created_at": now(), "scope": scope,
            "authorization": "--run only after explicit approval of this eight-case scope",
            "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
            "source_sha256": {name: sha(HERE / "implementation" / name) for name in baseline_plan["source_sha256"]},
            "script_sha256": sha(Path(__file__)), "plan_sha256": sha(plan_file),
            "dataset_sha256": sha(test_file), "cache_policy": baseline_plan["cache_policy"]}
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.run:
        print("预检完成，未调用模型。")
        return 0

    records = []
    started = time.perf_counter()
    output = args.output or HERE / "experiments/resource_gate_20261029_live.jsonl"
    completed = False
    response_models = {}
    with output.open("x", encoding="utf-8") as stream:
        previous_logging = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        def write(row):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()

        write(plan)
        try:
            system = RunbookQuerySystem()
            write({"type": "initialization", **system.initialization_metrics})
            if matcher._llm_client is not None:
                original_create = matcher._llm_client.chat.completions.create

                def capture_model(*call_args, **call_kwargs):
                    index = len(matcher.get_llm_events()) - 1
                    response = original_create(*call_args, **call_kwargs)
                    response_models[index] = getattr(response, "model", None)
                    return response

                matcher._llm_client.chat.completions.create = capture_model
            for case in cases:
                first_event = len(matcher.get_llm_events())
                t0 = time.perf_counter()
                try:
                    answer = system.query(case["question"])
                    elapsed = time.perf_counter() - t0
                finally:
                    for index, event in enumerate(matcher.get_llm_events()[first_event:], first_event):
                        write({"type": "request", "case_id": case["case_id"], **event,
                               "requested_model": scope["model"], "response_model": response_models.get(index)})
                scored = evaluate_case(case, answer, elapsed)
                untimed = evaluate_case(case, answer, 0)["score"]
                row = {"type": "case", **scored,
                       "group": "official_subset" if case["case_id"] in scope["official_case_ids"] else "derived_diagnostic",
                       **diagnostic_outcome(case["case_id"], answer, untimed, scope),
                       "score_without_time_penalty": untimed,
                       **{k: answer.get(k) for k in ["matched_runbook", "api_call", "sql", "diagnostics"]},
                       "result": result_preview(answer.get("result"))}
                records.append(row)
                write(row)
                print(case["case_id"], scored["score"], scored["reason"], flush=True)
            completed = True
        except Exception as exc:
            write({"type": "run_error", "error_type": type(exc).__name__})
        finally:
            events = matcher.get_llm_events()
            official = [r for r in records if r["group"] == "official_subset"]
            summary = {"type": "summary", "status": "complete" if completed else "incomplete",
                       "completed_cases": len(records), "planned_cases": len(cases),
                       "official_cases": len(official), "official_score": round(sum(r["score"] for r in official), 1),
                       "official_untimed_score": round(sum(r["score_without_time_penalty"] for r in official), 1),
                       "match_expectation_observed": sum(r["match_expectation_observed"] for r in records),
                       "expected_paths_exercised": sum(r["expected_path_exercised"] for r in records),
                       "diagnostics_passed": sum(r["diagnostic_passed"] for r in records),
                       "generation_requests": len(events),
                       "previous_600_request_budget_used": scope["prior_round_requests_used"],
                       "combined_requests_for_previous_budget_and_this_check": scope["prior_round_requests_used"] + len(events),
                       "failed_requests": sum(e["status"] != "ok" for e in events),
                       "prompt_tokens": sum(e["prompt_tokens"] for e in events), "completion_tokens": sum(e["completion_tokens"] for e in events),
                       "wall_seconds": round(time.perf_counter() - started, 3), "peak_evaluation_process_mib": peak_memory_mib(), "finished_at": now()}
            write(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            if matcher._llm_client:
                matcher._llm_client.close()
            logging.disable(previous_logging)
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
