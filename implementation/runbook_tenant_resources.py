"""显式区域内按tenantName独立统计VM、卷和规格；不依赖挂载覆盖。"""

import copy
import json
import math
import re
import sqlite3
from contextlib import closing
from urllib.parse import parse_qsl, quote, urlsplit

import runbook_executor as executor
import runbook_matcher as m


_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_TABLES = {"VM_NOVA": "CLOUD_VM_NOVA", "VOLUME": "CLOUD_VOLUME", "FLAVOR": "CLOUD_FLAVOR"}
_FIELDS = {"VM_NOVA": ["id", "tenantName", "flavorId", "logicalRegionName"],
           "VOLUME": ["id", "tenantName", "size", "logicalRegionName"],
           "FLAVOR": ["id", "name", "vcpuSize", "ramSize", "diskSize"]}
_ADDED_COLUMNS = ("volume_count", "total_volume_size", "flavor_distribution", "unresolved_flavor_vm_count",
                  "row_kind", "volume_only_tenants_json")
_MAX_REQUEST_BYTES = 60000
_MAX_ID_LENGTH = 256


def _scope(question):
    if not isinstance(question, str):
        return None
    match = re.fullmatch(
        r"\s*(?:查询|统计)?\s*区域\s*(region_[A-Za-z0-9_\-]+)\s*(?:下|中|内)\s*"
        r"(?:各租户(?:的)?|按租户(?:统计)?)\s*(.*?)\s*[。?？]?\s*", question, re.I)
    if not match or len(match[1]) > _MAX_ID_LENGTH:
        return None
    roles = {"ECS实例数量": "vm_count", "ECS数量": "vm_count", "虚拟机数量": "vm_count",
             "云硬盘数量": "volume_count", "云硬盘总容量": "volume_size",
             "ECS规格分布": "flavors", "虚拟机规格分布": "flavors"}
    parts = [part.strip() for part in re.split(r"[、,，/]|和|与|及", match[2])]
    normalized = {key.casefold(): value for key, value in roles.items()}
    requested = [normalized.get(part.casefold()) for part in parts]
    if len(requested) != 4 or set(requested) != {"vm_count", "volume_count", "volume_size", "flavors"}:
        return None
    return {"logicalRegionName": match[1]}


def _shape(sql):
    if not isinstance(sql, str):
        return None
    field = r"(?:" + _IDENTIFIER + r"\.)?tenantName"
    match = re.fullmatch(
        r"SELECT\s+(?P<key>" + field + r")\s*,\s*COUNT\s*\(\s*\*\s*\)\s+AS\s+"
        r"(?P<count_alias>" + _IDENTIFIER + r")\s+FROM\s+CLOUD_VM_NOVA"
        r"(?:\s+(?:AS\s+)?(?P<table_alias>" + _IDENTIFIER + r"))?\s+GROUP\s+BY\s+"
        r"(?P<group>" + field + r")", sql.strip().removesuffix(";").strip(), re.I)
    if not match or match["count_alias"].casefold() in {name.casefold() for name in ("tenantName",) + _ADDED_COLUMNS}:
        return None
    prefixes = {"cloud_vm_nova"}
    if match["table_alias"]:
        prefixes.add(match["table_alias"].casefold())
    for role in ("key", "group"):
        prefix, separator, field_name = match[role].casefold().rpartition(".")
        if field_name != "tenantname" or separator and prefix not in prefixes:
            return None
    return {"base_table": "CLOUD_VM_NOVA", "group_field": "tenantName", "group_alias": "tenantName",
            "count_alias": match["count_alias"]}


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


def _constraints(call):
    if "condition" not in call:
        return []
    condition = call["condition"]
    if not isinstance(condition, dict) or set(condition) != {"constraint"} or not isinstance(condition["constraint"], list):
        return None
    result = []
    for entry in condition["constraint"]:
        if (not isinstance(entry, dict) or set(entry) - {"simple", "logOp"} or entry.get("logOp", "and") != "and"
                or not isinstance(entry.get("simple"), dict) or set(entry["simple"]) - {"name", "value", "operator"}):
            return None
        simple = entry["simple"]
        if not isinstance(simple.get("name"), str) or not isinstance(simple.get("operator", "equal"), str):
            return None
        result.append((simple.get("name"), simple.get("value"), simple.get("operator", "equal")))
    return result


