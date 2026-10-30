"""具名区域的逐VPC子网统计；已解析对象与未解析引用透明分列。"""

import copy
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from urllib.parse import parse_qsl, urlsplit

import runbook_matcher as m


_TABLES = {"ROUTER": "CLOUD_ROUTER", "PORT": "CLOUD_PORT",
           "R_PORT_IN_SUBNET": "R_PORT_IN_SUBNET", "SUBNET": "CLOUD_SUBNET"}
_FIELDS = {"ROUTER": ["id", "nativeId", "logicalRegionName", "vdcName", "name"],
           "PORT": ["id", "devNativeId"], "R_PORT_IN_SUBNET": ["portId", "subnetId"], "SUBNET": ["id"]}
_EDGES = [("CLOUD_ROUTER.nativeId", "CLOUD_PORT.devNativeId"),
          ("CLOUD_PORT.id", "R_PORT_IN_SUBNET.portId"),
          ("R_PORT_IN_SUBNET.subnetId", "CLOUD_SUBNET.id")]
_COUNTS = ["resolved_subnet_count", "referenced_subnet_count", "unresolved_subnet_count"]
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_ALIAS = r"(?!(?:INNER|LEFT|RIGHT|FULL|CROSS|JOIN|ON|WHERE|GROUP|ORDER|LIMIT)\b)" + _IDENTIFIER


def _shape(sql, augmented=False):
    """只识别单表平面明细投影；COUNT、聚合、表达式和别名变化不猜。"""
    if not isinstance(sql, str):
        return None
    text = sql.strip().removesuffix(";").strip()
    match = re.fullmatch(r"SELECT\s+(?P<columns>.+?)\s+FROM\s+(?P<from>CLOUD_ROUTER"
                         r"(?:\s+(?:AS\s+)?(?P<table_alias>" + _ALIAS + r"))?)", text, re.I | re.S)
    if not match:
        return None
    expected = [("vdcname", "vdcname"), ("name", "vpc_name")]
    if augmented:
        expected += [("id", "vpc_id"), ("nativeid", "vpc_native_id")]
    expressions = match["columns"].split(",")
    if len(expressions) != len(expected):
        return None
    prefix = (match["table_alias"] or "CLOUD_ROUTER").casefold()
    outputs = []
    for expression, (field, alias) in zip(expressions, expected):
        selected = re.fullmatch(r"\s*(?:(?P<prefix>" + _IDENTIFIER + r")\.)?(?P<field>" +
                                _IDENTIFIER + r")(?:\s+AS\s+(?P<alias>" + _IDENTIFIER + r"))?\s*", expression, re.I)
        if (not selected or selected["field"].casefold() != field
                or (selected["prefix"] and selected["prefix"].casefold() != prefix)
                or (selected["alias"] or selected["field"]).casefold() != alias):
            return None
        outputs.append(alias)
    return {"table": "CLOUD_ROUTER", "mode": "vpc_identity_details" if augmented else "vpc_display_details",
            "output_columns": outputs}


def _scope(question):
    if not isinstance(question, str):
        return None
    regions = set(re.findall(r"(?<![A-Za-z0-9_])region_[A-Za-z0-9_\-]+", question))
    if len(regions) != 1:
        return None
    region = next(iter(regions))
    if len(region) > 256:
        return None
    visible = question.replace(region, " ")
    per_vpc = re.search(r"(?:各|每个?)\s*VPC|各\s*VDC.{0,16}VPC(?:名称|名|列表)?", visible, re.I)
    visible = re.sub(r"各\s*VDC(?:的|下|中)?", " ", visible, flags=re.I)
    if (not per_vpc or not re.search(r"区域|logicalRegionName", question, re.I)
            or not re.search(r"子网(?:的)?(?:数量|总数|个数)|多少(?:个)?子网", visible)
            or re.search(r"租户|tenant|VDC|可用区|azoneName|\baz\d|状态|正常|异常|运行|停止|"
                         r"最多|最少|排名|\btop\b|前\s*\d|CIDR|安全组|ELB|弹性IP|云硬盘|"
                         r"虚拟机|ECS|宿主机|物理|networkId|子网名|子网列表", visible, re.I)
            or re.search(r"VPC\s*(?:名称为|名为|为|[:：=]|[\"“‘「])|VPC[A-Za-z0-9_@]|"
                         r"(?:nativeId|resId|\bid|\bname)\s*[:：=]", visible, re.I)):
        return None
    return {"logicalRegionName": region}


