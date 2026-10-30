"""仅补全具名虚拟机的网卡数量及子网CIDR；保留原计数和原执行器。"""

import copy
import json
import re
import sqlite3
from contextlib import closing
from urllib.parse import parse_qsl, quote, urlsplit

import runbook_executor as executor
import runbook_matcher as m


_TABLES = {"VM_NOVA": "CLOUD_VM_NOVA", "PORT": "CLOUD_PORT",
           "R_PORT_IN_SUBNET": "R_PORT_IN_SUBNET", "SUBNET": "CLOUD_SUBNET"}
_FIELDS = {"VM_NOVA": ["name", "resId"], "PORT": ["id", "devId"],
           "R_PORT_IN_SUBNET": ["portId", "subnetId"], "SUBNET": ["id", "cidr"]}
_EDGES = [("CLOUD_VM_NOVA.resId", "CLOUD_PORT.devId"),
          ("CLOUD_PORT.id", "R_PORT_IN_SUBNET.portId"),
          ("R_PORT_IN_SUBNET.subnetId", "CLOUD_SUBNET.id")]
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_ALIAS = r"(?!(?:INNER|LEFT|RIGHT|FULL|CROSS|JOIN|ON|WHERE|GROUP|ORDER|LIMIT)\b)" + _IDENTIFIER
_DETAIL_ALIAS = "port_subnet_details"
_MAX_IDS = 128
_MAX_ID_LENGTH = 256
_MAX_REQUEST_BYTES = 60000


def _shape(sql):
    if not isinstance(sql, str):
        return None
    text = sql.strip().removesuffix(";").strip()
    count = r"SELECT\s+COUNT\s*\(\s*\*\s*\)\s+AS\s+port_count\s+FROM\s+"
    if re.fullmatch(count + r"CLOUD_PORT(?:\s+(?:AS\s+)?" + _ALIAS + r")?", text, re.I):
        return {"mode": "port_only", "count_alias": "port_count", "base_tables": ["CLOUD_PORT"]}
    match = re.fullmatch(
        count + r"CLOUD_VM_NOVA(?:\s+(?:AS\s+)?(?P<vm>" + _ALIAS + r"))?\s+"
        r"(?:INNER\s+)?JOIN\s+CLOUD_PORT(?:\s+(?:AS\s+)?(?P<port>" + _ALIAS + r"))?\s+ON\s+"
        r"(?P<left>" + _IDENTIFIER + r"\." + _IDENTIFIER + r")\s*=\s*"
        r"(?P<right>" + _IDENTIFIER + r"\." + _IDENTIFIER + r")", text, re.I)
    if not match:
        return None
    vm, port = match["vm"] or "CLOUD_VM_NOVA", match["port"] or "CLOUD_PORT"
    if vm.casefold() == port.casefold():
        return None
    expected = {(vm + ".resId").casefold(), (port + ".devId").casefold()}
    if {match["left"].casefold(), match["right"].casefold()} != expected:
        return None
    return {"mode": "vm_join_port", "count_alias": "port_count",
            "base_tables": ["CLOUD_VM_NOVA", "CLOUD_PORT"]}


def _scope(question):
    if not isinstance(question, str):
        return None
    entity = r"[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*"
    found = list(re.finditer(
        r"(?:ECS(?:实例)?|虚拟机(?:实例)?|VM\b)\s*(?:名称为|名为|名称|名)?\s*(?:为|是|[:：=])?\s*"
        r"(?:[\"“‘「]([^\"”’」]+)[\"”’」]|'([^']+)'|(" + entity + r"))", question, re.I))
    values = {next(value for value in match.groups() if value is not None) for match in found}
    if len(values) != 1:
        return None
    name = next(iter(values))
    if not name.strip() or len(name) > _MAX_ID_LENGTH or "{{" in name:
        return None
    visible = question
    for match in reversed(found):
        visible = visible[:match.start()] + "虚拟机" + visible[match.end():]
    if (not re.search(r"(?:几|多少).{0,3}网卡|网卡.{0,4}(?:数量|总数|个数|多少|几)", visible)
            or not re.search(r"子网\s*CIDR", visible, re.I)
            or not re.search(r"分别|对应|关联|每块|各网卡", visible)
            or re.search(r"所有|全部|每台|各虚拟机|区域|可用区|租户|tenant|\bvdc\b|region_|\baz\d|"
                         r"状态|运行中|停止|异常|VPC|路由|安全组|ELB|负载均衡|云硬盘|镜像|集群|"
                         r"宿主机|物理|Gauss|RDS|Pod|MAC|网卡名|IP地址", visible, re.I)):
        return None
    return {"name": name}


