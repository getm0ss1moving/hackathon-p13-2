"""给A的字段合同证据：仅训练中缺显式筛选的7项，不推断名称到ID关系。"""

import argparse
import json
import logging
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
import requests

from training_data import load_training, sha

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE/"implementation"))
import runbook_matcher as matcher
import runbook_executor as executor
from runbook_items import RUNBOOK_ITEMS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖字段证据")
    manifest, train, _ = load_training()
    rows = [json.loads(line) for line in (HERE/"experiments/train150_v1_live.jsonl").read_text().splitlines()]
    cases = [row for row in rows if row["type"] == "case"]
    assert rows[0]["scope"] == "train_only" and rows[-1]["status"] == "complete"
    assert [row["case_id"] for row in cases] == [row["case_id"] for row in train]
    items = {item["id"]: item for item in RUNBOOK_ITEMS}
    native, wire, blocked, evidence = requests.Session.request, [], [], []

    class Forbidden(BaseException):
        pass

    def request(session, method, url, *values, **options):
        parsed = urlsplit(str(url))
        if parsed.hostname != "127.0.0.1" or parsed.port != 8080 or method.upper() != "GET":
            blocked.append("nonlocal_request")
            raise Forbidden("仅允许本地数据GET")
        response = native(session, method, url, *values, **options)
        wire.append({"path": parsed.path, "status": response.status_code})
        return response

    logging.disable(logging.CRITICAL)
    with patch.object(requests.Session, "request", request), patch.object(httpx.Client, "send", side_effect=Forbidden()), \
            patch.object(matcher, "llm_ask", side_effect=Forbidden()):
        matcher._warm_schema_cache()
        for case, row in zip(train, cases):
            details = row["diagnostics"]["matching"]
            if details.get("reason") != "missing_api_filter":
                continue
            template = items[details["selected_template"]]
            requested = {}
            matcher._auto_fill_params(case["question"], requested, ["logicalRegionName", "tenantName", "azoneName", "vdcName"], template)
            calls = template["api_call"] if isinstance(template["api_call"], list) else [template["api_call"]]
            resources = []
            for call in calls:
                ci = call["url"].split("?")[0].rsplit("/", 1)[-1]
                records, _ = executor._execute_single_api_call({"method": "GET", "url": "/rest/hackthon/db/instances/"+ci})
                columns = matcher._schema_columns.get(ci, [])
                fields = {}
                for field, value in requested.items():
                    fields[field] = {"requested_value": value, "field_exists": field in columns,
                                     "exact_value_records": sum(record.get(field) == value for record in records) if field in columns else None}
                resources.append({"ci": ci, "source_rows": len(records), "requested_fields": fields,
                                  "related_field_names": [field for field in columns if any(word in field.casefold() for word in ["tenant", "vdc", "region", "azone", "zone"])],
                                  "template_filter_fields": [entry.get("simple", {}).get("name") for entry in call.get("condition", {}).get("constraint", [])]})
            evidence.append({"case_id": case["case_id"], "template": template["id"], "question": case["question"], "resources": resources})
    assert len(evidence) == 7 and not blocked and not matcher.get_llm_events()
    assert not [entry for entry in wire if entry["status"] != 200 and not entry["path"].endswith("/VOLUME_TYPE")]
    report = {"scope": "train_only", "split_id": manifest["split_id"], "cases": len(evidence), "evidence": evidence,
              "real_model_requests": 0, "holdout_accessed": False,
              "http_failures": [entry for entry in wire if entry["status"] != 200],
              "sources": {str(path.relative_to(HERE)): sha(path) for path in [Path(__file__), HERE/"scripts/training_data.py", HERE/"implementation/runbook_items.py", HERE/"implementation/runbook_matcher.py"]},
              "limitation": "Field presence and literal matches do not prove tenant/VDC equivalence or any name-to-ID relationship; runtime remains unchanged."}
    with args.output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"cases": len(evidence), "real_model_requests": 0,
                      "missing_fields": [{"case_id": row["case_id"], "ci": resource["ci"], "field": field}
                                         for row in evidence for resource in row["resources"] for field, value in resource["requested_fields"].items() if not value["field_exists"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
