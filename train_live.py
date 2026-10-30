"""固定150训练题或其显式子集真实诊断，默认只预检；无留出集合入口。"""

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

from training_data import load_training, sha, SPLIT
from run_whitebox import now, result_preview, peak_memory_mib, percentile

HERE = Path(__file__).resolve().parent
V2_HISTORY_FILES = ("train150_v2_live.jsonl", "train150_v2_resume_live.jsonl")


def select_cases(cases, requested_ids, phase):
    """只缩小load_training给出的固定成员；题号只用于冻结实验范围。"""
    if len(cases) != 150 or len({case["case_id"] for case in cases}) != 150:
        raise ValueError("必须由load_training读取完整固定150训练题")
    if requested_ids is None:
        if phase is not None:
            raise ValueError("--phase必须与明确的--case-id子集一起使用")
        return cases, "train_only", "full_training"
    if (not requested_ids or len(requested_ids) > 150
            or any(not isinstance(value, str) or not value.strip() for value in requested_ids)):
        raise ValueError("子集题号不能为空且不能超过150个")
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("子集题号不能重复")
    if phase not in {"failure_probe", "passed_regression"}:
        raise ValueError("子集必须显式指定--phase failure_probe或passed_regression")
    known = {case["case_id"] for case in cases}
    if not set(requested_ids) <= known:
        raise ValueError("子集包含固定训练150之外的题号")
    return [case for case in cases if case["case_id"] in requested_ids], "train_subset", phase


def phase_metadata(selected, history, phase):
    """回归严格限v2已过题；失败小测是显式标签，可包含之后新发现的失败。"""
    if phase not in {"failure_probe", "passed_regression"}:
        raise ValueError("未知子集阶段")
    if len(history) != 150 or len({row["case_id"] for row in history}) != 150:
        raise ValueError("子集阶段必须引用完整150训练历史")
    by_id = {row["case_id"]: row for row in history}
    qualities = []
    for case in selected:
        prior = by_id.get(case["case_id"], {})
        quality = prior.get("score_without_time_penalty")
        if prior.get("question") != case["question"] or type(quality) not in {int, float}:
            raise ValueError("阶段历史缺题、题文或无时延质量")
        if phase == "passed_regression" and quality != 5:
            raise ValueError("passed_regression只能选固定v2历史已满5质量的训练题")
        qualities.append({"case_id": case["case_id"], "v2_quality": quality})
    return {"reference": "fixed v2 parent147 plus resume3; not one continuous pass",
            "membership_policy": ("v2 untimed quality must equal 5" if phase == "passed_regression" else
                                  "explicit failure-probe label; v2 quality may be 5 for later-discovered failures"),
            "case_quality": qualities,
            "v2_full_quality_members": [item["case_id"] for item in qualities if item["v2_quality"] == 5]}