def _endpoint(call):
    if (not isinstance(call, dict) or call.get("method", "GET") != "GET"
            or set(call) - {"method", "url", "condition"} or not isinstance(call.get("url"), str)):
        return None
    try:
        url = urlsplit(call["url"])
    except ValueError:
        return None
    match = re.fullmatch(r"/rest/hackthon/db/(instances|relations)/([A-Za-z_][A-Za-z0-9_]*)", url.path)
    if not match or url.scheme or url.netloc or url.fragment:
        return None
    try:
        pairs = parse_qsl(url.query, strict_parsing=True)
        query = dict(pairs)
        if (len(query) != len(pairs) or set(query) - {"pageNo", "pageSize"}
                or int(query.get("pageNo", "1")) != 1
                or not 1 <= int(query.get("pageSize", "10000")) <= 10000):
            return None
    except ValueError:
        return None
    ci = match[2]
    return ci if ci in _TABLES and match[1] == ("relations" if ci.startswith("R_") else "instances") else None


def _constraint(call):
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
    if not isinstance(simple, dict) or set(simple) - {"name", "value", "operator"}:
        return None
    return simple.get("name"), simple.get("value"), simple.get("operator", "equal")


def _call(ci, field, source, operator="in"):
    endpoint = "relations" if ci.startswith("R_") else "instances"
    return {"method": "GET", "url": "/rest/hackthon/db/" + endpoint + "/" + ci + "?pageNo=1&pageSize=10000",
            "condition": {"constraint": [{"simple": {"name": field, "value": source, "operator": operator}}]}}


def _schema_proof(sql):
    text = re.sub(r"\s+", "", getattr(m, "JOIN_RELATIONS", "")).casefold()
    if any(left.casefold() + "=" + right.casefold() not in text
           and right.casefold() + "=" + left.casefold() not in text for left, right in _EDGES):
        return False
    if any(not set(fields) <= set(m._schema_columns.get(ci, [])) for ci, fields in _FIELDS.items()):
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


def compose_network(base_sql, plan):
    """计数来自精调后的原子查询；JSON明细在独立子查询中关联，永不放大计数。"""
    shape = _shape(base_sql)
    if (not isinstance(plan, dict) or plan.get("kind") != "vm_port_subnet_details"
            or shape is None or shape != plan.get("base_shape")
            or plan.get("details_alias") != _DETAIL_ALIAS or plan.get("schema") != _FIELDS):
        return None
    details = ("SELECT DISTINCT p.id AS port_id,r.subnetId AS subnet_id,s.cidr AS cidr "
               "FROM CLOUD_VM_NOVA AS v INNER JOIN CLOUD_PORT AS p ON v.resId=p.devId "
               "LEFT JOIN R_PORT_IN_SUBNET AS r ON p.id=r.portId "
               "LEFT JOIN CLOUD_SUBNET AS s ON r.subnetId=s.id ORDER BY p.id,r.subnetId,s.cidr")
    return ("SELECT network_base.port_count,(SELECT json_group_array(json_object("
            "'port_id',network_detail.port_id,'subnet_id',network_detail.subnet_id,'cidr',network_detail.cidr)) "
            "FROM (" + details + ") AS network_detail) AS " + _DETAIL_ALIAS +
            " FROM (" + base_sql.strip().removesuffix(';').strip() + ") AS network_base")


