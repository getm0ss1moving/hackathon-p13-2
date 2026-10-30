"""仅150训练题：固定历史选择/精调输出，真实执行当前query流程；禁止外部模型。"""

import argparse
from collections import Counter
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
import requests

from training_data import load_training, sha, SPLIT

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/"implementation"))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system_module
from runbook_items import RUNBOOK_ITEMS
from evaluator import evaluate_case, _compare_answers


def recorded_parameters(template, actual):
    """从训练历史已填API重建固定fill；不使用参考答案或题号路由生产逻辑。"""
    values = {}

    def walk(before, after):
        if isinstance(before, str):
            found = re.fullmatch(r"\{\{([A-Za-z_]\w*)\}\}", before)
            if found:
                if found[1] in values and values[found[1]] != after:
                    raise ValueError("历史参数绑定冲突")
                values[found[1]] = after
        elif isinstance(before, dict) and isinstance(after, dict):
            for key in before.keys() & after.keys():
                walk(before[key], after[key])
        elif isinstance(before, list) and isinstance(after, list):
            for left, right in zip(before, after):
                walk(left, right)

    walk(template.get("api_call"), actual)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-baseline", action="store_true", help="要求当前完整流程逐题复现冻结历史")
    parser.add_argument("--latest-live", action="store_true", help="只使用已核验的最近150训练题真实记录")
    parser.add_argument("--candidate-flags", action="store_true", help="启用本轮通用候选，仍不调用模型")
    parser.add_argument("--candidate-feature", choices=["grain", "literals", "prune", "enum"], action="append", default=[])
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖已有训练结果")
    manifest, cases, history = load_training()
    history_path = SPLIT/"train_history.jsonl"
    if args.latest_live:
        history_path = HERE/"experiments/train150_v1_live.jsonl"
        records = [json.loads(line) for line in history_path.read_text().splitlines()]
        if (records[0].get("scope") != "train_only" or records[0].get("case_count") != 150
                or records[-1].get("status") != "complete" or records[-1].get("completed_cases") != 150):
            parser.error("不是完整150训练题记录，停止")
        history = [row for row in records if row["type"] == "case"]
        if (len(history) != 150 or [(row["case_id"], row["question"]) for row in history]
                != [(row["case_id"], row["question"][:60]) for row in cases]):
            parser.error("真实训练记录与固定训练集合不匹配")
    assert not executor._cache and not matcher.get_llm_events(), "请用新进程运行"
    flags = {"RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1", "RUNBOOK_RULE_ONLY_FILL": "1",
             "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1", "RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": "1",
             "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0", "RUNBOOK_BOUNDED_API": "0"}
    candidates = {"grain": "RUNBOOK_PRESERVE_AGGREGATE_GRAIN", "literals": "RUNBOOK_PRESERVE_LITERAL_LABELS",
                  "prune": "RUNBOOK_PRUNE_UNUSED_LOOKUPS", "enum": "RUNBOOK_GROUND_ENUM_LABELS"}
    flags.update({value: "1" if args.candidate_flags or key in args.candidate_feature else "0" for key, value in candidates.items()})
    flags["RUNBOOK_REFINE_CONTRACT_PROMPT"] = "0"  # 固定历史模型输出的回放不验证新提示词效果。
    readonly = json.loads((HERE/"baseline_manifest.json").read_text())["readonly_files"]
    assert all(sha(HERE/name) == value for name, value in readonly.items())
    items = {item["id"]: item for item in RUNBOOK_ITEMS}
    for name in ["runbook_items.py", "runbook_retriever.py", "runbook_executor.py", "evaluator.py"]:
        assert sha(HERE/"implementation"/name) == manifest["initial_runtime_sha256"]["implementation/"+name], "固定知识库/保护文件发生变化"
    native_request, wire, blocked, outputs, calls = requests.Session.request, [], [], [], []

    class ForbiddenModel(BaseException):
        pass

    def request(session, method, url, *values, **options):
        target = urlsplit(str(url))
        if target.hostname != "127.0.0.1" or target.port != 8080 or method.upper() != "GET":
            blocked.append("nonlocal_request")
            raise ForbiddenModel("训练回放只允许本地数据GET")
        response = native_request(session, method, url, *values, **options)
        wire.append({"kind": target.path.rsplit("/", 2)[-2], "resource": target.path.rsplit("/", 1)[-1], "status": response.status_code})
        return response

    active = {}

    def fake_model(prompt, stage="unknown"):
        row = active["record"]
        details = row["diagnostics"]["matching"]
        calls.append({"case_id": row["case_id"], "stage": stage})
        selected = details.get("selected_template")
        if stage == "select":
            return str(details["candidate_ids"].index(selected)+1) if selected else "0"
        if stage == "fill":
            return json.dumps(recorded_parameters(items[selected], row.get("api_call")), ensure_ascii=False)
        if stage == "refine" and row.get("sql"):
            return row["sql"]
        if stage == "refine" and selected in items and items[selected].get("sql") and "{{" not in items[selected]["sql"]:
            calls[-1]["missing_historical_response"] = True
            return items[selected]["sql"]  # 新解锁路径仅用不精调提案，必须单列条件性证据。
        raise ForbiddenModel("历史缺该阶段响应；不请求真实模型、不猜测")

    logging.disable(logging.CRITICAL)
    with patch.dict(os.environ, flags), patch.object(requests.Session, "request", request), \
            patch.object(httpx.Client, "send", side_effect=ForbiddenModel("禁止模型请求")), \
            patch.object(system_module, "get_llm", return_value=None), patch.object(matcher, "llm_ask", side_effect=fake_model):
        system = system_module.RunbookQuerySystem()
        for case, row in zip(cases, history):
            active["record"] = row
            if row.get("matched_runbook"):
                baseline = executor.execute({"api_call": row["api_call"], "sql": row["sql"]})
                baseline_output = {"matched_runbook": row["matched_runbook"], "api_call": row["api_call"],
                                   "sql": row["sql"], "result": baseline["result"], "error": baseline["error"]}
            else:
                baseline_output = {"matched_runbook": None, "result": None}
            old_score = evaluate_case(case, baseline_output, 0)["score"]
            assert old_score == row["score_without_time_penalty"], f"训练历史未重现：{case['case_id']}"
            current = system.query(case["question"])
            details = current["diagnostics"]["matching"]
            assert details["candidate_ids"] == row["diagnostics"]["matching"]["candidate_ids"], "候选顺序漂移，不能冒充固定模型选择"
            scored = evaluate_case(case, current, 0)
            new_score = scored["score"]
            answer_match, answer_ratio = _compare_answers(case.get("answer"), current.get("result")) if current.get("matched_runbook") else (False, 0)
            if args.require_baseline:
                assert new_score == old_score, f"当前query未逐题重现训练基线：{case['case_id']}"
                if row.get("matched_runbook"):
                    assert current["api_call"] == row["api_call"] and current["sql"].strip() == row["sql"].strip(), (
                        f"基线API/SQL漂移：{case['case_id']}，API相同={current['api_call'] == row['api_call']}，"
                        f"SQL前={row['sql']!r}，SQL后={current['sql']!r}")
            outputs.append({"case_id": case["case_id"], "baseline": old_score, "candidate": new_score,
                            "api_changed": current.get("api_call") != row.get("api_call"),
                            "sql_changed": (current.get("sql") or "").strip() != (row.get("sql") or "").strip(),
                            "api_call": current.get("api_call"), "sql": current.get("sql"),
                            "reason": details.get("reason"), "parameter_mode": details.get("parameter_mode"),
                            "runtime_abstained": current.get("matched_runbook") is None,
                            "scorer_reason": scored["reason"], "answer_only_match": answer_match,
                            "answer_only_ratio": answer_ratio,
                            "pruned_unused_lookups": details.get("pruned_unused_lookups"),
                            "unmapped_enum_labels": details.get("unmapped_enum_labels"),
                            "result_columns": (current.get("result") or {}).get("columns", []),
                            "result_row_count": (current.get("result") or {}).get("row_count")})
    assert len(outputs) == 150 and not blocked and not matcher.get_llm_events()
    assert not [entry for entry in wire if entry["kind"] != "schema" and entry["status"] != 200]
    metrics = {}
    for name in ["baseline", "candidate"]:
        metrics[name] = {"untimed_score": round(sum(row[name] for row in outputs), 1), "max_score": 750,
                         "full_quality_answers": sum(row[name] == 5 for row in outputs),
                         "partial": sum(0 < row[name] < 5 for row in outputs),
                         "wrong": sum(row[name] < 0 for row in outputs), "refused": sum(row[name] == 0 for row in outputs)}
    changed = [row for row in outputs if row["candidate"] != row["baseline"]]
    report = {"split_id": manifest["split_id"], "scope": "train_only", "cases": 150,
              "metrics": metrics, "improved": sum(row["candidate"] > row["baseline"] for row in outputs),
              "regressed": sum(row["candidate"] < row["baseline"] for row in outputs),
              "changed_cases": changed, "cases_detail": outputs, "feature_flags": flags,
              "simulated_model_stage_counts": dict(Counter(row["stage"] for row in calls)),
              "new_stage_without_historical_response": [row for row in calls if row.get("missing_historical_response")],
              "runtime_abstentions": sum(row["runtime_abstained"] for row in outputs),
              "answered_but_declined_by_scorer": [row["case_id"] for row in outputs if not row["runtime_abstained"] and row["candidate"] == 0],
              "real_model_requests": 0, "blocked_external_attempts": blocked,
              "network_failures": [entry for entry in wire if entry["status"] != 200],
              "history_scope": "latest_train150_live" if args.latest_live else "initial_training_subset",
              "sources": {str(path.relative_to(HERE)): sha(path) for path in [Path(__file__), HERE/"training_data.py", SPLIT/"manifest.json", SPLIT/"train.json", history_path,
                          *[HERE/"implementation"/name for name in ["runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "runbook_executor.py", "evaluator.py"]]]},
              "holdout_accessed": False, "limitation": "Fixed historical selections, reconstructed fill values and accepted SQL proposals; original query/API/executor/scorer rerun. No fresh model, latency or holdout result; library and prior whole-200 exposure remain."}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ["scope", "cases", "metrics", "improved", "regressed", "changed_cases", "real_model_requests", "holdout_accessed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
