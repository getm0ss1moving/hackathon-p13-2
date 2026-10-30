"""免费检查跨步候选：19 条原生模板固定输入，以及历史全量已作答路径。

不运行模型，不把旧选择和 API 参数下的路径检查称为当前版本全量成绩。
"""

import argparse
import copy
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import requests

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
from evaluator import evaluate_case
from runbook_items import RUNBOOK_ITEMS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖旧结果，请使用新文件名")
    source = HERE / "experiments/whitebox_20261029_full.jsonl"
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    cases_file = HERE / "CMDB用例集-白盒200.json"
    cases = {case["case_id"]: case for case in json.loads(cases_file.read_text())["cases"]}
    history = [row for row in rows if row["type"] == "case"]
    if len(history) != 200 or rows[-1].get("status") != "complete" or sha(cases_file) != rows[0]["dataset_sha256"]:
        parser.error("历史全量或数据版本不符合冻结输入")
    manifest = json.loads((HERE / "baseline_manifest.json").read_text())
    if any(sha(HERE / path) != expected for path, expected in manifest["readonly_files"].items()):
        parser.error("只读快照发生变化")
    native_request = requests.Session.request
    native_send = httpx.Client.send
    blocked = []
    http_failures = []

    def local(url):
        parsed = urlparse(str(url))
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.port != 8080:
            blocked.append(parsed.hostname)
            raise AssertionError("仅允许本地数据 API")

    def request(session, method, url, *args, **kwargs):
        local(url)
        response = native_request(session, method, url, *args, **kwargs)
        if response.status_code != 200:
            http_failures.append({"ci": urlparse(url).path.rsplit("/", 1)[-1], "status": response.status_code})
        return response

    def send(client, request, *args, **kwargs):
        local(request.url)
        return native_send(client, request, *args, **kwargs)

    native_rows = []
    frozen_rows = []
    old_logging = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with patch.object(requests.Session, "request", request), patch.object(httpx.Client, "send", send), \
             patch.object(matcher, "llm_ask", side_effect=AssertionError("禁止模型调用")) as model:
            for original in RUNBOOK_ITEMS:
                if "from step" not in json.dumps(original.get("api_call", {})).lower():
                    continue
                item = copy.deepcopy(original)
                if not matcher._fill_params(item, copy.deepcopy(item.get("default_params", {}))):
                    raise ValueError("固定模板输入无法填充，停止而不替换测试范围")
                native_rows.append({"template_id": item["id"], "check": matcher._validate_api_dependencies(item)})
            for row in history:
                if not row.get("matched_runbook"):
                    continue
                check = matcher._validate_api_dependencies({"api_call": row["api_call"]})
                entry = {"case_id": row["case_id"],
                         "historical_selected_template": row["diagnostics"]["matching"]["selected_template"],
                         "historical_untimed_score": row["score_without_time_penalty"], "check": check}
                if check and not check["valid"]:
                    refused = {"matched_runbook": None, "result": None, "error": "未命中任何查询手册"}
                    entry["candidate_refusal_untimed_score"] = evaluate_case(cases[row["case_id"]], refused, 0)["score"]
                frozen_rows.append(entry)
            model.assert_not_called()
    finally:
        logging.disable(old_logging)
    invalidated = [row for row in frozen_rows if row["check"] and not row["check"]["valid"]]
    summary = {"native_templates": len(native_rows),
               "native_validated": sum(bool(row["check"] and row["check"]["valid"]) for row in native_rows),
               "native_refused_templates": [row["template_id"] for row in native_rows if row["check"] and not row["check"]["valid"]],
               "historical_cases": len(history), "frozen_matched_paths": len(frozen_rows),
               "frozen_no_dependencies": sum(row["check"] is None for row in frozen_rows),
               "frozen_validated": sum(bool(row["check"] and row["check"]["valid"]) for row in frozen_rows),
               "frozen_refused": len(invalidated),
               "frozen_refusal_untimed_delta": sum(row["candidate_refusal_untimed_score"] - row["historical_untimed_score"] for row in invalidated),
               "http_failures": http_failures, "model_requests": 0, "blocked_external_attempts": blocked}
    result = {"code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
              "source_sha256": {name: sha(HERE / "implementation" / name) for name in
                                ("runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "runbook_executor.py", "evaluator.py")},
              "script_sha256": sha(Path(__file__)), "baseline_sha256": sha(source), "dataset_sha256": sha(cases_file),
              "candidate": "RUNBOOK_VALIDATE_API_DEPENDENCIES=1; default is off; helper invoked directly for this diagnostic",
              "cache": "fresh process; original executor cache shared across these fixed probes; last dependent target not fetched",
              "scope": "Fixed API input audit; no fresh selection/fill/refinement or end-to-end scoring; no production change to 199 templates.",
              "summary": summary, "native_template_checks": native_rows, "frozen_matched_path_checks": frozen_rows,
              "limitations": ["Existing template defaults are fixture inputs, not runtime parameter grounding.",
                              "Nonempty source fields do not establish join semantics, target read success or complete answers.",
                              "41 historical refusals are outside the frozen matched-path audit, not newly answered.",
                              "A refusal can lose points on empty-reference cases; no net official score improvement established.",
                              "No model, latency or blackbox claim; swallowed executor HTTP/pagination errors remain outside this guard."]}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not blocked and not http_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
