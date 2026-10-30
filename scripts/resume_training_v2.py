"""固定v2未完成训练题的独立补测提案；仅在新的人工补测授权后使用--run。"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

from training_data import load_training, sha
from run_whitebox import now, result_preview

HERE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expected-plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest, train, _ = load_training()
    parent = HERE/"experiments/train150_v2_live.jsonl"
    prior = [json.loads(line) for line in parent.read_text().splitlines()]
    previous, summary = prior[0], prior[-1]
    completed = [row for row in prior if row["type"] == "case"]
    requests = [row for row in prior if row["type"] == "request"]
    if (previous.get("scope") != "train_only" or summary.get("status") != "incomplete"
            or len(completed) != 147 or len(requests) != 289
            or [row["case_id"] for row in completed] != [row["case_id"] for row in train[:147]]):
        parser.error("父运行与既定147题超时记录不匹配，不推断其他范围")
    cases = train[147:]
    if requests[-1].get("error_type") != "APITimeoutError" or requests[-1]["case_id"] != cases[0]["case_id"]:
        parser.error("最后请求不是既定未完成题的接口超时")
    local = HERE/".env.local"
    if local.is_file():
        for line in local.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}:
                os.environ[name] = value
    flags = previous["feature_flags"]
    os.environ.update(flags)
    os.environ["RUNBOOK_MAX_LLM_CALLS"] = "9"
    os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"] = "1024"
    sys.path.insert(0, str(HERE/"implementation"))
    import runbook_matcher as matcher
    from runbook_system import RunbookQuerySystem
    from evaluator import evaluate_case
    plan = {"type": "resume_plan", "scope": "train_only_resume", "case_ids": [case["case_id"] for case in cases],
            "case_count": 3, "parent_sha256": sha(parent), "source_sha256": previous["source_sha256"],
            "runner_sha256": sha(Path(__file__)), "training_sha256": manifest["train_sha256"],
            "feature_flags": flags, "model": previous["model"], "base_url": previous["base_url"],
            "max_requests": 9, "max_output_tokens": 1024, "sdk_max_retries": 0,
            "previous_used_requests": 289, "original_total_limit": 450, "max_total_after_resume": 298,
            "manual_retry_of_timeout_case": cases[0]["case_id"], "new_process_and_executor_cache": True,
            "claim_boundary": "147 incomplete plus separate 3-case coverage; never a complete single-pass score"}
    historical_paths = {name: HERE / ("scripts/" + name if "/" not in name else name)
                        for name in plan["source_sha256"]}
    if not all(sha(historical_paths[name]) == digest for name, digest in plan["source_sha256"].items()):
        parser.error("源代码已偏离父运行，未调用模型")
    if matcher.DEEPSEEK_MODEL != plan["model"] or matcher.DEEPSEEK_BASE_URL != plan["base_url"]:
        parser.error("模型配置偏离父运行")
    if args.expected_plan and json.loads(args.expected_plan.read_text()) != plan:
        parser.error("补测提案不匹配")
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.run:
        return 0
    if not args.expected_plan or not args.output or args.output.exists() or matcher.get_llm_events():
        parser.error("需要新的补测授权、匹配计划、新进程与未存在的输出文件")
    original_ask, original_create = matcher.llm_ask, None
    records, identities, mismatches = [], {}, []
    started, exit_code = time.perf_counter(), 1

    def frozen():
        if (sha(parent) != plan["parent_sha256"] or sha(Path(__file__)) != plan["runner_sha256"]
                or any(sha(HERE/name) != value for name, value in plan["source_sha256"].items())
                or any(os.environ.get(name) != value for name, value in flags.items())
                or os.environ.get("RUNBOOK_MAX_LLM_CALLS") != "9"
                or os.environ.get("RUNBOOK_MAX_OUTPUT_TOKENS") != "1024" or mismatches):
            raise RuntimeError("补测来源/配置漂移，停止")

    logging.disable(logging.CRITICAL)
    with args.output.open("x") as stream:
        def write(row):
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
            stream.flush()
        write(plan)
        try:
            frozen()
            system = RunbookQuerySystem()
            original_create = matcher._llm_client.chat.completions.create
            def create(*values, **options):
                if matcher._llm_client.max_retries != 0:
                    raise RuntimeError("重试必须为0")
                response = original_create(*values, **options)
                identity = {"requested_model": options.get("model"), "response_model": getattr(response, "model", None)}
                identities[len(matcher.get_llm_events())-1] = identity
                if identity["requested_model"] != plan["model"] or identity["response_model"] != plan["model"]:
                    mismatches.append(identity)
                return response
            matcher._llm_client.chat.completions.create = create
            def ask(prompt, stage="unknown"):
                frozen()
                before, error = len(matcher.get_llm_events()), {}
                try:
                    value = original_ask(prompt, stage)
                    frozen()
                    return value
                except Exception as exc:
                    error = {"error_type": type(exc).__name__}
                    raise
                finally:
                    for index, event in enumerate(matcher.get_llm_events()[before:], before):
                        write({"type": "request", "case_id": cases[len(records)]["case_id"], **event,
                               "requested_model": plan["model"], "response_model": None, **identities.get(index, {}), **error})
            matcher.llm_ask = ask
            for case in cases:
                frozen()
                t0 = time.perf_counter()
                output = system.query(case["question"])
                elapsed = time.perf_counter()-t0
                frozen()
                scored, untimed = evaluate_case(case, output, elapsed), evaluate_case(case, output, 0)
                row = {"type": "case", **scored, "question": case["question"], "score_without_time_penalty": untimed["score"],
                       "matched_runbook": output.get("matched_runbook"), "api_call": output.get("api_call"),
                       "sql": output.get("sql"), "result": result_preview(output.get("result")), "diagnostics": output.get("diagnostics")}
                records.append(row)
                write(row)
            exit_code = 0
        except Exception as exc:
            write({"type": "run_error", "error_type": type(exc).__name__})
        finally:
            events = matcher.get_llm_events()
            write({"type": "summary", "status": "complete" if exit_code == 0 and len(records) == 3 else "incomplete",
                   "scope": "train_only_resume", "completed_cases": len(records), "generation_requests": len(events),
                   "total_requests_including_parent": 289+len(events), "model_identity_mismatches": mismatches,
                   "full_quality_answers": sum(row["score_without_time_penalty"] == 5 for row in records),
                   "wall_seconds": round(time.perf_counter()-started, 3), "single_pass_full_150": False})
            matcher.llm_ask = original_ask
            if matcher._llm_client is not None:
                if original_create is not None:
                    matcher._llm_client.chat.completions.create = original_create
                matcher._llm_client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
