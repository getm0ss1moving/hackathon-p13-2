"""Closed independent VDC network inventory; pure construction/validation only.

No question-text routing, network access, official executor, or runtime registration.
Receipt validation adapts Issue3 network R2; original files stay read-only.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import sqlite3

PROFILE = "vdc_network_inventory"
FAMILY_ID = "A_P0_VDC_NETWORK_INVENTORY"
RESOURCES = ("ROUTER", "SUBNET", "FLOATING_IPS")
SCOPE = ("vdcName", "logicalRegionName")
TABLES = {ci: "CLOUD_" + ci for ci in RESOURCES}
COLUMNS = {
    "ROUTER": ("id", "name", "vdcName", "logicalRegionName"),
    "SUBNET": ("id", "cidr", "vdcName", "logicalRegionName"),
    "FLOATING_IPS": ("id", "vdcName", "logicalRegionName"),
}
OUTPUT_COLUMNS = ("resource_type", "resource_id", "resource_name", "cidr", "resource_count")
WHITESPACE_CODEPOINTS = frozenset((9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
    8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239,
    8287, 12288))


class Unsupported(ValueError):
    """No SQL result exists for a rejected input; never treat as success-empty."""


class LengthBlocked(Unsupported):
    def __init__(self, measured_bytes, limit_bytes=4096):
        self.details = {"status": "blocked_transport_budget", "measured_bytes": measured_bytes,
            "limit_bytes": limit_bytes, "boundary": "compact UTF8 api_call+sql",
            "official_boundary_confirmed": False, "handling": "No truncation; B must verify another encoding or reject this transport."}
        super().__init__(json.dumps(self.details, ensure_ascii=False, sort_keys=True))


def _blank(value):
    return value is None or (isinstance(value, str) and
        (not value or all(ord(c) in WHITESPACE_CODEPOINTS for c in value)))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _surrogate(value):
    return isinstance(value, str) and any(0xD800 <= ord(c) <= 0xDFFF for c in value)


def _params(params):
    if not isinstance(params, dict) or set(params) != {"profile", "filters", "required_filters"}:
        raise Unsupported("closed profile, filters, required_filters structure required")
    if params["profile"] != PROFILE or params["required_filters"] != list(SCOPE):
        raise Unsupported("only the complete independent VPC-name/subnet-CIDR/EIP-count profile is supported")
    filters = params["filters"]
    if not isinstance(filters, dict) or set(filters) != set(SCOPE):
        raise Unsupported("explicit vdcName AND logicalRegionName required; extra scopes/obligations unsupported")
    for key, value in filters.items():
        if (not isinstance(value, str) or _blank(value) or _surrogate(value) or "{{" in value or "}}" in value
                or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
            raise Unsupported(key + " requires a fully bound nonblank Unicode literal without C0/DEL/C1 controls or surrogate codepoints")
    return {"profile": PROFILE, "filters": {key: filters[key] for key in SCOPE}, "required_filters": list(SCOPE)}


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def prepare(params):
    """Materialize one fixed obligation set. Caller must ground the full request."""
    params = _params(params)
    filters = params["filters"]
    where = " AND ".join(key + "=" + _literal(filters[key]) for key in SCOPE)
    sql = (
        "SELECT 'VPC' AS resource_type,id AS resource_id,name AS resource_name,NULL AS cidr,NULL AS resource_count FROM CLOUD_ROUTER WHERE " + where +
        " UNION ALL SELECT 'SUBNET',id,NULL,cidr,NULL FROM CLOUD_SUBNET WHERE " + where +
        " UNION ALL SELECT 'EIP_COUNT',NULL,NULL,NULL,COUNT(*) FROM CLOUD_FLOATING_IPS WHERE " + where +
        " ORDER BY resource_type,resource_id"
    )
    calls = [{"method": "GET", "url": "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=1000",
        "autoPagination": True, "condition": {"constraint": [{"simple": {
            "name": key, "value": filters[key], "operator": "equal"}} for key in SCOPE]}} for ci in RESOURCES]
    execution = {"api_call": calls, "sql": sql}
    measured = len(_json(execution).encode("utf-8"))
    if measured > 4096:
        raise LengthBlocked(measured)
    return {"family_id": FAMILY_ID, "profile": PROFILE, "resources": list(RESOURCES), **execution,
        "output_columns": list(OUTPUT_COLUMNS), "empty_input_schema": {TABLES[ci]: list(COLUMNS[ci]) for ci in RESOURCES},
        "requires_preflight_projection": True, "expanded_execution_bytes": measured,
        "final_B_envelope_and_official_depth": "pending"}


build = prepare


def collect_pages(pages):
    """Validate normalized trusted fetch-layer receipts, never manufacture them."""
    if not isinstance(pages, list) or not pages:
        raise Unsupported("missing successful page receipts; true-empty still requires totalNum=0")
    rows, ids = [], set()
    total = size = None
    for expected, page in enumerate(pages, 1):
        if not isinstance(page, dict) or page.get("ok") is not True or page.get("success") is False or page.get("error") is not None:
            raise Unsupported("failed request or unproven success")
        number, current_size, count = (page.get(k) for k in ("pageNo", "pageSize", "totalNum"))
        if type(number) is not int or number != expected or type(current_size) is not int or current_size <= 0 or type(count) is not int or count < 0:
            raise Unsupported("invalid or noncontiguous pagination metadata")
        if total is None:
            total, size = count, current_size
        if count != total or current_size != size:
            raise Unsupported("changing page total/size")
        expected_pages = max(1, (total + size - 1) // size)
        if "totalPageNo" in page and (type(page["totalPageNo"]) is not int
                or (page["totalPageNo"] != expected_pages and not (total == 0 and page["totalPageNo"] == 0))):
            raise Unsupported("contradictory totalPageNo")
        batch = page.get("objList")
        if not isinstance(batch, list) or len(batch) != min(size, max(total - len(rows), 0)):
            raise Unsupported("missing, partial, oversized, or extra batch")
        for row in batch:
            if not isinstance(row, dict) or "_empty" in row:
                raise Unsupported("invalid object or placeholder row")
            identity = row.get("id")
            if not isinstance(identity, str) or _blank(identity) or _surrogate(identity):
                raise Unsupported("nonblank string object identity required")
            if identity in ids:
                raise Unsupported("duplicate CI object identity within/across pages")
            ids.add(identity)
            rows.append(dict(row))
    if len(rows) != total or len(pages) != max(1, (total + size - 1) // size):
        raise Unsupported("incomplete or extra pages")
    return rows


def preflight(params, receipts):
    """Project independent validated tables. Missing/unknown fields never become 0."""
    params = _params(params)
    prepare(params)  # Enforce exactly the same construction/budget gate.
    if not isinstance(receipts, dict) or set(receipts) != set(RESOURCES):
        raise Unsupported("all three independent complete resources are required")
    tables = {}
    diagnostics = {"unknown_vpc_name_count": 0, "unknown_subnet_cidr_count": 0,
        "invalid_subnet_cidr_count": 0, "source_row_counts": {}, "snapshot_consistency": "live atomic snapshot and B request binding unproven"}
    for ci in RESOURCES:
        raw = collect_pages(receipts[ci])
        projected = []
        for row in raw:
            if any(key not in row for key in COLUMNS[ci]):
                raise Unsupported(ci + " missing required native schema column")
            for key in SCOPE:
                if not isinstance(row[key], str) or row[key] != params["filters"][key]:
                    raise Unsupported(ci + " missing, unknown, or mismatched " + key)
            row = {key: row[key] for key in COLUMNS[ci]}
            if any(_surrogate(value) for value in row.values()):
                raise Unsupported(ci + " contains non-UTF8 surrogate codepoints")
            if ci == "ROUTER":
                value = row["name"]
                if value is not None and not isinstance(value, str):
                    raise Unsupported("ROUTER.name must be string or NULL")
                diagnostics["unknown_vpc_name_count"] += int(_blank(value))
            elif ci == "SUBNET":
                value = row["cidr"]
                if value is not None and not isinstance(value, str):
                    raise Unsupported("SUBNET.cidr must be string or NULL")
                if _blank(value):
                    diagnostics["unknown_subnet_cidr_count"] += 1
                else:
                    try:
                        if "/" not in value:
                            raise ValueError("prefix missing")
                        ipaddress.ip_network(value, strict=False)
                    except ValueError:
                        diagnostics["invalid_subnet_cidr_count"] += 1
            projected.append(row)
        tables[TABLES[ci]] = projected
        diagnostics["source_row_counts"][ci] = len(projected)
    diagnostics["requested_values_complete"] = not any(diagnostics[k] for k in
        ("unknown_vpc_name_count", "unknown_subnet_cidr_count", "invalid_subnet_cidr_count"))
    return {"status": "ready_for_typed_sql", "projection_contract": PROFILE + "-v1",
        "params": params, "tables": tables, "schema": {TABLES[ci]: list(COLUMNS[ci]) for ci in RESOURCES},
        "parameter_sha256": hashlib.sha256(_json(params).encode()).hexdigest(),
        "projection_sha256": hashlib.sha256(_json(tables).encode()).hexdigest(), "diagnostics": diagnostics}


def execute_local(params, receipts):
    """Synthetic/offline SQLite verifier. Does not access official execution."""
    plan, prepared = prepare(params), preflight(params, receipts)
    conn = sqlite3.connect(":memory:")
    try:
        for table, columns in prepared["schema"].items():
            conn.execute('CREATE TABLE "' + table + '" (' + ','.join('"' + c + '" TEXT' for c in columns) + ')')
            conn.executemany('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for c in columns) + ')',
                [[row[c] for c in columns] for row in prepared["tables"][table]])
        cursor = conn.execute(plan["sql"])
        columns = [c[0] for c in cursor.description]
        if columns != list(OUTPUT_COLUMNS):
            raise AssertionError("output column drift")
        return {"columns": columns, "rows": [dict(zip(columns, row)) for row in cursor.fetchall()],
            "diagnostics": prepared["diagnostics"], "business_complete": prepared["diagnostics"]["requested_values_complete"],
            "business_complete_scope": "strictly validated declared local receipt snapshot only; no live/B/official certification"}
    finally:
        conn.close()
