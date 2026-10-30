"""同租户、同区域VM配置与卷完整明细；卷行含挂载VM，另列无范围内卷的VM。"""

import copy
import json
import math
import re
import sqlite3
from collections import Counter
from contextlib import closing
from urllib.parse import parse_qsl, quote, urlsplit

import runbook_executor as executor
import runbook_matcher as m


_ID = r"[A-Za-z_][A-Za-z0-9_]*"
_TABLES = {"VM_NOVA": "CLOUD_VM_NOVA", "FLAVOR": "CLOUD_FLAVOR", "VOLUME": "CLOUD_VOLUME",
           "R_VOLUME_MOUNTON_VM": "R_VOLUME_MOUNTON_VM"}
_FIELDS = {"VM_NOVA": ["id", "name", "flavorId", "tenantName", "logicalRegionName"],
           "FLAVOR": ["id", "name", "vcpuSize", "ramSize", "diskSize"],
           "VOLUME": ["id", "name", "size", "status", "tenantName", "logicalRegionName"],
           "R_VOLUME_MOUNTON_VM": ["vmId", "volumeId"]}
_EDGES = [("CLOUD_VM_NOVA.flavorId", "CLOUD_FLAVOR.id"),
          ("CLOUD_VM_NOVA.id", "R_VOLUME_MOUNTON_VM.vmId"),
          ("R_VOLUME_MOUNTON_VM.volumeId", "CLOUD_VOLUME.id")]
_EXTRA_COLUMNS = {"detail_kind", "volume_id", "vm_attachments"}
_MAX_ID_LENGTH = 256
_MAX_REQUEST_BYTES = 60000


def _scope(question):
    if not isinstance(question, str):
        return None
    entity = (r'(?:"(?P<double>[^"\n]+)"|“(?P<chinese>[^”\n]+)”|'
              r"'(?P<single>[^'\n]+)'|(?P<ascii>[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*))")
    region = r"(?P<region>region_[A-Za-z0-9_\-]+)"
    body = r"(?P<body>(?:ECS(?:实例)?|虚拟机(?:实例)?)(?:及|和|与)(?:规格|配置)[、,，]云硬盘列表(?:及|和|与)容量)"
    patterns = [r"\s*(?:查询|查看)?\s*租户\s*" + entity + r"\s*在区域\s*" + region + r"\s*(?:中|下|内)的?\s*" + body + r"[。?？]?\s*",
                r"\s*(?:查询|查看)?\s*区域\s*" + region + r"\s*(?:下|中|内)租户\s*" + entity + r"\s*的\s*" + body + r"[。?？]?\s*"]
    for pattern in patterns:
        match = re.fullmatch(pattern, question, re.I)
        if match:
            tenant = next(value for value in (match["double"], match["chinese"], match["single"], match["ascii"]) if value is not None)
            if (not tenant.strip() or len(tenant) > _MAX_ID_LENGTH or "{{" in tenant
                    or len(match["region"]) > _MAX_ID_LENGTH):
                return None
            return {"tenantName": tenant, "logicalRegionName": match["region"]}
    return None


