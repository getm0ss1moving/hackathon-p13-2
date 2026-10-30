"""固定训练16题的SQL精调prompt配对探针；默认仅打印冻结计划，零模型请求。"""

import argparse
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import time

from training_data import SPLIT, load_training, sha
from run_whitebox import result_preview

HERE = Path(__file__).resolve().parents[1]
PARENT = HERE / "experiments/train150_v2_live.jsonl"
RESUME = HERE / "experiments/train150_v2_resume_live.jsonl"
PROMPT_FLAG = "RUNBOOK_REFINE_CONTRACT_PROMPT"
# 仅为本次实验冻结范围，不参与生产匹配、填参或SQL路由。
AFFECTED_IDS = tuple("CMDB-" + suffix for suffix in
                     ("017", "021", "022", "060", "066", "081", "121", "127", "152", "259", "267", "270"))
CONTROL_IDS = ("CMDB-005", "CMDB-068", "CMDB-221", "CMDB-282")
V2_FLAGS = {name: "1" for name in (
    "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS", "RUNBOOK_RULE_ONLY_FILL",
    "RUNBOOK_PRESERVE_ROW_SEMANTICS", "RUNBOOK_RESOURCE_ATTRIBUTE_ROLES",
    "RUNBOOK_PRESERVE_AGGREGATE_GRAIN", "RUNBOOK_PRESERVE_LITERAL_LABELS",
    "RUNBOOK_PRUNE_UNUSED_LOOKUPS", "RUNBOOK_GROUND_ENUM_LABELS")}
V2_FLAGS.update(RUNBOOK_VALIDATE_API_DEPENDENCIES="0", RUNBOOK_BOUNDED_API="0")
HISTORICAL_SOURCES = (
    "train_live.py", "training_data.py", "run_whitebox.py",
    "implementation/runbook_matcher.py", "implementation/runbook_system.py",
    "implementation/runbook_items.py", "implementation/runbook_retriever.py",
    "implementation/evaluator.py", "implementation/runbook_executor.py")
CURRENT_SOURCES = tuple("scripts/" + name if "/" not in name else name for name in HISTORICAL_SOURCES) + ("scripts/train_prompt_probe.py",)
CONTRACT_KEYS = ("projection_contract", "row_semantics_contract", "literal_label_contract")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def validate_history(manifest, cases, parent_rows, resume_rows, parent_digest, manifest_digest):
    """只接受已知v2训练主运行和其完整后缀，不按逐题得分改变范围。"""
    if len(cases) != 150 or len({case["case_id"] for case in cases}) != 150:
        raise ValueError("必须是固定150训练题")
    if not parent_rows or not resume_rows:
        raise ValueError("训练历史缺失")
    parent, resume = parent_rows[0], resume_rows[0]
    if (parent.get("type") != "training_plan" or parent.get("scope") != "train_only"
            or parent.get("split_id") != manifest["split_id"] or parent.get("record_format") != 2
            or parent.get("case_count") != 150 or parent.get("repeats") != 1
            or parent.get("case_order") != "fixed train file order"
            or parent.get("training_sha256") != manifest["train_sha256"]
            or parent.get("split_manifest_sha256") != manifest_digest
            or parent.get("feature_flags") != V2_FLAGS
            or set(parent.get("source_sha256", {})) != set(HISTORICAL_SOURCES)
            or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in parent["source_sha256"].values())
            or parent.get("max_output_tokens") != 1024 or parent.get("sdk_max_retries") != 0
            or not parent.get("model") or not str(parent.get("base_url", "")).startswith("https://")):
        raise ValueError("父训练计划/来源合同不匹配")
    if (resume.get("type") != "resume_plan" or resume.get("scope") != "train_only_resume"
            or resume.get("parent_sha256") != parent_digest
            or any(resume.get(key) != parent.get(key) for key in (
                "source_sha256", "training_sha256", "feature_flags", "model", "base_url",
                "max_output_tokens", "sdk_max_retries"))):
        raise ValueError("补测来源与父计划不一致")
    completed = []
    for rows, plan_type, count, status in ((parent_rows, "training_plan", 147, "incomplete"),
                                           (resume_rows, "resume_plan", 3, "complete")):
        if (sum(row.get("type") == plan_type for row in rows) != 1
                or sum(row.get("type") == "summary" for row in rows) != 1
                or rows[-1].get("type") != "summary" or rows[-1].get("status") != status):
            raise ValueError("历史记录未完整闭合")
        records = [row for row in rows if row.get("type") == "case"]
        requests = [row for row in rows if row.get("type") == "request"]
        summary = rows[-1]
        if (len(records) != count or summary.get("completed_cases") != count
                or summary.get("generation_requests") != len(requests)
                or summary.get("model_identity_mismatches")):
            raise ValueError("历史完成数/请求数或型号不一致")
        if plan_type == "training_plan" and [row.get("case_index") for row in records] != list(range(1, 148)):
            raise ValueError("父运行题目索引不连续")
        completed.extend(records)
        known = {case["case_id"] for case in cases}
        for request in requests:
            if (request.get("case_id") not in known or request.get("stage") not in {"select", "fill", "refine"}
                    or request.get("status") not in {"ok", "error"}
                    or request.get("requested_model") != parent["model"]
                    or request.get("status") == "ok" and request.get("response_model") != parent["model"]):
                raise ValueError("历史请求范围/型号不匹配")
        for record in records:
            diagnostic_events = record.get("diagnostics", {}).get("llm_calls", [])
            real_events = [row for row in requests if row.get("case_id") == record["case_id"]]
            # 父运行的超时题没有case；其请求不与补测的独立进程混合。
            if [(event.get("stage"), event.get("status")) for event in diagnostic_events] != [
                    (event.get("stage"), event.get("status")) for event in real_events]:
                raise ValueError("case诊断与独立请求记录不一致")
    expected = [(case["case_id"], case["question"]) for case in cases]
    if ([(record.get("case_id"), record.get("question")) for record in completed] != expected
            or resume.get("case_ids") != [case["case_id"] for case in cases[147:]]
            or resume.get("case_count") != 3):
        raise ValueError("主运行加补测未按固定顺序完整覆盖150训练题")
    return parent, completed


