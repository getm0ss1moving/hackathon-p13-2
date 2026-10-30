"""同scope的VM、卷、VPC并列完整列表，不推断三个资源之间的关联。"""

import copy
import math
import re
import sqlite3
from contextlib import closing
from urllib.parse import parse_qsl, urlsplit

import runbook_matcher as m


_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_TABLES = {"VOLUME": "CLOUD_VOLUME", "VM_NOVA": "CLOUD_VM_NOVA", "ROUTER": "CLOUD_ROUTER"}
_LABELS = {"VOLUME": "Volume", "VM_NOVA": "ECS", "ROUTER": "VPC"}
_FIELDS = {"VOLUME": ["id", "name", "size", "status", "tenantName"],
           "VM_NOVA": ["id", "name", "privateIps", "tenantName"], "ROUTER": ["id", "name", "tenantName"]}
_METADATA_COLUMNS = {"resource_type", "resource_id", "ecs_list_json", "vpc_list_json"}


def _scope(question):
    if not isinstance(question, str):
        return None
    entity = (r'(?:"(?P<double>[^"\n]+)"|“(?P<chinese>[^”\n]+)”|'
              r"'(?P<single>[^'\n]+)'|(?P<ascii>[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*))")
    region = r"(?P<region>region_[A-Za-z0-9_\-]+)"
    patterns = [r"\s*(?:查询|查看)?\s*租户\s*" + entity + r"(?:\s*在区域\s*" + region + r"\s*(?:中|下|内))?的\s*(?P<body>.+?)\s*[。?？]?\s*",
                r"\s*(?:查询|查看)?\s*区域\s*" + region + r"\s*(?:下|中|内)租户\s*" + entity + r"的\s*(?P<body>.+?)\s*[。?？]?\s*"]
    roles = {"VM_NOVA": r"(?:ECS(?:实例)?|虚拟机(?:实例)?)(?:名称|名)(?:和|及|与)IP(?:列表)?",
             "VOLUME": r"云硬盘(?:名称|名)(?:和|及|与)容量(?:列表)?",
             "ROUTER": r"VPC(?:名称|名)列表"}
    for pattern in patterns:
        match = re.fullmatch(pattern, question, re.I)
        if not match:
            continue
        tenant = next(value for value in (match["double"], match["chinese"], match["single"], match["ascii"]) if value is not None)
        if not tenant.strip() or len(tenant) > 256 or "{{" in tenant or match["region"] and len(match["region"]) > 256:
            return None
        parts = [part.strip() for part in re.split(r"[、,，]", match["body"])]
        requested = [next((ci for ci, role in roles.items() if re.fullmatch(role, part, re.I)), None) for part in parts]
        if len(requested) != 3 or set(requested) != set(_TABLES):
            return None
        scope = {"tenantName": tenant}
        if match["region"]:
            scope["logicalRegionName"] = match["region"]
        return scope
    return None


def _shape(sql):
    if not isinstance(sql, str):
        return None
    match = re.fullmatch(r"SELECT\s+(?P<columns>.+?)\s+FROM\s+CLOUD_VOLUME(?:\s+(?:AS\s+)?(?P<table_alias>" + _IDENTIFIER + r"))?",
                         sql.strip().removesuffix(";").strip(), re.I)
    if not match:
        return None
    prefixes = {"cloud_volume"}
    if match["table_alias"]:
        prefixes.add(match["table_alias"].casefold())
    outputs = []
    for expression in match["columns"].split(","):
        column = re.fullmatch(r"\s*(?:(?P<prefix>" + _IDENTIFIER + r")\.)?(?P<field>name|size|status)\s+AS\s+(?P<alias>" + _IDENTIFIER + r")\s*", expression, re.I)
        if not column or column["prefix"] and column["prefix"].casefold() not in prefixes:
            return None
        outputs.append({"field": column["field"].casefold(), "alias": column["alias"]})
    aliases = [output["alias"].casefold() for output in outputs]
    if (len(outputs) != 3 or {output["field"] for output in outputs} != {"name", "size", "status"}
            or len(set(aliases)) != 3 or set(aliases) & _METADATA_COLUMNS):
        return None
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE CLOUD_VOLUME (name TEXT,size TEXT,status TEXT)")
            connection.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return None
    return {"base_table": "CLOUD_VOLUME", "outputs": outputs}