def plan_network(question, item):
    """只接受具名VM的原计数形状和已知API前缀，不读取题库或采用实体默认值。"""
    if not isinstance(item, dict):
        return None
    shape, scope = _shape(item.get("sql")), _scope(question)
    if shape is None or scope is None:
        return None
    calls = item.get("api_call")
    calls = [calls] if isinstance(calls, dict) else calls
    if (not isinstance(calls, list) or not calls
            or len(calls) != (1 if shape["mode"] == "vm_join_port" else 2)
            or _endpoint(calls[0]) != "VM_NOVA"
            or _constraint(calls[0]) not in [("name", "{{name}}", "equal"), ("name", scope["name"], "equal")]):
        return None
    if len(calls) == 2 and (_endpoint(calls[1]) != "PORT"
            or _constraint(calls[1]) != ("devId", "{{resId from step 1}}", "equal")):
        return None
    expanded = [copy.deepcopy(calls[0]),
                _call("PORT", "devId", "{{resId from step 1}}", "equal"),
                _call("R_PORT_IN_SUBNET", "portId", "{{id from step 2}}"),
                _call("SUBNET", "id", "{{subnetId from step 3}}")]
    updated = copy.deepcopy(item)
    updated["api_call"] = expanded
    plan = {"kind": "vm_port_subnet_details", "item": updated, "base_sql": item["sql"],
            "base_shape": shape, "base_tables": shape["base_tables"], "scope_values": scope,
            "details_alias": _DETAIL_ALIAS, "schema": copy.deepcopy(_FIELDS),
            "resources": [{"ci": ci, "table": table} for ci, table in _TABLES.items()],
            "dependencies": [{"source_step": 1, "target_step": 2, "source_field": "resId", "target_field": "devId"},
                             {"source_step": 2, "target_step": 3, "source_field": "id", "target_field": "portId"},
                             {"source_step": 3, "target_step": 4, "source_field": "subnetId", "target_field": "id"}],
            "dependency_limits": {"max_ids": _MAX_IDS, "max_id_characters": _MAX_ID_LENGTH,
                                  "max_request_line_bytes": _MAX_REQUEST_BYTES}}
    sql = compose_network(item["sql"], plan)
    if sql is None or not _schema_proof(sql):
        return None
    plan["preview_sql"] = sql
    return plan


def _ids(records, field):
    if not records or any(not isinstance(record, dict) or not isinstance(record.get(field), str)
                          or not record[field].strip() or len(record[field]) > _MAX_ID_LENGTH for record in records):
        return None
    values = set(record[field] for record in records)
    return values if len(values) <= _MAX_IDS else None


def _request_line_bytes(call, bound):
    """复现原执行器首个GET的完整URL序列化；不发送请求或改执行器常量。"""
    ci = _endpoint(call)
    field, value, operator = _constraint(call)
    if bound is not None:
        # 原执行器使用list(set(...))；顺序不影响URL字节总数，这里排序便于复核。
        values = sorted(bound)
        value = values[0] if len(values) == 1 else values
        operator = "in" if len(values) > 1 or operator == "in" else "equal"
    endpoint = "relations" if ci.startswith("R_") else "instances"
    url = (executor.BASE_URL + "/rest/hackthon/db/" + endpoint + "/" + ci +
           "?pageNo=1&pageSize=" + str(executor.PAGE_SIZE))
    condition = {"constraint": [{"simple": {"name": field, "value": value, "operator": operator}}]}
    url += "&condition=" + quote(json.dumps(condition, ensure_ascii=False))
    return len(url.encode("utf-8"))


