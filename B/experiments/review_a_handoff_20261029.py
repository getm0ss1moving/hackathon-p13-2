"""免费复核 A 交接的跨步依赖；仅输出结构、计数和哈希，不输出资产值。

用模板原有 default_params 作为固定原生探针输入，不模拟模型能力或 B 填参结果。
从 B 目录运行；需启动原本地服务，不调用模型、不执行或改写模板 SQL。
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import requests

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
from runbook_executor import _execute_single_api_call
from runbook_items import RUNBOOK_ITEMS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖已有证据，请使用新文件名")
    blocked = []
    api_failures = []
    failed_ci = set()
    native_request = requests.Session.request
    native_send = httpx.Client.send

    def check_local(url):
        parsed = urlparse(str(url))
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 8080:
            blocked.append(parsed.hostname)
            raise AssertionError("复核仅允许本地 8080 数据 API")

    def request(session, method, url, *args, **kwargs):
        check_local(url)
        response = native_request(session, method, url, *args, **kwargs)
        endpoint, ci = urlparse(str(url)).path.rsplit("/", 2)[-2:]
        failure = None
        if response.status_code != 200:
            failure = f"http_{response.status_code}"
        else:
            try:
                body = response.json()
                expected_field = "columns" if endpoint == "schema" else "objList"
                if not isinstance(body, dict) or not isinstance(body.get(expected_field), list):
                    failure = "invalid_records_envelope"
            except ValueError:
                failure = "invalid_json"
        if failure:
            if endpoint != "schema":
                failed_ci.add(ci)
            api_failures.append({"endpoint": endpoint, "ci": ci, "failure": failure,
                                 "url_length_bytes": len(str(url).encode("utf-8"))})
        return response

    def send(client, request, *args, **kwargs):
        check_local(request.url)
        return native_send(client, request, *args, **kwargs)

    rows = []
    with patch.object(requests.Session, "request", request), patch.object(httpx.Client, "send", send), \
         patch.object(matcher, "llm_ask", side_effect=AssertionError("禁止模型调用")) as model:
        matcher._warm_schema_cache()
        for original in RUNBOOK_ITEMS:
            if "from step" not in json.dumps(original.get("api_call", {})).lower():
                continue
            item = copy.deepcopy(original)
            coverage = matcher._resource_coverage(original["examples"][0], original)
            filled = matcher._fill_params(item, copy.deepcopy(original.get("default_params", {})))
            entry = {"template_id": item["id"], "fixture_defaults_filled": filled,
                     "B_resource_gate_unsupported": coverage["unsupported"],
                     "B_current_lookup_guard_reachable": not coverage["unsupported"] and bool(coverage["covered_by_lookup"]),
                     "dependencies": [], "native_api_failed_cis": []}
            rows.append(entry)
            if not filled:
                continue
            previous = None
            previous_ci = None
            for step_index, call in enumerate(item["api_call"], 1):
                ci = call["url"].split("?")[0].rsplit("/", 1)[-1]
                for constraint in call.get("condition", {}).get("constraint", []):
                    simple = constraint.get("simple", {})
                    value = simple.get("value")
                    if not isinstance(value, str) or "from step" not in value.lower():
                        continue
                    match = re.fullmatch(r"\{\{\s*(\w+)\s+from step\s+(\d+)\s*\}\}", value, re.I)
                    if not match:
                        raise ValueError("存在未支持的依赖写法，停止而不推断")
                    field, declared = match[1], int(match[2])
                    valid_rows = sum(bool(record.get(field)) for record in previous or [])
                    entry["dependencies"].append({
                        "target_step": step_index, "target_ci": ci, "target_field": simple.get("name"),
                        "declared_source_step": declared, "executor_source_step": step_index - 1,
                        "previous_ci": previous_ci, "source_field": field,
                        "previous_api_read_valid": previous_ci not in failed_ci,
                        "source_field_in_previous_schema": field in matcher._schema_columns.get(previous_ci, []),
                        "previous_rows": len(previous or []), "previous_rows_with_truthy_field": valid_rows,
                        "native_executor_drops_dependency_condition": valid_rows == 0,
                        "declared_step_matches_executor": declared == step_index - 1})
                previous, _ = _execute_single_api_call(call, previous)
                previous_ci = ci
                if ci in failed_ci:
                    entry["native_api_failed_cis"].append(ci)
        model.assert_not_called()
    dependencies = [dependency for row in rows for dependency in row["dependencies"]]
    dropped = [(row["template_id"], dep) for row in rows for dep in row["dependencies"]
               if dep["native_executor_drops_dependency_condition"] and dep["previous_api_read_valid"]]
    result = {
        "scope": "Fixed native API path diagnostic using existing template defaults; not model or answer evaluation.",
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
        "script_sha256": sha(Path(__file__)),
        "source_sha256": {name: sha(HERE / "implementation" / name) for name in
                          ("runbook_items.py", "runbook_retriever.py", "runbook_matcher.py", "runbook_executor.py")},
        "a_handoff_sha256": sha(HERE.parent / "A_HANDOFF.md"),
        "dataset_sha256": sha(HERE / "CMDB用例集-白盒200.json"),
        "A_B_components_identical": {name: sha(HERE / "implementation" / name) == sha(HERE.parent / "implementation" / name)
                                     for name in ("runbook_items.py", "runbook_retriever.py")},
        "summary": {"templates": len(rows), "dependencies": len(dependencies),
                    "fixture_fill_failed": sum(not row["fixture_defaults_filled"] for row in rows),
                    "native_dependency_conditions_dropped": len(dropped),
                    "empty_previous_result": sum(dep["previous_rows"] == 0 for _, dep in dropped),
                    "nonempty_previous_without_dependency_value": sum(dep["previous_rows"] > 0 for _, dep in dropped),
                    "drop_templates": [template for template, _ in dropped],
                    "declared_step_mismatches": sum(not dep["declared_step_matches_executor"] for dep in dependencies),
                    "native_api_failures": api_failures,
                    "templates_with_api_failure": [row["template_id"] for row in rows if row["native_api_failed_cis"]],
                    "model_requests": 0, "blocked_external_network_attempts": blocked},
        "templates": rows,
        "limitations": ["Existing defaults are fixed diagnostic inputs, not accepted runtime grounding.",
                        "B resource-gate reachability excludes later selection and parameter rejection.",
                        "API errors are retained as failures and cannot establish valid empty results or full-path success.",
                        "No SQL answer, score, performance, generalization or official-model claim.",
                        "No executor, scorer, template or production source modified."]}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