def _endpoint(call):
    if (not isinstance(call, dict) or call.get("method", "GET") != "GET"
            or set(call) - {"method", "url", "condition"} or not isinstance(call.get("url"), str)):
        return None
    try:
        url = urlsplit(call["url"])
        pairs = parse_qsl(url.query, strict_parsing=True)
        query = dict(pairs)
        if (url.scheme or url.netloc or url.fragment or len(pairs) != len(query)
                or set(query) - {"pageNo", "pageSize"} or int(query.get("pageNo", "1")) != 1
                or not 1 <= int(query.get("pageSize", "10000")) <= 10000):
            return None
    except ValueError:
        return None
    match = re.fullmatch(r"/rest/hackthon/db/(instances|relations)/([A-Za-z_][A-Za-z0-9_]*)", url.path)
    if not match or match[2] not in _TABLES:
        return None
    return match[2] if match[1] == ("relations" if match[2].startswith("R_") else "instances") else None


def _region_filter(call):
    condition = call.get("condition")
    if not isinstance(condition, dict) or set(condition) != {"constraint"}:
        return None
    constraints = condition["constraint"]
    if not isinstance(constraints, list) or len(constraints) != 1:
        return None
    entry = constraints[0]
    if not isinstance(entry, dict) or set(entry) - {"simple", "logOp"} or entry.get("logOp", "and") != "and":
        return None
    simple = entry.get("simple")
    if (not isinstance(simple, dict) or set(simple) - {"name", "value", "operator"}
            or simple.get("name") != "logicalRegionName" or simple.get("operator", "equal") != "equal"):
        return None
    return simple.get("value")


def _lookup(ci):
    endpoint = "relations" if ci.startswith("R_") else "instances"
    return {"method": "GET", "url": "/rest/hackthon/db/" + endpoint + "/" + ci + "?pageNo=1&pageSize=10000"}


def _schema_proof(sql):
    relations = re.sub(r"\s+", "", getattr(m, "JOIN_RELATIONS", "")).casefold()
    if any(left.casefold() + "=" + right.casefold() not in relations
           and right.casefold() + "=" + left.casefold() not in relations for left, right in _EDGES):
        return False
    if any(not set(fields) <= set(m._schema_columns.get(ci, [])) for ci, fields in _FIELDS.items()):
        return False
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            for ci, fields in _FIELDS.items():
                connection.execute('CREATE TABLE "' + _TABLES[ci] + '" (' +
                                   ','.join('"' + field + '" TEXT' for field in fields) + ')')
            connection.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return False
    return True


def compose_vpc(base_sql, plan):
    """先按设备原生ID独立聚合，再LEFT JOIN逐VPC基表；空引用不算真实子网。"""
    shape = _shape(base_sql, augmented=True)
    if (not isinstance(plan, dict) or plan.get("kind") != "transparent_vpc_subnet_counts"
            or shape is None or shape != plan.get("base_shape")
            or plan.get("schema") != _FIELDS or plan.get("count_aliases") != _COUNTS):
        return None
    counts = ("SELECT p.devNativeId AS vpc_native_key,COUNT(DISTINCT s.id) AS resolved_subnet_count,"
              "COUNT(DISTINCT NULLIF(r.subnetId,'')) AS referenced_subnet_count,"
              "COUNT(DISTINCT CASE WHEN s.id IS NULL THEN NULLIF(r.subnetId,'') END) AS unresolved_subnet_count "
              "FROM CLOUD_PORT AS p LEFT JOIN R_PORT_IN_SUBNET AS r ON p.id=r.portId "
              "LEFT JOIN CLOUD_SUBNET AS s ON r.subnetId=s.id GROUP BY p.devNativeId")
    additions = ','.join("COALESCE(vpc_counts." + alias + ",0) AS " + alias for alias in _COUNTS)
    return ("SELECT vpc_base.*," + additions + " FROM (" + base_sql.strip().removesuffix(';').strip() +
            ") AS vpc_base LEFT JOIN (" + counts + ") AS vpc_counts "
            "ON vpc_base.vpc_native_id=vpc_counts.vpc_native_key")


