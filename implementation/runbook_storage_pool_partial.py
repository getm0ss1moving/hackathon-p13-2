"""存储池明确部分回答：保留原分组、真实池明细，并标注磁盘类型缺失。"""

import copy
import json
import math
import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, quote, urlsplit

import runbook_executor as executor
import runbook_matcher as m


_CI = "STORAGE_POOL"
_TABLE = "CLOUD_STORAGE_POOL"
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_ENTITY = r"[A-Za-z0-9_@][A-Za-z0-9_@./:#%+\-]*"
_FIELDS = ["id", "name", "poolName", "nativeId", "logicalRegionName", "azoneName", "storageProtocol",
           "totalCapacityGB", "freeCapacityGB", "provisionedCapacityGB"]
_GROUPS = ["azoneName", "storageProtocol"]
_NUMERIC = ["totalCapacityGB", "freeCapacityGB", "provisionedCapacityGB"]
_COLUMNS = ["azoneName", "storageProtocol", "total_capacity", "used_capacity", "free_capacity", "over_subscription_ratio"]
_PROJECTION = ("azoneName,storageProtocol,SUM(totalCapacityGB) AS total_capacity,"
               "SUM(totalCapacityGB-freeCapacityGB) AS used_capacity,SUM(freeCapacityGB) AS free_capacity,"
               "ROUND(SUM(provisionedCapacityGB)*100.0/SUM(totalCapacityGB),2) AS over_subscription_ratio")
_ATTRIBUTES = {"存储池名称": "pool_names", "名称": "pool_names", "磁盘类型": "disk_type",
               "物理容量总量": "total_capacity", "已用量": "used_capacity", "已用容量": "used_capacity",
               "可用量": "free_capacity", "可用容量": "free_capacity", "空闲容量": "free_capacity",
               "超配比": "over_subscription_ratio", "超配比例": "over_subscription_ratio", "超分比": "over_subscription_ratio"}
_REQUIRED_ATTRIBUTES = {"pool_names", "disk_type", "total_capacity", "used_capacity", "free_capacity", "over_subscription_ratio"}
_CAPACITY_SCOPE = "按可用区和存储协议汇总"
_UNAVAILABLE = "数据源未提供磁盘类型"
_MAX_URL_BYTES = 60000


def _schema_support():
    columns = m._schema_columns.get(_CI)
    if not isinstance(columns, (list, tuple)) or not all(isinstance(field, str) for field in columns):
        return False
    names = {re.sub(r"[_\-\s]", "", field.casefold()) for field in columns}
    # 若后续schema出现可能直接回答此缺项的列，先交还原路径复核，不继续宣称schema缺失。
    possible_disk_fields = {"disktype", "diskmediatype", "diskmedium", "mediatype", "mediumtype", "storagemediatype"}
    return set(_FIELDS) <= set(columns) and not names.intersection(possible_disk_fields)


def _question(question):
    """正向完整语法；六项属性必须齐全，未知尾部/多实体/额外scope一律不猜。"""
    if not isinstance(question, str):
        return None
    entity = (r'(?:"(?P<double>[^"\r\n]+)"|“(?P<curly>[^”\r\n]+)”|'
              r"'(?P<single>[^'\r\n]+)'|‘(?P<single_curly>[^’\r\n]+)’|「(?P<corner>[^」\r\n]+)」|(?P<bare>" + _ENTITY + r"))")
    match = re.fullmatch(
        r"\s*(?:请)?(?:帮我)?(?:查询|统计|列出)\s*(?:区域|logicalRegionName\s*[:：=]?)\s*" + entity
        + r"\s*(?:下|中)(?:的)?\s*(?:各|每个)\s*可用区\s*(?:中|下)?(?:的)?\s*"
        r"(?P<subject>存储池的)?(?P<attributes>[^。?？]+?)\s*[。?？]?\s*", question, re.I)
    if not match:
        return None
    region = next(match[name] for name in ("double", "curly", "single", "single_curly", "corner", "bare") if match[name] is not None)
    if not region.strip() or len(region) > 256 or "{{" in region or "}}" in region:
        return None
    attributes = match["attributes"]
    pieces = list(re.finditer(r"[^、，,和及与]+", attributes))
    if not re.fullmatch(r"[^、，,和及与]+(?:\s*[、，,和及与]\s*[^、，,和及与]+)*", attributes):
        return None
    roles, spans = [], []
    explicit_pool_subject = bool(match["subject"])
    for piece in pieces:
        text = piece[0].strip()
        role = _ATTRIBUTES.get(text)
        if role is None:
            return None
        explicit_pool_subject |= text == "存储池名称"
        roles.append(role)
        if role == "disk_type":
            start = match.start("attributes") + piece.start() + len(piece[0]) - len(piece[0].lstrip())
            spans.append({"start": start, "end": start + len(text), "text": text,
                          "role": "unavailable_storage_pool_attribute", "field": "disk_type", "availability": _UNAVAILABLE})
    if not explicit_pool_subject or len(roles) != len(_REQUIRED_ATTRIBUTES) or set(roles) != _REQUIRED_ATTRIBUTES:
        return None
    visible = question
    for span in reversed(spans):
        visible = visible[:span["start"]] + " " * (span["end"] - span["start"]) + visible[span["end"]:]
    return {"scope_values": {"logicalRegionName": region}, "matched_attribute_spans": spans, "coverage_question": visible}


