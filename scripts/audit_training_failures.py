"""完整列出150训练题中的未满分项，复核参考执行和模板覆盖；不打开留出集。"""

import argparse
from collections import Counter
import copy
import json
import logging
import os
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
import requests

from training_data import load_training, sha, SPLIT

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE/"implementation"))
import runbook_matcher as matcher
import runbook_executor as executor
from runbook_items import RUNBOOK_ITEMS
from evaluator import evaluate_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖训练审计")
    manifest, train, _ = load_training()
    live = HERE/"experiments/train150_v1_live.jsonl"
    rows = [json.loads(line) for line in live.read_text().splitlines()]
    assert rows[0]["scope"] == "train_only" and rows[-1]["status"] == "complete"
    history = [row for row in rows if row["type"] == "case"]
    assert [row["case_id"] for row in history] == [case["case_id"] for case in train]
    items = {item["id"]: item for item in RUNBOOK_ITEMS}
    native, wire, blocked = requests.Session.request, [], []

    class Forbidden(BaseException):
        pass

    def request(session, method, url, *values, **options):
        target = urlsplit(str(url))
        if target.hostname != "127.0.0.1" or target.port != 8080 or method.upper() != "GET":
            blocked.append("nonlocal_request")
            raise Forbidden("仅允许本地数据GET")
        options["timeout"] = (2, 10)
        response = native(session, method, url, *values, **options)
        wire.append({"path": target.path, "status": response.status_code})
        return response

    def resources(calls):
        calls = calls if isinstance(calls, list) else [calls]
        return [call["url"].split("?")[0].rsplit("/", 1)[-1] for call in calls if call]

    logging.disable(logging.CRITICAL)
    issues = []
    with patch.dict(os.environ, {"RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": "1"}), \
            patch.object(requests.Session, "request", request), patch.object(httpx.Client, "send", side_effect=Forbidden()), \
            patch.object(matcher, "llm_ask", side_effect=Forbidden()):
        matcher._warm_schema_cache()
        for case, row in zip(train, history):
            if row["score_without_time_penalty"] == 5:
                continue
            matching = row["diagnostics"]["matching"]
            template = items.get(matching.get("selected_template"), {})
            start = len(wire)
            result = executor.execute({"api_call": case["api_call"], "sql": case["sql"]})
            reference_score = evaluate_case(case, {"matched_runbook": "reference_audit", "api_call": case["api_call"],
                                                   "sql": case["sql"], "result": result["result"], "error": result["error"]}, 0)
            reference_coverage = matcher._resource_coverage(case["question"], {"api_call": case["api_call"], "sql": case["sql"]})
            calls = template.get("api_call", [])
            calls = calls if isinstance(calls, list) else [calls]
            bindings = [{"resource": call["url"].split("?")[0].rsplit("/", 1)[-1],
                         "fields": [constraint.get("simple", {}).get("name") for constraint in call.get("condition", {}).get("constraint", [])]}
                        for call in calls]
            result_shape = result.get("result") or {}
            issues.append({"case_id": case["case_id"], "question": case["question"], "quality": row["score_without_time_penalty"],
                           "selected_template": matching.get("selected_template"), "reason": matching.get("reason"),
                           "template_missing_resources": (matching.get("resource_coverage") or {}).get("unsupported", []),
                           "template_placeholders": matcher._get_placeholders(template), "template_bindings": bindings,
                           "template_sql": template.get("sql"), "reference_sql": case["sql"],
                           "reference_api_resources": resources(case["api_call"]), "reference_missing_resources": reference_coverage["unsupported"],
                           "reference_native_score": reference_score["score"], "reference_native_reason": reference_score["reason"],
                           "reference_native_columns": result_shape.get("columns", []),
                           "reference_native_rows": result_shape.get("row_count"),
                           "reference_error": result.get("error"), "reference_http_failures": [entry for entry in wire[start:] if entry["status"] != 200],
                           "api_actual": row.get("api_call"), "sql_actual": row.get("sql")})
    assert len(issues) == 37 and not blocked and not matcher.get_llm_events()
    summary = {"issues": len(issues), "refusals": sum(issue["quality"] == 0 for issue in issues),
               "wrong": sum(issue["quality"] < 0 for issue in issues), "partial": sum(0 < issue["quality"] < 5 for issue in issues),
               "reference_reproduced_full": sum(issue["reference_native_score"] == 5 for issue in issues),
               "reference_not_full": sum(issue["reference_native_score"] != 5 for issue in issues),
               "reference_sql_omits_mentioned_resource": sum(bool(issue["reference_missing_resources"]) for issue in issues),
               "refusal_reasons": dict(Counter(issue["reason"] for issue in issues if issue["quality"] == 0))}
    report = {"scope": "train_only", "split_id": manifest["split_id"], "summary": summary, "issues": issues,
              "real_model_requests": 0, "holdout_accessed": False, "blocked_external_attempts": blocked,
              "resource_attribute_roles": True,
              "http_failures": [entry for entry in wire if entry["status"] != 200],
              "sources": {str(path.relative_to(HERE)): sha(path) for path in [Path(__file__), live, SPLIT/"train.json",
                          HERE/"implementation/runbook_items.py", HERE/"implementation/runbook_matcher.py", HERE/"implementation/runbook_executor.py", HERE/"implementation/evaluator.py"]},
              "limitation": "Reference scorer agreement is not proof of complete business semantics; coverage detector is a heuristic and requires review. No runtime answer routing from this audit."}
    with args.output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
