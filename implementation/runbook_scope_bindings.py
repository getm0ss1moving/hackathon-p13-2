"""以同CI租户查询的完整观察范围填原VDC条件；不将租户字段当作VDC别名。"""

import copy
import json
import re
import sqlite3
import sys
from contextlib import closing
from urllib.parse import parse_qsl, quote, urlsplit

import runbook_executor as executor
import runbook_matcher as m


_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_ENTITY = r"[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*"
_MAX_VDCS = 128
_MAX_VDC_LENGTH = 256
_MAX_URL_BYTES = 60000
_SCOPE_FIELDS = {"tenantName", "vdcName", "logicalRegionName"}


def _prefix(labels):
    return r"(?:" + "|".join(labels) + r")\s*(?:名称为|名为|名称|名)?\s*(?:为|是|[:：=])?\s*"


def _matches(question, labels):
    pattern = (_prefix(labels) + r'(?:"(?P<double>[^"\r\n]+)"|“(?P<curly_double>[^”\r\n]+)”|'
               r"'(?P<single>[^'\r\n]+)'|‘(?P<curly_single>[^’\r\n]+)’|「(?P<corner>[^」\r\n]+)」|"
               r"(?P<unquoted>" + _ENTITY + r"))")
    return list(re.finditer(pattern, question, re.I))


def _values(question, labels):
    return {next(value for value in found.groups() if value is not None)
            for found in _matches(question, labels)}


def _invalid_quoted_scope(question, labels, matches):
    # 引号必须配对；不允许未被完整解析的引号范围悄悄变成“不存在该scope”。
    for opening in re.finditer(_prefix(labels) + r"[\"'“‘「]", question, re.I):
        if not any(match.start() <= opening.start() < match.end() for match in matches):
            return True
    return False


def _ambiguous_boundary(question, match):
    tail = question[match.end():]
    if match["unquoted"] is None:
        return bool(re.match(r"[A-Za-z0-9_@]", tail))
    if match["unquoted"].endswith((".", ":")):
        return True  # 未加引号时无法区分名称末尾标点和语句标点。
    rest = tail.lstrip()
    if not rest or re.match(r"[，,。；;?？!！)\]】]", rest):
        return False
    if re.match(r"(?:logicalRegionName|vdcName|tenantName|status|azoneName)(?![A-Za-z0-9_])\s*[:：=]|"
                r"(?:VDC|vdcName)(?![A-Za-z0-9_])\s+(?=[A-Za-z0-9_\"'“‘「])", rest, re.I):
        return False
    if tail[:1].isspace():
        return not bool(re.match(r"的|在\s*(?:区域|logicalRegionName)", rest, re.I))
    if re.match(r"(?:的|在|下|中|内|有|包含|分别|和|及|且|与|返回|列出|查询|统计)", rest):
        return False
    # 空格后的续词、未支持的名称字符、以及不明确的中文续词均不能当成名称结束。
    return bool(tail[:1].isspace() or re.match(r"[A-Za-z0-9_@'\"&=\\\u4e00-\u9fff]", rest))


def _literal(value):
    return isinstance(value, str) and bool(value.strip()) and "{{" not in value and "}}" not in value


