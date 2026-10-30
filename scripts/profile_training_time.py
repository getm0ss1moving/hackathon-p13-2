"""只读固定训练日志，重算端到端分解；不导入查询系统、不发网络请求。"""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import zipfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def records(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)] if values else None


def describe(values):
    return {"n": len(values), "sum": sum(values), "mean": statistics.mean(values),
            "p50": percentile(values, .5), "p95": percentile(values, .95), "max": max(values)} if values else None


def correlation(a, b):
    if len(a) < 2:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    denominator = math.sqrt(sum((v-ma)**2 for v in a) * sum((v-mb)**2 for v in b))
    return sum((x-ma)*(y-mb) for x, y in zip(a, b)) / denominator if denominator else None


def stage_stats(events):
    times = [r["seconds"] for r in events]
    inputs = [r["prompt_tokens"] for r in events]
    outputs = [r["completion_tokens"] for r in events]
    return {"seconds": describe(times), "input_tokens": describe(inputs), "output_tokens": describe(outputs),
            "input_time_pearson_r": correlation(inputs, times),
            "output_time_pearson_r": correlation(outputs, times)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root, args.out
    trace = root / "experiments/train150_v18_full_live.jsonl"
    planpath = root / "experiments/train150_v18_full_plan.json"
    freeze_path = root / "experiments/train150_v18_freeze.json"
    budgetpath = root / "experiments/train150_v18_full_budget.json"
    plan = json.loads(planpath.read_text())
    freeze = json.loads(freeze_path.read_text())
    budget = json.loads(budgetpath.read_text())
    rows = records(trace)
    cases = [r for r in rows if r["type"] == "case"]
    events = [r for r in rows if r["type"] == "request"]
    summary = rows[-1]
    assert plan["scope"] == "train_only" and plan["case_count"] == 150
    assert summary["status"] == "complete" and summary["completed_cases"] == len(cases) == 150
    assert [r["case_id"] for r in cases] == plan["case_ids"]
    assert len(events) == summary["generation_requests"] == budget["actual_requests"] == 301
    assert budget["status"] == "closed" and budget["trace_sha256"] == sha(trace)
    assert freeze["evidence_sha256"][str(trace.relative_to(root))] == sha(trace)
    assert all(r["status"] == "ok" and r["usage_available"] and r["thinking_mode"] == "disabled" for r in events)
    assert all(r["requested_model"] == r["response_model"] == "deepseek-flash" for r in events)
    assert all(r["score"] == r["score_without_time_penalty"] for r in cases)
    archive = root / "reports/train150_v18_A198_revised_source.zip"
    source_archive_sha256 = None
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert all(hashlib.sha256(z.read(name)).hexdigest() == digest for name, digest in plan["source_sha256"].items())
        source_archive_sha256 = sha(archive)
    else:
        # Git交付不含本机恢复ZIP；当前发布的源码可直接逐项核验。
        assert all(sha(root / name) == digest for name, digest in plan["source_sha256"].items())
    case_ids = set(plan["case_ids"])
    per_case = []
    for r in cases:
        diag = r["diagnostics"]
        own = [e for e in events if e["case_id"] == r["case_id"]]
        assert len(own) == len(diag["llm_calls"])
        for independent, nested in zip(own, diag["llm_calls"]):
            assert all(independent.get(key) == value for key, value in nested.items())
        llm = sum(e["seconds"] for e in own)
        match, execute = diag["match_seconds"], diag["execute_seconds"]
        per_case.append({"case_id": r["case_id"], "query_seconds": r["elapsed"],
                         "select_seconds": sum(e["seconds"] for e in own if e["stage"] == "select"),
                         "fill_seconds": sum(e["seconds"] for e in own if e["stage"] == "fill"),
                         "refine_seconds": sum(e["seconds"] for e in own if e["stage"] == "refine"),
                         "llm_seconds": llm, "match_seconds": match, "execute_seconds": execute,
                         "match_other_seconds": match - llm,
                         "query_rounding_and_outer_residual_seconds": r["elapsed"] - match - execute,
                         "llm_query_fraction": llm / r["elapsed"], "request_count": len(own),
                         "input_tokens": sum(e["prompt_tokens"] for e in own),
                         "output_tokens": sum(e["completion_tokens"] for e in own),
                         "refine_status": diag["matching"].get("refine_status", "no_refine"), "score": r["score"]})
    query_total = sum(r["elapsed"] for r in cases)
    stages = {stage: stage_stats([e for e in events if e["stage"] == stage]) for stage in ["select", "fill", "refine"]}
    llm_total = sum(e["seconds"] for e in events)
    match_total = sum(r["match_seconds"] for r in per_case)
    execute_total = sum(r["execute_seconds"] for r in per_case)
    components = {stage: stats["seconds"]["sum"] for stage, stats in stages.items()}
    components.update(local_execute=execute_total, other_match=match_total-llm_total,
                      rounding_outer_residual=query_total-match_total-execute_total)
    refine_status = {}
    for status in sorted({r["refine_status"] for r in per_case} - {"no_refine"}):
        ids = {r["case_id"] for r in per_case if r["refine_status"] == status}
        refine_status[status] = stage_stats([e for e in events if e["stage"] == "refine" and e["case_id"] in ids])
    thinking = {}
    thinking_plans = []
    for mode in ["default4", "disabled4"]:
        p = root / ("experiments/train150_v5_thinking_" + mode + "_live.jsonl")
        history = records(p)
        old_plan = history[0]
        thinking_plans.append(old_plan)
        old_cases = [r for r in history if r["type"] == "case"]
        old_events = [r for r in history if r["type"] == "request"]
        assert {r["case_id"] for r in old_cases} <= case_ids
        thinking[mode] = {"case_count": len(old_cases), "query_seconds": describe([r["elapsed"] for r in old_cases]),
                          "requests": len(old_events), "completion_tokens": sum(e["completion_tokens"] for e in old_events),
                          "observed_reasoning_tokens": (sum(e["reasoning_tokens"] for e in old_events if e.get("reasoning_tokens") is not None)
                                                        if any(e.get("reasoning_tokens") is not None for e in old_events) else None),
                          "reasoning_usage_missing_events": sum(e.get("reasoning_tokens") is None for e in old_events),
                          "length_events": sum(e.get("finish_reason") == "length" for e in old_events),
                          "full_untimed": sum(r["score_without_time_penalty"] == 5 for r in old_cases),
                          "trace_sha256": sha(p), "limitation": "four selected train cases, one pair, default always first; historical scorer/source"}
    a, b = thinking_plans
    assert a["source_sha256"] == b["source_sha256"] and a["case_ids"] == b["case_ids"]
    assert {k:v for k,v in a["feature_flags"].items() if k != "RUNBOOK_THINKING_MODE"} == {
        k:v for k,v in b["feature_flags"].items() if k != "RUNBOOK_THINKING_MODE"}
    prompt_trace = root / "experiments/train150_v3_prompt_probe_live.jsonl"
    prompt_rows = records(prompt_trace)
    assert set(prompt_rows[0]["case_ids"]) <= case_ids
    prompt_history = {}
    for variant in ["original", "candidate"]:
        e = [r for r in prompt_rows if r["type"] == "request" and r["variant"] == variant]
        arms = [r for r in prompt_rows if r["type"] == "arm" and r["variant"] == variant]
        scores = [r["untimed_score"]["score"] if isinstance(r["untimed_score"], dict) else r["untimed_score"] for r in arms]
        prompt_history[variant] = {"requests": len(e), "seconds": describe([r["seconds"] for r in e]),
                                   "input_tokens": sum(r["prompt_tokens"] for r in e),
                                   "output_tokens": sum(r["completion_tokens"] for r in e),
                                   "untimed_quality_sum": sum(scores), "full_quality": sum(s == 5 for s in scores),
                                   "length_events": sum(r["finish_reason"] == "length" for r in e)}
    hypothetical = {}
    for label, seconds in [("all_api_20pct_faster", llm_total), ("refine_20pct_faster", stages["refine"]["seconds"]["sum"]),
                           ("eliminate_all_local_execute", execute_total)]:
        saved = seconds if label.startswith("eliminate") else seconds * .2
        hypothetical[label] = {"saved_seconds": saved, "end_to_end_reduction_fraction": saved/query_total,
                               "new_mean_query_seconds": (query_total-saved)/150,
                               "status": "arithmetic scenario, not measured and not a token-to-time prediction"}
    report = {"scope": "fixed_train150_v18_timing_profile", "new_model_requests": 0,
              "trace_sha256": sha(trace), "plan_sha256": sha(planpath),
              "source_archive_sha256": source_archive_sha256,
              "source_archive_matches_plan": True if source_archive_sha256 else None,
              "source_verification": "local archive" if source_archive_sha256 else "published source files",
              "request_diagnostics_match": True,
              "model": plan["model"], "thinking_mode": plan["thinking_mode"], "scoring_revision": plan["scoring_revision"],
              "summary": summary, "query_seconds": describe([r["elapsed"] for r in cases]), "query_total_seconds": query_total,
              "wall_seconds": summary["wall_seconds"], "wall_outside_query_seconds": summary["wall_seconds"]-query_total,
              "llm_total_seconds": llm_total, "llm_fraction_of_query_sum": llm_total/query_total,
              "components": {name: {"total_seconds": value, "per_case_seconds": value/150,
                                     "fraction_of_query_sum": value/query_total} for name, value in components.items()},
              "stages": stages, "refine_status": refine_status,
              "calls_per_case": dict(Counter(r["request_count"] for r in per_case)),
              "top_query_cases": sorted(per_case, key=lambda r:r["query_seconds"], reverse=True)[:10],
              "top_execute_cases": sorted(per_case, key=lambda r:r["execute_seconds"], reverse=True)[:10],
              "historical_thinking_comparison": thinking, "historical_prompt_comparison": prompt_history,
              "historical_prompt_trace_sha256": sha(prompt_trace), "hypothetical_only": hypothetical,
              "limitations": ["one fixed-order pass; no independent-repeat confidence intervals",
                              "API timer includes SDK/network/response and inner source-freeze wrapper; server compute/TTFT not instrumented",
                              "request is nested in match; match+execute are inside query; do not add nested totals",
                              "query rounded to 0.01 seconds, other timers to 0.0001; signed tiny residual is rounding, not precise CPU time",
                              "prompt-length associations are not causal; fill only n=14; select output fixed at one token",
                              "historical comparisons use old source/scorer, not v18 full-run improvements"],
              "holdout_read_or_evaluated": False}
    out.mkdir(parents=True, exist_ok=True)
    destination = out / "profile.json"
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    with (out/"cases.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_case[0]))
        writer.writeheader(); writer.writerows(per_case)
    print(json.dumps({"query_total": query_total, "llm_total": llm_total, "llm_share": llm_total/query_total,
                      "stage_sums": {k:v["seconds"]["sum"] for k,v in stages.items()}, "new_model_requests": 0}))


if __name__ == "__main__":
    main()
