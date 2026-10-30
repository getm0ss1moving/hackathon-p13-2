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

HERE = Path(__file__).resolve().parents[1]
V2_HISTORY_FILES = ("train150_v2_live.jsonl", "train150_v2_resume_live.jsonl")


def runtime_source_paths(modules):
    """拒绝被旧目录/PYTHONPATH/sys.modules污染的运行时。"""
    result = {}
    for name, module in modules.items():
        actual = Path(getattr(module, "__file__", "")).resolve()
        expected = (HERE / "implementation" / (name + ".py")).resolve()
        if actual != expected:
            raise ValueError("运行时源码不来自本clone：" + name)
        result[name] = str(actual)
    return result


def a170_source_contract(root):
    """只接受已复建并审查的170库与全部来源；不放宽原保护文件。"""
    name = "experiments/a170_runtime_port_20261030/SOURCE_MANIFEST.json"
    candidate = json.loads((root / name).read_text())
    expected = {
        "implementation/runbook_items.py": "040040177f8db8bcfa62252567ffbc41199dd0ae8bfd8d2a34aa68364680b28c",
        "implementation/runbook_retriever.py": "befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24",
        "implementation/runbook_family_views.py": "55d732ab2f8abaca45b0513a9a5edf6007bd72e7afad43968890d28a36ed065e",
    }
    if (candidate.get("A_ref") != "6d3b47318ce767ef947c68019a2dce522de98c7a"
            or candidate.get("template_json_sha256") != "f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c"
            or candidate.get("runtime_hashes") != expected
            or any(sha(root / path) != digest for path, digest in expected.items())
            or any(sha(root / path) != digest for path, digest in candidate["source_files"].items())):
        raise ValueError("A170库、检索、视图或来源指纹变化，停止")
    return candidate, [name, *sorted(candidate["source_files"]), "implementation/runbook_family_views.py"]


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
    parser.add_argument("--request-limit", type=int, help="本次最多请求数；仅可收紧默认3倍题数及450上限")
    parser.add_argument("--a180-candidate", action="store_true", help="显式采用已审查A180构建指纹；不改变原198基线清单")
    parser.add_argument("--a170-candidate", action="store_true", help="采用已审查A170完整来源清单；仅隔离候选")
    parser.add_argument("--candidate-flags", action="store_true", help="启用已通过训练回放的本轮通用保护")
    parser.add_argument("--refine-contract-prompt", action="store_true", help="独立SQL输出合同提示词候选，默认关闭")
    parser.add_argument("--independent-aggregates", action="store_true", help="独立资源完整聚合候选，默认关闭")
    parser.add_argument("--grouped-aggregates", action="store_true", help="同范围各VDC网络资源完整计数，默认关闭")
    parser.add_argument("--network-details", action="store_true", help="具名VM网卡计数与CIDR对应明细，默认关闭")
    parser.add_argument("--identity-projection", action="store_true", help="固定SQL角色证明的实例标识补列，默认关闭")
    parser.add_argument("--vpc-subnets", action="store_true", help="逐VPC透明子网统计，默认关闭")
    parser.add_argument("--tenant-resources", action="store_true", help="同区域各租户完整资源及规格统计，默认关闭")
    parser.add_argument("--vm-volume-details", action="store_true", help="同租户区域VM及卷完整明细，默认关闭")
    parser.add_argument("--tenant-vdc-binding", action="store_true", help="同CI原生查询证明租户对应VDC条件，默认关闭")
    parser.add_argument("--parallel-resource-lists", action="store_true", help="同范围VM/卷/VPC三份独立列表，默认关闭")
    parser.add_argument("--thinking-mode", choices=("provider_default", "disabled"), default="disabled",
                        help="固定思考模式；默认disabled显式关闭thinking，provider_default不传额外参数")
    parser.add_argument("--case-id", action="append", help="可重复指定固定训练成员；最终按原train顺序运行")
    parser.add_argument("--phase", choices=("failure_probe", "passed_regression"), help="子集实验阶段，必须显式指定")
    args = parser.parse_args(argv)
    from check_official_integrity import require_official_files
    try:
        official_integrity = require_official_files(HERE)
    except ValueError as exc:
        parser.error(str(exc))
    manifest, all_cases, _ = load_training()  # 失败即停；不打开原200题或封存文件。
    try:
        cases, scope, phase = select_cases(all_cases, args.case_id, args.phase)
        phase_reference = subset_history(manifest, all_cases, cases, phase) if scope == "train_subset" else None
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    case_count, max_requests = len(cases), 3 * len(cases)
    if args.request_limit is not None:
        if not 1 <= args.request_limit <= min(max_requests, 450):
            parser.error("--request-limit只能在1与默认预算之间收紧")
        max_requests = args.request_limit
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
    flags["RUNBOOK_COMPLETE_NETWORK_DETAILS"] = "1" if args.network_details else "0"
    flags["RUNBOOK_COMPLETE_IDENTITY_PROJECTION"] = "1" if args.identity_projection else "0"
    flags["RUNBOOK_COMPLETE_VPC_SUBNETS"] = "1" if args.vpc_subnets else "0"
    flags["RUNBOOK_COMPLETE_TENANT_RESOURCES"] = "1" if args.tenant_resources else "0"
    flags["RUNBOOK_COMPLETE_VM_VOLUME_DETAILS"] = "1" if args.vm_volume_details else "0"
    flags["RUNBOOK_BIND_TENANT_VDC"] = "1" if args.tenant_vdc_binding else "0"
    flags["RUNBOOK_COMPLETE_PARALLEL_LISTS"] = "1" if args.parallel_resource_lists else "0"
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
    is170 = args.a170_candidate or len(runbook_items.RUNBOOK_ITEMS) == 170
    if args.a180_candidate and is170:
        parser.error("不能同时选择180与170候选")
    module_names = ["runbook_matcher", "runbook_system", "runbook_items", "runbook_retriever", "runbook_executor", "evaluator"]
    if is170:
        import runbook_family_views
        module_names.append("runbook_family_views")
    try:
        runtime_paths = runtime_source_paths({name: sys.modules[name] for name in module_names})
    except ValueError as exc:
        parser.error(str(exc))
    runtime_manifest = json.loads((HERE/"baseline_manifest.json").read_text())
    readonly = dict(runtime_manifest["readonly_files"])
    template_revision = {"mode": "baseline", "expected_items_sha256": readonly["implementation/runbook_items.py"]}
    candidate_sources = []
    if is170:
        try:
            candidate, candidate_sources = a170_source_contract(HERE)
        except (ValueError, KeyError, OSError) as exc:
            parser.error(str(exc))
        if (len(runbook_items.RUNBOOK_ITEMS) != 170
                or len({item["id"] for item in runbook_items.RUNBOOK_ITEMS}) != 170
                or sorted(item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id")) != candidate["families"]):
            parser.error("A170活动库结构不符，停止")
        for path in ("implementation/runbook_items.py", "implementation/runbook_retriever.py"):
            readonly[path] = candidate["runtime_hashes"][path]
        template_revision = {"mode": "a170_reviewed_private_build", "A_ref": candidate["A_ref"],
                             "manifest_sha256": sha(HERE / "experiments/a170_runtime_port_20261030/SOURCE_MANIFEST.json"),
                             "runtime_hashes": candidate["runtime_hashes"]}
    elif args.a180_candidate or any(item.get("family_id") for item in runbook_items.RUNBOOK_ITEMS):
        package = HERE / "experiments/a_family_candidate_20261030"
        candidate = json.loads((package / "manifest.json").read_text())
        if any(sha(package / name) != digest for name, digest in candidate["files"].items()):
            parser.error("A180候选来源指纹变化，停止")
        if (len(runbook_items.RUNBOOK_ITEMS) != 180
                or len({item["id"] for item in runbook_items.RUNBOOK_ITEMS}) != 180
                or sorted(item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id"))
                != ["F01", "F08", "F14", "F18", "F20", "F21"]):
            parser.error("A180活动库结构不符，停止")
        readonly["implementation/runbook_items.py"] = candidate["materialized_candidate_Python_sha256"]
        template_revision = {"mode": "a180_reviewed_build", "base_ref": candidate["base_ref"],
                             "previous_items_sha256": runtime_manifest["readonly_files"]["implementation/runbook_items.py"],
                             "expected_items_sha256": readonly["implementation/runbook_items.py"],
                             "manifest_sha256": sha(package / "manifest.json")}
        candidate_sources = ["scripts/build_a180_candidate.py", "experiments/a_family_candidate_20261030/manifest.json"]
        candidate_sources += ["experiments/a_family_candidate_20261030/" + name for name in sorted(candidate["files"])]
    if not all(sha(HERE/name) == digest for name, digest in readonly.items()):
        parser.error("只读文件变化，停止")
    sources = ["scripts/train_live.py", "scripts/training_data.py", "scripts/run_whitebox.py", "scripts/check_official_integrity.py", "baseline_manifest.json"] + ["implementation/"+name for name in
               ["runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "evaluator.py", "runbook_executor.py"]]
    sources.append("implementation/runbook_aggregates.py")
    sources += ["implementation/runbook_network_details.py", "implementation/runbook_projection_roles.py"]
    sources.append("implementation/runbook_vpc_subnets.py")
    sources.append("implementation/runbook_tenant_resources.py")
    sources.append("implementation/runbook_vm_volume_details.py")
    sources += ["implementation/runbook_scope_bindings.py", "implementation/runbook_identity_guard.py"]
    sources.append("implementation/runbook_parallel_resource_lists.py")
    sources += ["implementation/quick_eval.py", "implementation/blackbox_eval.py"]
    sources += candidate_sources
    handoff_evidence = {}
    for record in runtime_manifest.get("integration", {}).get("reconciled_files", {}).values():
        path, expected = record.get("handoff_evidence"), record.get("handoff_evidence_sha256")
        if path and expected:
            if sha(HERE/path) != expected:
                parser.error("来源交接证据哈希不符，未调用模型")
            handoff_evidence[path] = expected
    sources += sorted(handoff_evidence)
    if scope == "train_subset":
        sources.append("scripts/train_prompt_probe.py")
    plan = {"type": "training_plan", "created_at": now(), "split_id": manifest["split_id"],
            "record_format": 2,
            "case_count": case_count, "case_ids": [case["case_id"] for case in cases], "phase": phase,
            "phase_reference": phase_reference,
            "repeats": 1, "case_order": "fixed train file order", "scope": scope,
            "training_sha256": manifest["train_sha256"], "split_manifest_sha256": sha(SPLIT/"manifest.json"),
            "training_history_sha256": manifest["train_history_sha256"],
            "source_sha256": {name: sha(HERE/name) for name in sources},
            "runtime_source_paths": runtime_paths,
            "template_revision": template_revision,
            "family_ids": sorted({item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id")}),
            "scoring_revision": official_integrity.get("accepted_revisions", {}),
            "source_handoff_sha256": handoff_evidence,
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
    fatal_request_errors = []
    started, exit_code = time.perf_counter(), 1

    def frozen():
        if fatal_request_errors:
            raise RuntimeError("本轮已有模型请求或来源异常，禁止发起后续请求")
        if (runtime_source_paths({name: sys.modules[name] for name in runtime_paths}) != runtime_paths
                or any(sha(HERE/name) != digest for name, digest in plan["source_sha256"].items())
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
                    fatal_request_errors.append(error)
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
