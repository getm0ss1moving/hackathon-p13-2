"""Closed independent tenant lists; pure materialization/preflight, no I/O.

No natural-language matching, template registration, SDK changes or networking.
Local SQLite is only a synthetic verifier and loads preflight projections.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sqlite3
import unicodedata

PROFILE = "tenant_parallel_lists"
RESOURCES = ("VM_NOVA", "SECURITY_GROUP", "VOLUME")
TABLES = {ci: "CLOUD_" + ci for ci in RESOURCES}
OUTPUT_COLUMNS = ("resource_type", "resource_id", "resource_name")
PROJECTION_CONTRACT = "tenant-parallel-lists-v1"
BYTE_LIMIT = 4096


class Unsupported(ValueError):
    """Missing evidence or an obligation outside this closed profile."""


class TransportBlocked(Unsupported):
    def __init__(self, size):
        self.details = {"status": "blocked_transport_budget", "boundary": "expanded_api_call+sql",
                        "measured_bytes": size, "limit_bytes": BYTE_LIMIT,
                        "official_boundary_confirmed": False,
                        "handling": "No truncation; B must verify another encoding and its final envelope."}
        super().__init__(json.dumps(self.details, ensure_ascii=False, sort_keys=True))


def compact_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate(params):
    keys = {"profile", "resource_set", "filters", "required_filters", "output_columns"}
    if type(params) is not dict or set(params) != keys:
        raise Unsupported("closed_parameter_schema_required")
    if params["profile"] != PROFILE or params["resource_set"] != list(RESOURCES):
        raise Unsupported("fixed_profile_and_ordered_three_resource_set_required")
    if params["output_columns"] != list(OUTPUT_COLUMNS):
        raise Unsupported("exact_output_columns_required; extra obligations need another profile")
    filters = params["filters"]
    if type(filters) is not dict or set(filters) not in ({"tenantName"}, {"tenantName", "logicalRegionName"}):
        raise Unsupported("tenantName_required_only_explicit_logicalRegionName_optional")
    ordered = [key for key in ("tenantName", "logicalRegionName") if key in filters]
    if params["required_filters"] != ordered:
        raise Unsupported("required_filters_must_equal_exact_scope_in_fixed_order")
    for key, value in filters.items():
        if (type(value) is not str or not value.strip() or "{{" in value or "}}" in value
                or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value)):
            raise Unsupported(key + " requires a literal nonblank Unicode string without controls")
    return {"profile": PROFILE, "resource_set": list(RESOURCES),
            "filters": {key: filters[key] for key in ordered},
            "required_filters": ordered, "output_columns": list(OUTPUT_COLUMNS)}


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def _core(filters):
    calls, branches = [], []
    where = " AND ".join(key + "=" + _literal(value) for key, value in filters.items())
    for ci in RESOURCES:
        calls.append({"method": "GET", "url": "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=1000",
                      "autoPagination": True, "condition": {"constraint": [
                          {"simple": {"name": key, "value": value, "operator": "equal"}}
                          for key, value in filters.items()]}})
        branches.append("SELECT '" + ci + "' AS resource_type,id AS resource_id,name AS resource_name FROM "
                        + TABLES[ci] + " WHERE " + where)
    return {"api_call": calls, "sql": " UNION ALL ".join(branches) + " ORDER BY resource_type,resource_id"}


def prepare(params):
    """Closed structured obligation contract -> ordinary API/SQL plus local metadata.

    B still owns grounding every original-request obligation before calling this
    function. This function cannot certify a natural-language match.
    """
    params = _validate(params)
    core = _core(params["filters"])
    size = compact_bytes(core)
    if size > BYTE_LIMIT:
        raise TransportBlocked(size)
    columns = ["id", "name", *params["required_filters"]]
    static = _core({key: "{{" + key + "}}" for key in params["required_filters"]})
    return {"profile": PROFILE, "resources": list(RESOURCES), **core,
            "output_columns": list(OUTPUT_COLUMNS), "grain": "one independent row per CI identity; no joins",
            "required_schema": {ci: {key: "TEXT" for key in columns} for ci in RESOURCES},
            "empty_input_schema": {TABLES[ci]: {key: "TEXT" for key in columns} for ci in RESOURCES},
            "projection_contract": PROJECTION_CONTRACT, "requires_preflight": True,
            "requires_preflight_projection": True, "status": "isolated_candidate_not_registered",
            "byte_boundaries": {"expanded_api_call_sql_bytes": size,
                                "static_placeholder_api_call_sql_bytes": compact_bytes(static),
                                "local_api_call_sql_limit": BYTE_LIMIT,
                                "encoding": "compact ensure_ascii=False UTF-8 JSON",
                                "final_B_envelope": "unconstructed/unmeasured; B must check exact final payload",
                                "formal_depth_gate": "pending official algorithm and final payload"}}


def _collect_pages(pages):
    """R2-style strict normalized B receipt validation; never fabricates success."""
    if type(pages) is not list or not pages:
        raise Unsupported("missing_pages; even true empty needs successful zero-total receipt")
    rows, seen_ids, metadata = [], set(), None
    for expected, page in enumerate(pages, 1):
        if (type(page) is not dict or page.get("ok") is not True or page.get("success") is False
                or page.get("error") is not None):
            raise Unsupported("request_failed_or_success_unproven")
        n, size, total = (page.get(k) for k in ("pageNo", "pageSize", "totalNum"))
        if type(n) is not int or n != expected or type(size) is not int or size < 1 or type(total) is not int or total < 0:
            raise Unsupported("invalid_or_out_of_order_pagination")
        total_pages = max(1, (total + size - 1) // size)
        if "totalPageNo" in page and (type(page["totalPageNo"]) is not int
                or (page["totalPageNo"] != total_pages and not (total == 0 and page["totalPageNo"] == 0))):
            raise Unsupported("contradictory_totalPageNo")
        if metadata is None:
            metadata = (size, total)
        if metadata != (size, total):
            raise Unsupported("unstable_pagination_metadata")
        batch = page.get("objList")
        if type(batch) is not list or len(batch) != min(size, max(total - len(rows), 0)):
            raise Unsupported("missing_truncated_or_oversized_batch")
        for row in batch:
            if type(row) is not dict:
                raise Unsupported("invalid_row")
            identity = row.get("id")
            if type(identity) is not str or not identity.strip():
                raise Unsupported("missing_NULL_blank_or_nonstring_resource_identity")
            if identity in seen_ids:
                raise Unsupported("duplicate_resource_identity_in_snapshot")
            seen_ids.add(identity)
            rows.append(row)
    size, total = metadata
    if len(rows) != total or len(pages) != max(1, (total + size - 1) // size):
        raise Unsupported("incomplete_or_extra_page_set")
    return rows


def preflight(params, receipts):
    """Validate complete receipts and return new schema-only typed table copies."""
    params = _validate(params)
    plan = prepare(params)
    if type(receipts) is not dict or set(receipts) != set(RESOURCES):
        raise Unsupported("all_three_and_only_three_source_receipts_required")
    tables = {}
    for ci in RESOURCES:
        schema = plan["required_schema"][ci]
        projected = []
        for row in _collect_pages(receipts[ci]):
            if any(key not in row for key in schema):
                raise Unsupported(ci + ":missing_required_native_schema")
            if any(value is not None and type(value) is not str for key, value in row.items() if key in schema):
                raise Unsupported(ci + ":nontext_native_schema_value")
            if any(type(row[key]) is str and any(unicodedata.category(ch) == "Cs" for ch in row[key]) for key in schema):
                raise Unsupported(ci + ":invalid_native_Unicode_scalar")
            if any(row[key] != value for key, value in params["filters"].items()):
                raise Unsupported(ci + ":NULL_unknown_or_wrong_scope")
            projected.append({key: row[key] for key in schema})
        tables[ci] = projected
    unknown_names = {ci: sum(row["name"] is None or not row["name"].strip() for row in tables[ci]) for ci in RESOURCES}
    diagnostics = {"resource_rows": {ci: len(tables[ci]) for ci in RESOURCES},
                   "empty_resource_lists": [ci for ci in RESOURCES if not tables[ci]],
                   "unknown_resource_name_count": unknown_names,
                   "requested_values_complete": not any(unknown_names.values()),
                   "identity_complete": True,
                   "selection_semantics": "native tenantName equality; homonymous tenant IDs are not inferred unique",
                   "declared_local_receipts_complete": True,
                   "live_atomic_snapshot_and_fetch_binding": "not proven by local receipt validation"}
    return {"status": "ready_for_typed_sql", "projection_contract": PROJECTION_CONTRACT,
            "parameter_sha256": fingerprint(params), "projection_sha256": fingerprint(tables),
            "tables": tables, "schemas": deepcopy(plan["required_schema"]), "diagnostics": diagnostics}


def execute_local(params, receipts):
    """Offline synthetic verifier; not the official executor or runtime adapter."""
    plan = prepare(params)
    prepared = preflight(params, receipts)
    connection = sqlite3.connect(":memory:")
    try:
        for ci in RESOURCES:
            schema = prepared["schemas"][ci]
            connection.execute("CREATE TABLE " + TABLES[ci] + " (" + ",".join('"' + key + '" TEXT' for key in schema) + ")")
            connection.executemany("INSERT INTO " + TABLES[ci] + " VALUES (" + ",".join("?" for _ in schema) + ")",
                                   [[row[key] for key in schema] for row in prepared["tables"][ci]])
        cursor = connection.execute(plan["sql"])
        columns = [item[0] for item in cursor.description]
        if columns != list(OUTPUT_COLUMNS):
            raise AssertionError("output_column_drift")
        return {"columns": columns, "rows": [dict(zip(columns, row)) for row in cursor.fetchall()],
                "diagnostics": prepared["diagnostics"], "scope": "declared_local_receipt_snapshot_only"}
    finally:
        connection.close()