def affected_reasons(record):
    matching = record.get("diagnostics", {}).get("matching", {})
    reasons = [key + ":" + str(matching[key].get("reason")) for key in CONTRACT_KEYS
               if matching.get(key, {}).get("reject") is True]
    if any(event.get("stage") == "refine" and event.get("status") != "ok"
           for event in record.get("diagnostics", {}).get("llm_calls", [])):
        reasons.append("refine_request_error")
    if (matching.get("sql_before_refine") and matching.get("sql_after_refine")
            and matching["sql_before_refine"] != matching["sql_after_refine"]
            and record.get("score_without_time_penalty", 5) < 5):
        reasons.append("accepted_refinement_not_full_quality")
    return reasons


def select_inputs(cases, history, affected_ids=AFFECTED_IDS, control_ids=CONTROL_IDS):
    """范围由审阅者先冻结，诊断仅用于说明覆盖，绝不按分数替换选题。"""
    ids = tuple(affected_ids) + tuple(control_ids)
    if not 0 < len(ids) <= 16 or len(ids) != len(set(ids)) or len(affected_ids) > 12 or len(control_ids) > 4:
        raise ValueError("配对范围最多受影响12题和对照4题，不能重复")
    if len(cases) != 150 or len(history) != 150:
        raise ValueError("范围选择必须接收完整训练150历史")
    by_id = {case["case_id"]: (case, record) for case, record in zip(cases, history)}
    if any(case["case_id"] != record.get("case_id") or case["question"] != record.get("question")
           for case, record in zip(cases, history)) or len(by_id) != 150 or not set(ids) <= set(by_id):
        raise ValueError("选题必须全部属于固定训练顺序")
    selected = []
    for case, record in zip(cases, history):
        if case["case_id"] not in ids:
            continue
        matching = record.get("diagnostics", {}).get("matching", {})
        events = [event for event in record.get("diagnostics", {}).get("llm_calls", [])
                  if event.get("stage") == "refine"]
        if (matching.get("reason") != "matched" or not record.get("matched_runbook")
                or not isinstance(record.get("api_call"), (dict, list)) or not record["api_call"]
                or not isinstance(matching.get("sql_before_refine"), str)
                or not matching["sql_before_refine"].strip() or len(events) != 1):
            raise ValueError("冻结题缺少已接受API/原SQL或唯一refine请求")
        frozen_input = {"case_id": case["case_id"], "question": case["question"],
                        "api_call": copy.deepcopy(record["api_call"]),
                        "sql_before_refine": matching["sql_before_refine"],
                        "matched_runbook": record["matched_runbook"]}
        selected.append({"case": case, "input": frozen_input, "input_sha256": digest(frozen_input),
                         "design_group": "affected" if case["case_id"] in affected_ids else "control",
                         "historical_reasons": affected_reasons(record)})
    return selected


