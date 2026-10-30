"""从完整单轮 JSONL 重新计算描述统计与失败清单；不调用模型，不更改查询代码。"""

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

HERE = Path(__file__).resolve().parents[1]


def percentile(values, q):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * q) - 1)] if ordered else None


def category(case):
    reason = case["reason"]
    if reason.startswith("答案正确"):
        return "答案正确但超时" if case["score"] < 5 else "答案正确且未扣时延分"
    if reason.startswith("部分正确"):
        return "答案部分正确"
    if reason.startswith("答案错误"):
        return "答案错误，原因待复核"
    if reason.startswith("错误:"):
        return "执行错误"
    matching = (case.get("diagnostics") or {}).get("matching", {})
    gate = matching.get("reason", "unknown")
    names = {"resource_mismatch": "资源门禁拒答", "missing_parameters": "必要参数缺失拒答",
             "missing_api_filter": "显式API条件缺失拒答", "selector_refused": "模型选择器拒答",
             "invalid_selection": "选择编号格式错误", "no_candidates": "未召回候选"}
    if gate.startswith("invalid_model_output"):
        return "模型输出无效或截断拒答"
    return names.get(gate, "其他拒答或异常")


def sql_shape(sql):
    if re.search(r"\bJOIN\b", sql, re.I):
        return "多表JOIN"
    if re.search(r"\bGROUP\s+BY\b", sql, re.I):
        return "分组"
    if re.search(r"\b(COUNT|SUM|AVG|MAX|MIN)\s*\(", sql, re.I):
        return "聚合"
    return "明细"


def analyze(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    plan = next(row for row in rows if row["type"] == "plan")
    summary = rows[-1]
    cases = [row for row in rows if row["type"] == "case"]
    requests = [row for row in rows if row["type"] == "request"]
    if summary.get("type") != "summary" or summary.get("status") != "complete":
        raise ValueError("输入不是完整测试；保留中断记录，不生成全量结论")
    ids = [row["case_id"] for row in cases]
    if len(cases) != plan["case_count"] or len(ids) != len(set(ids)):
        raise ValueError("记录范围不完整或存在重复题目")
    reference_file = HERE / "CMDB用例集-白盒200.json"
    if hashlib.sha256(reference_file.read_bytes()).hexdigest() != plan["dataset_sha256"]:
        raise ValueError("参考数据与运行记录的哈希不一致")
    reference = json.loads(reference_file.read_text(encoding="utf-8"))["cases"][:len(cases)]
    if ids != [row["case_id"] for row in reference]:
        raise ValueError("实际顺序与固定白盒范围不一致")
    if len(requests) != summary["generation_requests"]:
        raise ValueError("模型请求记录不完整")

    causes = collections.Counter(category(case) for case in cases)
    elapsed = [case["elapsed"] for case in cases]
    groups = collections.defaultdict(list)
    for case, standard in zip(cases, reference):
        groups[sql_shape(standard["sql"])].append(case)
    grouped = {}
    for shape, selected in groups.items():
        grouped[shape] = {"cases": len(selected), "score": round(sum(c["score"] for c in selected), 1),
                          "correct": sum(c["reason"].startswith("答案正确") for c in selected),
                          "median_seconds": statistics.median(c["elapsed"] for c in selected)}
    stages = {}
    for stage in {r["stage"] for r in requests}:
        selected = [r for r in requests if r["stage"] == stage]
        stages[stage] = {"requests": len(selected), "seconds": round(sum(r["seconds"] for r in selected), 3),
                         "median_seconds": statistics.median(r["seconds"] for r in selected),
                         "failed": sum(r["status"] != "ok" for r in selected)}
    changed = [case for case in cases if (case.get("diagnostics") or {}).get("matching", {}).get("sql_before_refine")
               != (case.get("diagnostics") or {}).get("matching", {}).get("sql_after_refine")]
    changed = [case for case in changed if case.get("sql")]
    analysis = {
        "source": str(path), "plan": plan, "summary": summary, "case_count": len(cases),
        "score": round(sum(case["score"] for case in cases), 1),
        "untimed_score": round(sum(case["score_without_time_penalty"] for case in cases), 1),
        "correct_answers": sum(case["reason"].startswith("答案正确") for case in cases),
        "failure_categories": dict(causes), "reference_sql_groups": grouped, "stages": stages,
        "latency": {"mean": statistics.mean(elapsed), "p50": percentile(elapsed, .5),
                    "p95": percentile(elapsed, .95), "max": max(elapsed),
                    "precision": "original evaluator rounds logged case latency to 0.01 seconds"},
        "time_penalty": round(sum(c["score_without_time_penalty"] - c["score"] for c in cases), 1),
        "sql_changed_cases": len(changed),
        "changed_sql_nonperfect_cases": [c["case_id"] for c in changed if c["score_without_time_penalty"] < 5],
        "failures": [{"case_id": c["case_id"], "category": category(c), "score": c["score"],
                      "reason": c["reason"], "elapsed": c["elapsed"],
                      "matching": (c.get("diagnostics") or {}).get("matching", {})}
                     for c in cases if not c["reason"].startswith("答案正确")],
        "claims": {"measurement": "DESCRIPTIVE_ONLY", "effect_direction": "NOT_ASSESSABLE",
                   "mechanism": "ASSOCIATED", "coverage": "LOCAL"},
    }
    if analysis["score"] != summary["total_score"] or analysis["untimed_score"] != summary["score_without_time_penalty"]:
        raise ValueError("汇总分数与逐题重新计算不一致")
    return analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(args.input)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({key: result[key] for key in ["case_count", "score", "untimed_score", "correct_answers", "failure_categories", "latency", "time_penalty", "sql_changed_cases"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