def _shape(sql):
    if not isinstance(sql, str):
        return None
    text = sql.strip().removesuffix(";").strip()
    match = re.fullmatch(r"SELECT\s+(?P<outputs>.+?)\s+FROM\s+CLOUD_VOLUME(?:\s+(?:AS\s+)?(?P<table_alias>" + _ID + r"))?", text, re.I)
    if not match:
        return None
    prefixes = {"cloud_volume"}
    if match["table_alias"]:
        prefixes.add(match["table_alias"].casefold())
    outputs = []
    for expression in match["outputs"].split(","):
        part = re.fullmatch(r"\s*(?:(?P<prefix>" + _ID + r")\.)?(?P<field>name|size|status)\s+AS\s+(?P<alias>" + _ID + r")\s*", expression, re.I)
        if not part or part["prefix"] and part["prefix"].casefold() not in prefixes:
            return None
        outputs.append({"field": part["field"].casefold(), "alias": part["alias"]})
    aliases = [output["alias"].casefold() for output in outputs]
    if (len(outputs) != 3 or {output["field"] for output in outputs} != {"name", "size", "status"}
            or len(set(aliases)) != 3 or set(aliases) & _EXTRA_COLUMNS):
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
        match = re.fullmatch(r"/rest/hackthon/db/(instances|relations)/([A-Za-z_][A-Za-z0-9_]*)", url.path)
        pairs = parse_qsl(url.query, strict_parsing=True)
        query = dict(pairs)
        if (not match or url.scheme or url.netloc or url.fragment or len(pairs) != len(query)
                or set(query) - {"pageNo", "pageSize"} or int(query.get("pageNo", "1")) != 1
                or not 1 <= int(query.get("pageSize", "10000")) <= 10000):
            return None
        ci = match[2]
        return ci if ci in _TABLES and match[1] == ("relations" if ci.startswith("R_") else "instances") else None
    except ValueError:
        return None


def _constraints(call):
    if "condition" not in call:
        return []
    condition = call["condition"]
    if not isinstance(condition, dict) or set(condition) != {"constraint"} or not isinstance(condition["constraint"], list):
        return None
    values = []
    for entry in condition["constraint"]:
        if (not isinstance(entry, dict) or set(entry) - {"simple", "logOp"} or entry.get("logOp", "and") != "and"
                or not isinstance(entry.get("simple"), dict) or set(entry["simple"]) - {"name", "value", "operator"}):
            return None
        simple = entry["simple"]
        if not isinstance(simple.get("name"), str) or not isinstance(simple.get("operator", "equal"), str):
            return None
        values.append((simple["name"], simple.get("value"), simple.get("operator", "equal")))
    return values


def _api_contract(item, scope, expanded=False):
    if not isinstance(item, dict):
        return None
    calls = item.get("api_call")
    expected = set(_TABLES) if expanded else {"VM_NOVA", "FLAVOR", "VOLUME"}
    if not isinstance(calls, list) or len(calls) != len(expected):
        return None
    resources = [_endpoint(call) for call in calls]
    if set(resources) != expected or len(set(resources)) != len(resources):
        return None
    if expanded and resources[-1] != "R_VOLUME_MOUNTON_VM":
        return None
    dependency = None
    for index, (ci, call) in enumerate(zip(resources, calls)):
        conditions = _constraints(call)
        if conditions is None:
            return None
        if ci in {"VM_NOVA", "VOLUME"}:
            if len(conditions) != 2 or {condition[0] for condition in conditions} != set(scope):
                return None
            for field, value, operator in conditions:
                if operator != "equal" or value not in (scope[field], "{{" + field + "}}"):
                    return None
        elif ci == "FLAVOR" and conditions:
            if (index == 0 or resources[index - 1] != "VM_NOVA" or len(conditions) != 1
                    or conditions[0][0] != "id" or conditions[0][2] not in {"equal", "in"}
                    or conditions[0][1] != "{{flavorId from step " + str(index) + "}}"):
                return None
            dependency = {"source_step": index, "target_step": index + 1, "source_field": "flavorId"}
        elif ci == "R_VOLUME_MOUNTON_VM" and conditions:
            return None
    return {"resources": resources, "dependency": dependency}


def _plan_contract(plan):
    return (isinstance(plan, dict) and plan.get("kind") == "vm_volume_complete_details"
            and plan.get("schema") == _FIELDS and plan.get("base_shape") == _shape(plan.get("base_sql"))
            and plan.get("resources") == [{"ci": ci, "table": table} for ci, table in _TABLES.items()])


def _vm_object(prefix):
    return ("json_object('vm_id'," + prefix + ".vm_id,'vm_name'," + prefix + ".vm_name,"
            "'flavor_id'," + prefix + ".flavor_id,'flavor_name'," + prefix + ".flavor_name,"
            "'vcpu'," + prefix + ".vcpu,'ram'," + prefix + ".ram,'disk'," + prefix + ".disk,"
            "'flavor_resolved'," + prefix + ".flavor_resolved)")