def _shape(sql):
    if not isinstance(sql, str):
        return None
    match = re.fullmatch(
        r"\s*SELECT\s+(?P<columns>.+?)\s+FROM\s+CLOUD_STORAGE_POOL"
        r"(?:\s+(?:AS\s+)?(?P<alias>(?!GROUP\b)" + _IDENT + r"))?\s+GROUP\s+BY\s+(?P<groups>.+?)\s*;?\s*", sql, re.I | re.S)
    if not match:
        return None
    prefix = match["alias"] or _TABLE

    def normalize(value):
        value = re.sub(r"\b" + re.escape(prefix) + r"\.", "", value, flags=re.I)
        return re.sub(r"\s+", "", value).casefold()

    if (normalize(match["columns"]) != normalize(_PROJECTION)
            or normalize(match["groups"]) != "azonename,storageprotocol"):
        return None
    return {"table": _TABLE, "group_fields": list(_GROUPS), "output_columns": list(_COLUMNS),
            "projection": "original_storage_pool_capacity_sums"}


def _call(item):
    api = item.get("api_call") if isinstance(item, dict) else None
    if isinstance(api, list):
        return api[0] if len(api) == 1 else None
    return api if isinstance(api, dict) else None


def _api_scope(call, scope, filled=False):
    if (not isinstance(call, dict) or call.get("method", "GET") != "GET"
            or set(call) - {"method", "url", "condition"} or not isinstance(call.get("url"), str)):
        return False
    try:
        url = urlsplit(call["url"])
        pairs = parse_qsl(url.query, strict_parsing=True)
        params = dict(pairs)
        if (url.scheme or url.netloc or url.fragment or url.path != "/rest/hackthon/db/instances/STORAGE_POOL"
                or len(pairs) != len(params) or set(params) - {"pageNo", "pageSize"}
                or int(params.get("pageNo", "1")) != 1 or not 1 <= int(params.get("pageSize", "10000")) <= 10000):
            return False
    except ValueError:
        return False
    condition = call.get("condition")
    if not isinstance(condition, dict) or set(condition) != {"constraint"}:
        return False
    entries = condition["constraint"]
    if not isinstance(entries, list) or len(entries) != 1:
        return False
    entry = entries[0]
    if not isinstance(entry, dict) or set(entry) - {"simple", "logOp"} or entry.get("logOp", "and") != "and":
        return False
    simple = entry.get("simple")
    values = [scope["logicalRegionName"]] if filled else [scope["logicalRegionName"], "{{logicalRegionName}}"]
    return (isinstance(simple, dict) and not set(simple) - {"name", "value", "operator"}
            and simple.get("name") == "logicalRegionName" and simple.get("value") in values
            and simple.get("operator", "equal") == "equal")