def _source(item):
    if not isinstance(item, dict):
        return None
    calls = item.get("api_call")
    was_list = isinstance(calls, list)
    if was_list:
        if len(calls) != 1:
            return None
        call = calls[0]
    else:
        call = calls
    if (not isinstance(call, dict) or call.get("method", "GET") != "GET"
            or set(call) - {"method", "url", "condition"} or not isinstance(call.get("url"), str)):
        return None
    try:
        url = urlsplit(call["url"])
        pairs = parse_qsl(url.query, strict_parsing=True)
        query = dict(pairs)
        if (url.scheme or url.netloc or url.fragment or len(query) != len(pairs)
                or set(query) - {"pageNo", "pageSize"} or int(query.get("pageNo", "1")) != 1
                or not 1 <= int(query.get("pageSize", "10000")) <= 10000):
            return None
    except ValueError:
        return None
    resource = re.fullmatch(r"/rest/hackthon/db/instances/(" + _IDENTIFIER + r")", url.path)
    if not resource:
        return None
    ci = resource[1]
    if executor._is_relation(ci):
        return None
    columns = m._schema_columns.get(ci, [])
    if not {"tenantName", "vdcName"} <= set(columns):
        return None
    condition = call.get("condition")
    if not isinstance(condition, dict) or set(condition) != {"constraint"}:
        return None
    constraints = condition["constraint"]
    if not isinstance(constraints, list) or len(constraints) not in {1, 2}:
        return None
    names = []
    for entry in constraints:
        if (not isinstance(entry, dict) or set(entry) - {"simple", "logOp"}
                or entry.get("logOp", "and") != "and"):
            return None
        simple = entry.get("simple")
        if (not isinstance(simple, dict) or set(simple) - {"name", "value", "operator"}
                or simple.get("operator", "equal") != "equal"
                or not isinstance(simple.get("name"), str)
                or simple.get("name") not in {"vdcName", "logicalRegionName"}
                or simple.get("value") != "{{" + simple["name"] + "}}"):
            return None
        names.append(simple["name"])
    if "vdcName" not in names or len(names) != len(set(names)):
        return None
    sql = item.get("sql")
    if (not isinstance(sql, str) or re.search(r"\{\{[^{}]*\}\}", sql)
            or re.search(r"\{\{[^{}]*\}\}", json.dumps(item.get("params", {}), ensure_ascii=False))):
        return None
    structure = m._sql_structure(sql).strip().removesuffix(";").strip()
    if not re.match(r"^SELECT\b", structure, re.I) or ";" in structure:
        return None
    tables = m._extract_sql_tables(structure)
    if len(tables) != 1:
        return None
    table = next(iter(tables))
    mapped = next((value for original, value in m._ORIG_TO_DESENS.items()
                   if original.casefold() == table.casefold()), None)
    if mapped != ci or not re.fullmatch(_IDENTIFIER, table):
        return None
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute('CREATE TABLE "' + table + '" (' +
                               ','.join('"' + field.replace('"', '""') + '" TEXT' for field in columns) + ')')
            connection.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return None
    return {"ci": ci, "table": table, "call": call, "was_list": was_list, "fields": names, "columns": columns}


def _condition(entries):
    result = []
    for index, (field, value, operator) in enumerate(entries):
        entry = {"simple": {"name": field, "value": copy.deepcopy(value), "operator": operator}}
        if index:
            entry["logOp"] = "and"
        result.append(entry)
    return {"constraint": result}


def _native_conditions(call):
    """只镜像原执行器无需前步的字面量分支；不接受可被当作占位符的值。"""
    parsed, names = [], set()
    for entry in call["condition"]["constraint"]:
        simple = entry["simple"]
        name, value, operator = simple.get("name"), simple.get("value"), simple.get("operator", "equal")
        if name not in _SCOPE_FIELDS or name in names or entry.get("logOp", "and") != "and":
            return None
        if operator == "equal":
            if not _literal(value):
                return None
        elif operator == "in":
            if not isinstance(value, list) or not value or not all(_literal(part) for part in value):
                return None
        else:
            return None
        parsed.append({"key": name, "value": copy.deepcopy(value), "operator": operator})
        names.add(name)
    return parsed


def _url_bytes(ci, native, page_no=1):
    wire = _condition([(entry["key"], entry["value"], entry["operator"]) for entry in native])
    url = (executor.BASE_URL + "/rest/hackthon/db/instances/" + ci +
           "?pageNo=" + str(page_no) + "&pageSize=" + str(executor.PAGE_SIZE) +
           "&condition=" + quote(json.dumps(wire, ensure_ascii=False)))
    return len(url.encode("utf-8"))


def _uri_bound(ci, native):
    # 固定原服务非末页均满页，原executor逐页累计到Python list；可请求页数受list容量限制。
    # 为页码增长保守预留空间，避免首个URI合规而后续pageNo=10等越界。不增加任何GET。
    maximum_page = sys.maxsize + 1
    return {"first_page_bytes": _url_bytes(ci, native),
            "max_page_request_line_bytes": _url_bytes(ci, native, maximum_page),
            "max_buffered_page_number": str(maximum_page),
            "basis": "native_buffered_list_bound_under_full_nonfinal_page_contract"}


def _where(native):
    clauses, parameters = [], []
    for entry in native:
        field, value = entry["key"], entry["value"]
        if entry["operator"] == "in":
            clauses.append('"' + field + '" IN (' + ','.join('?' for _ in value) + ')')
            parameters.extend(value)
        else:
            clauses.append('"' + field + '" = ?')
            parameters.append(value)
    return " AND ".join(clauses), parameters


