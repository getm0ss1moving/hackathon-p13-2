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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    plan_file = HERE / "experiments/resource_gate_20261029_plan.json"
    scope = json.loads(plan_file.read_text())
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

    logging.disable(logging.CRITICAL)
    records = []
    started = time.perf_counter()
    output = HERE / "experiments/resource_gate_20261029_live.jsonl"
    completed = False
    with output.open("x", encoding="utf-8") as stream:
        def write(row):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()

        write(plan)
        try:
            system = RunbookQuerySystem()
            write({"type": "initialization", **system.initialization_metrics})
            for case in cases:
                first_event = len(matcher.get_llm_events())
                t0 = time.perf_counter()
                try:
                    answer = system.query(case["question"])
                    elapsed = time.perf_counter() - t0
                finally:
                    for event in matcher.get_llm_events()[first_event:]:
                        write({"type": "request", "case_id": case["case_id"], **event})
                scored = evaluate_case(case, answer, elapsed)
                row = {"type": "case", **scored,
                       "group": "official_subset" if case["case_id"] in scope["official_case_ids"] else "derived_diagnostic",
                       "expected_match": scope["expected_match"][case["case_id"]],
                       "expected_behavior_observed": bool(answer.get("matched_runbook")) == scope["expected_match"][case["case_id"]],
                       "score_without_time_penalty": evaluate_case(case, answer, 0)["score"],
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
                       "expected_behavior_observed": sum(r["expected_behavior_observed"] for r in records),
                       "generation_requests": len(events), "all_rounds_requests_so_far": scope["prior_round_requests_used"] + len(events),
                       "failed_requests": sum(e["status"] != "ok" for e in events),
                       "prompt_tokens": sum(e["prompt_tokens"] for e in events), "completion_tokens": sum(e["completion_tokens"] for e in events),
                       "wall_seconds": round(time.perf_counter() - started, 3), "peak_evaluation_process_mib": peak_memory_mib(), "finished_at": now()}
            write(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            if matcher._llm_client:
                matcher._llm_client.close()
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
