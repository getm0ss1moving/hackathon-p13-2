"""Isolated VPC child-count family. Pure construction and local validation only."""
from __future__ import annotations
import json
import sqlite3
from collections import defaultdict

FAMILY_ID = "vpc_child_counts"
SOURCE_IDS = ("rb_192",)
RESOURCES = ("ROUTER", "PORT", "R_PORT_IN_SUBNET", "SUBNET", "FLOATING_IPS")
TABLES = {r: (r if r.startswith("R_") else "CLOUD_" + r) for r in RESOURCES}
COLUMNS = {
    "ROUTER": ("id", "name", "nativeId", "logicalRegionName", "vdcName"),
    "PORT": ("id", "devNativeId", "logicalRegionName"),
    "R_PORT_IN_SUBNET": ("id", "portId", "subnetId"),
    "SUBNET": ("id", "logicalRegionName"),
    "FLOATING_IPS": ("id", "routerId", "logicalRegionName"),
}
OUTPUT_COLUMNS = ("vpc_id", "vpc_name", "resolved_subnet_count", "referenced_subnet_count", "unresolved_subnet_count", "known_eip_count")

class Unsupported(ValueError):
    pass


class LengthBlocked(Unsupported):
    """A supported semantic request exceeds this provisional encoding gate."""
    def __init__(self, measured_bytes, execution_bytes, limit_bytes=4096):
        self.details = {
            "status": "blocked_materialization_length",
            "boundary": "entire build() return value as compact ensure_ascii=False UTF-8 JSON",
            "measured_bytes": measured_bytes,
            "api_call_plus_sql_bytes": execution_bytes,
            "limit_bytes": limit_bytes,
            "official_boundary_confirmed": False,
            "handling": "No entity or SQL truncation. B can separately validate a supported bound-parameter/compact execution encoding and its final request envelope; this candidate does not implement that path.",
        }
        super().__init__(json.dumps(self.details, ensure_ascii=False, sort_keys=True))


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _params(params):
    if not isinstance(params, dict) or set(params) != {"logicalRegionName", "vdcName"}:
        raise Unsupported("exactly logicalRegionName and vdcName are required; additional scopes/obligations need another contract")
    for key, value in params.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(c) < 32 for c in value):
            raise Unsupported(key + " must be a nonblank string without ASCII control characters; supported parameter capacity is 1024 Unicode characters. Longer business identifiers are not declared invalid; they need another verified encoding, never truncation.")
    return dict(params)


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def build(params):
    """Materialize only a closed structure; never infer intent from question/entity."""
    params = _params(params)
    region, vdc = map(_literal, (params["logicalRegionName"], params["vdcName"]))
    sql = f"""WITH parents AS (
 SELECT DISTINCT id, name, nativeId, logicalRegionName FROM CLOUD_ROUTER
 WHERE logicalRegionName={region} AND vdcName={vdc}
), refs AS (
 SELECT DISTINCT p.id AS vpc_id, r.subnetId AS subnet_id
 FROM parents p JOIN CLOUD_PORT t
 ON t.devNativeId=p.nativeId AND t.logicalRegionName=p.logicalRegionName
 JOIN R_PORT_IN_SUBNET r ON r.portId=t.id
 WHERE r.subnetId IS NOT NULL AND r.subnetId<>''
), subnet_counts AS (
 SELECT r.vpc_id, COUNT(*) AS referenced_subnet_count,
 SUM(CASE WHEN EXISTS (SELECT 1 FROM CLOUD_SUBNET s WHERE s.id=r.subnet_id AND s.logicalRegionName={region}) THEN 1 ELSE 0 END) AS resolved_subnet_count
 FROM refs r GROUP BY r.vpc_id
), eip_counts AS (
 SELECT e.routerId AS vpc_id, COUNT(DISTINCT e.id) AS known_eip_count
 FROM CLOUD_FLOATING_IPS e JOIN parents p ON p.id=e.routerId
 WHERE e.logicalRegionName={region} GROUP BY e.routerId
)
SELECT p.id AS vpc_id, p.name AS vpc_name,
 COALESCE(s.resolved_subnet_count,0) AS resolved_subnet_count,
 COALESCE(s.referenced_subnet_count,0) AS referenced_subnet_count,
 COALESCE(s.referenced_subnet_count,0)-COALESCE(s.resolved_subnet_count,0) AS unresolved_subnet_count,
 COALESCE(e.known_eip_count,0) AS known_eip_count
FROM parents p LEFT JOIN subnet_counts s ON s.vpc_id=p.id
LEFT JOIN eip_counts e ON e.vpc_id=p.id ORDER BY p.id"""
    def request(resource, fields):
        endpoint = "relations" if resource.startswith("R_") else "instances"
        result = {"method": "GET", "url": f"/rest/hackthon/db/{endpoint}/{resource}?pageNo=1&pageSize=1000", "autoPagination": True}
        if fields:
            result["condition"] = {"constraint": [{"simple": {"name": key, "value": params[key], "operator": "equal"}} for key in fields]}
        return result
    result = {
        "family_id": FAMILY_ID,
        "resources": list(RESOURCES),
        "api_call": [request("ROUTER", ("logicalRegionName",)), request("PORT", ("logicalRegionName",)), request("R_PORT_IN_SUBNET", ()), request("SUBNET", ("logicalRegionName",)), request("FLOATING_IPS", ("logicalRegionName",))],
        "sql": sql, "output_columns": list(OUTPUT_COLUMNS),
        "requires_preflight": True, "requires_preflight_projection": True,
        "empty_input_schema": {TABLES[r]: list(COLUMNS[r]) for r in RESOURCES},
        "pagination": {"follow_all_pages": True, "require_stable_total": True, "reject_partial_or_failed": True},
    }
    full_bytes = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    execution_bytes = len(json.dumps({k: result[k] for k in ("api_call", "sql")}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if full_bytes > 4096:
        raise LengthBlocked(full_bytes, execution_bytes)
    return result


def collect_pages(pages):
    """Pure validation of normalized page receipts supplied by B's fetch layer.

    Receipt: ok/pageNo/pageSize/totalNum/objList. Never fetches pages itself.
    A stable total is necessary, not proof of a live atomic snapshot.
    """
    if not isinstance(pages, list) or not pages:
        raise Unsupported("missing page receipt; empty results still require a successful zero-total receipt")
    total = None
    rows = []
    page_size = None
    seen_page_contents = set()
    seen_object_ids = set()
    for expected, page in enumerate(pages, 1):
        if not isinstance(page, dict) or page.get("ok") is not True:
            raise Unsupported("request failed or success is unproven")
        n, size, count = page.get("pageNo"), page.get("pageSize"), page.get("totalNum")
        if type(n) is not int or n != expected or type(size) is not int or size < 1 or type(count) is not int or count < 0:
            raise Unsupported("invalid or out-of-order pagination metadata")
        if total is None:
            total, page_size = count, size
        if count != total or size != page_size:
            raise Unsupported("changing total/page size cannot establish completeness")
        batch = page.get("objList")
        if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
            raise Unsupported("missing/invalid objList")
        remaining = max(total - len(rows), 0)
        if len(batch) != min(size, remaining):
            raise Unsupported("truncated, oversized, or extra page")
        fingerprint = json.dumps(batch, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if batch and fingerprint in seen_page_contents:
            raise Unsupported("repeated page content cannot establish completeness")
        seen_page_contents.add(fingerprint)
        for row in batch:
            identity = row.get("id")
            if not isinstance(identity, str) or _blank(identity):
                raise Unsupported("every snapshot object requires a nonblank string id")
            if identity in seen_object_ids:
                raise Unsupported("duplicate object id in one CI snapshot; overlap can conceal a missing object")
            seen_object_ids.add(identity)
            rows.append(dict(row))
    if len(rows) != total or len(pages) != max(1, (total + page_size - 1) // page_size):
        raise Unsupported("pagination incomplete or contains extra pages")
    return rows


def preflight(params, receipts):
    """Return validated rows plus diagnostics; failure cannot become COUNT=0.

    Every required field must exist on every nonempty row. NULL child FK means
    unknown ownership, never an invented match. Explicit empty schema is local
    to this candidate and must be supported by B before runtime integration.
    """
    params = _params(params)
    if not isinstance(receipts, dict) or set(receipts) != set(RESOURCES):
        raise Unsupported("all five complete input resources are required")
    tables = {}
    diagnostics = {"unknown_eip_parent_rows": 0, "unknown_subnet_reference_rows": 0, "unassigned_port_rows": 0, "orphan_port_reference_rows": 0, "unresolved_eip_parent_rows": 0, "duplicate_identity_policy": "reject within each CI, including identical rows", "preflight_passed": True, "completeness_evidence": "validated declared local page receipts and known relationships only", "snapshot_consistency": "live atomic snapshot, B request binding, and official business acceptance are not proven"}
    for resource in RESOURCES:
        raw = collect_pages(receipts[resource])
        projected = []
        for row in raw:
            # Scope is enforced only for fields declared by this CI contract.
            # The global relationship resource has no region ownership field;
            # any extra metadata is projected away, then its keys join scoped ports.
            required = COLUMNS[resource]
            # nullable foreign keys may be absent in native EIP rows; absence is
            # retained as unknown, while missing join/scope columns elsewhere fails.
            optional = {"routerId"} if resource == "FLOATING_IPS" else set()
            if any(key not in row for key in required if key not in optional):
                raise Unsupported(resource + " has a missing schema/join/scope field")
            row = {key: row.get(key) for key in required}
            if "logicalRegionName" in row and row["logicalRegionName"] != params["logicalRegionName"]:
                raise Unsupported(resource + " receipt contains a missing, unknown, or wrong logical region")
            if resource == "ROUTER":
                if row["vdcName"] is not None and not isinstance(row["vdcName"], str):
                    raise Unsupported("ROUTER has invalid VDC field type")
                if _blank(row["vdcName"]):
                    row["vdcName"] = None
            if not isinstance(row["id"], str) or _blank(row["id"]):
                raise Unsupported(resource + " requires a nonblank string identity")
            nullable_keys = {"PORT": ("devNativeId",), "R_PORT_IN_SUBNET": ("portId", "subnetId"), "FLOATING_IPS": ("routerId",)}.get(resource, ())
            for key in nullable_keys:
                if _blank(row[key]):
                    row[key] = None
                elif not isinstance(row[key], str):
                    raise Unsupported(resource + "." + key + " must be a string identity or unknown")
            projected.append(row)
        tables[resource] = projected
    region, vdc = params["logicalRegionName"], params["vdcName"]
    diagnostics["unknown_vdc_parent_rows"] = sum(row["vdcName"] is None for row in tables["ROUTER"])
    diagnostics["scope_complete"] = diagnostics["unknown_vdc_parent_rows"] == 0
    diagnostics["unknown_vdc_parent_policy"] = "retain full parent directory; report known scoped parents plus unresolved VDC membership"
    scoped = [row for row in tables["ROUTER"] if row["logicalRegionName"] == region and row["vdcName"] == vdc]
    keys = defaultdict(set)
    for row in tables["ROUTER"]:
        if row["logicalRegionName"] != region:
            continue
        if not isinstance(row["nativeId"], str) or _blank(row["nativeId"]):
            raise Unsupported("scoped parent without nativeId has unknown subnet membership")
        keys[(row["logicalRegionName"], row["nativeId"])].add(row["id"])
    if any(len(ids) > 1 for ids in keys.values()):
        raise Unsupported("ambiguous region/nativeId parent identity")
    parent_ids = {row["id"] for row in scoped}
    all_parent_ids = {row["id"] for row in tables["ROUTER"] if row["logicalRegionName"] == region}
    scoped_keys = {(row["logicalRegionName"], row["nativeId"]) for row in scoped}
    all_port_ids = {row["id"] for row in tables["PORT"]}
    port_ids = {row["id"] for row in tables["PORT"] if (row["logicalRegionName"], row["devNativeId"]) in scoped_keys}
    for row in tables["PORT"]:
        if row["logicalRegionName"] == region and row["devNativeId"] in (None, ""):
            diagnostics["unassigned_port_rows"] += 1
    for row in tables["R_PORT_IN_SUBNET"]:
        if row["portId"] not in all_port_ids:
            diagnostics["orphan_port_reference_rows"] += 1
        if row["portId"] in port_ids and row["subnetId"] in (None, ""):
            diagnostics["unknown_subnet_reference_rows"] += 1
    for row in tables["FLOATING_IPS"]:
        if row["logicalRegionName"] == region and row["routerId"] in (None, ""):
            diagnostics["unknown_eip_parent_rows"] += 1
        elif row["logicalRegionName"] == region and row["routerId"] not in all_parent_ids:
            diagnostics["unresolved_eip_parent_rows"] += 1
    diagnostics["count_meaning"] = "known links only; unresolved references and unknown ownership are explicit diagnostics, not certified full business totals"
    diagnostics["scoped_parent_count"] = len(parent_ids)
    return tables, diagnostics


def execute_local(params, receipts):
    """Synthetic/local verifier, never an official executor or service adapter."""
    candidate = build(params)
    tables, diagnostics = preflight(params, receipts)
    conn = sqlite3.connect(":memory:")
    try:
        for resource, rows in tables.items():
            columns = COLUMNS[resource]
            conn.execute('CREATE TABLE "' + TABLES[resource] + '" (' + ','.join('"' + key + '" TEXT' for key in columns) + ')')
            conn.executemany('INSERT INTO "' + TABLES[resource] + '" VALUES (' + ','.join('?' for _ in columns) + ')', [[row.get(key) for key in columns] for row in rows])
        cur = conn.execute(candidate["sql"])
        if tuple(col[0] for col in cur.description) != OUTPUT_COLUMNS:
            raise AssertionError("output contract drift")
        rows = [dict(zip(OUTPUT_COLUMNS, row)) for row in cur.fetchall()]
        diagnostics["unresolved_subnet_count"] = sum(row["unresolved_subnet_count"] for row in rows)
        diagnostics["business_complete"] = diagnostics["scope_complete"] and diagnostics["preflight_passed"] and not any(diagnostics[k] for k in ("unknown_eip_parent_rows", "unknown_subnet_reference_rows", "unassigned_port_rows", "orphan_port_reference_rows", "unresolved_eip_parent_rows", "unresolved_subnet_count"))
        diagnostics["business_complete_scope"] = "only this strictly validated local receipt snapshot and known relationship graph; no live atomic snapshot, B binding, or official business certification"
        diagnostics["result_status"] = "complete_known_local_graph" if diagnostics["business_complete"] else "partial_graph_cannot_answer_as_complete"
        return {"columns": list(OUTPUT_COLUMNS), "rows": rows, "diagnostics": diagnostics}
    finally:
        conn.close()