def _equivalence(records, lookup_conditions, final_conditions):
    """在同一完整观察源上用SQLite验证全部行覆盖；不访问标准答案或全CI数据。"""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("CREATE TABLE scope_records(row_id INTEGER,tenantName TEXT,vdcName TEXT,logicalRegionName TEXT)")
        connection.executemany("INSERT INTO scope_records VALUES (?,?,?,?)", [
            (index, row["tenantName"], row["vdcName"], row.get("logicalRegionName")) for index, row in enumerate(records)])

        def matched(native):
            where, values = _where(native)
            return {row[0] for row in connection.execute("SELECT row_id FROM scope_records WHERE " + where, values)}

        source, grounded = matched(lookup_conditions), matched(final_conditions)
    return {"source_scope_rows": len(source), "grounded_scope_rows": len(grounded),
            "source_rows": len(records), "equivalent_on_observed_source": source == grounded == set(range(len(records))),
            "native_condition_contract": "flat_literal_equal_or_in_with_and"}


def resolve_tenant_vdc(question, item):
    """同CI最多一次原生查询；由观察到的完整S(T)动态填VDC，并保留真实tenant过滤。"""
    source = _source(item)
    if source is None or not isinstance(question, str):
        return item, None
    tenant_labels = [r"租户", r"tenantName(?![A-Za-z0-9_])", r"tenant(?![A-Za-z0-9_])"]
    tenant_matches = _matches(question, tenant_labels)
    parse_proof = {"ci": source["ci"], "table": source["table"], "lookup_calls": 0, "valid": False}
    if _invalid_quoted_scope(question, tenant_labels, tenant_matches):
        return item, {**parse_proof, "reason": "invalid_quoted_tenant_scope"}
    if any(_ambiguous_boundary(question, match) for match in tenant_matches):
        return item, {**parse_proof, "reason": "ambiguous_tenant_name_boundary"}
    tenants = _values(question, tenant_labels)
    if len(tenants) > 1:
        return item, {**parse_proof, "reason": "ambiguous_question_tenant"}
    visible = question
    for match in reversed(tenant_matches):
        visible = visible[:match.start()] + " " * (match.end() - match.start()) + visible[match.end():]
    explicit_vdcs = _values(visible, [r"vdcName(?![A-Za-z0-9_])", r"VDC(?![A-Za-z0-9_])", r"虚拟数据中心"])
    if (len(tenants) != 1 or explicit_vdcs
            or re.search(r"可用区|azoneName|状态(?:为|是)|status\s*[:：=]|运行中|异常|已停止", visible, re.I)):
        return item, None
    tenant = next(iter(tenants))
    region_labels = [r"区域", r"logicalRegionName(?![A-Za-z0-9_])"]
    region_matches = _matches(visible, region_labels)
    regions = _values(visible, region_labels)
    proof = {"ci": source["ci"], "table": source["table"], "lookup_calls": 0,
             "question_scope": {"tenantName": tenant}}

    def fail(reason, **details):
        return item, {**proof, "valid": False, "reason": reason, **details}

    if not _literal(tenant):
        return fail("unusable_question_tenant")
    if _invalid_quoted_scope(visible, region_labels, region_matches):
        return fail("invalid_quoted_region_scope")
    if any(_ambiguous_boundary(visible, match) for match in region_matches):
        return fail("ambiguous_region_name_boundary")
    if len(regions) > 1:
        return fail("ambiguous_question_region")
    region = next(iter(regions)) if regions else None
    if (re.search(r"区域|logicalRegionName", visible, re.I) and region is None
            or "logicalRegionName" in source["fields"] and region is None):
        return fail("explicit_question_region_required")
    if region is not None:
        if not _literal(region):
            return fail("unusable_question_region")
        if "logicalRegionName" not in source["columns"]:
            return fail("missing_region_schema")
        proof["question_scope"]["logicalRegionName"] = region
    if not isinstance(executor.PAGE_SIZE, int) or isinstance(executor.PAGE_SIZE, bool) or executor.PAGE_SIZE < 1:
        return fail("invalid_native_page_size")
    entries = [("tenantName", tenant, "equal")]
    if region is not None:
        entries.append(("logicalRegionName", region, "equal"))
    lookup = copy.deepcopy(source["call"])
    lookup["condition"] = _condition(entries)
    lookup_native = _native_conditions(lookup)
    proof["lookup_uri_bound"] = _uri_bound(source["ci"], lookup_native)
    proof["lookup_request_line_bytes"] = proof["lookup_uri_bound"]["first_page_bytes"]
    if proof["lookup_uri_bound"]["max_page_request_line_bytes"] > _MAX_URL_BYTES:
        return fail("tenant_vdc_lookup_uri_too_large")
    proof["lookup_calls"] = 1
    try:
        records, actual_table = m._execute_lookup_api(lookup)
    except Exception as exc:
        return fail("tenant_vdc_lookup_failed", error_type=type(exc).__name__)
    if not isinstance(actual_table, str) or actual_table.casefold() != source["table"].casefold():
        return fail("tenant_vdc_lookup_resource_mismatch")
    if not isinstance(records, list) or not records:
        return fail("empty_tenant_vdc_lookup")
    if any(not isinstance(row, dict) for row in records):
        return fail("invalid_tenant_vdc_lookup_records")
    proof["lookup_rows"] = len(records)
    # 条件证明仅适用于固定原data_server的静态数据、非末页均满页以及未改变的原分页/缓存契约。
    # 原_query_server分页异常只会留下完整页。非整页尾部证明走到了正常的不足页停止分支。
    # 未直接观察HTTP页状态；整页倍数无法区分正常完整结果与后页出错，一律不猜。
    tail = len(records) % executor.PAGE_SIZE
    proof["pagination_proof"] = {"native_page_size": executor.PAGE_SIZE, "tail_rows": tail,
                                 "basis": "native_short_last_page", "complete_under_native_contract": tail != 0,
                                 "http_page_status_observed": False,
                                 "assumptions": ["fixed_native_data_server_static_data", "all_nonfinal_pages_full",
                                                 "unchanged_native_pagination_and_cache_contract"]}
    if tail == 0:
        return fail("native_scope_completeness_unproven")
    if any(row.get("tenantName") != tenant for row in records):
        return fail("lookup_tenant_scope_mismatch")
    if region is not None and any(row.get("logicalRegionName") != region for row in records):
        return fail("lookup_region_scope_mismatch")
    if any(not _literal(row.get("vdcName")) or len(row["vdcName"]) > _MAX_VDC_LENGTH for row in records):
        return fail("unusable_observed_vdc")
    observed = sorted({row["vdcName"] for row in records})
    proof["observed_vdc_count"] = len(observed)
    if len(observed) > _MAX_VDCS:
        return fail("observed_vdc_set_too_large")
    proof["observed_vdc_values"] = observed
    grounded = copy.deepcopy(source["call"])
    final_entries = []
    for entry in source["call"]["condition"]["constraint"]:
        field = entry["simple"]["name"]
        if field == "vdcName":
            final_entries.append((field, observed[0] if len(observed) == 1 else observed,
                                  "equal" if len(observed) == 1 else "in"))
        else:
            final_entries.append((field, region, "equal"))
    if region is not None and "logicalRegionName" not in source["fields"]:
        final_entries.append(("logicalRegionName", region, "equal"))
    final_entries.append(("tenantName", tenant, "equal"))
    grounded["condition"] = _condition(final_entries)
    final_native = _native_conditions(grounded)
    if final_native is None:
        return fail("unsupported_grounded_native_conditions")
    proof["grounded_uri_bound"] = _uri_bound(source["ci"], final_native)
    proof["grounded_request_line_bytes"] = proof["grounded_uri_bound"]["first_page_bytes"]
    if proof["grounded_uri_bound"]["max_page_request_line_bytes"] > _MAX_URL_BYTES:
        return fail("tenant_vdc_grounded_uri_too_large")
    try:
        equivalence = _equivalence(records, lookup_native, final_native)
    except sqlite3.Error:
        return fail("tenant_vdc_scope_equivalence_error")
    if not equivalence["equivalent_on_observed_source"]:
        return fail("tenant_vdc_scope_not_equivalent", scope_proof=equivalence)
    updated = copy.deepcopy(item)
    updated["api_call"] = [grounded] if source["was_list"] else grounded
    return updated, {**proof, "valid": True, "reason": "observed_tenant_vdc_binding_under_native_contract",
                     "scope_proof": equivalence, "grounded_native_conditions": final_native}