def validate_current_sources(historical, current):
    # matcher加入候选prompt，train_live加入开关记录；其他保护/执行文件必须仍为v2。
    for name in HISTORICAL_SOURCES:
        if name not in {"train_live.py", "implementation/runbook_matcher.py"} and current.get(name) != historical[name]:
            raise ValueError("保护/执行源码已偏离v2：" + name)


def read_local_config():
    values = {}
    local = HERE / ".env.local"
    if local.exists():
        for line in local.read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}:
                values[name.strip()] = value.strip().strip('"\'')
    return values


def prepare():
    manifest, cases, _ = load_training()
    parent_rows = [json.loads(line) for line in PARENT.read_text().splitlines()]
    resume_rows = [json.loads(line) for line in RESUME.read_text().splitlines()]
    parent, history = validate_history(manifest, cases, parent_rows, resume_rows, sha(PARENT), sha(SPLIT / "manifest.json"))
    selected = select_inputs(cases, history)
    sources = {name: sha(HERE / name) for name in CURRENT_SOURCES}
    validate_current_sources(parent["source_sha256"], sources)
    config = read_local_config()
    if (config.get("DEEPSEEK_MODEL") != parent["model"] or config.get("DEEPSEEK_BASE_URL") != parent["base_url"]):
        raise ValueError("本机模型/地址与v2不同")
    timeout = float(config.get("RUNBOOK_LLM_TIMEOUT", "60"))
    if not 0 < timeout <= 60:
        raise ValueError("模型超时必须在0到60秒内")
    reasons = [affected_reasons(record) for record in history]
    total_affected = sum(bool(reason) for reason in reasons)
    plan = {"type": "prompt_probe_plan", "scope": "train_only_paired_refine", "record_format": 1,
            "split_id": manifest["split_id"], "training_sha256": manifest["train_sha256"],
            "training_history_sha256": manifest["train_history_sha256"],
            "split_manifest_sha256": sha(SPLIT / "manifest.json"),
            "history_sha256": {PARENT.name: sha(PARENT), RESUME.name: sha(RESUME)},
            "historical_source_sha256": parent["source_sha256"], "source_sha256": sources,
            "historical_coverage": 150, "historical_single_pass_complete": False,
            "case_ids": [item["input"]["case_id"] for item in selected], "case_count": len(selected),
            "case_order": "fixed train file order; original then candidate per case",
            "selection_policy": "reviewer-frozen 12 affected plus 4 controls; no score-based replacement",
            "selected_inputs": [{key: item[key] for key in ("input_sha256", "design_group", "historical_reasons")}
                                | {"case_id": item["input"]["case_id"]} for item in selected],
            "affected_population": total_affected, "affected_selected": sum(bool(item["historical_reasons"]) for item in selected),
            "all_affected_covered": total_affected == sum(bool(item["historical_reasons"]) for item in selected),
            "model": parent["model"], "base_url": parent["base_url"], "timeout_seconds": timeout,
            "max_requests": 2 * len(selected), "max_output_tokens": 1024, "sdk_max_retries": 0,
            "feature_flags": dict(V2_FLAGS), "variants": {"original": "0", "candidate": "1"},
            "only_variant_flag": PROMPT_FLAG, "thinking": "provider default", "temperature": "provider default",
            "cache_policy": "schema warmed once; original executor cache cleared before each arm",
            "input_policy": "same accepted v2 API and sql_before_refine; no select/fill calls",
            "error_policy": "ModelOutputError: record one failed output and execute original SQL fallback; transport/identity/drift/unknown: stop without retry",
            "score_policy": "original executor and evaluate_case; timed and untimed diagnostic only",
            "holdout_accessed": False, "holdout_evaluated": False}
    return plan, selected, config