def compose_storage_pool_partial(base_sql, plan):
    if (not isinstance(plan, dict) or plan.get("kind") != "partial_storage_pool_attributes"
            or _shape(base_sql) is None or _shape(base_sql) != plan.get("base_shape")
            or plan.get("schema_fields") != _FIELDS or plan.get("capacity_scope") != _CAPACITY_SCOPE
            or plan.get("disk_type_availability") != _UNAVAILABLE or plan.get("answer_completeness") != "partial"
            or not _schema_support()):
        return None
    return ("SELECT pool_base.*,'" + _CAPACITY_SCOPE + "' AS capacity_scope,'存储协议' AS storage_protocol_label,"
            "'GB' AS capacity_unit,'%' AS over_subscription_ratio_unit,"
            "NULL AS disk_type,'" + _UNAVAILABLE + "' AS disk_type_availability,pool_details.pool_details FROM ("
            + base_sql.strip().rstrip(";") + ") AS pool_base LEFT JOIN ("
            "SELECT azoneName,storageProtocol,json_group_array(json_object("
            "'pool_id',id,'name',name,'poolName',poolName,'nativeId',nativeId,'storage_protocol',storageProtocol,"
            "'totalCapacityGB',totalCapacityGB,'freeCapacityGB',freeCapacityGB,'provisionedCapacityGB',provisionedCapacityGB,"
            "'used_capacity',totalCapacityGB-freeCapacityGB,'disk_type',NULL,'disk_type_availability','" + _UNAVAILABLE + "'"
            ")) AS pool_details FROM CLOUD_STORAGE_POOL GROUP BY azoneName,storageProtocol"
            ") AS pool_details ON pool_base.azoneName IS pool_details.azoneName "
            "AND pool_base.storageProtocol IS pool_details.storageProtocol")


def _compiles(sql):
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute('CREATE TABLE "' + _TABLE + '" (' + ','.join('"' + f + '" TEXT' for f in _FIELDS) + ')')
            db.execute("EXPLAIN " + sql)
    except sqlite3.Error:
        return False
    return True


def plan_storage_pool_partial(question, item):
    parsed = _question(question)
    shape = _shape(item.get("sql")) if isinstance(item, dict) else None
    if (parsed is None or shape is None or not _api_scope(_call(item), parsed["scope_values"])
            or not _schema_support()):
        return None
    plan = {"kind": "partial_storage_pool_attributes", "item": copy.deepcopy(item), "base_sql": item["sql"],
            "base_shape": shape, "schema_fields": list(_FIELDS), "capacity_scope": _CAPACITY_SCOPE,
            "disk_type_availability": _UNAVAILABLE, "answer_completeness": "partial", "runtime_default_enabled": False,
            "unavailable_attributes": ["disk_type"], **parsed}
    preview = compose_storage_pool_partial(item["sql"], plan)
    if preview is None or not _compiles(preview):
        return None
    plan["preview_sql"] = preview
    return plan