def validate_network(question, filled_item, plan):
    """逐步原生GET；每一步必须非空且依赖有效，失败后绝不执行下一步。"""
    checks = []

    def result(valid, reason, **values):
        return {"valid": valid, "reason": reason, "tables": checks, **values}

    if (not isinstance(plan, dict) or not isinstance(filled_item, dict)
            or _scope(question) != plan.get("scope_values")
            or compose_network(filled_item.get("sql"), plan) is None
            or plan.get("preview_sql") != compose_network(plan.get("base_sql"), plan)
            or not _schema_proof(plan["preview_sql"])):
        return result(False, "network_scope_schema_or_shape_changed")
    try:
        expected = copy.deepcopy(plan["item"]["api_call"])
        expected[0]["condition"]["constraint"][0]["simple"]["value"] = plan["scope_values"]["name"]
        constraints = [("name", plan["scope_values"]["name"], "equal"),
                       ("devId", "{{resId from step 1}}", "equal"),
                       ("portId", "{{id from step 2}}", "in"),
                       ("id", "{{subnetId from step 3}}", "in")]
        if (len(expected) != 4 or [_endpoint(call) for call in expected] != list(_TABLES)
                or [_constraint(call) for call in expected] != constraints
                or filled_item.get("api_call") != expected):
            return result(False, "network_api_scope_changed_or_unresolved")
    except (KeyError, IndexError, TypeError):
        return result(False, "invalid_network_plan")
    previous, observed = None, {}
    source_fields = [None, "resId", "id", "subnetId"]
    for index, (ci, table) in enumerate(_TABLES.items()):
        step = index + 1
        bound = _ids(previous, source_fields[index]) if index else None
        if index and bound is None:
            return result(False, "invalid_or_oversized_network_dependency", target_step=step)
        request_bytes = _request_line_bytes(expected[index], bound)
        check = {"step": step, "ci": ci, "table": table, "rows": None,
                 "required_fields": list(_FIELDS[ci]), "dependency_ids": len(bound) if bound is not None else None,
                 "request_line_bytes": request_bytes}
        checks.append(check)
        if request_bytes > _MAX_REQUEST_BYTES:
            return result(False, "network_request_line_too_large", step=step, max_request_line_bytes=_MAX_REQUEST_BYTES)
        try:
            records, actual_table = m._execute_lookup_api(expected[index], previous)
        except Exception as exc:
            return result(False, "network_lookup_failed", step=step, error_type=type(exc).__name__)
        if isinstance(records, list):
            check["rows"] = len(records)
        if actual_table != table:
            return result(False, "network_resource_mismatch", step=step)
        if not records:
            return result(False, "empty_network_resource", step=step)
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            return result(False, "invalid_network_records", step=step)
        for field in _FIELDS[ci]:
            if field == "cidr":
                # 数据服务可能返回脱敏CIDR；仅原样输出，不解释为真实IP网络。
                if any(not isinstance(row.get(field), str) or not row[field].strip()
                       or len(row[field]) > 512 for row in records):
                    return result(False, "invalid_network_field", step=step, field=field)
            elif _ids(records, field) is None:
                return result(False, "invalid_or_oversized_network_field", step=step, field=field)
        if index == 0 and (len(records) != 1 or records[0]["name"] != plan["scope_values"]["name"]):
            return result(False, "ambiguous_or_changed_vm_name", step=step)
        target = [None, "devId", "portId", "id"][index]
        if index and not {row[target] for row in records} <= bound:
            return result(False, "network_dependency_value_mismatch", step=step)
        if ci in {"PORT", "SUBNET"} and len({row["id"] for row in records}) != len(records):
            return result(False, "duplicate_network_identity", step=step)
        if ci == "SUBNET" and {row["id"] for row in records} != bound:
            return result(False, "dangling_network_subnet_dependency", step=step)
        previous, observed[ci] = records, records
    mapped = {row["portId"] for row in observed["R_PORT_IN_SUBNET"]}
    return result(True, "verified_vm_port_subnet_details", port_count=len(observed["PORT"]),
                  unmapped_ports=sum(row["id"] not in mapped for row in observed["PORT"]))
