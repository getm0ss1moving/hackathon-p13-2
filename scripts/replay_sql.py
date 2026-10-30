"""固定已返回的模型输出，离线比较精调 SQL 与所选模板原 SQL；模型请求为零。"""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlparse

import httpx
import requests

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
import runbook_executor as executor
from evaluator import evaluate_case
from runbook_items import RUNBOOK_ITEMS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_cases(rows, cases, all_cases):
    recorded = [row for row in rows if row["type"] == "case"]
    if len({row["case_id"] for row in recorded}) != len(recorded):
        raise ValueError("记录中存在重复题号")
    if any(row["case_id"] not in cases for row in recorded):
        raise ValueError("存在原数据集以外的题号")
    if all_cases and set(row["case_id"] for row in recorded) != set(cases):
        raise ValueError("全范围回放必须覆盖原用例的全部题号")
    if any(row["question"] not in {cases[row["case_id"]]["question"], cases[row["case_id"]]["question"][:60]}
           for row in recorded):
        raise ValueError("记录文本与原用例全文或原评分器的 60 字前缀不一致")
    recorded = [{**row, "question": cases[row["case_id"]]["question"]} for row in recorded]
    for row in recorded:
        if row.get("sql") and not (row.get("diagnostics") or {}).get("matching", {}).get("sql_before_refine"):
            raise ValueError("已作答记录缺少精调前 SQL，不能推断或补造")
    return recorded if all_cases else [row for row in recorded if row.get("sql")
        and row["diagnostics"]["matching"]["sql_before_refine"] != row["sql"]]



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-cases", action="store_true", help="全部原记录：重放已作答路径，原拒答保持拒答")
    parser.add_argument("--rule-fill-proof", type=Path, help="核对既有规则填参证据中的可省略路径与输出列候选组合")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--contract", choices=["projection", "row-semantics"], default="projection")
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    if rows[-1].get("status") != "complete":
        parser.error("只接受已完整完成的测试记录")
    cases_file = HERE / "CMDB用例集-白盒200.json"
    if sha(cases_file) != rows[0]["dataset_sha256"]:
        parser.error("原数据哈希变化，停止回放")
    cases = {c["case_id"]: c for c in json.loads(cases_file.read_text())["cases"]}
    try:
        selected_rows = source_cases(rows, cases, args.all_cases)
    except ValueError as error:
        parser.error(str(error))
    proof = json.loads(args.rule_fill_proof.read_text()) if args.rule_fill_proof else None
    if proof and (proof["history_sha256"] != sha(args.input) or proof["dataset_sha256"] != sha(cases_file)
                  or proof["candidate_matcher_sha256"] != sha(HERE / "implementation/runbook_matcher.py")
                  or not proof["summary"]["compatible_in_checked_scope"]):
        parser.error("规则填参证据与当前输入/源码不一致")
    eligible = {row["case_id"] for row in proof["comparisons"] if row["eligible"]} if proof else set()
    if eligible - {row["case_id"] for row in selected_rows}:
        parser.error("组合回归范围未覆盖规则证据，使用 --all-cases")
    manifest = json.loads((HERE / "baseline_manifest.json").read_text())
    if any(sha(HERE / relative) != expected for relative, expected in manifest["readonly_files"].items()):
        parser.error("只读快照发生变化")
    if matcher.get_llm_events() or executor._cache:
        parser.error("请使用新进程，避免混入模型请求或既有执行缓存")
    if args.output.exists():
        parser.error("不覆盖历史证据，请使用新输出文件")
    results = []
    item_by_id = {item["id"]: item for item in RUNBOOK_ITEMS}
    native_request, native_send, native_query = requests.Session.request, httpx.Client.send, executor._query_server
    network_failures, blocked, tainted_cache = [], [], set()
    read_failures = set()

    def local(url):
        parsed = urlparse(str(url))
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.port != 8080:
            blocked.append(parsed.hostname)
            raise AssertionError("回放禁止外部网络")

    def request(session, method, url, *args, **kwargs):
        local(url)
        endpoint, ci = urlparse(str(url)).path.rsplit("/", 2)[-2:]
        failure = None
        try:
            response = native_request(session, method, url, *args, **kwargs)
            if response.status_code != 200:
                failure = f"http_{response.status_code}"
            else:
                try:
                    body = response.json()
                    field = "columns" if endpoint == "schema" else "objList"
                    if not isinstance(body, dict) or not isinstance(body.get(field), list):
                        failure = "invalid_envelope"
                except ValueError:
                    failure = "invalid_json"
            return response
        except requests.RequestException:
            failure = "request_error"
            raise
        finally:
            if failure:
                network_failures.append({"endpoint": endpoint, "ci": ci, "failure": failure})

    def send(client, request, *args, **kwargs):
        local(request.url)
        return native_send(client, request, *args, **kwargs)

    def observe_query(ci, conditions=None):
        # 不更改原返回值、条件、缓存或分页；只跟踪失败结果进入缓存后的复用。
        key = ci + "::" + json.dumps(conditions or [], sort_keys=True)
        before = len(network_failures)
        records = native_query(ci, conditions)
        if any(row["endpoint"] != "schema" for row in network_failures[before:]):
            tainted_cache.add(key)
        if key in tainted_cache:
            read_failures.add(ci)
        return records

    class UnexpectedModelCall(BaseException):
        pass

    old_logging = logging.root.manager.disable
    try:
      logging.disable(logging.CRITICAL)
      with patch.object(requests.Session, "request", request), patch.object(httpx.Client, "send", send), \
           patch.object(executor, "_query_server", observe_query), \
           patch.object(matcher, "llm_ask", side_effect=UnexpectedModelCall("回放禁止真实模型")), \
           args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps({"type": "plan", "source": str(args.input), "source_sha256": sha(args.input),
                                 "cases": len(selected_rows), "all_cases": args.all_cases,
                                 "matcher_sha256": sha(HERE / "implementation/runbook_matcher.py"),
                                 "script_sha256": sha(Path(__file__)), "dataset_sha256": sha(cases_file),
                                 "rule_fill_proof_sha256": sha(args.rule_fill_proof) if proof else None,
                                 "question_policy": "full canonical dataset question; stored scorer prefix verified",
                                 "contract": args.contract,
                                 "model_requests": 0, "protocol": "fixed recorded API/SQL; original executor/evaluator; untimed scores only"}) + "\n")
        matcher._warm_schema_cache()
        for i, row in enumerate(selected_rows):
            case = cases[row["case_id"]]
            if not row.get("matched_runbook"):
                actual = evaluate_case(case, {"matched_runbook": None, "result": None}, 0)
                result = {"type": "case", "case_id": row["case_id"], "path": "recorded_refusal_unchanged",
                          "baseline_recorded": row["score_without_time_penalty"] , "baseline_replayed": actual["score"],
                          "candidate_score": actual["score"], "delta": 0,
                          "replay_consistent": actual["score"] == row["score_without_time_penalty"],
                          "policy": {"reject": False, "reason": "recorded_refusal_unchanged"}}
                results.append(result)
                output.write(json.dumps(result, ensure_ascii=False) + "\n")
                output.flush()
                continue
            original = row["diagnostics"]["matching"]["sql_before_refine"]
            def score(sql):
                read_failures.clear()
                result = executor.execute({"api_call": row["api_call"], "sql": sql})
                scored = evaluate_case(case, {"matched_runbook": row["matched_runbook"], "api_call": row["api_call"],
                                            "sql": sql, "result": result["result"], "error": result["error"]}, 0)
                return scored, sorted(read_failures), result["error"]
            actual, actual_failures, actual_error = score(row["sql"])
            before, before_failures, before_error = score(original) if original != row["sql"] else (actual, actual_failures, actual_error)
            restored, restored_columns = (matcher._recover_grouped_identity_columns(original, row["sql"], case["question"])
                                          if args.contract == "row-semantics" else (row["sql"], []))
            policy = (matcher._row_semantics_contract(original, restored, case["question"])
                      if args.contract == "row-semantics" else matcher._projection_contract(original, restored))
            policy["restored_identity_columns"] = restored_columns
            consistent = actual["score"] == row["score_without_time_penalty"]
            candidate_sql = original if policy["reject"] else restored
            chosen, chosen_failures, chosen_error = (score(candidate_sql) if candidate_sql not in {row["sql"], original}
                else (before, before_failures, before_error) if candidate_sql == original else (actual, actual_failures, actual_error))
            candidate = chosen["score"]
            combo = None
            if row["case_id"] in eligible:
                template_id = row["diagnostics"]["matching"]["selected_template"]
                retriever = Mock()
                retriever.retrieve.return_value = [SimpleNamespace(id=template_id, tier="strong")]
                def model_answer(prompt, stage):
                    if stage == "fill":
                        raise UnexpectedModelCall("规则完整的组合路径不应请求 fill")
                    return {"select": "1", "refine": row["sql"]}[stage]
                with patch.dict(os.environ, {"RUNBOOK_RULE_ONLY_FILL": "1", "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1",
                                             "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0"}), \
                     patch.object(matcher, "llm_ask", side_effect=model_answer) as model:
                    matched = matcher.match_runbook(row["question"], [item_by_id[template_id]], retriever, {})
                combo = (matched is not None and matched["api_call"] == row["api_call"] and matched["sql"] == candidate_sql
                         and [call.kwargs["stage"] for call in model.call_args_list] == ["select", "refine"])
            result = {"type": "case", "case_id": row["case_id"], "baseline_recorded": row["score_without_time_penalty"],
                      "baseline_replayed": actual["score"], "original_sql_score": before["score"],
                      "candidate_score": candidate, "delta": round(candidate - actual["score"], 1),
                      "replay_consistent": consistent, "policy": policy,
                      "path": "recorded_answer_reexecuted", "rule_fill_combo_verified": combo,
                      "baseline_data_read_failures": actual_failures,
                      "candidate_data_read_failures": chosen_failures,
                      "baseline_execution_error": actual_error,
                      "candidate_execution_error": chosen_error,
                      "original_sql": original, "refined_sql": row["sql"], "candidate_sql": candidate_sql}
            results.append(result)
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            if not args.quiet:
                print(f"[{i+1}/{len(selected_rows)}] {row['case_id']}: 当前 {actual['score']} / 原SQL {before['score']} / 契约候选 {candidate}", flush=True)
        consistent = [row for row in results if row["replay_consistent"]]
        summary = {"type": "summary", "cases": len(results), "replay_consistent": len(consistent),
                   "guarded_cases": sum(row["policy"]["reject"] for row in consistent),
                   "improved_cases": sum(row["delta"] > 0 for row in consistent),
                   "regressed_cases": sum(row["delta"] < 0 for row in consistent),
                   "untimed_delta": round(sum(row["delta"] for row in consistent), 1), "model_requests": len(matcher.get_llm_events()),
                   "baseline_untimed_score": round(sum(row["baseline_replayed"] for row in results), 1),
                   "candidate_untimed_score": round(sum(row["candidate_score"] for row in results), 1),
                   "baseline_full_score_answers": sum(row["baseline_replayed"] == 5 for row in results),
                   "candidate_full_score_answers": sum(row["candidate_score"] == 5 for row in results),
                   "recorded_refusals_unchanged": sum(row.get("path") == "recorded_refusal_unchanged" for row in results),
                   "answered_paths_reexecuted": sum(row.get("path") == "recorded_answer_reexecuted" for row in results),
                   "baseline_data_failure_cases": [row["case_id"] for row in results if row.get("baseline_data_read_failures")],
                   "candidate_data_failure_cases": [row["case_id"] for row in results if row.get("candidate_data_read_failures")],
                   "network_failures": network_failures, "blocked_external_attempts": blocked,
                   "rule_fill_combo_cases": sum(row.get("rule_fill_combo_verified") is not None for row in results),
                   "rule_fill_combo_verified": sum(row.get("rule_fill_combo_verified") is True for row in results),
                   "limitation": "conditional on frozen model outputs; not a fresh-model or latency comparison"}
        summary["comparison_consistent"] = len(consistent) == len(results) and not blocked and not any(
            row.get("rule_fill_combo_verified") is False for row in results)
        summary["status"] = "complete"
        output.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        logging.disable(old_logging)
    return 0 if summary["comparison_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
