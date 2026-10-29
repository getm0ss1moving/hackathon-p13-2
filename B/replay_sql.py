"""固定已返回的模型输出，离线比较精调 SQL 与所选模板原 SQL；模型请求为零。"""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
from runbook_executor import execute
from evaluator import evaluate_case



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    if rows[-1].get("status") != "complete":
        parser.error("只接受已完整完成的测试记录")
    cases = {c["case_id"]: c for c in json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"]}
    changed = [row for row in rows if row["type"] == "case" and row.get("sql")
               and (row.get("diagnostics") or {}).get("matching", {}).get("sql_before_refine") != row["sql"]]
    if matcher.get_llm_events():
        parser.error("请使用新进程，避免混入模型请求")
    matcher._warm_schema_cache()
    results = []
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps({"type": "plan", "source": str(args.input), "cases": len(changed),
                                 "model_requests": 0, "protocol": "fixed recorded API/SQL; original executor/evaluator; untimed scores only"}) + "\n")
        for i, row in enumerate(changed):
            case = cases[row["case_id"]]
            original = row["diagnostics"]["matching"]["sql_before_refine"]
            def score(sql):
                result = execute({"api_call": row["api_call"], "sql": sql})
                return evaluate_case(case, {"matched_runbook": row["matched_runbook"], "api_call": row["api_call"],
                                            "sql": sql, "result": result["result"], "error": result["error"]}, 0)
            actual = score(row["sql"])
            before = score(original)
            policy = matcher._projection_contract(original, row["sql"])
            consistent = actual["score"] == row["score_without_time_penalty"]
            candidate = before["score"] if policy["reject"] else actual["score"]
            result = {"type": "case", "case_id": row["case_id"], "baseline_recorded": row["score_without_time_penalty"],
                      "baseline_replayed": actual["score"], "original_sql_score": before["score"],
                      "candidate_score": candidate, "delta": round(candidate - actual["score"], 1),
                      "replay_consistent": consistent, "policy": policy,
                      "original_sql": original, "refined_sql": row["sql"]}
            results.append(result)
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            print(f"[{i+1}/{len(changed)}] {row['case_id']}: 当前 {actual['score']} / 原SQL {before['score']} / 契约候选 {candidate}", flush=True)
        consistent = [row for row in results if row["replay_consistent"]]
        summary = {"type": "summary", "cases": len(results), "replay_consistent": len(consistent),
                   "guarded_cases": sum(row["policy"]["reject"] for row in consistent),
                   "improved_cases": sum(row["delta"] > 0 for row in consistent),
                   "regressed_cases": sum(row["delta"] < 0 for row in consistent),
                   "untimed_delta": round(sum(row["delta"] for row in consistent), 1), "model_requests": len(matcher.get_llm_events()),
                   "limitation": "conditional on frozen model outputs; not a fresh-model or latency comparison"}
        output.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