def _uri_bound(call):
    simple = call["condition"]["constraint"][0]["simple"]
    condition = {"constraint": [{"simple": {"name": "logicalRegionName", "value": simple["value"],
                                            "operator": simple.get("operator", "equal")}}]}
    def size(page):
        url = (executor.BASE_URL + "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=" + str(page)
               + "&pageSize=" + str(executor.PAGE_SIZE) + "&condition=" + quote(json.dumps(condition, ensure_ascii=False)))
        return len(url.encode("utf-8"))
    page = sys.maxsize + 1
    return {"first_page_bytes": size(1), "max_page_request_line_bytes": size(page), "max_buffered_page_number": str(page),
            "basis": "native_buffered_list_bound_under_full_nonfinal_page_contract"}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip(" \t\r\n")
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
        return None
    try:
        number = Decimal(text)
        native = float(number)
        return number if number.is_finite() and math.isfinite(native) and (number == 0 or native != 0) else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def validate_storage_pool_partial(question, filled_item, plan):
    def result(valid, reason, **detail):
        return {"valid": valid, "reason": reason, "answer_completeness": "partial",
                "unavailable_attributes": ["disk_type"], **detail}

    if not isinstance(plan, dict) or not isinstance(filled_item, dict):
        return result(False, "invalid_storage_pool_partial_plan")
    current = plan_storage_pool_partial(question, plan.get("item"))
    if current != plan or current is None or compose_storage_pool_partial(filled_item.get("sql"), plan) is None:
        return result(False, "storage_pool_question_shape_or_contract_changed")
    expected = copy.deepcopy(plan["item"])
    _call(expected)["condition"]["constraint"][0]["simple"]["value"] = plan["scope_values"]["logicalRegionName"]
    call = _call(filled_item)
    if filled_item.get("api_call") != expected["api_call"] or not _api_scope(call, plan["scope_values"], True):
        return result(False, "storage_pool_api_scope_changed_or_unresolved")
    if not isinstance(executor.PAGE_SIZE, int) or isinstance(executor.PAGE_SIZE, bool) or executor.PAGE_SIZE < 1:
        return result(False, "invalid_native_page_size")
    uri = _uri_bound(call)
    if uri["max_page_request_line_bytes"] > _MAX_URL_BYTES:
        return result(False, "storage_pool_native_uri_too_large", uri_bound=uri)
    try:
        records, table = m._execute_lookup_api(call)
    except Exception as exc:
        return result(False, "storage_pool_lookup_failed", error_type=type(exc).__name__, uri_bound=uri)
    if table != _TABLE or not isinstance(records, list) or not records:
        return result(False, "empty_or_changed_storage_pool_resource", uri_bound=uri)
    tail = len(records) % executor.PAGE_SIZE
    evidence = {"uri_bound": uri, "lookup_rows": len(records), "pagination_proof": {
        "native_page_size": executor.PAGE_SIZE, "tail_rows": tail, "basis": "native_short_last_page",
        "complete_under_native_contract": tail != 0, "http_page_status_observed": False,
        "assumptions": ["fixed_native_data_server_static_data", "all_nonfinal_pages_full", "unchanged_native_pagination_and_cache_contract"]}}
    if tail == 0:
        return result(False, "native_storage_pool_completeness_unproven", **evidence)
    if any(not isinstance(row, dict) or not set(_FIELDS) <= row.keys() for row in records):
        return result(False, "missing_storage_pool_field", **evidence)
    if any(not isinstance(row[f], str) or not row[f].strip() for row in records for f in ["id", "name", "poolName", "nativeId"]):
        return result(False, "invalid_storage_pool_identity_or_name", **evidence)
    if len({row["id"] for row in records}) != len(records):
        return result(False, "duplicate_storage_pool_identity", **evidence)
    if any(row["logicalRegionName"] != plan["scope_values"]["logicalRegionName"] for row in records):
        return result(False, "returned_storage_pool_scope_mismatch", **evidence)
    if any(row[f] is not None and not isinstance(row[f], str) for row in records for f in _GROUPS):
        return result(False, "invalid_storage_pool_group_key", **evidence)
    for row in records:
        numbers = [_number(row[field]) for field in _NUMERIC]
        if any(n is None or n < 0 for n in numbers) or numbers[1] > numbers[0]:
            return result(False, "invalid_storage_pool_capacity", **evidence)
    # 单字段有限不保证原SUM或*100中间值有限；按原SQL实际复核，仍不新增GET。
    try:
        with closing(executor.load_into_sqlite({_TABLE: records})) as db:
            cursor = db.execute(filled_item["sql"])
            columns = [field[0].casefold() for field in cursor.description]
            numeric_indexes = [columns.index(field) for field in _COLUMNS[2:]]
            for group in cursor:
                if any(group[index] is not None and _number(group[index]) is None for index in numeric_indexes):
                    return result(False, "nonfinite_storage_pool_group_capacity", **evidence)
    except (sqlite3.Error, TypeError, ValueError, OverflowError):
        return result(False, "storage_pool_capacity_sql_unproven", **evidence)
    groups = Counter((row["azoneName"], row["storageProtocol"]) for row in records)
    return result(True, "verified_partial_storage_pool_attributes", **evidence,
                  scope_proof={"ci": _CI, "region_exact": True, "unique_pool_ids": len(records), "group_count": len(groups),
                               "group_fields": list(_GROUPS), "all_display_fields_from_same_resource": True},
                  data_quality={"null_group_key_rows": sum(any(row[f] is None for f in _GROUPS) for row in records),
                                "nonunique_display_name_rows": len(records)-len({row["name"] for row in records}),
                                "disk_type": None, "disk_type_availability": _UNAVAILABLE,
                                "storageProtocol_meaning": "存储协议", "is_complete_business_answer": False})
