"""Closed NEXT_N28 VDC count extension; pure construction and local validation.

The original five profiles remain owned by their original materializer. No natural
language, dataset, model, network, B matcher or official executor is used here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

FAMILY_ID = "NEXT_N28"
PROFILE = "vdc_vm_volume_gaussdb_instance_counts"
RESOURCES = ("VM_NOVA", "VOLUME", "GAUSSDB_INSTANCE")
TABLES = {ci: "CLOUD_" + ci for ci in RESOURCES}
COLUMNS = ("id", "logicalRegionName", "vdcName")
OUTPUT_COLUMNS = ("vdc_name", "ecs_count", "volume_count", "gaussdb_instance_count")
PAGE_SIZE = 1000
PROJECTION_CONTRACT = "n28-vdc-independent-counts-v1"


class Unsupported(ValueError):
    pass


class LengthBlocked(Unsupported):
    def __init__(self, measured_bytes):
        self.details = {"status": "blocked_transport_budget", "measured_bytes": measured_bytes,
                        "limit_bytes": 4096, "boundary": "compact UTF-8 api_call+sql",
                        "official_boundary_confirmed": False,
                        "handling": "Do not truncate; B needs a separately validated encoding and final envelope."}
        super().__init__(json.dumps(self.details, sort_keys=True))


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def _surrogate(value):
    return isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value)


def _params(params):
    expected = {"profile", "resource_set", "group", "layout", "metric", "filters", "required_filters"}
    if not isinstance(params, dict) or set(params) != expected:
        raise Unsupported("closed parameter keys required; additional obligations need another profile")
    if (params["profile"] != PROFILE or params["resource_set"] != list(RESOURCES)
            or params["group"] != "vdcName" or params["layout"] != "grouped_counts_wide"
            or params["metric"] != "count_rows"):
        raise Unsupported("unreviewed profile/resource/group/layout/metric")
    filters = params["filters"]
    if (not isinstance(filters, dict) or set(filters) != {"logicalRegionName"}
            or params["required_filters"] != ["logicalRegionName"]):
        raise Unsupported("exactly one explicit equal logicalRegionName required")
    region = filters["logicalRegionName"]
    if (not isinstance(region, str) or not region.strip()
            or _surrogate(region)
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in region)
            or "{{" in region or "}}" in region):
        raise Unsupported("literal nonblank UTF-8 region without controls/surrogates required; no default region")
    return json.loads(_encode(params))


def prepare(params):
    """Fresh ordinary API/SQL plan for exactly one additional closed N28 profile."""
    params = _params(params)
    region = params["filters"]["logicalRegionName"]
    literal = "'" + region.replace("'", "''") + "'"
    aggregates = [f"a{i} AS (SELECT vdcName d,COUNT(*) n FROM {TABLES[ci]} "
                  f"WHERE logicalRegionName={literal} GROUP BY vdcName)"
                  for i, ci in enumerate(RESOURCES)]
    domain = "d AS (" + " UNION ".join(f"SELECT d FROM a{i}" for i in range(3)) + ")"
    selects = ["d.d AS vdc_name"] + [f"COALESCE(a{i}.n,0) AS {OUTPUT_COLUMNS[i+1]}" for i in range(3)]
    sql = ("WITH " + ",".join(aggregates + [domain]) + " SELECT " + ",".join(selects)
           + " FROM d" + "".join(f" LEFT JOIN a{i} ON d.d IS a{i}.d" for i in range(3))
           + " ORDER BY d.d IS NOT NULL,d.d")
    calls = [{"method": "GET", "url": f"/rest/hackthon/db/instances/{ci}?pageNo=1&pageSize={PAGE_SIZE}",
              "condition": {"constraint": [{"simple": {"name": "logicalRegionName", "operator": "equal", "value": region}}]},
              "autoPagination": True} for ci in RESOURCES]
    core = {"api_call": calls, "sql": sql}
    size = len(_encode(core))
    if size > 4096:
        raise LengthBlocked(size)
    return {"family_id": FAMILY_ID, "profile": PROFILE, "resources": list(RESOURCES), **core,
            "output_columns": list(OUTPUT_COLUMNS),
            "typed_input_schema": {TABLES[ci]: {key: "TEXT" for key in COLUMNS} for ci in RESOURCES},
            "output_schema": {"vdc_name": "TEXT NULL", "ecs_count": "INTEGER NOT NULL",
                              "volume_count": "INTEGER NOT NULL", "gaussdb_instance_count": "INTEGER NOT NULL"},
            "requires_preflight_projection": True, "projection_contract": PROJECTION_CONTRACT,
            "api_call_plus_sql_bytes": size, "final_B_envelope_and_formal_depth": "unmeasured_pending"}


def _collect(snapshot, ci, call):
    if not isinstance(snapshot, dict) or set(snapshot) != {"resource", "table", "request", "columns", "schema_source", "pages"}:
        raise Unsupported(ci + ": complete closed snapshot receipt required")
    if snapshot["resource"] != ci or snapshot["table"] != TABLES[ci] or snapshot["request"] != call:
        raise Unsupported(ci + ": resource/table/request binding mismatch")
    columns = snapshot["columns"]
    if (not isinstance(columns, list) or not all(isinstance(c, str) for c in columns)
            or len(set(columns)) != len(columns) or not set(COLUMNS) <= set(columns)):
        raise Unsupported(ci + ": required native schema columns absent")
    if not isinstance(snapshot["schema_source"], str) or not snapshot["schema_source"].strip():
        raise Unsupported(ci + ": schema provenance required even for true empty")
    pages = snapshot["pages"]
    if not isinstance(pages, list) or not pages:
        raise Unsupported(ci + ": missing successful page receipt")
    total = total_pages = None
    rows, seen = [], set()
    for index, page in enumerate(pages, 1):
        if (not isinstance(page, dict) or page.get("ok") is not True
                or page.get("success") is False or page.get("error") not in (None, "")):
            raise Unsupported(ci + ": failed or unproven request")
        number, size, count, declared_pages = (page.get(k) for k in ("pageNo", "pageSize", "totalNum", "totalPageNo"))
        if (type(number) is not int or number != index or type(size) is not int or size != PAGE_SIZE
                or type(count) is not int or count < 0 or type(declared_pages) is not int):
            raise Unsupported(ci + ": invalid/out-of-order pagination metadata")
        expected_pages = max(1, (count + size - 1) // size)
        if declared_pages != expected_pages and not (count == 0 and declared_pages == 0):
            raise Unsupported(ci + ": inconsistent totalPageNo")
        if total is None:
            total, total_pages = count, declared_pages
        if (count, declared_pages) != (total, total_pages):
            raise Unsupported(ci + ": unstable pagination totals")
        batch = page.get("objList")
        if not isinstance(batch, list) or len(batch) != min(size, max(0, total - len(rows))):
            raise Unsupported(ci + ": truncated/extra page rows")
        for row in batch:
            if not isinstance(row, dict) or any(key not in row for key in COLUMNS):
                raise Unsupported(ci + ": missing per-row schema column or placeholder row")
            identity = row["id"]
            if not isinstance(identity, str) or _blank(identity):
                raise Unsupported(ci + ": missing/NULL/blank/nonstring object identity")
            if _surrogate(identity) or _surrogate(row["vdcName"]):
                raise Unsupported(ci + ": invalid Unicode surrogate in identity/group value")
            if identity in seen:
                raise Unsupported(ci + ": duplicate identity within/across pages")
            seen.add(identity)
            if row["logicalRegionName"] != call["condition"]["constraint"][0]["simple"]["value"]:
                raise Unsupported(ci + ": wrong/missing logicalRegionName")
            if row["vdcName"] is not None and not isinstance(row["vdcName"], str):
                raise Unsupported(ci + ": vdcName must be string or NULL")
            rows.append({key: row[key] for key in COLUMNS})
    if len(rows) != total or len(pages) != max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE):
        raise Unsupported(ci + ": incomplete or extra pagination")
    return rows


def preflight(params, receipts):
    """Validate complete bound snapshots; successful empty requires typed schema."""
    params = _params(params)
    plan = prepare(params)
    if not isinstance(receipts, dict) or set(receipts) != set(RESOURCES):
        raise Unsupported("all three independent resource snapshots required")
    tables = {TABLES[ci]: _collect(receipts[ci], ci, plan["api_call"][i]) for i, ci in enumerate(RESOURCES)}
    diagnostics = {
        "population": "complete declared local snapshots only; not a live atomic snapshot certificate",
        "group_identity": "exact vdcName buckets; not authoritative VDC identity",
        "null_vdc_rows": {ci: sum(r["vdcName"] is None for r in tables[TABLES[ci]]) for ci in RESOURCES},
        "blank_vdc_rows": {ci: sum(isinstance(r["vdcName"], str) and not r["vdcName"].strip() for r in tables[TABLES[ci]]) for ci in RESOURCES},
        "count_role": "GAUSSDB_INSTANCE objects, never GAUSSDB_NODE objects",
        "source_rows": {ci: len(tables[TABLES[ci]]) for ci in RESOURCES}}
    diagnostics["named_vdc_identity_complete"] = not any(diagnostics["null_vdc_rows"].values()) and not any(diagnostics["blank_vdc_rows"].values())
    prepared = {"status": "ready_for_typed_sql", "projection_contract": PROJECTION_CONTRACT,
                "parameters_sha256": _hash(params), "plan_sha256": _hash(plan),
                "tables": tables, "diagnostics": diagnostics}
    prepared["projection_sha256"] = _hash({"tables": tables, "diagnostics": diagnostics})
    return prepared


def execute_local(params, receipts):
    """Synthetic in-memory SQLite verifier; not B or the official executor."""
    plan = prepare(params)
    projected = preflight(params, receipts)
    connection = sqlite3.connect(":memory:")
    try:
        for table, rows in projected["tables"].items():
            connection.execute('CREATE TABLE "' + table + '" (' + ','.join('"' + key + '" TEXT' for key in COLUMNS) + ')')
            connection.executemany('INSERT INTO "' + table + '" VALUES (?,?,?)',
                                   [[row[key] for key in COLUMNS] for row in rows])
        cursor = connection.execute(plan["sql"])
        if tuple(c[0] for c in cursor.description) != OUTPUT_COLUMNS:
            raise AssertionError("output column drift")
        rows = [dict(zip(OUTPUT_COLUMNS, row)) for row in cursor.fetchall()]
        return {"rows": rows, "diagnostics": projected["diagnostics"], "local_snapshot_verified": True,
                "runtime_adopted": False}
    finally:
        connection.close()
