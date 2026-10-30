"""只分析固定150题训练结果；不打开原200题或封存50题。"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from training_data import load_training, sha, SPLIT

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", choices=["v1", "v2"], default="v1")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖训练分析")
    expected_input = HERE/("experiments/train150_"+args.round+"_live.jsonl")
    if args.input is not None and args.input.resolve() != expected_input.resolve():
        parser.error("只分析指定轮次的150训练题记录，不打开其他集合")
    args.input = expected_input
    manifest, train, historical = load_training()
    baseline_training_metrics = manifest["training_summary"]
    previous_live = None
    if args.round == "v2":
        previous_live = HERE/"experiments/train150_v1_live.jsonl"
        previous_rows = [json.loads(line) for line in previous_live.read_text().splitlines()]
        historical = [row for row in previous_rows if row["type"] == "case"]
        if (previous_rows[0].get("scope") != "train_only" or previous_rows[-1].get("status") != "complete"
                or [row["case_id"] for row in historical] != [row["case_id"] for row in train]):
            parser.error("前轮不是相同150题的完整训练运行")
        baseline_training_metrics = {"case_count": 150,
            "untimed_score": previous_rows[-1]["untimed_score"], "score": previous_rows[-1]["total_score"],
            "full_quality_answers": previous_rows[-1]["full_quality_answers"],
            "partial": sum(0 < row["score_without_time_penalty"] < 5 for row in historical),
            "wrong": sum(row["score_without_time_penalty"] < 0 for row in historical),
            "refused": sum(row["score_without_time_penalty"] == 0 for row in historical),
            "source_sha256": sha(previous_live)}
    allowed = {case["case_id"] for case in train}
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    plan, summary = rows[0], rows[-1]
    if plan.get("scope") != "train_only" or plan.get("case_count") != 150:
        parser.error("仅接受固定150训练题记录；不分析其他范围")
    if summary.get("status") != "complete" or summary.get("completed_cases") != 150 or summary.get("type") != "summary":
        parser.error("训练未完整完成，不能记全量成绩")
    cases = [row for row in rows if row["type"] == "case"]
    events = [row for row in rows if row["type"] == "request"]
    assert len(cases) == 150 and len({row["case_id"] for row in cases}) == 150
    # 原evaluate_case返回的question仅60字；本轮记录合并顺序保留了该预览。
    # 冻结入口实际给system.query和evaluate_case传的是train.json中的完整问题。
    full_question_log = plan.get("record_format", 1) >= 2
    assert [(row["case_id"], row["question"]) for row in cases] == [(row["case_id"], row["question"] if full_question_log else row["question"][:60]) for row in train]
    assert all(row["case_id"] in allowed for row in events)
    assert len(events) == summary["generation_requests"] <= 450
    assert len(events) == sum(len(row["diagnostics"]["llm_calls"]) for row in cases)
    assert all(row["requested_model"] == row["response_model"] == plan["model"] == "deepseek-flash" for row in events)
    assert plan["max_requests"] == 450 and plan["max_output_tokens"] == 1024 and plan["sdk_max_retries"] == 0
    assert not summary["model_identity_mismatches"] and not summary["holdout_evaluated"]
    assert plan["training_sha256"] == manifest["train_sha256"] == sha(SPLIT/"train.json")
    frozen_path = HERE/("experiments/train150_"+args.round+"_live_plan.json")
    auth_path = HERE/("experiments/train150_"+args.round+"_authorization.json")
    frozen, auth = json.loads(frozen_path.read_text()), json.loads(auth_path.read_text())
    assert auth["plan_sha256"] == sha(frozen_path)
    assert all(frozen.get(key) == value for key, value in plan.items() if key not in {"created_at", "authorization"})
    assert auth["scope"]["cases"] == 150 and auth["scope"]["max_requests"] == 450
    assert not auth["scope"]["holdout_read_or_eval"] and not auth["scope"]["git_stage_commit_push"]
    assert all(sha(HERE/name) == digest for name, digest in plan["source_sha256"].items())
    score = round(sum(row["score"] for row in cases), 1)
    quality = round(sum(row["score_without_time_penalty"] for row in cases), 1)
    assert score == summary["total_score"] and quality == summary["untimed_score"]
    metrics = {"score": score, "untimed_score": quality, "max_score": 750,
               "full_quality_answers": sum(row["score_without_time_penalty"] == 5 for row in cases),
               "partial": sum(0 < row["score_without_time_penalty"] < 5 for row in cases),
               "wrong": sum(row["score_without_time_penalty"] < 0 for row in cases),
               "refused": sum(row["score_without_time_penalty"] == 0 for row in cases),
               "time_penalty": round(quality-score, 1), "generation_requests": len(events),
               "runtime_abstentions": sum(row["matched_runbook"] is None for row in cases),
               "failed_requests": sum(row["status"] != "ok" for row in events),
               "prompt_tokens": sum(row["prompt_tokens"] for row in events),
               "completion_tokens": sum(row["completion_tokens"] for row in events),
               **{key: summary[key] for key in ["latency_p50", "latency_p95", "wall_seconds", "peak_evaluation_process_mib"]}}
    pairs = [{"case_id": old["case_id"], "historical_quality": old["score_without_time_penalty"],
              "current_quality": new["score_without_time_penalty"],
              "delta": round(new["score_without_time_penalty"]-old["score_without_time_penalty"], 1),
              "selected_changed": old["diagnostics"]["matching"].get("selected_template") != new["diagnostics"]["matching"].get("selected_template")}
             for old, new in zip(historical, cases)]
    stage_data = defaultdict(lambda: {"requests": 0, "failures": 0, "seconds": 0.0})
    for event in events:
        stage = stage_data[event["stage"]]
        stage["requests"] += 1
        stage["failures"] += event["status"] != "ok"
        stage["seconds"] = round(stage["seconds"]+event["seconds"], 4)
    report = {"scope": "train_only", "split_id": manifest["split_id"], "status": "complete", "metrics": metrics,
              "baseline_training_metrics": baseline_training_metrics, "independent_runs_each": 1,
              "pairs": pairs, "quality_improved": sum(row["delta"] > 0 for row in pairs),
              "quality_regressed": sum(row["delta"] < 0 for row in pairs),
              "stages": dict(stage_data), "model_error_types": dict(Counter(row.get("error_type", "unspecified") for row in events if row["status"] != "ok")),
              "refusal_reasons": dict(Counter(row["diagnostics"]["matching"].get("reason") for row in cases if row["score_without_time_penalty"] == 0)),
              "nonperfect_training_cases": [{"case_id": row["case_id"], "quality": row["score_without_time_penalty"],
                                             "reason": row["diagnostics"]["matching"].get("reason")} for row in cases if row["score_without_time_penalty"] != 5],
              "unused_requests": 450-len(events), "budget_scope_closed": True, "unused_requests_reusable": False,
              "holdout_accessed_or_evaluated": False, "formal_model_confirmed": False,
              "logged_question_preview_limit": None if full_question_log else 60,
              "truncated_log_question_count": 0 if full_question_log else sum(len(row["question"]) > 60 for row in train),
              "full_input_source": "fixed train.json; frozen runner passes full case['question']; raw logs remain unchanged",
              "source_sha256": {str(path.relative_to(HERE)): sha(path) for path in [Path(__file__), args.input.resolve(), frozen_path, auth_path,
                                  SPLIT/"manifest.json", SPLIT/"train.json", SPLIT/"train_history.jsonl"]},
              "limitations": ["Historical single training subset versus current single run; model outputs and provider load may differ; no causal or stable speed claim.",
                              "All original questions/outcomes and fixed 200-template examples were exposed before split; prospective tuning exclusion only.",
                              "Training fit is not generalization; no holdout metrics, independent final test, blackbox or formal aggregate score.",
                              "Process memory excludes data service; per-step data HTTP status and provider backend are not recorded."],
              "decision": "继续按训练集改进，候选保持本地；不查看封存集反馈。"}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ["metrics", "quality_improved", "quality_regressed", "unused_requests", "refusal_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
