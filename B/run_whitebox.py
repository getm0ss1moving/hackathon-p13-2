"""固定版本白盒单轮记录。默认只预检，--run 才调用模型；原评估入口和评分函数不变。"""

import argparse
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def peak_memory_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)


def percentile(values, q):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * q) - 1)] if values else None


def result_preview(result):
    if isinstance(result, list):
        return [result_preview(part) for part in result]
    if not isinstance(result, dict):
        return None
    return {"columns": result.get("columns", []), "row_count": result.get("row_count"),
            "rows_preview": result.get("rows", [])[:3]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="显式执行已获授权的真实模型测试")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-requests", type=int, default=600)
    parser.add_argument("--spent-requests", type=int, default=0, help="本轮此前已用请求数，从总上限扣除")
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.limit < 1 or args.max_requests < 1 or args.max_output_tokens < 1:
        parser.error("题数、请求上限和输出 token 上限必须为正整数")
    if args.spent_requests < 0 or args.spent_requests >= args.max_requests:
        parser.error("此前已用请求数必须非负且小于本轮总上限")

    # 只加载列出的配置项，不执行 shell，不输出密钥。
    local = HERE / ".env.local"
    allowed = {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "RUNBOOK_LLM_TIMEOUT",
               "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS"}
    if local.is_file():
        for line in local.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name in allowed:
                os.environ[name] = value
    remaining_requests = args.max_requests - args.spent_requests
    os.environ["RUNBOOK_MAX_LLM_CALLS"] = str(remaining_requests)
    os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"] = str(args.max_output_tokens)
    test_file = HERE / "CMDB用例集-白盒200.json"
    cases = json.loads(test_file.read_text(encoding="utf-8"))["cases"]
    if args.limit > len(cases):
        parser.error(f"题数超过实际白盒范围 {len(cases)}")
    cases = cases[:args.limit]
    sys.path.insert(0, str(HERE / "implementation"))
    import runbook_items
    import runbook_matcher as matcher
    import runbook_system as system_module
    import evaluator
    import quick_eval

    manifest = json.loads((HERE / "baseline_manifest.json").read_text())
    for relative, expected in manifest["readonly_files"].items():
        if hashlib.sha256((HERE / relative).read_bytes()).hexdigest() != expected:
            parser.error(f"只读文件校验失败：{relative}")
    plan = {
        "type": "plan", "created_at": now(), "working_directory": str(HERE),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
        "source_sha256": {name: hashlib.sha256((HERE / "implementation" / name).read_bytes()).hexdigest()
                          for name in ["runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "evaluator.py", "runbook_executor.py"]},
        "dataset_sha256": hashlib.sha256(test_file.read_bytes()).hexdigest(),
        "case_count": len(cases), "case_order": "original file order", "repeats": 1,
        "model": matcher.DEEPSEEK_MODEL, "base_url": matcher.DEEPSEEK_BASE_URL,
        "max_requests": remaining_requests, "authorized_total_max_requests": args.max_requests,
        "requests_spent_before_run": args.spent_requests, "max_output_tokens": args.max_output_tokens,
        "sdk_max_retries": 0, "thinking": "provider default", "temperature": "provider default",
        "template_count": len(runbook_items.RUNBOOK_ITEMS),
        "preserve_template_columns": os.environ.get("RUNBOOK_PRESERVE_TEMPLATE_COLUMNS") == "1",
        "cache_policy": "new system process; schema warmup excluded; executor cache shared across cases",
        "score_policy": "original evaluate_case; one pass; no official weighting or template adjustment",
        "blackbox": "missing; not tested", "generation_requests_before_run": len(matcher.get_llm_events()),
    }
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.run:
        print("预检完成，未调用模型。使用 --run 执行已获授权的测试。")
        return 0
    if not matcher.DEEPSEEK_API_KEY.strip():
        parser.error("本机未配置模型密钥")
    if matcher.get_llm_events():
        parser.error("请从新进程运行，避免混入既有调用或缓存")
    output_path = args.output or HERE / "experiments" / ("whitebox_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    original_ask = matcher.llm_ask
    original_evaluate = evaluator.evaluate_case
    original_init = system_module.RunbookQuerySystem.__init__
    started = time.perf_counter()
    usage_started = resource.getrusage(resource.RUSAGE_SELF)
    previous_logging = logging.root.manager.disable
    with output_path.open("x", encoding="utf-8") as stream:
        def write(record):
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()

        write(plan)

        def tracked_init(self):
            original_init(self)
            write({"type": "initialization", **self.initialization_metrics,
                   "peak_process_memory_mib": peak_memory_mib()})

        def tracked_ask(prompt, stage="unknown"):
            before = len(matcher.get_llm_events())
            error = None
            try:
                return original_ask(prompt, stage)
            except Exception as exc:
                error = {"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}
                raise
            finally:
                events = matcher.get_llm_events()
                for event in events[before:]:
                    write({"type": "request", "case_id": cases[len(records)]["case_id"],
                           **event, **(error or {})})

        def tracked_evaluate(case, output, elapsed):
            scored = original_evaluate(case, output, elapsed)
            untimed = original_evaluate(case, output, 0)
            row = {"type": "case", "case_index": len(records) + 1, **scored,
                   "score_without_time_penalty": untimed["score"],
                   "matched_runbook": output.get("matched_runbook"), "api_call": output.get("api_call"),
                   "sql": output.get("sql"), "result": result_preview(output.get("result")),
                   "diagnostics": output.get("diagnostics"), "peak_process_memory_mib": peak_memory_mib()}
            records.append(row)
            write(row)
            return scored

        matcher.llm_ask = tracked_ask
        evaluator.evaluate_case = tracked_evaluate
        system_module.RunbookQuerySystem.__init__ = tracked_init
        exit_code = 1
        try:
            exit_code = quick_eval.main([str(args.limit)])
        except Exception as exc:
            write({"type": "run_error", "error_type": type(exc).__name__})
        finally:
            matcher.llm_ask = original_ask
            evaluator.evaluate_case = original_evaluate
            system_module.RunbookQuerySystem.__init__ = original_init
            logging.disable(previous_logging)
            events = matcher.get_llm_events()
            elapsed = [row["elapsed"] for row in records]
            usage_finished = resource.getrusage(resource.RUSAGE_SELF)
            summary = {"type": "summary", "finished_at": now(),
                       "status": "complete" if exit_code == 0 and len(records) == len(cases) else "incomplete",
                       "completed_cases": len(records), "planned_cases": len(cases), "exit_code": exit_code,
                       "max_possible_score_planned": len(cases) * 5,
                       "max_possible_score_completed": len(records) * 5,
                       "total_score": round(sum(row["score"] for row in records), 1),
                       "score_without_time_penalty": round(sum(row["score_without_time_penalty"] for row in records), 1),
                       "correct_answers": sum(row["reason"].startswith("答案正确") for row in records),
                       "partial_answers": sum(row["reason"].startswith("部分正确") for row in records),
                       "wrong_answers": sum(row["reason"].startswith("答案错误") for row in records),
                       "abstentions": sum(row["score_without_time_penalty"] == 0 for row in records),
                       "over_4s": sum(t > 4 for t in elapsed), "over_6s": sum(t > 6 for t in elapsed),
                       "elapsed_p50": percentile(elapsed, .5), "elapsed_p95": percentile(elapsed, .95),
                       "generation_requests": len(events), "failed_requests": sum(e["status"] != "ok" for e in events),
                       "authorized_total_requests_used": args.spent_requests + len(events),
                       "prompt_tokens": sum(e["prompt_tokens"] for e in events),
                       "completion_tokens": sum(e["completion_tokens"] for e in events),
                       "wall_seconds": round(time.perf_counter() - started, 3),
                       "process_cpu_seconds": round(usage_finished.ru_utime + usage_finished.ru_stime - usage_started.ru_utime - usage_started.ru_stime, 3),
                       "peak_process_memory_mib": peak_memory_mib(),
                       "memory_scope": "evaluation process only; data server is separate"}
            write(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            if matcher._llm_client:
                matcher._llm_client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
