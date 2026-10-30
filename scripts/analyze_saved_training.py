"""仅分析run_saved_training固定训练范围，保留计时/不计时分与拒答实况。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

from training_data import load_training


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    destination = directory / "analysis.json"
    if destination.exists():
        parser.error("分析已存在，不能覆盖")
    manifest, train, _ = load_training()
    training = {case["case_id"]: case for case in train}
    plan = json.loads((directory / "plan.json").read_text())
    rows = [json.loads(line) for line in (directory / "live.jsonl").read_text().splitlines()]
    cases = [row for row in rows if row.get("type") == "case"]
    events = [row for row in rows if row.get("type") == "request"]
    summary = rows[-1]
    assert rows[0]["type"] == "training_plan"
    assert all(rows[0].get(key) == value for key, value in plan.items() if key not in {"created_at", "authorization"})
    assert plan["scope"] in {"train_only", "train_subset"} and not plan["holdout_evaluated"]
    assert set(plan["case_ids"]) <= set(training) and len(plan["case_ids"]) == len(set(plan["case_ids"]))
    assert plan["training_sha256"] == manifest["train_sha256"]
    assert summary["type"] == "summary" and summary["status"] == "complete"
    assert [case["case_id"] for case in cases] == plan["case_ids"]
    assert all(case["question"] == training[case["case_id"]]["question"] for case in cases)
    assert all(event["case_id"] in plan["case_ids"] for event in events)
    assert len(events) == summary["generation_requests"] <= plan["max_requests"] <= 450
    assert len(events) == sum(len(case["diagnostics"]["llm_calls"]) for case in cases)
    assert all(event["requested_model"] == event["response_model"] == plan["model"] == "deepseek-flash" for event in events)
    assert plan["thinking_mode"] == "disabled" and plan["sdk_max_retries"] == 0 and plan["max_output_tokens"] == 1024
    with zipfile.ZipFile(directory / "source.zip") as frozen:
        assert all(sha(frozen.read("runtime/" + name)) == digest for name, digest in plan["source_sha256"].items())
    quality = round(sum(case["score_without_time_penalty"] for case in cases), 1)
    timed = round(sum(case["score"] for case in cases), 1)
    assert quality == summary["untimed_score"] and timed == summary["total_score"]
    failures = []
    for case in cases:
        if case["score_without_time_penalty"] == 5 and case.get("matched_runbook") is not None:
            continue
        detail = case["diagnostics"]
        rejection = detail.get("rejection") or {}
        category = rejection.get("reason") or detail.get("family_error") or detail.get("reason") or "unclassified"
        if case["score_without_time_penalty"] == 5:
            category = "grader_full_but_runtime_abstained"
        elif case.get("matched_runbook") is not None:
            category = "executed_answer_mismatch_or_partial"
        failures.append({"case_id": case["case_id"], "quality": case["score_without_time_penalty"],
                         "timed_score": case["score"], "category": category,
                         "selected_template": detail.get("selected_template"),
                         "family_error": detail.get("family_error"), "question": case["question"],
                         "sql": case.get("sql"), "result": case.get("result"),
                         "diagnostics": detail})
    result = {"status": "complete", "scope": plan["scope"], "template_count": plan["template_count"],
              "evaluator_sha256": plan["source_sha256"]["implementation/evaluator.py"],
              "scoring_revision": plan.get("scoring_revision", {}),
              "cases": len(cases), "max_score": 5 * len(cases), "untimed_quality": quality, "timed_score": timed,
              "grader_full_quality": sum(case["score_without_time_penalty"] == 5 for case in cases),
              "runtime_abstentions": sum(case.get("matched_runbook") is None for case in cases),
              "grader_full_but_runtime_abstained": sum(case["score_without_time_penalty"] == 5 and case.get("matched_runbook") is None for case in cases),
              "generation_requests": len(events), "failed_requests": sum(event["status"] != "ok" for event in events),
              "categories": dict(Counter(row["category"] for row in failures)), "issues": failures,
              "source_zip_sha256": sha((directory / "source.zip").read_bytes()),
              "trace_sha256": sha((directory / "live.jsonl").read_bytes()),
              "holdout_read_or_evaluated": False, "cross_round_scores_combined": False,
              "limitations": ["固定训练集单次诊断，不是泛化或正式比赛成绩。",
                              "评分满分可能包括对空参考的拒答；不将其统称业务成功。",
                              "原题和模板曾在划分前曝光，50题只隔离未来调参。"]}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in {"issues", "limitations"}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