def compose(base_sql, plan):
    """每卷一行+每个无范围内卷VM一行；多挂载在JSON内展开，绝不删无卷VM。"""
    shape = _shape(base_sql)
    if not _plan_contract(plan) or shape is None or shape != plan["base_shape"]:
        return None
    # 原base严格为单表三字段投影；加入id再关联不会按非唯一名称或容量匹配。
    volume_columns = ["d." + output["field"] + ' AS "' + output["alias"] + '"' for output in shape["outputs"]]
    null_columns = ['NULL AS "' + output["alias"] + '"' for output in shape["outputs"]]
    vm_fields = ("v.id AS vm_id,v.name AS vm_name,v.flavorId AS flavor_id,f.name AS flavor_name,"
                 "f.vcpuSize AS vcpu,f.ramSize AS ram,f.diskSize AS disk,"
                 "CASE WHEN f.id IS NULL THEN 0 ELSE 1 END AS flavor_resolved")
    mounted = ("SELECT DISTINCT r.volumeId AS volume_id," + vm_fields +
               " FROM R_VOLUME_MOUNTON_VM AS r INNER JOIN CLOUD_VM_NOVA AS v ON r.vmId=v.id "
               "LEFT JOIN CLOUD_FLAVOR AS f ON v.flavorId=f.id")
    attachments = ("SELECT volume_id,json_group_array(" + _vm_object("mounted_vm") + ") AS vm_attachments "
                   "FROM (" + mounted + ") AS mounted_vm GROUP BY volume_id")
    orphans = ("SELECT " + vm_fields + " FROM CLOUD_VM_NOVA AS v "
               "LEFT JOIN R_VOLUME_MOUNTON_VM AS r ON r.vmId=v.id "
               "LEFT JOIN CLOUD_VOLUME AS d ON r.volumeId=d.id "
               "LEFT JOIN CLOUD_FLAVOR AS f ON v.flavorId=f.id "
               "GROUP BY v.id,v.name,v.flavorId,f.id,f.name,f.vcpuSize,f.ramSize,f.diskSize HAVING COUNT(d.id)=0")
    return ("SELECT " + ",".join(volume_columns) + ",d.id AS volume_id,'volume' AS detail_kind,"
            "COALESCE(volume_vms.vm_attachments,'[]') AS vm_attachments FROM CLOUD_VOLUME AS d LEFT JOIN (" +
            attachments + ") AS volume_vms ON volume_vms.volume_id=d.id UNION ALL SELECT " +
            ",".join(null_columns) + ",NULL AS volume_id,'vm_without_scoped_volume' AS detail_kind,"
            "json_array(" + _vm_object("orphan_vm") + ") AS vm_attachments FROM (" + orphans + ") AS orphan_vm")


def _schema_proof(sql):
    relationships = re.sub(r"\s+", "", getattr(m, "JOIN_RELATIONS", "")).casefold()
    if (any(left.casefold() + "=" + right.casefold() not in relationships
            and right.casefold() + "=" + left.casefold() not in relationships for left, right in _EDGES)
            or any(not set(fields) <= set(m._schema_columns.get(ci, [])) for ci, fields in _FIELDS.items())):
        return False
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            for ci, fields in _FIELDS.items():
                connection.execute('CREATE TABLE "' + _TABLES[ci] + '" (' +
                                   ','.join('"' + field + '" TEXT' for field in fields) + ')')
            connection.execute("SELECT json_array(json_object('proof',NULL))").fetchone()
            connection.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return False
    return True


