"""预先固定的六题候选诊断；默认预检，--run 才执行另行获准的 18 次额度。"""

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
    plan_file = HERE / "experiments/whitebox_20261029_projection_plan.json"
    scope = json.loads(plan_file.read_text())
    baseline = HERE / "experiments" / scope["baseline"]
    if sha(baseline) != scope["baseline_sha256"]:
        parser.error("固定对照记录哈希不一致")
    for line in (HERE / ".env.local").read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}:
            os.environ[name] = value
    if os.environ.get("DEEPSEEK_MODEL") != scope["model"] or os.environ.get("DEEPSEEK_BASE_URL") != scope["base_url"]:
        parser.error("模型配置与固定授权范围不一致")
    os.environ["RUNBOOK_MAX_LLM_CALLS"] = str(scope["max_requests_this_check"])
    os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"] = str(scope["max_output_tokens"])
    os.environ.update(scope["candidate_factor"])

    import runbook_matcher as matcher
    from runbook_system import RunbookQuerySystem
    from evaluator import evaluate_case
    from run_whitebox import now, result_preview, peak_memory_mib

    test_file = HERE / "CMDB用例集-白盒200.json"
    all_cases = {c["case_id"]: c for c in json.loads(test_file.read_text())["cases"]}
    cases = [all_cases[cid] for cid in scope["case_ids"]]
    baseline_plan = json.loads(baseline.read_text().splitlines()[0])
    if sha(test_file) != baseline_plan["dataset_sha256"]:
        parser.error("测试数据版本变化")
    plan = {"type": "plan", "created_at": now(), "scope": scope,
            "authorization": "user explicitly approved fixed six-case rerun within remaining budget",
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
    output = HERE / "experiments/whitebox_20261029_projection_live.jsonl"
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
            summary = {"type": "summary", "status": "complete" if completed else "incomplete",
                       "completed_cases": len(records), "planned_cases": len(cases),
                       "score": round(sum(r["score"] for r in records), 1),
                       "untimed_score": round(sum(r["score_without_time_penalty"] for r in records), 1),
                       "generation_requests": len(events), "requests_total_including_baseline": 579 + len(events),
                       "failed_requests": sum(e["status"] != "ok" for e in events),
                       "prompt_tokens": sum(e["prompt_tokens"] for e in events),
                       "completion_tokens": sum(e["completion_tokens"] for e in events),
                       "wall_seconds": round(time.perf_counter() - started, 3),
                       "peak_evaluation_process_mib": peak_memory_mib(), "finished_at": now()}
            write(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            if matcher._llm_client:
                matcher._llm_client.close()
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