def plan_vpc(question, item):
    """只补有明确区域的逐VPC子网数量；原区域过滤保留，lookup不发依赖ID长URL。"""
    if not isinstance(item, dict):
        return None
    shape, scope = _shape(item.get("sql")), _scope(question)
    if shape is None or scope is None:
        return None
    calls = item.get("api_call")
    calls = [calls] if isinstance(calls, dict) else calls
    if (not isinstance(calls, list) or len(calls) not in {1, 2}
            or _endpoint(calls[0]) != "ROUTER"
            or _region_filter(calls[0]) not in ["{{logicalRegionName}}", scope["logicalRegionName"]]
            or len(calls) == 2 and calls[0] != calls[1]):
        return None
    parts = re.fullmatch(r"\s*SELECT\s+(.+?)\s+FROM\s+(.+?)\s*;?\s*", item["sql"], re.I | re.S)
    from_text = parts[2].strip().removesuffix(';').strip()
    alias_match = re.fullmatch(r"CLOUD_ROUTER(?:\s+(?:AS\s+)?(" + _ALIAS + r"))?", from_text, re.I)
    prefix = (alias_match[1] or "CLOUD_ROUTER") + "."
    base_sql = ("SELECT " + parts[1].strip() + "," + prefix + "id AS vpc_id," +
                prefix + "nativeId AS vpc_native_id FROM " + from_text)
    updated = copy.deepcopy(item)
    updated["api_call"] = [copy.deepcopy(calls[0])] + [_lookup(ci) for ci in list(_TABLES)[1:]]
    updated["sql"] = base_sql
    plan = {"kind": "transparent_vpc_subnet_counts", "item": updated, "original_sql": item["sql"],
            "base_sql": base_sql, "base_shape": _shape(base_sql, augmented=True),
            "base_tables": ["CLOUD_ROUTER"], "scope_values": scope, "schema": copy.deepcopy(_FIELDS),
            "count_aliases": list(_COUNTS), "deduplicated_root_calls": len(calls) - 1,
            "resources": [{"ci": ci, "table": table, "role": "scope" if ci == "ROUTER" else "lookup"}
                          for ci, table in _TABLES.items()]}
    preview = compose_vpc(base_sql, plan)
    if preview is None or not _schema_proof(preview):
        return None
    plan["preview_sql"] = preview
    return plan


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _data_quality(observed):
    routers, ports, relations, subnets = (observed[ci] for ci in _TABLES)
    port_ids, subnet_ids = {row["id"] for row in ports}, {row["id"] for row in subnets}
    port_by_native, refs_by_port = defaultdict(set), defaultdict(set)
    for row in ports:
        if _nonempty(row["devNativeId"]):
            port_by_native[row["devNativeId"]].add(row["id"])
    for row in relations:
        if _nonempty(row["portId"]) and row["subnetId"] not in {None, ""}:
            refs_by_port[row["portId"]].add(row["subnetId"])
    unresolved, occurrence_count, samples, max_count = set(), 0, [], 0
    affected_vpcs = 0
    for router in routers:
        refs = set().union(*(refs_by_port[port] for port in port_by_native[router["nativeId"]]))
        dangling = refs - subnet_ids
        if dangling:
            affected_vpcs += 1
            unresolved.update(dangling)
            occurrence_count += len(dangling)
            max_count = max(max_count, len(dangling))
            if len(samples) < 8:
                samples.append({"vpc_id": router["id"], "unresolved_subnet_count": len(dangling),
                                "sample_subnet_ids": sorted(dangling)[:8]})
    return {"scoped_vpcs": len(routers), "vpcs_with_unresolved_subnets": affected_vpcs,
            "scoped_unresolved_reference_count": occurrence_count,
            "scoped_unique_unresolved_subnet_ids": len(unresolved), "max_unresolved_per_vpc": max_count,
            "sample_unresolved_references": samples,
            "blank_port_device_keys": sum(not _nonempty(row["devNativeId"]) for row in ports),
            "blank_relation_port_keys": sum(not _nonempty(row["portId"]) for row in relations),
            "blank_relation_subnet_keys": sum(row["subnetId"] in {None, ""} for row in relations),
            "duplicate_port_rows": len(ports) - len(port_ids),
            "duplicate_subnet_rows": len(subnets) - len(subnet_ids),
            "orphan_relation_port_ids": len({row["portId"] for row in relations if _nonempty(row["portId"])} - port_ids),
            "global_unresolved_subnet_ids": len({row["subnetId"] for row in relations
                                                 if row["subnetId"] not in {None, ""}} - subnet_ids)}