class RequestBudget:
    def __init__(self, maximum):
        if type(maximum) is not int or not 0 < maximum <= 32:
            raise ValueError("真实请求上限必须在1到32内")
        self.maximum, self.used = maximum, 0

    def take(self):
        if self.used >= self.maximum:
            raise RuntimeError("已达冻结请求上限，未发送新请求")
        self.used += 1  # 失败/超时请求也占预算，不重试。
        return self.used


def frozen(plan, variant, private_config):
    if (any(sha(HERE / name) != value for name, value in plan["source_sha256"].items())
            or sha(SPLIT / "train.json") != plan["training_sha256"]
            or sha(SPLIT / "train_history.jsonl") != plan["training_history_sha256"]
            or sha(SPLIT / "manifest.json") != plan["split_manifest_sha256"]
            or any(sha(HERE / "experiments" / name) != value for name, value in plan["history_sha256"].items())
            or read_local_config() != private_config
            or any(os.environ.get(name) != value for name, value in plan["feature_flags"].items())
            or os.environ.get(PROMPT_FLAG) != plan["variants"][variant]
            or os.environ.get("RUNBOOK_MAX_LLM_CALLS") != str(plan["max_requests"])
            or os.environ.get("RUNBOOK_MAX_OUTPUT_TOKENS") != "1024"
            or os.environ.get("RUNBOOK_LLM_TIMEOUT") != str(plan["timeout_seconds"])
            or os.environ.get("DEEPSEEK_MODEL") != plan["model"]
            or os.environ.get("DEEPSEEK_BASE_URL") != plan["base_url"]
            or os.environ.get("DEEPSEEK_API_KEY") != private_config.get("DEEPSEEK_API_KEY")):
        raise RuntimeError("训练/历史/源码/配置漂移，停止请求")


