"""Pure ELB child-count materializer. No retrieval, I/O, service calls or defaults.

Run validate_snapshots before SQL. Empty inputs require typed schemas; the
unchanged official executor's _empty placeholder is deliberately rejected.
"""
from copy import deepcopy
import json
import math

FAMILY_ID = "family_elb_child_counts_candidate"
SCOPES = ("logicalRegionName", "tenantName", "vdcName")
RESOURCES = ("ELB", "LISTENER", "ELB_POOL", "ELB_POOL_MEMBERS")
COLUMNS = {
    "per_elb": ["elb_id", "elb_name", "elb_ip", "status", "listener_count", "member_count"],
    "totals": ["elb_count", "listener_count", "member_count"],
}
BASE_SCHEMA = {
    "ELB": {"id": "TEXT", "name": "TEXT", "ip": "TEXT", "status": "TEXT"},
    "LISTENER": {"id": "TEXT", "elbId": "TEXT"},
    "ELB_POOL": {"id": "TEXT", "elbId": "TEXT"},
    "ELB_POOL_MEMBERS": {"id": "TEXT", "poolId": "TEXT"},
}
REFERENCES = {"LISTENER": "elbId", "ELB_POOL": "elbId", "ELB_POOL_MEMBERS": "poolId"}
COUNT_POLICY = "identity_complete_zero"
MAX_REQUEST_BYTES = 4096


class ContractError(ValueError):
    """An unsupported/invalid plan or unknown input; never a successful result."""


