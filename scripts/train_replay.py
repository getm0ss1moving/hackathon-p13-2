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

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE/"implementation"))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system_module
from runbook_items import RUNBOOK_ITEMS
from evaluator import evaluate_case, _compare_answers
from replay_compat import (SelectionReplay, guard_retrieve, load_verified_scorers,
                           reconcile_sources, require_official_hashes, verified_library_aliases,
                           verify_legacy_then_rescore)


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
    parser.add_argument("--history-v2", action="store_true", help="使用v2主运行147题和独立补3题；不合并计时成绩")
    parser.add_argument("--candidate-flags", action="store_true", help="启用本轮通用候选，仍不调用模型")
    parser.add_argument("--independent-aggregates", action="store_true", help="独立标量补全候选，默认关闭")
    parser.add_argument("--grouped-aggregates", action="store_true", help="各VDC完整网络资源计数候选，默认关闭")
    parser.add_argument("--network-details", action="store_true", help="VM网卡数量与CIDR明细补全，默认关闭")
    parser.add_argument("--identity-projection", action="store_true", help="固定SQL角色证明的实例标识补列，默认关闭")
    parser.add_argument("--vpc-subnets", action="store_true", help="逐VPC透明子网统计，默认关闭")
    parser.add_argument("--tenant-resources", action="store_true", help="同区域各租户完整资源及规格统计，默认关闭")
    parser.add_argument("--vm-volume-details", action="store_true", help="同租户区域VM及卷完整明细，默认关闭")
    parser.add_argument("--tenant-vdc-binding", action="store_true", help="同CI原生查询证明租户对应VDC条件，默认关闭")
    parser.add_argument("--parallel-resource-lists", action="store_true", help="同范围VM/卷/VPC三份独立列表，默认关闭")
    parser.add_argument("--candidate-feature", choices=["grain", "literals", "prune", "enum"], action="append", default=[])
    args = parser.parse_args()
    from check_official_integrity import require_official_files
    official_integrity = require_official_files(HERE)
    if args.output.exists():
        parser.error("不覆盖已有训练结果")
    manifest, cases, history = load_training()
    history_path = SPLIT/"train_history.jsonl"
    extra_history = []
    if args.history_v2 and args.latest_live:
        parser.error("只能选择一份训练历史")
    if args.history_v2:
        from train_prompt_probe import PARENT, RESUME, validate_history
        parent = [json.loads(line) for line in PARENT.read_text().splitlines()]
        resume = [json.loads(line) for line in RESUME.read_text().splitlines()]
        _, history = validate_history(manifest, cases, parent, resume, sha(PARENT), sha(SPLIT/"manifest.json"))
        history_path = PARENT
        extra_history = [RESUME, HERE/"scripts/train_prompt_probe.py"]
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
    flags["RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES"] = "1" if args.independent_aggregates else "0"
    flags["RUNBOOK_COMPLETE_GROUPED_AGGREGATES"] = "1" if args.grouped_aggregates else "0"
    flags["RUNBOOK_COMPLETE_NETWORK_DETAILS"] = "1" if args.network_details else "0"
    flags["RUNBOOK_COMPLETE_IDENTITY_PROJECTION"] = "1" if args.identity_projection else "0"
    flags["RUNBOOK_COMPLETE_VPC_SUBNETS"] = "1" if args.vpc_subnets else "0"
    flags["RUNBOOK_COMPLETE_TENANT_RESOURCES"] = "1" if args.tenant_resources else "0"
    flags["RUNBOOK_COMPLETE_VM_VOLUME_DETAILS"] = "1" if args.vm_volume_details else "0"
    flags["RUNBOOK_BIND_TENANT_VDC"] = "1" if args.tenant_vdc_binding else "0"
    flags["RUNBOOK_COMPLETE_PARALLEL_LISTS"] = "1" if args.parallel_resource_lists else "0"
    flags["RUNBOOK_THINKING_MODE"] = "provider_default"  # 固定响应回放不能证明模型模式差异。
    snapshot = json.loads((HERE/"baseline_manifest.json").read_text())
    readonly = snapshot["readonly_files"]
    assert all(sha(HERE/name) == value for name, value in readonly.items())
    items = {item["id"]: item for item in RUNBOOK_ITEMS}
    protected_names = ["implementation/" + name for name in
                       ["runbook_items.py", "runbook_retriever.py", "runbook_executor.py", "evaluator.py"]]
    protected_current = {name: sha(HERE/name) for name in
                         protected_names + ["implementation/quick_eval.py", "implementation/blackbox_eval.py"]}
    require_official_hashes(protected_current)
    library_reconciliation = reconcile_sources(
        {name: manifest["initial_runtime_sha256"][name] for name in protected_names}, protected_current)
    aliases = verified_library_aliases(RUNBOOK_ITEMS, protected_current)
    revisions = [entry for entry in snapshot.get("authorized_official_revisions", [])
                 if entry.get("file") == "implementation/evaluator.py"]
    assert len(revisions) == 1, "缺少唯一用户授权评分器修订"
    legacy_evaluate, revised_evaluate, scoring_revision = load_verified_scorers(
        (HERE/"implementation/evaluator.py").read_bytes(), revisions[0], HERE/"implementation/evaluator.py")
    for entry in snapshot.get("integration", {}).get("reconciled_files", {}).values():
        if entry.get("handoff_evidence_sha256"):
            assert sha(HERE/entry["handoff_evidence"]) == entry["handoff_evidence_sha256"]
    native_request, wire, blocked, outputs, calls = requests.Session.request, [], [], [], []
    active = {}

    class ForbiddenModel(BaseException):
        pass

    def request(session, method, url, *values, **options):
        target = urlsplit(str(url))
        if target.hostname != "127.0.0.1" or target.port != 8080 or method.upper() != "GET":
            blocked.append("nonlocal_request")
            raise ForbiddenModel("训练回放只允许本地数据GET")
        if "/schema" not in target.path:
            active["gate"].require_ready()
        response = native_request(session, method, url, *values, **options)
        wire.append({"kind": target.path.rsplit("/", 2)[-2], "resource": target.path.rsplit("/", 1)[-1], "status": response.status_code})
        return response

    def fake_model(prompt, stage="unknown"):
        row = active["record"]
        details = row["diagnostics"]["matching"]
        calls.append({"case_id": row["case_id"], "stage": stage})
        gate = active["gate"]
        gate.require_ready()
        selected = gate.selected_canonical_id
        if stage == "select":
            return str(gate.model_index())
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
        gates = []
        # 全部150题先做纯检索核对；不按旧序号误选去重后的候选，不读取逐题API。
        for case, row in zip(cases, history):
            details = row["diagnostics"]["matching"]
            gate = SelectionReplay(details["candidate_ids"], details.get("selected_template"), items, aliases,
                                   details.get("selection", {}).get("model_index"))
            gate.observe([candidate.id for candidate in system.retriever.retrieve(case["question"])])
            gates.append(gate)
        system.retriever.retrieve = guard_retrieve(system.retriever.retrieve, lambda: active.get("gate"))
        for case, row, gate in zip(cases, history, gates):
            active["record"] = row
            active["gate"] = gate
            if row.get("matched_runbook"):
                baseline = executor.execute({"api_call": row["api_call"], "sql": row["sql"]})
                baseline_output = {"matched_runbook": row["matched_runbook"], "api_call": row["api_call"],
                                   "sql": row["sql"], "result": baseline["result"], "error": baseline["error"]}
            else:
                baseline_output = {"matched_runbook": None, "result": None}
            candidate_output = {}
            def query_candidate():
                candidate_output["output"] = system.query(case["question"])
                return candidate_output["output"]
            score_proof = verify_legacy_then_rescore(case, baseline_output, row, legacy_evaluate,
                                                   revised_evaluate, query_candidate)
            old_score = score_proof["revised_baseline"]["score"]
            current = candidate_output["output"]
            details = current["diagnostics"]["matching"]
            gate.observe(details["candidate_ids"])
            scored = score_proof["revised_candidate"]
            new_score = scored["score"]
            answer_match, answer_ratio = _compare_answers(case.get("answer"), current.get("result")) if current.get("matched_runbook") else (False, 0)
            if args.require_baseline:
                assert new_score == old_score, f"当前query未逐题重现训练基线：{case['case_id']}"
                if row.get("matched_runbook"):
                    assert current["api_call"] == row["api_call"] and current["sql"].strip() == row["sql"].strip(), (
                        f"基线API/SQL漂移：{case['case_id']}，API相同={current['api_call'] == row['api_call']}，"
                        f"SQL前={row['sql']!r}，SQL后={current['sql']!r}")
            outputs.append({"case_id": case["case_id"], "baseline": old_score, "candidate": new_score,
                            "legacy_historical_score": score_proof["legacy_historical_expected"],
                            "legacy_replay_verified": score_proof["legacy_verified"],
                            "selection_replay": gate.proof,
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
              "history_scope": "v2_segmented_train150" if args.history_v2 else "latest_train150_live" if args.latest_live else "initial_training_subset",
              "library_reconciliation": library_reconciliation,
              "scoring_revision": scoring_revision,
              "official_integrity": official_integrity,
              "legacy_score_policy": "verified with byte-identical original evaluator; baseline and candidate metrics are rescored with authorized revision",
              "sources": {str(path.relative_to(HERE)): sha(path) for path in [Path(__file__), HERE/"scripts/training_data.py", HERE/"baseline_manifest.json", SPLIT/"manifest.json", SPLIT/"train.json", history_path,
                          *extra_history, HERE/"implementation/runbook_aggregates.py",
                          HERE/"implementation/runbook_network_details.py", HERE/"implementation/runbook_projection_roles.py",
                          HERE/"implementation/runbook_vpc_subnets.py",
                          HERE/"implementation/runbook_tenant_resources.py",
                          HERE/"implementation/runbook_vm_volume_details.py",
                          HERE/"scripts/check_official_integrity.py", HERE/"implementation/quick_eval.py", HERE/"implementation/blackbox_eval.py",
                          HERE/"implementation/runbook_scope_bindings.py", HERE/"implementation/runbook_identity_guard.py",
                          HERE/"implementation/runbook_parallel_resource_lists.py",
                          HERE/"scripts/replay_compat.py", HERE/"experiments/a_2707ff9_training_handoff.json",
                          *[HERE/"implementation"/name for name in ["runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "runbook_executor.py", "evaluator.py"]]]},
              "holdout_accessed": False, "limitation": "Fixed historical selections, reconstructed fill values and accepted SQL proposals; original query/API/executor/scorer rerun. No fresh model, latency or holdout result; library and prior whole-200 exposure remain."}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ["scope", "cases", "metrics", "improved", "regressed", "changed_cases", "real_model_requests", "holdout_accessed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