def _api_plan(item, scope):
    if not isinstance(item, dict):
        return None
    calls = item.get("api_call")
    if not isinstance(calls, list) or len(calls) != 3:
        return None
    resources = [_endpoint(call) for call in calls]
    if len(set(resources)) != 3 or set(resources) != set(_TABLES):
        return None
    updated, dependency, added = copy.deepcopy(calls), None, False
    region_values = (scope["logicalRegionName"], "{{logicalRegionName}}")
    for index, (ci, call) in enumerate(zip(resources, calls)):
        constraints = _constraints(call)
        if constraints is None:
            return None
        if ci in {"VM_NOVA", "VOLUME"}:
            if not constraints and ci == "VOLUME":
                # 区域前缀覆盖整个列表；只补同字段过滤，不删除或替换任何已有条件。
                vm_condition = _constraints(calls[resources.index("VM_NOVA")])
                if (vm_condition is None or len(vm_condition) != 1 or vm_condition[0][0] != "logicalRegionName"
                        or vm_condition[0][1] not in region_values or vm_condition[0][2] != "equal"):
                    return None
                value = vm_condition[0][1]
                updated[index]["condition"] = {"constraint": [{"simple": {
                    "name": "logicalRegionName", "value": value, "operator": "equal"}}]}
                added = True
            elif (len(constraints) != 1 or constraints[0][0] != "logicalRegionName"
                  or constraints[0][1] not in region_values or constraints[0][2] != "equal"):
                return None
        elif constraints:
            if (index == 0 or resources[index - 1] != "VM_NOVA" or len(constraints) != 1
                    or constraints[0][0] != "id" or constraints[0][2] not in {"equal", "in"}
                    or constraints[0][1] != "{{flavorId from step " + str(index) + "}}"):
                return None
            dependency = {"source_step": index, "target_step": index + 1, "source_field": "flavorId", "target_field": "id"}
    return {"calls": updated, "call_resources": resources, "dependency": dependency, "volume_scope_added": added}


def _plan_contract(plan):
    return (isinstance(plan, dict) and plan.get("kind") == "tenant_resource_distribution"
            and plan.get("schema") == _FIELDS
            and plan.get("resources") == [{"ci": ci, "table": table} for ci, table in _TABLES.items()]
            and plan.get("base_shape") == _shape(plan.get("base_sql")))


def compose_tenants(base_sql, plan):
    """VM租户逐行，只有卷的租户完整放入JSON；NULL和空串仍为不同桶。"""
    shape = _shape(base_sql)
    if not _plan_contract(plan) or shape is None or shape != plan["base_shape"]:
        return None
    alias = shape["count_alias"]
    source = base_sql.strip().removesuffix(";").strip()
    specs = (
        "SELECT v.tenantName,v.flavorId,f.name AS flavor_name,f.vcpuSize,f.ramSize,f.diskSize,"
        "COUNT(*) AS n,CASE WHEN f.id IS NULL THEN 0 ELSE 1 END AS resolved "
        "FROM CLOUD_VM_NOVA AS v LEFT JOIN CLOUD_FLAVOR AS f ON v.flavorId=f.id "
        "GROUP BY v.tenantName,v.flavorId,f.id,f.name,f.vcpuSize,f.ramSize,f.diskSize")
    distribution = (
        "SELECT tenantName,json_group_array(json_object('flavor_id',flavorId,'flavor_name',flavor_name,"
        "'vcpu',vcpuSize,'ram',ramSize,'disk',diskSize,'ecs_count',n,'resolved',resolved)) AS flavor_distribution,"
        "SUM(CASE WHEN resolved=0 THEN n ELSE 0 END) AS unresolved_flavor_vm_count FROM (" + specs +
        ") AS tenant_specs GROUP BY tenantName")
    complete = (
        'SELECT tenant_domain.tenantName,COALESCE(tenant_base."' + alias + '",0) AS "' + alias + '",'
        "COALESCE(tenant_volumes.volume_count,0) AS volume_count,"
        "COALESCE(tenant_volumes.total_volume_size,0) AS total_volume_size,"
        "COALESCE(tenant_flavors.flavor_distribution,'[]') AS flavor_distribution,"
        "COALESCE(tenant_flavors.unresolved_flavor_vm_count,0) AS unresolved_flavor_vm_count "
        "FROM (SELECT tenantName FROM CLOUD_VM_NOVA UNION SELECT tenantName FROM CLOUD_VOLUME) AS tenant_domain "
        "LEFT JOIN (" + source + ') AS tenant_base ON tenant_base.tenantName IS tenant_domain.tenantName '
        "LEFT JOIN (SELECT tenantName,COUNT(*) AS volume_count,SUM(CAST(size AS REAL)) AS total_volume_size "
        "FROM CLOUD_VOLUME GROUP BY tenantName) AS tenant_volumes ON tenant_volumes.tenantName IS tenant_domain.tenantName "
        "LEFT JOIN (" + distribution + ") AS tenant_flavors ON tenant_flavors.tenantName IS tenant_domain.tenantName")
    columns = ['tenantName',alias,'volume_count','total_volume_size','flavor_distribution','unresolved_flavor_vm_count']
    quoted = lambda prefix: ','.join(prefix+'."'+name+'"' for name in columns)
    first = 'a.tenantName IS (SELECT tenantName FROM b_anchor ORDER BY tenantName LIMIT 1)'
    extra = ("SELECT json_group_array(json_object('tenantName',x.tenantName,'"+alias+"',x.\""+alias+"\","
             "'volume_count',x.volume_count,'total_volume_size',x.total_volume_size,"
             "'flavor_distribution',json(x.flavor_distribution),"
             "'unresolved_flavor_vm_count',x.unresolved_flavor_vm_count)) FROM b_complete x "
             "WHERE NOT EXISTS(SELECT 1 FROM CLOUD_VM_NOVA v WHERE v.tenantName IS x.tenantName)")
    return ('WITH b_complete AS ('+complete+'),b_anchor AS (SELECT '+quoted('c')+
            ",'vm_tenant' AS row_kind FROM b_complete c WHERE EXISTS(SELECT 1 FROM CLOUD_VM_NOVA v "
            'WHERE v.tenantName IS c.tenantName) UNION ALL SELECT '+','.join('NULL' for _ in columns)+
            ",'summary_only' WHERE NOT EXISTS(SELECT 1 FROM CLOUD_VM_NOVA) AND EXISTS(SELECT 1 FROM CLOUD_VOLUME)) "
            'SELECT '+quoted('a')+',a.row_kind,CASE WHEN '+first+' THEN ('+extra+
            ') END AS volume_only_tenants_json FROM b_anchor a ORDER BY a.tenantName')