def _text(value):
    return (type(value) is str and bool(value) and value == value.strip()
            and "{{" not in value and "}}" not in value
            and not any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def _quote(value):
    return "'" + value.replace("'", "''") + "'"


def build(params):
    """Return a closed ordinary api_call/sql candidate, or raise ContractError.

    params={view:per_elb|totals,filters:{one or more parent scopes},
            required_filters:[exactly the supplied keys],count_policy:...}.
    AZ, backend/deployment roles, added obligations and extra keys are rejected.
    This structured function intentionally does not interpret natural language.
    """
    if type(params) is not dict or set(params) != {"view", "filters", "required_filters", "count_policy"}:
        raise ContractError("closed_parameter_schema_required")
    view, filters, required = params["view"], params["filters"], params["required_filters"]
    if type(view) is not str or view not in COLUMNS:
        raise ContractError("unsupported_view")
    if params["count_policy"] != COUNT_POLICY:
        raise ContractError("explicit_identity_complete_zero_policy_required")
    if type(filters) is not dict or not filters or not set(filters) <= set(SCOPES):
        raise ContractError("only_proven_parent_region_tenant_vdc_scopes_supported_AZ_unproved")
    if (type(required) is not list or any(type(x) is not str for x in required)
            or len(set(required)) != len(required) or set(required) != set(filters)):
        raise ContractError("required_filters_must_equal_supplied_filters")
    if any(not _text(x) for x in filters.values()):
        raise ContractError("nonempty_unmodified_scope_text_required")
    ordered = {key: filters[key] for key in SCOPES if key in filters}
    condition = {"constraint": [{"simple": {"name": key, "value": value, "operator": "equal"}}
                                 for key, value in ordered.items()]}
    apis = [{"method": "GET", "url": "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=10000",
             "autoPagination": True} for ci in RESOURCES]
    apis[0]["condition"] = condition
    where = " AND ".join("e." + key + " = " + _quote(value) for key, value in ordered.items())
    ctes = "WITH scoped_elb AS (SELECT e.* FROM CLOUD_ELB e WHERE " + where + "), "
    ctes += "listener_counts AS (SELECT elbId, COUNT(DISTINCT id) AS listener_count FROM CLOUD_LISTENER GROUP BY elbId), "
    ctes += "member_counts AS (SELECT p.elbId, COUNT(DISTINCT m.id) AS member_count FROM CLOUD_ELB_POOL p INNER JOIN CLOUD_ELB_POOL_MEMBERS m ON p.id=m.poolId GROUP BY p.elbId) "
    joined = "FROM scoped_elb e LEFT JOIN listener_counts l ON e.id=l.elbId LEFT JOIN member_counts m ON e.id=m.elbId"
    if view == "per_elb":
        sql = ctes + "SELECT e.id AS elb_id,e.name AS elb_name,e.ip AS elb_ip,e.status,COALESCE(l.listener_count,0) AS listener_count,COALESCE(m.member_count,0) AS member_count " + joined + " ORDER BY e.id"
    else:
        sql = ctes + "SELECT COUNT(e.id) AS elb_count,COALESCE(SUM(l.listener_count),0) AS listener_count,COALESCE(SUM(m.member_count),0) AS member_count " + joined
    schemas = deepcopy(BASE_SCHEMA)
    schemas["ELB"].update({key: "TEXT" for key in ordered})
    result = {"id": FAMILY_ID, "view": view, "resources": list(RESOURCES), "api_call": apis,
              "sql": sql, "output_columns": list(COLUMNS[view]), "required_schema": schemas,
              "filters": ordered, "count_policy": COUNT_POLICY,
              "requires_snapshot_preflight": True, "requires_typed_empty_loader": True}
    wire = {"api_call": apis, "sql": sql}
    if len(json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ContractError("api_sql_utf8_request_exceeds_4096_bytes_no_truncation")
    return result


def validate_snapshots(plan, snapshots):
    """Validate all pages and schemas, return flattened rows for a typed loader.

    snapshots[CI] is a list of page dicts with ok=True, page_no (1-based),
    page_size, total, rows. schema is mandatory on an empty page; if supplied,
    schema is a list of field names or dict name->type. Page sizes/totals must
    be stable, pages consecutive and complete, IDs nonempty and globally unique.
    No missing row, failed page, _empty placeholder or unknown relation is zero.
    """
    if type(plan) is not dict or plan.get("id") != FAMILY_ID:
        raise ContractError("materialized_plan_required")
    if type(snapshots) is not dict or set(snapshots) != set(RESOURCES):
        raise ContractError("all_four_successful_resource_snapshots_required")
    tables = {}
    for ci in RESOURCES:
        pages = snapshots[ci]
        required = set(plan["required_schema"][ci])
        if type(pages) is not list or not pages:
            raise ContractError(ci + ":missing_pages")
        first = pages[0]
        if type(first) is not dict:
            raise ContractError(ci + ":invalid_page")
        total, size = first.get("total"), first.get("page_size")
        if type(total) is not int or total < 0 or type(size) is not int or size <= 0:
            raise ContractError(ci + ":invalid_pagination_metadata")
        expected_pages = max(1, math.ceil(total / size))
        if len(pages) != expected_pages:
            raise ContractError(ci + ":truncated_or_extra_pages")
        rows, ids = [], set()
        for i, page in enumerate(pages, 1):
            if type(page) is not dict or page.get("ok") is not True:
                raise ContractError(ci + ":request_failed_or_unknown")
            if page.get("page_no") != i or type(page.get("page_no")) is not int:
                raise ContractError(ci + ":pages_not_consecutive")
            if type(page.get("total")) is not int or page["total"] != total or type(page.get("page_size")) is not int or page["page_size"] != size:
                raise ContractError(ci + ":pagination_drift")
            part = page.get("rows")
            if type(part) is not list or len(part) != min(size, max(total - (i - 1) * size, 0)):
                raise ContractError(ci + ":missing_or_truncated_rows")
            schema = page.get("schema")
            if schema is not None:
                if type(schema) not in (list, dict) or any(type(x) is not str for x in schema) or "_empty" in schema or not required <= set(schema):
                    raise ContractError(ci + ":unproven_or_placeholder_schema")
            if not part and schema is None:
                raise ContractError(ci + ":typed_empty_schema_required")
            for row in part:
                if type(row) is not dict or "_empty" in row or not required <= set(row):
                    raise ContractError(ci + ":missing_required_field")
                ident = row["id"]
                if not _text(ident) or ident in ids:
                    raise ContractError(ci + ":missing_or_duplicate_identity")
                if ci in REFERENCES and not _text(row[REFERENCES[ci]]):
                    raise ContractError(ci + ":missing_reference_unknown_not_zero")
                if any(value is not None and type(value) not in (str, int, float, bool) for key, value in row.items() if key in required):
                    raise ContractError(ci + ":unsupported_nested_value")
                ids.add(ident)
                rows.append(deepcopy(row))
        tables[ci] = rows
    pools = {row["id"] for row in tables["ELB_POOL"]}
    if any(row["poolId"] not in pools for row in tables["ELB_POOL_MEMBERS"]):
        raise ContractError("ELB_POOL_MEMBERS:unresolved_pool_reference")
    return {"tables": tables, "schemas": deepcopy(plan["required_schema"]),
            "row_counts": {ci: len(rows) for ci, rows in tables.items()}}