def _endpoint(call):
    if (not isinstance(call, dict) or call.get("method", "GET") != "GET"
            or set(call) - {"method", "url", "condition", "autoPagination"}
            or "autoPagination" in call and type(call["autoPagination"]) is not bool
            or not isinstance(call.get("url"), str)):
        return None
    try:
        url = urlsplit(call["url"])
        match = re.fullmatch(r"/rest/hackthon/db/instances/([A-Za-z_][A-Za-z0-9_]*)", url.path)
        pairs = parse_qsl(url.query, strict_parsing=True)
        query = dict(pairs)
        if (not match or url.scheme or url.netloc or url.fragment or len(query) != len(pairs)
                or set(query) - {"pageNo", "pageSize"} or int(query.get("pageNo", "1")) != 1
                or not 1 <= int(query.get("pageSize", "10000")) <= 10000):
            return None
        return match[1] if match[1] in _TABLES else None
    except ValueError:
        return None


def _api_contract(item, scope):
    if not isinstance(item, dict) or not isinstance(item.get("api_call"), list) or len(item["api_call"]) != 3:
        return None
    calls = item["api_call"]
    resources = [_endpoint(call) for call in calls]
    if len(set(resources)) != 3 or set(resources) != set(_TABLES):
        return None
    for call in calls:
        condition = call.get("condition")
        if (not isinstance(condition, dict) or set(condition) != {"constraint"}
                or not isinstance(condition["constraint"], list) or len(condition["constraint"]) != len(scope)):
            return None
        found = []
        for entry in condition["constraint"]:
            if (not isinstance(entry, dict) or set(entry) - {"simple", "logOp"} or entry.get("logOp", "and") != "and"
                    or not isinstance(entry.get("simple"), dict) or set(entry["simple"]) - {"name", "value", "operator"}):
                return None
            simple = entry["simple"]
            field = simple.get("name")
            if (not isinstance(field, str) or field not in scope or field in found
                    or simple.get("operator", "equal") != "equal"
                    or simple.get("value") not in (scope[field], "{{" + field + "}}")):
                return None
            found.append(field)
        if set(found) != set(scope):
            return None
    return resources


def _schema(scope):
    return {ci: fields + (["logicalRegionName"] if "logicalRegionName" in scope else []) for ci, fields in _FIELDS.items()}


def _plan_contract(proposed):
    return (isinstance(proposed, dict) and proposed.get("kind") == "parallel_resource_lists"
            and isinstance(proposed.get("scope_values"), dict)
            and proposed.get("schema") == _schema(proposed["scope_values"])
            and proposed.get("base_shape") == _shape(proposed.get("base_sql"))
            and proposed.get("resources") == [{"ci": ci, "table": table, "label": _LABELS[ci]} for ci, table in _TABLES.items()])


def compose(sql, proposed):
    """卷明细逐行，独立ECS/VPC清单完整置于首行JSON；不推断三者关联。"""
    shape = _shape(sql)
    if not _plan_contract(proposed) or shape is None or shape != proposed["base_shape"]:
        return None
    volume = ["d." + output["field"] + ' AS "' + output["alias"] + '"' for output in shape["outputs"]]
    missing = ['NULL AS "' + output["alias"] + '"' for output in shape["outputs"]]
    projected = ','.join('a."'+output['alias']+'"' for output in shape['outputs'])
    first = 'a.resource_id IS (SELECT id FROM CLOUD_VOLUME ORDER BY id LIMIT 1)'
    return ("WITH b_anchor AS (SELECT " + ",".join(volume) + ",d.id AS resource_id FROM CLOUD_VOLUME d "
            "UNION ALL SELECT " + ",".join(missing) + ",NULL WHERE NOT EXISTS(SELECT 1 FROM CLOUD_VOLUME) "
            "AND (EXISTS(SELECT 1 FROM CLOUD_VM_NOVA) OR EXISTS(SELECT 1 FROM CLOUD_ROUTER))) SELECT " +
            projected + ",CASE WHEN a.resource_id IS NULL THEN 'summary_only' ELSE 'Volume' END AS resource_type,"
            "a.resource_id,CASE WHEN " + first + " THEN (SELECT json_group_array(json_object("
            "'vm_id',v.id,'vm_name',v.name,'vm_ip',v.privateIps)) FROM CLOUD_VM_NOVA v) END AS ecs_list_json,"
            "CASE WHEN " + first + " THEN (SELECT json_group_array(json_object('vpc_id',r.id,'vpc_name',r.name)) "
            "FROM CLOUD_ROUTER r) END AS vpc_list_json FROM b_anchor a ORDER BY a.resource_id")