def plan(question, item):
    scope, shape = _scope(question), _shape(item.get("sql") if isinstance(item, dict) else None)
    if scope is None or shape is None:
        return None
    api = _api_contract(item, scope)
    if api is None:
        return None
    updated = copy.deepcopy(item)
    updated["api_call"].append({"method": "GET", "url": "/rest/hackthon/db/relations/R_VOLUME_MOUNTON_VM?pageNo=1&pageSize=10000"})
    result = {"kind": "vm_volume_complete_details", "item": updated, "base_sql": item["sql"],
              "base_shape": shape, "base_tables": ["CLOUD_VOLUME"], "scope_values": scope,
              "schema": copy.deepcopy(_FIELDS), "resources": [{"ci": ci, "table": table} for ci, table in _TABLES.items()],
              "call_resources": api["resources"] + ["R_VOLUME_MOUNTON_VM"], "dependency": api["dependency"],
              "relation_lookup_policy": "global paginated GET; no added ID-list dependency",
              "coverage_policy": "one row per scoped volume plus one row per VM with no scoped volume; preserve unknown flavor",
              "unresolved_relation_policy": "report references outside the retrieved scope as unresolved_or_out_of_scope; do not infer their objects"}
    sql = compose(item["sql"], result)
    if sql is None or not _schema_proof(sql):
        return None
    result["preview_sql"] = sql
    return result


