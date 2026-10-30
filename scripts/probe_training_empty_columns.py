"""训练日志缺列案例的原API/SQL原生诊断；不调用模型，不改官方执行器。"""
import argparse
import copy
import json
from pathlib import Path
import sys

from training_data import load_training

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))
import runbook_matcher as matcher
import runbook_system as system
from evaluator import evaluate_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不能覆盖原生诊断")
    _, train, _ = load_training()
    by_id = {case["case_id"]: case for case in train}
    rows = [json.loads(line) for line in (args.run_dir / "live.jsonl").read_text().splitlines()]
    assert rows[0]["scope"] == "train_only" and rows[-1]["status"] == "complete"
    cases = [row for row in rows if row.get("type") == "case"]
    assert [row["case_id"] for row in cases] == [row["case_id"] for row in train]
    system.RunbookQuerySystem()  # 只初始化原生字段字典，无模型请求。
    results = []
    for row in cases:
        detail = row["diagnostics"]
        if detail.get("rejection", {}).get("reason") != "unverified_result_schema":
            continue
        api = detail.get("parameters", {}).get("effective_api")
        assert api is not None and row["question"] == by_id[row["case_id"]]["question"]
        item = {"api_call": copy.deepcopy(api), "sql": detail["execution"]["input_sql"]}
        execution = {}
        record = {"case_id": row["case_id"], "original_quality": row["score_without_time_penalty"],
                  "original_API_and_SQL_unchanged": True, "item": item}
        try:
            result = system._execute_bounded_api(item, execution)
            output = {"matched_runbook": "same_saved_plan_native_probe", "api_call": item["api_call"],
                      "sql": item["sql"], "result": result["result"], "error": result["error"]}
            record.update(status="executed", output=output, untimed=evaluate_case(by_id[row["case_id"]], output, 0))
        except (RuntimeError, system._APIPlanRefusal, ValueError) as exc:
            record.update(status="refused", error_type=type(exc).__name__, reason=str(exc))
        record["execution"] = execution
        results.append(record)
    report = {"scope": "fixed_training_saved_plan_native_probe", "model_requests": 0,
              "official_files_modified": False, "cases": results,
              "not_a_fresh_model_run_or_full150_score": True}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([{"case_id": row["case_id"], "status": row["status"],
                       "quality": row.get("untimed", {}).get("score"), "reason": row.get("reason"),
                       "root_counts": [step.get("rows") for step in row["execution"].get("steps", [])]}
                      for row in results], ensure_ascii=False))


if __name__ == "__main__":
    main()