def subset_history(manifest, all_cases, selected, phase):
    # 复用既有严格parent+resume来源、顺序、请求账目核验；没有任意历史文件入口。
    from train_prompt_probe import validate_history
    paths = [HERE/"experiments"/name for name in V2_HISTORY_FILES]
    rows = [[json.loads(line) for line in path.read_text().splitlines()] for path in paths]
    parent, history = validate_history(manifest, all_cases, rows[0], rows[1], sha(paths[0]), sha(SPLIT/"manifest.json"))
    metadata = phase_metadata(selected, history, phase)
    metadata.update(file_sha256={path.name: sha(path) for path in paths},
                    source_sha256=parent["source_sha256"], training_sha256=parent["training_sha256"])
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expected-plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-flags", action="store_true", help="启用已通过训练回放的本轮通用保护")
    parser.add_argument("--refine-contract-prompt", action="store_true", help="独立SQL输出合同提示词候选，默认关闭")
    parser.add_argument("--independent-aggregates", action="store_true", help="独立资源完整聚合候选，默认关闭")
    parser.add_argument("--grouped-aggregates", action="store_true", help="同范围各VDC网络资源完整计数，默认关闭")
    parser.add_argument("--thinking-mode", choices=("provider_default", "disabled"), default="provider_default",
                        help="固定思考模式；默认不传extra_body，disabled显式关闭thinking")
    parser.add_argument("--case-id", action="append", help="可重复指定固定训练成员；最终按原train顺序运行")
    parser.add_argument("--phase", choices=("failure_probe", "passed_regression"), help="子集实验阶段，必须显式指定")
    args = parser.parse_args(argv)
    manifest, all_cases, _ = load_training()  # 失败即停；不打开原200题或封存文件。
    try:
        cases, scope, phase = select_cases(all_cases, args.case_id, args.phase)
        phase_reference = subset_history(manifest, all_cases, cases, phase) if scope == "train_subset" else None
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    case_count, max_requests = len(cases), 3 * len(cases)
    training_indices = {case["case_id"]: index+1 for index, case in enumerate(all_cases)}
    local = HERE/".env.local"
    if local.exists():
        for line in local.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}:
                os.environ[name] = value
    flags = {"RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1", "RUNBOOK_RULE_ONLY_FILL": "1",
             "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1", "RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": "1",
             "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0", "RUNBOOK_BOUNDED_API": "0"}
    flags.update({name: "1" if args.candidate_flags else "0" for name in [
        "RUNBOOK_PRESERVE_AGGREGATE_GRAIN", "RUNBOOK_PRESERVE_LITERAL_LABELS",
        "RUNBOOK_PRUNE_UNUSED_LOOKUPS", "RUNBOOK_GROUND_ENUM_LABELS"]})
    flags["RUNBOOK_REFINE_CONTRACT_PROMPT"] = "1" if args.refine_contract_prompt else "0"
    flags["RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES"] = "1" if args.independent_aggregates else "0"
    flags["RUNBOOK_COMPLETE_GROUPED_AGGREGATES"] = "1" if args.grouped_aggregates else "0"
    flags["RUNBOOK_THINKING_MODE"] = args.thinking_mode
    thinking_extra_body = {"thinking": {"type": "disabled"}} if args.thinking_mode == "disabled" else None
    os.environ.update(flags)
    os.environ["RUNBOOK_MAX_LLM_CALLS"] = str(max_requests)
    os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"] = "1024"
    sys.path.insert(0, str(HERE/"implementation"))
    import runbook_matcher as matcher
    import runbook_system as system_module
    import runbook_items
    from evaluator import evaluate_case
    readonly = json.loads((HERE/"baseline_manifest.json").read_text())["readonly_files"]
    if not all(sha(HERE/name) == digest for name, digest in readonly.items()):
        parser.error("只读文件变化，停止")
    sources = ["train_live.py", "training_data.py", "run_whitebox.py"] + ["implementation/"+name for name in
               ["runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "evaluator.py", "runbook_executor.py"]]
    sources.append("implementation/runbook_aggregates.py")
    if scope == "train_subset":
        sources.append("train_prompt_probe.py")
    plan = {"type": "training_plan", "created_at": now(), "split_id": manifest["split_id"],
            "record_format": 2,
            "case_count": case_count, "case_ids": [case["case_id"] for case in cases], "phase": phase,
            "phase_reference": phase_reference,
            "repeats": 1, "case_order": "fixed train file order", "scope": scope,
            "training_sha256": manifest["train_sha256"], "split_manifest_sha256": sha(SPLIT/"manifest.json"),
            "training_history_sha256": manifest["train_history_sha256"],
            "source_sha256": {name: sha(HERE/name) for name in sources},
            "code_base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
            "model": matcher.DEEPSEEK_MODEL, "base_url": matcher.DEEPSEEK_BASE_URL,
            "max_requests": max_requests, "max_output_tokens": 1024, "sdk_max_retries": 0,
            "thinking": "provider default" if args.thinking_mode == "provider_default" else "disabled",
            "thinking_mode": args.thinking_mode, "thinking_extra_body": thinking_extra_body,
            "temperature": "provider default", "feature_flags": flags,
            "template_count": len(runbook_items.RUNBOOK_ITEMS), "holdout_evaluated": False,
            "score_policy": "original query and evaluate_case; no weighting or template-count score",
            "cache_policy": "fresh process; schema warmup excluded; executor cache shared across training cases",
            "authorization": "preflight only; bounded training runs may be decided under the user's standing autonomy authorization; freeze and record each actual scope before --run"}
    if args.expected_plan:
        expected = json.loads(args.expected_plan.read_text())
        if any(expected.get(key) != value for key, value in plan.items() if key not in {"created_at", "authorization"}):
            parser.error("候选/范围/配置与冻结计划不同，未调用模型")
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.run:
        return 0
    if not args.expected_plan or not args.output:
        parser.error("真实运行必须指定冻结计划和新的输出路径")
    if not matcher.DEEPSEEK_API_KEY or matcher.get_llm_events():
        parser.error("需要已配置密钥及新进程")
    if args.output.exists():
        parser.error("不覆盖已有训练记录")
    original_ask, original_create = matcher.llm_ask, None
    records, identities, mismatch = [], {}, []
    started, exit_code = time.perf_counter(), 1

    def frozen():
        if (any(sha(HERE/name) != digest for name, digest in plan["source_sha256"].items())
                or sha(SPLIT/"train.json") != plan["training_sha256"]
                or sha(SPLIT/"train_history.jsonl") != plan["training_history_sha256"]
                or sha(SPLIT/"manifest.json") != plan["split_manifest_sha256"]
                or phase_reference is not None and any(sha(HERE/"experiments"/name) != digest
                                                       for name, digest in phase_reference["file_sha256"].items())
                or any(os.environ.get(key) != value for key, value in flags.items())
                or os.environ.get("RUNBOOK_MAX_LLM_CALLS") != str(max_requests)
                or os.environ.get("RUNBOOK_MAX_OUTPUT_TOKENS") != "1024" or mismatch):
            raise RuntimeError("训练源码、集合、配置或型号漂移，停止请求")

    logging.disable(logging.CRITICAL)
    with args.output.open("x", encoding="utf-8") as stream:
        def write(row):
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
            stream.flush()

        write(plan)
        try:
            frozen()
            system = system_module.RunbookQuerySystem()
            write({"type": "initialization", **system.initialization_metrics})
            original_create = matcher._llm_client.chat.completions.create

            def create(*values, **options):
                frozen()
                if matcher._llm_client.max_retries != 0:
                    raise RuntimeError("SDK重试必须为0")
                if (options.get("max_tokens") != 1024 or options.get("model") != plan["model"]
                        or len(matcher.get_llm_events()) > max_requests):
                    raise RuntimeError("模型输出/请求数超出冻结上限")
                if options.get("extra_body") != plan["thinking_extra_body"]:
                    raise RuntimeError("实际thinking请求参数与冻结模式不同，未发送请求")
                index = len(matcher.get_llm_events())-1
                response = original_create(*values, **options)
                identity = {"requested_model": options.get("model"), "response_model": getattr(response, "model", None)}
                identities[index] = identity
                if identity["requested_model"] != plan["model"] or identity["response_model"] != plan["model"]:
                    mismatch.append(identity)
                frozen()
                return response

            matcher._llm_client.chat.completions.create = create

            def ask(prompt, stage="unknown"):
                frozen()
                before = len(matcher.get_llm_events())
                error = {}
                try:
                    value = original_ask(prompt, stage)
                    frozen()
                    return value
                except Exception as exc:
                    error = {"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}
                    raise
                finally:
                    for index, event in enumerate(matcher.get_llm_events()[before:], before):
                        write({"type": "request", "case_id": cases[len(records)]["case_id"], **event,
                               "requested_model": plan["model"], "response_model": None, **identities.get(index, {}), **error})

            matcher.llm_ask = ask
            for index, case in enumerate(cases):
                frozen()
                t0 = time.perf_counter()
                output = system.query(case["question"])
                elapsed = time.perf_counter()-t0
                frozen()
                scored, untimed = evaluate_case(case, output, elapsed), evaluate_case(case, output, 0)
                row = {"type": "case", "case_index": index+1, **scored, "question": case["question"],
                       "training_case_index": training_indices[case["case_id"]],
                       "score_without_time_penalty": untimed["score"], "matched_runbook": output.get("matched_runbook"),
                       "api_call": output.get("api_call"), "sql": output.get("sql"), "result": result_preview(output.get("result")),
                       "diagnostics": output.get("diagnostics")}
                records.append(row)
                write(row)
                print(json.dumps({"completed": len(records), "of": case_count, "score": scored["score"]}), flush=True)
            exit_code = 0
        except Exception as exc:
            write({"type": "run_error", "error_type": type(exc).__name__})
        finally:
            events = matcher.get_llm_events()
            summary = {"type": "summary", "scope": scope, "phase": phase,
                       "thinking_mode": plan["thinking_mode"],
                       "case_ids": plan["case_ids"], "status": "complete" if exit_code == 0 and len(records) == case_count else "incomplete",
                       "completed_cases": len(records), "planned_cases": case_count, "max_score": 5 * case_count,
                       "total_score": round(sum(row["score"] for row in records), 1),
                       "untimed_score": round(sum(row["score_without_time_penalty"] for row in records), 1),
                       "full_quality_answers": sum(row["score_without_time_penalty"] == 5 for row in records),
                       "runtime_abstentions": sum(row["matched_runbook"] is None for row in records),
                       "scorer_abstentions": sum(row["score_without_time_penalty"] == 0 for row in records),
                       "generation_requests": len(events), "failed_requests": sum(row["status"] != "ok" for row in events),
                       "max_requests": max_requests,
                       "model_identity_mismatches": mismatch, "holdout_evaluated": False,
                       "wall_seconds": round(time.perf_counter()-started, 3), "peak_evaluation_process_mib": peak_memory_mib(),
                       "latency_p50": percentile([row["elapsed"] for row in records], .5),
                       "latency_p95": percentile([row["elapsed"] for row in records], .95)}
            write(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            matcher.llm_ask = original_ask
            if matcher._llm_client is not None:
                if original_create is not None:
                    matcher._llm_client.chat.completions.create = original_create
                matcher._llm_client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