def _identity(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= _MAX_ID_LENGTH


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _dependency_bytes(call, values):
    _, _, operator = _constraints(call)[0]
    values = sorted(values)
    value = values[0] if len(values) == 1 else values
    if len(values) > 1 or operator == "in":
        operator = "in"
    condition = {"constraint": [{"simple": {"name": "id", "value": value, "operator": operator}}]}
    url = executor.BASE_URL + "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=" + str(executor.PAGE_SIZE)
    return len((url + "&condition=" + quote(json.dumps(condition, ensure_ascii=False))).encode())


def validate(question, filled_item, proposed):
    """原生GET验证范围和身份；关联表全局读，未知规格与未挂载VM都保留。"""
    checks = []

    def result(valid, reason, **details):
        return {"valid": valid, "reason": reason, "tables": checks, **details}

    if (not isinstance(filled_item, dict) or not _plan_contract(proposed)
            or _scope(question) != proposed.get("scope_values")
            or compose(filled_item.get("sql"), proposed) is None
            or proposed.get("preview_sql") != compose(proposed.get("base_sql"), proposed)
            or not _schema_proof(proposed["preview_sql"])):
        return result(False, "vm_volume_scope_schema_or_shape_changed")
    try:
        api = _api_contract(proposed["item"], proposed["scope_values"], True)
        if (api is None or api["resources"] != proposed["call_resources"] or api["dependency"] != proposed["dependency"]
                or proposed["item"].get("sql") != proposed["base_sql"]):
            return result(False, "invalid_vm_volume_api_plan")
        expected = copy.deepcopy(proposed["item"]["api_call"])
        for call in expected:
            for entry in call.get("condition", {}).get("constraint", []):
                field = entry["simple"]["name"]
                if field in proposed["scope_values"] and entry["simple"].get("value") == "{{" + field + "}}":
                    entry["simple"]["value"] = proposed["scope_values"][field]
        if filled_item.get("api_call") != expected:
            return result(False, "vm_volume_api_scope_changed_or_unresolved")
    except (KeyError, TypeError):
        return result(False, "invalid_vm_volume_api_plan")
    observed, previous = {}, None
    for index, (ci, call) in enumerate(zip(proposed["call_resources"], expected), 1):
        bound = None
        if proposed["dependency"] and index == proposed["dependency"]["target_step"]:
            bound = {row.get("flavorId") for row in previous if row.get("flavorId") not in (None, "")}
            if not bound or _dependency_bytes(call, bound) > _MAX_REQUEST_BYTES:
                return result(False, "empty_or_oversized_vm_flavor_dependency", step=index)
        try:
            rows, table = m._execute_lookup_api(call, previous)
        except Exception as exc:
            return result(False, "vm_volume_lookup_failed", ci=ci, error_type=type(exc).__name__)
        checks.append({"ci": ci, "table": table, "rows": len(rows) if isinstance(rows, list) else None})
        if table != _TABLES[ci]:
            return result(False, "vm_volume_resource_mismatch", ci=ci)
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
            return result(False, "empty_or_invalid_vm_volume_resource", ci=ci)
        if any(not any(field in row for row in rows) for field in _FIELDS[ci]):
            return result(False, "vm_volume_loader_column_absent", ci=ci)
        if ci != "R_VOLUME_MOUNTON_VM":
            if any(not _identity(row.get("id")) for row in rows) or len({row["id"] for row in rows}) != len(rows):
                return result(False, "invalid_or_duplicate_vm_volume_identity", ci=ci)
            if any(not _text(row.get("name")) for row in rows):
                return result(False, "invalid_vm_volume_name", ci=ci)
        if ci in {"VM_NOVA", "VOLUME"}:
            if any(any(row.get(field) != value for field, value in proposed["scope_values"].items()) for row in rows):
                return result(False, "vm_volume_resource_scope_mismatch", ci=ci)
        if ci == "VM_NOVA" and any(row.get("flavorId") not in (None, "") and not _identity(row["flavorId"]) for row in rows):
            return result(False, "invalid_vm_flavor_reference", ci=ci)
        if ci == "VOLUME":
            amounts = [_number(row.get("size")) for row in rows]
            if (any(value is None for value in amounts) or not math.isfinite(sum(value for value in amounts if value is not None))
                    or any(row.get("status") is not None and not isinstance(row["status"], str) for row in rows)):
                return result(False, "invalid_volume_size_or_status", ci=ci)
        if ci == "FLAVOR":
            if any(_number(row.get(field)) is None for row in rows for field in ("vcpuSize", "ramSize", "diskSize")):
                return result(False, "invalid_flavor_configuration", ci=ci)
            if bound is not None and not {row["id"] for row in rows} <= bound:
                return result(False, "vm_flavor_dependency_value_mismatch", ci=ci)
        if ci == "R_VOLUME_MOUNTON_VM" and any(not _identity(row.get(field)) for row in rows for field in ("vmId", "volumeId")):
            return result(False, "invalid_mount_relation_key", ci=ci)
        observed[ci], previous = rows, rows
    vms, volumes, flavors, relations = (observed[ci] for ci in ("VM_NOVA", "VOLUME", "FLAVOR", "R_VOLUME_MOUNTON_VM"))
    vm_ids, volume_ids, flavor_ids = ({row["id"] for row in rows} for rows in (vms, volumes, flavors))
    pairs = {(row["vmId"], row["volumeId"]) for row in relations}
    same_scope = {(vm_id, volume_id) for vm_id, volume_id in pairs if vm_id in vm_ids and volume_id in volume_ids}
    mounted = {vm_id for vm_id, _ in same_scope}
    counts = Counter(volume_id for _, volume_id in same_scope)
    return result(True, "verified_complete_vm_volume_details", vm_count=len(vms), volume_count=len(volumes),
                  same_scope_mount_pairs=len(same_scope), mounted_vm_count=len(mounted),
                  vm_without_scoped_volume_count=len(vm_ids - mounted), expected_output_rows=len(volumes) + len(vm_ids - mounted),
                  per_volume_vm_count_distribution=dict(Counter(counts.get(volume_id, 0) for volume_id in volume_ids)),
                  duplicate_mount_pairs=len(relations) - len(pairs),
                  unresolved_or_out_of_scope_volume_references=sum(vm_id in vm_ids and volume_id not in volume_ids for vm_id, volume_id in pairs),
                  unresolved_or_out_of_scope_vm_references=sum(volume_id in volume_ids and vm_id not in vm_ids for vm_id, volume_id in pairs),
                  missing_flavor_field_rows=sum("flavorId" not in row for row in vms),
                  unresolved_flavor_vm_count=sum(row.get("flavorId") not in flavor_ids for row in vms))