def validate_vpc(question, filled_item, plan):
    """独立原生GET核对区域、身份和字段；悬空引用明确诊断，不补造对象。"""
    checks = []

    def result(valid, reason, **values):
        return {"valid": valid, "reason": reason, "tables": checks, **values}

    if (not isinstance(plan, dict) or not isinstance(filled_item, dict)
            or _scope(question) != plan.get("scope_values")
            or compose_vpc(filled_item.get("sql"), plan) is None
            or plan.get("preview_sql") != compose_vpc(plan.get("base_sql"), plan)
            or not _schema_proof(plan["preview_sql"])):
        return result(False, "vpc_scope_schema_or_shape_changed")
    try:
        expected = copy.deepcopy(plan["item"]["api_call"])
        expected[0]["condition"]["constraint"][0]["simple"]["value"] = plan["scope_values"]["logicalRegionName"]
        if (len(expected) != 4 or [_endpoint(call) for call in expected] != list(_TABLES)
                or _region_filter(expected[0]) != plan["scope_values"]["logicalRegionName"]
                or expected[1:] != [_lookup(ci) for ci in list(_TABLES)[1:]]
                or filled_item.get("api_call") != expected):
            return result(False, "vpc_api_scope_changed_or_unresolved")
    except (KeyError, IndexError, TypeError):
        return result(False, "invalid_vpc_plan")
    observed = {}
    for step, (ci, table) in enumerate(_TABLES.items(), 1):
        try:
            records, actual_table = m._execute_lookup_api(expected[step - 1])
        except Exception as exc:
            return result(False, "vpc_lookup_failed", step=step, error_type=type(exc).__name__)
        if actual_table != table:
            return result(False, "vpc_resource_mismatch", step=step)
        if not records:
            return result(False, "empty_vpc_resource", step=step)
        if (not isinstance(records, list) or any(not isinstance(row, dict) for row in records)
                or any(not set(_FIELDS[ci]) <= row.keys() for row in records)):
            return result(False, "missing_vpc_resource_field", step=step)
        if any(row[field] is not None and not isinstance(row[field], str)
               for row in records for field in _FIELDS[ci]):
            return result(False, "invalid_vpc_resource_field_type", step=step)
        identities = ["id", "nativeId"] if ci == "ROUTER" else ["id"] if ci in {"PORT", "SUBNET"} else []
        for field in identities:
            if any(not _nonempty(row[field]) for row in records):
                return result(False, "empty_vpc_identity", step=step, field=field)
            if ci == "ROUTER" and len({row[field] for row in records}) != len(records):
                return result(False, "duplicate_vpc_identity", step=step, field=field)
        if ci == "PORT":
            owners = defaultdict(set)
            for row in records:
                owners[row["id"]].add(row["devNativeId"])
            if any(len(values) != 1 for values in owners.values()):
                return result(False, "conflicting_port_device_identity", step=step)
        if ci == "ROUTER" and any(row["logicalRegionName"] != plan["scope_values"]["logicalRegionName"] for row in records):
            return result(False, "vpc_region_value_mismatch", step=step)
        checks.append({"step": step, "ci": ci, "table": table, "rows": len(records),
                       "role": "scope" if ci == "ROUTER" else "lookup", "required_fields": list(_FIELDS[ci])})
        observed[ci] = records
    return result(True, "verified_transparent_vpc_subnet_counts", data_quality=_data_quality(observed))
