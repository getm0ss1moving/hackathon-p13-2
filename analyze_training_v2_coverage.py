"""147题超时中断+获准3题补测的训练覆盖分析；不伪造完整单轮。"""

import argparse
from collections import Counter
import json
from pathlib import Path

from training_data import load_training, sha, SPLIT

HERE = Path(__file__).resolve().parent


def read(name):
    return [json.loads(line) for line in (HERE/"experiments"/name).read_text().splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖覆盖分析")
    manifest, train, _ = load_training()
    parent = read("train150_v2_live.jsonl")
    resume = read("train150_v2_resume_live.jsonl")
    baseline = read("train150_v1_live.jsonl")
    first = [row for row in parent if row["type"] == "case"]
    tail = [row for row in resume if row["type"] == "case"]
    old = [row for row in baseline if row["type"] == "case"]
    events = [row for row in parent+resume if row["type"] == "request"]
    cases = first+tail
    assert parent[-1]["status"] == "incomplete" and len(first) == 147
    assert resume[-1]["status"] == "complete" and len(tail) == 3
    assert len(cases) == 150 and len({row["case_id"] for row in cases}) == 150
    assert [(row["case_id"], row["question"]) for row in cases] == [(row["case_id"], row["question"]) for row in train]
    assert [row["case_id"] for row in old] == [row["case_id"] for row in train]
    assert len(events) == 293 and len([row for row in parent if row["type"] == "request"]) == 289
    assert len([row for row in resume if row["type"] == "request"]) == 4 <= 9
    original_plan = HERE/"experiments/train150_v2_live_plan.json"
    original_auth = json.loads((HERE/"experiments/train150_v2_authorization.json").read_text())
    resume_plan = HERE/"experiments/train150_v2_resume_plan.json"
    resume_auth = json.loads((HERE/"experiments/train150_v2_resume_authorization.json").read_text())
    assert original_auth["plan_sha256"] == sha(original_plan)
    assert resume_auth["plan_sha256"] == sha(resume_plan)
    assert resume[0]["parent_sha256"] == sha(HERE/"experiments/train150_v2_live.jsonl")
    assert not resume_auth["single_pass_full_150_claim_allowed"]
    assert all(sha(HERE/name) == digest for name, digest in parent[0]["source_sha256"].items())
    assert resume[0]["source_sha256"] == parent[0]["source_sha256"]
    assert sha(HERE/"resume_training_v2.py") == resume[0]["runner_sha256"]
    unknown = [row for row in events if row.get("response_model") is None]
    assert len(unknown) == 1 and unknown[0]["error_type"] == "APITimeoutError"
    assert all(row["requested_model"] == "deepseek-flash" for row in events)
    assert all(row.get("response_model") == "deepseek-flash" for row in events if row.get("response_model") is not None)
    metrics = {"full_quality_answers": sum(row["score_without_time_penalty"] == 5 for row in cases),
               "partial": sum(0 < row["score_without_time_penalty"] < 5 for row in cases),
               "wrong": sum(row["score_without_time_penalty"] < 0 for row in cases),
               "scorer_zero": sum(row["score_without_time_penalty"] == 0 for row in cases),
               "runtime_abstentions": sum(row["matched_runbook"] is None for row in cases),
               "untimed_coverage_diagnostic": round(sum(row["score_without_time_penalty"] for row in cases), 1),
               "generation_requests": len(events), "known_response_models_verified": len(events)-len(unknown),
               "visible_prompt_tokens": sum(row["prompt_tokens"] for row in events),
               "visible_completion_tokens": sum(row["completion_tokens"] for row in events),
               "failed_requests": sum(row["status"] != "ok" for row in events)}
    pairs = [{"case_id": before["case_id"], "old_quality": before["score_without_time_penalty"],
              "new_quality": after["score_without_time_penalty"],
              "delta": round(after["score_without_time_penalty"]-before["score_without_time_penalty"], 1)} for before, after in zip(old, cases)]
    segments = [{"file": "train150_v2_live.jsonl", "status": "incomplete", "cases": 147,
                 "score_sum_completed": round(sum(row["score"] for row in first), 1), "max_completed": 735,
                 "untimed_completed": round(sum(row["score_without_time_penalty"] for row in first), 1),
                 "full_quality": sum(row["score_without_time_penalty"] == 5 for row in first),
                 "historical_full_same_cases": sum(row["score_without_time_penalty"] == 5 for row in old[:147]),
                 "requests": 289, "timeout": unknown[0]["case_id"]},
                {"file": "train150_v2_resume_live.jsonl", "status": "complete", "cases": 3,
                 "score_sum_completed": round(sum(row["score"] for row in tail), 1), "max_completed": 15,
                 "untimed_completed": round(sum(row["score_without_time_penalty"] for row in tail), 1),
                 "requests": 4, "fresh_process_and_cache": True}]
    sources = [Path(__file__), SPLIT/"train.json", original_plan, resume_plan, HERE/"experiments/train150_v2_live.jsonl",
               HERE/"experiments/train150_v2_resume_live.jsonl", HERE/"experiments/train150_v1_live.jsonl",
               HERE/"experiments/train150_v2_authorization.json", HERE/"experiments/train150_v2_resume_authorization.json"]
    report = {"scope": "train_only_segmented_coverage", "split_id": manifest["split_id"], "coverage_cases": 150,
              "full_training_coverage": True, "single_pass_complete": False, "segments": segments, "metrics": metrics,
              "baseline_full_quality": sum(row["score_without_time_penalty"] == 5 for row in old),
              "baseline_untimed_diagnostic": round(sum(row["score_without_time_penalty"] for row in old), 1),
              "pairs": pairs, "improved": sum(row["delta"] > 0 for row in pairs), "regressed": sum(row["delta"] < 0 for row in pairs),
              "error_types": dict(Counter(row.get("error_type") for row in events if row["status"] != "ok")),
              "new_cases_not_full": [{"case_id": row["case_id"], "quality": row["score_without_time_penalty"],
                                      "runtime_abstained": row["matched_runbook"] is None, "reason": row["reason"],
                                      "matching": row["diagnostics"]["matching"]} for row in cases if row["score_without_time_penalty"] != 5],
              "holdout_accessed": False, "budget_used": 293, "budget_limit": 450, "unused_requests_nonreusable": 157,
              "sources": {str(path.relative_to(HERE)): sha(path) for path in sources},
              "limitations": ["Original150 run stopped after147; resume3 was explicitly approved. Do not combine timed scores into a purported complete single-pass score.",
                              "One timeout has no returned model identity or token usage; visible token sums are not a billing total.",
                              "Historical single run versus two-segment coverage is descriptive, not a stable or per-component causal improvement.",
                              "The fixed200 public template library and prior exposure remain; no heldout or official-model generalization claim."]}
    with args.output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ["coverage_cases", "single_pass_complete", "metrics", "improved", "regressed", "error_types"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