def _schema_proof(sql):
    relationships = re.sub(r"\s+", "", getattr(m, "JOIN_RELATIONS", "")).casefold()
    edge = ("cloud_vm_nova.flavorid=cloud_flavor.id", "cloud_flavor.id=cloud_vm_nova.flavorid")
    if (not any(value in relationships for value in edge)
            or any(not set(fields) <= set(m._schema_columns.get(ci, [])) for ci, fields in _FIELDS.items())):
        return False
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            for ci, fields in _FIELDS.items():
                connection.execute('CREATE TABLE "' + _TABLES[ci] + '" (' +
                                   ','.join('"' + field + '" TEXT' for field in fields) + ')')
            connection.execute("SELECT json_group_array(json_object('proof',NULL))").fetchone()
            connection.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return False
    return True


def plan_tenants(question, item):
    if not isinstance(item, dict):
        return None
    scope, shape = _scope(question), _shape(item.get("sql"))
    if scope is None or shape is None:
        return None
    api = _api_plan(item, scope)
    if api is None:
        return None
    updated = copy.deepcopy(item)
    updated["api_call"] = api["calls"]
    plan = {"kind": "tenant_resource_distribution", "item": updated, "base_sql": item["sql"],
            "base_shape": shape, "base_tables": ["CLOUD_VM_NOVA"], "scope_values": scope,
            "resources": [{"ci": ci, "table": table} for ci, table in _TABLES.items()],
            "schema": copy.deepcopy(_FIELDS), "call_resources": api["call_resources"],
            "dependency": api["dependency"], "volume_scope_added": api["volume_scope_added"],
            "unknown_flavor_policy": "retain all VM rows; NULL or dangling flavor is an explicit unresolved bucket",
            "domain_policy": "complete VM/VOLUME tenantName union; VM tenant rows plus first-row JSON for volume-only groups; NULL and empty string separate"}
    sql = compose_tenants(item["sql"], plan)
    if sql is None or not _schema_proof(sql):
        return None
    plan["preview_sql"] = sql
    return plan


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _identity(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= _MAX_ID_LENGTH


def _dependency_bytes(call, values):
    ci = _endpoint(call)
    field, _, operator = _constraints(call)[0]
    values = sorted(values)
    value = values[0] if len(values) == 1 else values
    if len(values) > 1 or operator == "in":
        operator = "in"
    url = executor.BASE_URL + "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=" + str(executor.PAGE_SIZE)
    condition = {"constraint": [{"simple": {"name": field, "value": value, "operator": operator}}]}
    return len((url + "&condition=" + quote(json.dumps(condition, ensure_ascii=False))).encode())


def validate_tenants(question, filled_item, plan):
    """只用原GET读取三CI；全量验证、保留未知，不注入执行器缓存或改写数据。"""
    checks = []

    def result(valid, reason, **details):
        return {"valid": valid, "reason": reason, "tables": checks, **details}

    if (not isinstance(filled_item, dict) or not _plan_contract(plan)
            or _scope(question) != plan.get("scope_values")
            or compose_tenants(filled_item.get("sql"), plan) is None
            or plan.get("preview_sql") != compose_tenants(plan.get("base_sql"), plan)
            or not _schema_proof(plan["preview_sql"])):
        return result(False, "tenant_scope_schema_or_shape_changed")
    try:
        proposed = _api_plan(plan["item"], plan["scope_values"])
        if (proposed is None or proposed["call_resources"] != plan["call_resources"]
                or proposed["dependency"] != plan["dependency"] or plan["item"].get("sql") != plan["base_sql"]):
            return result(False, "invalid_tenant_api_plan")
        expected = copy.deepcopy(proposed["calls"])
        for call in expected:
            for entry in call.get("condition", {}).get("constraint", []):
                if entry["simple"].get("value") == "{{logicalRegionName}}":
                    entry["simple"]["value"] = plan["scope_values"]["logicalRegionName"]
        if filled_item.get("api_call") != expected:
            return result(False, "tenant_api_scope_changed_or_unresolved")
    except (KeyError, TypeError):
        return result(False, "invalid_tenant_api_plan")
    observed, previous = {}, None
    for index, (call, ci) in enumerate(zip(expected, plan["call_resources"]), 1):
        bound = None
        if plan["dependency"] and index == plan["dependency"]["target_step"]:
            bound = {row.get("flavorId") for row in previous if row.get("flavorId") not in (None, "")}
            if not bound:
                return result(False, "empty_tenant_flavor_dependency", step=index)
            if _dependency_bytes(call, bound) > _MAX_REQUEST_BYTES:
                return result(False, "tenant_flavor_dependency_too_large", step=index)
        try:
            records, table = m._execute_lookup_api(call, previous)
        except Exception as exc:
            return result(False, "tenant_resource_lookup_failed", ci=ci, error_type=type(exc).__name__)
        check = {"ci": ci, "table": table, "rows": len(records) if isinstance(records, list) else None}
        checks.append(check)
        if table != _TABLES[ci]:
            return result(False, "tenant_resource_mismatch", ci=ci)
        if not isinstance(records, list) or not records or any(not isinstance(row, dict) for row in records):
            return result(False, "empty_or_invalid_tenant_resource", ci=ci)
        if any(not any(field in row for row in records) for field in _FIELDS[ci]):
            return result(False, "tenant_loader_column_absent", ci=ci)
        if any(not _identity(row.get("id")) for row in records) or len({row["id"] for row in records}) != len(records):
            return result(False, "invalid_or_duplicate_tenant_identity", ci=ci)
        if ci in {"VM_NOVA", "VOLUME"}:
            if any(row.get("logicalRegionName") != plan["scope_values"]["logicalRegionName"] for row in records):
                return result(False, "tenant_resource_scope_mismatch", ci=ci)
            if any(row.get("tenantName") is not None and not isinstance(row["tenantName"], str) for row in records):
                return result(False, "invalid_tenant_name_type", ci=ci)
            check.update(null_tenant_rows=sum(row.get("tenantName") is None for row in records),
                         empty_tenant_rows=sum(row.get("tenantName") == "" for row in records))
        if ci == "VM_NOVA" and any(row.get("flavorId") not in (None, "") and not _identity(row["flavorId"]) for row in records):
            return result(False, "invalid_vm_flavor_reference", ci=ci)
        if ci == "VOLUME":
            amounts = [_number(row.get("size")) for row in records]
            if any(value is None for value in amounts) or not math.isfinite(sum(value for value in amounts if value is not None)):
                return result(False, "invalid_volume_size", ci=ci)
        if ci == "FLAVOR":
            if (any(not _identity(row.get("name")) for row in records)
                    or any(_number(row.get(field)) is None for row in records for field in ("vcpuSize", "ramSize", "diskSize"))):
                return result(False, "invalid_flavor_configuration", ci=ci)
            if bound is not None and not {row["id"] for row in records} <= bound:
                return result(False, "tenant_flavor_dependency_value_mismatch", ci=ci)
        previous, observed[ci] = records, records
    vms, volumes, flavors = (observed[ci] for ci in _TABLES)
    known_flavors = {row["id"] for row in flavors}
    vm_tenants = {row.get("tenantName") for row in vms}
    volume_tenants = {row.get("tenantName") for row in volumes}
    return result(True, "verified_independent_tenant_resources", vm_count=len(vms), volume_count=len(volumes),
                  tenant_domain_count=len(vm_tenants | volume_tenants), vm_tenant_group_count=len(vm_tenants),
                  volume_tenant_group_count=len(volume_tenants), volume_only_tenant_groups=len(volume_tenants - vm_tenants),
                  expected_output_rows=len(vm_tenants), volume_only_groups_retained_in_json=True,
                  missing_flavor_field_rows=sum("flavorId" not in row for row in vms),
                  null_or_empty_flavor_rows=sum(row.get("flavorId") in (None, "") for row in vms),
                  dangling_flavor_rows=sum(row.get("flavorId") not in (None, "") and row["flavorId"] not in known_flavors for row in vms),
                  unresolved_flavor_vm_count=sum(row.get("flavorId") not in known_flavors for row in vms),
                  total_volume_size=sum(_number(row["size"]) for row in volumes))