def _schema_proof(sql, schema):
    if any(not set(fields) <= set(m._schema_columns.get(ci, [])) for ci, fields in schema.items()):
        return False
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            for ci, fields in schema.items():
                connection.execute('CREATE TABLE "' + _TABLES[ci] + '" (' +
                                   ','.join('"' + field + '" TEXT' for field in fields) + ')')
            connection.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return False
    return True


def plan(question, item):
    scope, shape = _scope(question), _shape(item.get("sql") if isinstance(item, dict) else None)
    if scope is None or shape is None:
        return None
    resources = _api_contract(item, scope)
    if resources is None:
        return None
    proposed = {"kind": "parallel_resource_lists", "item": copy.deepcopy(item), "base_sql": item["sql"],
                "base_shape": shape, "base_tables": ["CLOUD_VOLUME"], "scope_values": scope, "schema": _schema(scope),
                "resources": [{"ci": ci, "table": table, "label": _LABELS[ci]} for ci, table in _TABLES.items()],
                "call_resources": resources, "coverage_policy": "all rows from all three same-scope CIs; no inferred attachment or VPC relationship",
                "output_layout": "volume detail rows; complete independent ECS/VPC JSON lists on first row; labeled carrier if no volumes",
                "null_policy": "nonfirst list cells NULL; empty lists are JSON []; summary_only carrier is not a volume"}
    sql = compose(item["sql"], proposed)
    if sql is None or not _schema_proof(sql, proposed["schema"]):
        return None
    proposed["preview_sql"] = sql
    return proposed


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def validate(question, filled_item, proposed):
    checks = []

    def result(valid, reason, **details):
        return {"valid": valid, "reason": reason, "tables": checks, **details}

    if (not isinstance(filled_item, dict) or not _plan_contract(proposed)
            or _scope(question) != proposed.get("scope_values") or compose(filled_item.get("sql"), proposed) is None
            or proposed.get("preview_sql") != compose(proposed.get("base_sql"), proposed)
            or not _schema_proof(proposed["preview_sql"], proposed["schema"])):
        return result(False, "parallel_scope_schema_or_shape_changed")
    try:
        if (_api_contract(proposed["item"], proposed["scope_values"]) != proposed["call_resources"]
                or proposed["item"].get("sql") != proposed["base_sql"]):
            return result(False, "invalid_parallel_api_plan")
        expected = copy.deepcopy(proposed["item"]["api_call"])
        for call in expected:
            for entry in call["condition"]["constraint"]:
                field = entry["simple"]["name"]
                if entry["simple"]["value"] == "{{" + field + "}}":
                    entry["simple"]["value"] = proposed["scope_values"][field]
        if filled_item.get("api_call") != expected:
            return result(False, "parallel_api_scope_changed_or_unresolved")
    except (KeyError, TypeError):
        return result(False, "invalid_parallel_api_plan")
    counts = {}
    for ci, call in zip(proposed["call_resources"], expected):
        try:
            rows, table = m._execute_lookup_api(call)
        except Exception as exc:
            return result(False, "parallel_lookup_failed", ci=ci, error_type=type(exc).__name__)
        checks.append({"ci": ci, "table": table, "rows": len(rows) if isinstance(rows, list) else None})
        if table != _TABLES[ci]:
            return result(False, "parallel_resource_mismatch", ci=ci)
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
            return result(False, "empty_or_invalid_parallel_resource", ci=ci)
        if any(any(field not in row for field in proposed["schema"][ci]) for row in rows):
            return result(False, "missing_parallel_field", ci=ci)
        for field in proposed["schema"][ci]:
            if field == "size":
                if any(_number(row[field]) is None for row in rows):
                    return result(False, "invalid_parallel_volume_size", ci=ci)
            elif any(not isinstance(row[field], str) or not row[field].strip() for row in rows):
                return result(False, "invalid_parallel_text_field", ci=ci, field=field)
        if len({row["id"] for row in rows}) != len(rows):
            return result(False, "duplicate_parallel_identity", ci=ci)
        if any(any(row[field] != value for field, value in proposed["scope_values"].items()) for row in rows):
            return result(False, "parallel_resource_scope_mismatch", ci=ci)
        counts[_LABELS[ci]] = len(rows)
    return result(True, "verified_complete_parallel_lists", resource_counts=counts,
                  expected_output_rows=counts['Volume'], identity_key=["resource_type", "resource_id"],
                  independent_list_identity_keys={"ecs_list_json":"vm_id","vpc_list_json":"vpc_id"})