def run_probe(plan, selected, matcher, executor, evaluate_case, write, check_frozen):
    """独立依赖注入便于合成验证；真实路径始终调用matcher._refine_sql及原执行器。"""
    if (not 0 < len(selected) <= 16 or plan["max_requests"] != 2 * len(selected)
            or plan["case_ids"] != [item["input"]["case_id"] for item in selected]
            or plan["variants"] != {"original": "0", "candidate": "1"}
            or matcher.get_llm_events() or matcher._llm_client is not None):
        raise ValueError("需要冻结小范围与全新模型进程")
    expected_inputs = {item["case_id"]: item["input_sha256"] for item in plan["selected_inputs"]}
    if (set(expected_inputs) != set(plan["case_ids"])
            or any(expected_inputs.get(item["input"]["case_id"]) != item["input_sha256"] for item in selected)):
        raise ValueError("配对输入不匹配冻结计划")
    budget = RequestBudget(plan["max_requests"])
    original_ask, original_create, client = matcher.llm_ask, None, None
    active, arms, pairs = {}, [], []
    error_type, started = None, time.perf_counter()
    request_records = []

    def failure(exc):
        output_error = isinstance(exc, matcher.ModelOutputError)
        transport = (isinstance(exc, (TimeoutError, ConnectionError)) or getattr(exc, "status_code", None) is not None
                     or type(exc).__name__ in {"APIConnectionError", "APITimeoutError", "ConnectTimeout", "ReadTimeout", "ConnectError"})
        return {"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None),
                "error_kind": "model_output" if output_error else "transport" if transport else "invariant_or_unknown"}

    def check():
        check_frozen(active.get("variant", "original"))
        if (matcher.DEEPSEEK_MODEL != plan["model"] or matcher.DEEPSEEK_BASE_URL != plan["base_url"]
                or client is not None and client.max_retries != 0):
            raise RuntimeError("模型配置/SDK重试漂移")

    def create(*args, **kwargs):
        check()
        if (active.get("requests") or kwargs.get("model") != plan["model"]
                or kwargs.get("max_tokens") != 1024 or kwargs.get("stream") is not False):
            raise RuntimeError("每臂仅允许一次固定配置refine请求")
        active["requests"] = 1
        active["request_index"] = budget.take()
        try:
            response = original_create(*args, **kwargs)
            active["response_model"] = getattr(response, "model", None)
            choices = getattr(response, "choices", [])
            if choices:
                active["raw_proposal"] = getattr(getattr(choices[0], "message", None), "content", None)
                active["finish_reason"] = getattr(choices[0], "finish_reason", None)
            if active["response_model"] != plan["model"]:
                raise RuntimeError("响应型号与冻结型号不同")
            check()
            return response
        except Exception as exc:
            active["request_error"] = failure(exc)
            raise

    def ask(prompt, stage="unknown"):
        check()
        if stage != "refine" or active.get("ask_started"):
            raise RuntimeError("只允许一次refine，不允许select/fill")
        active["ask_started"] = True
        try:
            value = original_ask(prompt, stage)
            check()
            return value
        except Exception as exc:
            active["request_error"] = failure(exc)
            raise

    try:
        os.environ[PROMPT_FLAG] = plan["variants"]["original"]
        check()
        matcher._warm_schema_cache()
        check()
        client = matcher.get_llm()
        original_create = client.chat.completions.create
        client.chat.completions.create, matcher.llm_ask = create, ask
        for item in selected:
            source = item["input"]
            if digest(source) != expected_inputs[source["case_id"]]:
                raise RuntimeError("冻结配对输入漂移")
            for variant, flag in plan["variants"].items():
                active.clear()
                active.update(variant=variant, case_id=source["case_id"], raw_proposal=None,
                              response_model=None, finish_reason=None)
                os.environ[PROMPT_FLAG] = flag
                check()
                if digest(source) != expected_inputs[source["case_id"]]:
                    raise RuntimeError("两臂之间配对输入漂移")
                before, diagnostics, t0 = len(matcher.get_llm_events()), {}, time.perf_counter()
                arm = {"type": "arm", "case_id": source["case_id"], "variant": variant,
                       "input_sha256": item["input_sha256"], "api_call": copy.deepcopy(source["api_call"]),
                       "sql_before_refine": source["sql_before_refine"], "status": "incomplete",
                       "raw_proposal": None, "contracts": diagnostics, "execution": None, "score": None}
                try:
                    schemas = matcher._get_table_schemas(source["sql_before_refine"])
                    sql = matcher._refine_sql(source["question"], source["sql_before_refine"], schemas, diagnostics)
                    arm["sql_after_refine"] = sql
                    events = matcher.get_llm_events()[before:]
                    if len(events) != 1 or events[0].get("stage") != "refine" or not active.get("requests"):
                        raise RuntimeError("每臂必须恰好一个可追溯refine事件")
                    request_error = active.get("request_error", {})
                    if request_error.get("error_kind") == "model_output" and events[0].get("status") == "error":
                        if sql != source["sql_before_refine"]:
                            raise RuntimeError("无效模型输出必须回退原SQL")
                        arm["proposal_status"] = "invalid_model_output_fallback"
                    elif request_error or events[0].get("status") != "ok":
                        raise RuntimeError("refine请求失败，保留失败记录并停止，不继续另一臂")
                    else:
                        arm["proposal_status"] = "valid_model_output"
                    check()
                    executor._cache.clear()
                    output = executor.execute({"api_call": copy.deepcopy(source["api_call"]), "sql": sql})
                    output.update(api_call=copy.deepcopy(source["api_call"]), matched_runbook=source["matched_runbook"])
                    elapsed = time.perf_counter() - t0
                    arm["execution"] = {"result": result_preview(output.get("result")), "error": output.get("error")}
                    arm["score"] = evaluate_case(item["case"], output, elapsed)
                    arm["untimed_score"] = evaluate_case(item["case"], output, 0)
                    check()
                    if output.get("error"):
                        raise RuntimeError("原执行器返回错误，停止配对实验")
                    arm["status"] = "complete"
                except Exception as exc:
                    arm["error_type"] = type(exc).__name__
                    raise
                finally:
                    events = matcher.get_llm_events()[before:]
                    arm.update(raw_proposal=active.get("raw_proposal"), contracts=diagnostics,
                               elapsed=round(time.perf_counter() - t0, 4),
                               request_index=active.get("request_index"),
                               returned_template_sql=arm.get("sql_after_refine") == source["sql_before_refine"])
                    for event in events:
                        request = {"type": "request", "case_id": source["case_id"], "variant": variant,
                                   "request_index": active.get("request_index"), "input_sha256": item["input_sha256"],
                                   **event, "requested_model": plan["model"], "response_model": active.get("response_model"),
                                   "finish_reason": active.get("finish_reason"), "raw_proposal": active.get("raw_proposal"),
                                   **active.get("request_error", {})}
                        request_records.append(request)
                        write(request)
                    arms.append(arm)
                    write(arm)
            pair = {"type": "pair", "case_id": source["case_id"], "input_sha256": item["input_sha256"],
                    "original_untimed_score": arms[-2]["untimed_score"]["score"],
                    "candidate_untimed_score": arms[-1]["untimed_score"]["score"]}
            pair["delta"] = pair["candidate_untimed_score"] - pair["original_untimed_score"]
            pairs.append(pair)
            write(pair)
    except Exception as exc:
        error_type = type(exc).__name__
        write({"type": "run_error", "error_type": error_type, "case_id": active.get("case_id"),
               "variant": active.get("variant")})
    finally:
        complete = (error_type is None and len(pairs) == len(selected) and len(arms) == 2 * len(selected)
                    and budget.used == plan["max_requests"] and all(arm["status"] == "complete" for arm in arms))
        summary = {"type": "summary", "scope": plan["scope"], "status": "complete" if complete else "incomplete",
                   "planned_cases": len(selected), "completed_pairs": len(pairs), "completed_arms": sum(arm["status"] == "complete" for arm in arms),
                   "generation_requests": budget.used, "recorded_events": len(matcher.get_llm_events()),
                   "failed_events": sum(event.get("status") != "ok" for event in matcher.get_llm_events()),
                   "failed_model_outputs": sum(event.get("error_kind") == "model_output" for event in request_records),
                   "transport_errors": sum(event.get("error_kind") == "transport" for event in request_records),
                   "invariant_or_unknown_errors": sum(event.get("error_kind") == "invariant_or_unknown" for event in request_records),
                   "prompt_tokens": sum(event.get("prompt_tokens", 0) for event in matcher.get_llm_events()),
                   "completion_tokens": sum(event.get("completion_tokens", 0) for event in matcher.get_llm_events()),
                   "max_requests": plan["max_requests"], "wall_seconds": round(time.perf_counter() - started, 3),
                   "holdout_accessed": False, "holdout_evaluated": False, "full_training_evaluation": False}
        write(summary)
        matcher.llm_ask = original_ask
        if client is not None:
            if original_create is not None:
                client.chat.completions.create = original_create
            client.close()
    return 0 if complete else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expected-plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        plan, selected, config = prepare()
        if args.expected_plan and json.loads(args.expected_plan.read_text()) != plan:
            raise ValueError("与冻结计划不同，未调用模型")
        if args.run and (not args.expected_plan or not args.output or args.output.exists()):
            raise ValueError("--run需要匹配冻结计划和新的输出路径")
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.run:
        return 0
    if not config.get("DEEPSEEK_API_KEY"):
        parser.error("只从根目录.env.local读取密钥；未配置，未调用模型")
    os.environ.update(plan["feature_flags"])
    os.environ.update(DEEPSEEK_MODEL=plan["model"], DEEPSEEK_BASE_URL=plan["base_url"],
                      DEEPSEEK_API_KEY=config["DEEPSEEK_API_KEY"], RUNBOOK_MAX_LLM_CALLS=str(plan["max_requests"]),
                      RUNBOOK_MAX_OUTPUT_TOKENS="1024", RUNBOOK_LLM_TIMEOUT=str(plan["timeout_seconds"]))
    os.environ[PROMPT_FLAG] = "0"
    sys.path.insert(0, str(HERE / "implementation"))
    import runbook_matcher as matcher
    import runbook_executor as executor
    from evaluator import evaluate_case
    logging.disable(logging.CRITICAL)
    with args.output.open("x", encoding="utf-8") as stream:
        def write(row):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
        write(plan)
        return run_probe(plan, selected, matcher, executor, evaluate_case, write,
                         lambda variant: frozen(plan, variant, config))


if __name__ == "__main__":
    raise SystemExit(main())
