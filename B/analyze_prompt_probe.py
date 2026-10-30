"""分析训练子集的新旧精调配对；不读取用例答案或发起网络请求。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from training_data import load_training, sha


def proposal_text(text):
    text = (text or "").strip()
    fence = chr(96)*3
    if text.startswith(fence) and text.endswith(fence):
        text = re.sub("^"+fence+r"(?:sql)?\s*", "", text, flags=re.I)[:-3].strip()
    return text


def analyze(path):
    manifest, cases, _ = load_training()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    plan, summary = rows[0], rows[-1]
    assert plan["type"] == "prompt_probe_plan" and summary["type"] == "summary"
    assert plan["scope"] == summary["scope"] == "train_only_paired_refine"
    assert plan["training_sha256"] == manifest["train_sha256"]
    known = {case["case_id"] for case in cases}
    assert set(plan["case_ids"]) <= known and len(plan["case_ids"]) <= 16
    requests = [row for row in rows if row["type"] == "request"]
    arms = [row for row in rows if row["type"] == "arm"]
    pairs = [row for row in rows if row["type"] == "pair"]
    assert len(requests) <= plan["max_requests"] <= 32
    assert [row["request_index"] for row in requests] == list(range(1, len(requests)+1))
    assert summary["generation_requests"] == len(requests)
    assert all(row["case_id"] in plan["case_ids"] and row["stage"] == "refine" for row in requests)
    assert all(row["requested_model"] == plan["model"] and row["response_model"] in (None, plan["model"]) for row in requests)
    assert len({(row["case_id"], row["variant"]) for row in arms}) == len(arms)
    index = {(row["case_id"], row["variant"]): row for row in arms}
    for pair in pairs:
        before, after = (index[(pair["case_id"], name)] for name in ["original", "candidate"])
        assert before["status"] == after["status"] == "complete"
        for key in ["input_sha256", "api_call", "sql_before_refine"]:
            assert before[key] == after[key]
        assert pair["delta"] == after["untimed_score"]["score"] - before["untimed_score"]["score"]
    if summary["status"] == "complete":
        assert [pair["case_id"] for pair in pairs] == plan["case_ids"]
        assert len(arms) == len(requests) == plan["max_requests"]
    metrics = {}
    for variant in ["original", "candidate"]:
        group = [row for row in arms if row["variant"] == variant and row["status"] == "complete"]
        events = [row for row in requests if row["variant"] == variant]
        contracts = Counter(key+":"+str(value.get("reason")) for row in group
                            for key,value in row["contracts"].items() if isinstance(value,dict) and value.get("reject"))
        metrics[variant] = {"completed_arms": len(group),
            "full_quality": sum(row["untimed_score"]["score"] == 5 for row in group),
            "untimed_score": round(sum(row["untimed_score"]["score"] for row in group),1),
            "rejected_by_contract": sum(any(isinstance(v,dict) and v.get("reject") for v in row["contracts"].values()) for row in group),
            "contract_reasons": dict(contracts),
            "model_returned_exact_original": sum(proposal_text(row["raw_proposal"]) == row["sql_before_refine"].strip() for row in group),
            "accepted_sql_unchanged": sum(row["sql_after_refine"].strip() == row["sql_before_refine"].strip() for row in group),
            "length_truncated": sum(row.get("finish_reason") == "length" for row in events),
            "failed_events": sum(row["status"] != "ok" for row in events),
            "prompt_tokens": sum(row.get("prompt_tokens",0) for row in events),
            "completion_tokens": sum(row.get("completion_tokens",0) for row in events)}
    return {"scope": plan["scope"], "status": summary["status"], "planned_cases": plan["case_count"],
            "completed_pairs": len(pairs), "max_requests": plan["max_requests"], "actual_requests": len(requests),
            "metrics": metrics, "paired_improvements": sum(row["delta"] > 0 for row in pairs),
            "paired_regressions": sum(row["delta"] < 0 for row in pairs),
            "changed_pairs": [row for row in pairs if row["delta"]], "holdout_accessed": False,
            "source": {str(path): sha(path), "analyzer_sha256": sha(Path(__file__))},
            "limitation": "Reviewer-selected training subset, one response per arm, original always first; same fixed v2 selection/API/SQL input, only refine prompt changed. No full query(), full150, holdout or official result; remaining rejected/missing capabilities not solved."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖既有分析")
    report = analyze(args.input)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))


if __name__ == "__main__":
    main()
