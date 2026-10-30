"""同CI原明细行追加对象总数；开关启用且同范围验证成功后保护行粒度。"""

import copy
import hashlib
import json
import re
import sqlite3
import sys
from contextlib import closing
from urllib.parse import parse_qsl, quote, urlsplit

import runbook_executor as executor
import runbook_matcher as m


_ID = r"[A-Za-z_][A-Za-z0-9_]*"
_TOTAL = "total_count"
_MAX_URL_BYTES = 60000
_NOUNS = {ci: tuple(word for word in words if word == word.strip() and not word.endswith("_"))
          for words, ci in m._RESOURCE_CHECKS}
_FIELD_WORDS = {"cidr": ("cidr", "cidr范围", "cidr列表", "cidr明细"),
                "name": ("name", "名称", "名字", "名称列表"),
                "id": ("id", "编号", "标识")}
_REQUEST = r"(?:请(?:问|(?:帮我)?(?:查询|统计|查看|列出))?|查询|统计|查看|列出)?"
_REGION = r"region_[A-Za-z0-9_\-]{1,128}"
_COUNT = r"(?:数量|总数|个数|台数|块数)"
_AND = r"(?:以及|和|及|与|、)"


def _column_key(label):
    # 与现有输出合同一致，避免totalcount/total_count归一化后覆盖原明细列。
    return re.sub(r"[_\-\s]", "", label.casefold())


def _shape(sql):
    """单表简单字段投影；整句匹配意味着无过滤、聚合、去重或排序。"""
    if not isinstance(sql, str):
        return None
    match = re.fullmatch(r"\s*SELECT\s+(?P<projection>.+?)\s+FROM\s+(?P<table>" + _ID
                         + r")(?:\s+(?:AS\s+)?(?P<alias>" + _ID + r"))?\s*;?\s*", sql, re.I | re.S)
    if not match:
        return None
    known = {table.casefold(): (table, ci) for table, ci in m._ORIG_TO_DESENS.items()}
    if match["table"].casefold() not in known:
        return None
    table, ci = known[match["table"].casefold()]
    reference = match["alias"] or match["table"]
    columns = []
    for piece in match["projection"].split(","):
        column = re.fullmatch(r"\s*(?:(?P<prefix>" + _ID + r")\.)?(?P<field>" + _ID
                              + r")(?:\s+AS\s+(?P<label>" + _ID + r"))?\s*", piece, re.I)
        if not column or column["prefix"] and column["prefix"].casefold() != reference.casefold():
            return None
        field, label = column["field"], column["label"] or column["field"]
        if field not in m._schema_columns.get(ci, []) or _column_key(label) == _column_key(_TOTAL):
            return None
        columns.append({"field": field, "label": label})
    if not columns or len({_column_key(column["label"]) for column in columns}) != len(columns):
        return None
    return {"table": table, "ci": ci, "reference": reference, "columns": columns,
            "projection_end": match.end("projection")}


def _question_contract(question, shape):
    nouns = _NOUNS.get(shape["ci"], ())
    if not isinstance(question, str) or not nouns:
        return None
    # 不删除标点/词语，只忽略空白；所有其他字符必须被正向槽完整消费。
    text = re.sub(r"\s+", "", question)
    noun = "(?:" + "|".join(re.escape(word) for word in nouns) + ")"
    words = {}
    for column in shape["columns"]:
        field = column["field"]
        labels = _FIELD_WORDS.get(field.casefold(), (field, field + "列表", field + "明细"))
        for label in labels:
            key = label.casefold()
            if key in words and words[key] != field:
                return None
            words[key] = field
    term = "(?:" + "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True)) + ")"
    fields = r"(?P<details>" + term + "(?:" + _AND + term + ")*)"
    scope = r"(?:区域(?P<region>" + _REGION + r")下)?"
    resource = r"(?:所有|全部)?" + noun + r"(?:的)?"
    patterns = (resource + _COUNT + _AND + fields,
                resource + fields + _AND + _COUNT)
    for body in patterns:
        match = re.fullmatch(_REQUEST + scope + body + r"[?？。]?", text, re.I)
        if match:
            requested = [words[word.casefold()] for word in re.split(_AND, match["details"])]
            if len(set(requested)) != len(requested):
                return None
            return {"scope": {"logicalRegionName": match["region"]} if match["region"] else {},
                    "requested_fields": requested, "quantity_grain": "one_resource_per_unique_id"}
    return None


def _native_call(call, ci, scope):
    if (not isinstance(call, dict) or set(call) - {"method", "url", "condition"}
            or call.get("method", "GET") != "GET" or not isinstance(call.get("url"), str)):
        return None
    try:
        url = urlsplit(call["url"])
        pairs = parse_qsl(url.query, strict_parsing=True)
        query = dict(pairs)
        if (url.scheme or url.netloc or url.fragment or len(query) != len(pairs)
                or url.path != "/rest/hackthon/db/instances/" + ci
                or set(query) - {"pageNo", "pageSize"} or int(query.get("pageNo", "1")) != 1
                or not 1 <= int(query.get("pageSize", "10000")) <= 10000):
            return None
    except ValueError:
        return None
    resolved = copy.deepcopy(call)
    if not scope:
        return resolved if "condition" not in call else None
    condition = call.get("condition")
    if not isinstance(condition, dict) or set(condition) != {"constraint"}:
        return None
    entries = condition["constraint"]
    if not isinstance(entries, list) or len(entries) != 1:
        return None
    entry = entries[0]
    if not isinstance(entry, dict) or set(entry) - {"simple", "logOp"} or entry.get("logOp", "and") != "and":
        return None
    simple = entry.get("simple")
    if (not isinstance(simple, dict) or set(simple) - {"name", "value", "operator"}
            or simple.get("name") != "logicalRegionName" or simple.get("operator", "equal") != "equal"
            or simple.get("value") not in (scope["logicalRegionName"], "{{logicalRegionName}}")):
        return None
    resolved["condition"]["constraint"][0]["simple"]["value"] = scope["logicalRegionName"]
    return resolved


def _counted_sql(base_sql, shape):
    end = shape["projection_end"]
    return base_sql[:end] + ", COUNT(*) OVER() AS " + _TOTAL + base_sql[end:]


def _compiles(sql, shape, fields):
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            columns = ",".join('"' + field + '" TEXT' for field in fields)
            connection.execute('CREATE TABLE "' + shape["table"] + '" (' + columns + ')')
            cursor = connection.execute(sql)
            return [column[0] for column in cursor.description] == [column["label"] for column in shape["columns"]] + [_TOTAL]
    except sqlite3.Error:
        return False


def plan_detail_count(question, item):
    if not isinstance(item, dict):
        return None
    shape = _shape(item.get("sql"))
    if shape is None:
        return None
    contract = _question_contract(question, shape)
    if contract is None:
        return None
    call = _native_call(item.get("api_call"), shape["ci"], contract["scope"])
    fields = sorted({"id", *[column["field"] for column in shape["columns"]], *contract["scope"]})
    if call is None or not set(fields) <= set(m._schema_columns.get(shape["ci"], [])):
        return None
    preview = _counted_sql(item["sql"], shape)
    if not _compiles(preview, shape, fields):
        return None
    return {"kind": "single_ci_detail_count", "item": copy.deepcopy(item), "base_sql": item["sql"],
            "preview_sql": preview, "base_shape": shape, "question_contract": contract,
            "native_call": call, "schema_fields": fields, "runtime_default_enabled": False,
            "total_count_role": "当前明确范围内的资源对象总数；每个原明细行重复同一总数"}


def _verified_preview(plan):
    if not isinstance(plan, dict) or plan.get("kind") != "single_ci_detail_count":
        return None
    shape = _shape(plan.get("base_sql"))
    if shape is None or shape != plan.get("base_shape"):
        return None
    preview = _counted_sql(plan["base_sql"], shape)
    if (plan.get("preview_sql") != preview or not set(plan.get("schema_fields", [])) <= set(m._schema_columns.get(shape["ci"], []))
            or not _compiles(preview, shape, plan["schema_fields"])):
        return None
    return preview


def compose_detail_count(sql, plan):
    """仅接受原投影合同或本helper补列SQL；精调未知形状返回None供保护函数回退。"""
    preview = _verified_preview(plan)
    if preview is None or not isinstance(sql, str):
        return None
    if sql.strip().rstrip(";").strip() == preview.strip().rstrip(";").strip():
        return preview
    return preview if _shape(sql) == plan["base_shape"] else None


def _plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def protect_detail_count(refined_sql, plan, validation=None):
    """只有对应native验证成功才启用；压聚合/改行粒度整体回退已补count原SQL。"""
    if (not isinstance(validation, dict) or validation.get("valid") is not True
            or validation.get("plan_sha256") != _plan_digest(plan)):
        return refined_sql, {"applied": False, "reason": "native_validation_unproven_keep_original_path"}
    preview = _verified_preview(plan)
    if preview is None:
        return refined_sql, {"applied": False, "reason": "invalid_detail_count_plan"}
    accepted = compose_detail_count(refined_sql, plan)
    return accepted or preview, {"applied": True, "reverted": accepted is None,
                                 "reason": "detail_projection_and_grain_preserved" if accepted else "refinement_changed_detail_contract"}


def _uri_bound(ci, scope):
    condition = ""
    if scope:
        condition = "&condition=" + quote(json.dumps({"constraint": [{"simple": {
            "name": "logicalRegionName", "value": scope["logicalRegionName"], "operator": "equal"}}]}))
    def size(page):
        path = "/rest/hackthon/db/instances/" + ci + "?pageNo=" + str(page) + "&pageSize=" + str(executor.PAGE_SIZE) + condition
        return len(("GET " + path + " HTTP/1.1\r\n").encode())
    return {"first_request_line_bytes": size(1), "max_request_line_bytes": size(sys.maxsize + 1)}


def validate_detail_count(question, filled_item, plan):
    """False仅停用补全，调用方保留原路径；禁止据此新建拒答或数empty dummy。"""
    def result(valid, reason, **detail):
        return {"valid": valid, "reason": reason, "failure_policy": "keep_original_path", **detail}
    if not isinstance(plan, dict) or not isinstance(filled_item, dict):
        return result(False, "invalid_detail_count_plan")
    current = plan_detail_count(question, plan.get("item"))
    if (current is None or current != plan or filled_item.get("api_call") != plan["native_call"]
            or _shape(filled_item.get("sql")) != plan["base_shape"]):
        return result(False, "detail_count_scope_or_projection_changed")
    if type(executor.PAGE_SIZE) is not int or executor.PAGE_SIZE < 1:
        return result(False, "invalid_native_page_size")
    shape, scope = plan["base_shape"], plan["question_contract"]["scope"]
    uri = _uri_bound(shape["ci"], scope)
    if uri["max_request_line_bytes"] > _MAX_URL_BYTES:
        return result(False, "native_uri_too_large", uri_bound=uri)
    try:
        records, table = m._execute_lookup_api(plan["native_call"])
    except Exception as exc:
        return result(False, "detail_count_lookup_failed", error_type=type(exc).__name__)
    if table != shape["table"] or not isinstance(records, list) or not records:
        return result(False, "nonempty_native_objects_unproven")
    tail = len(records) % executor.PAGE_SIZE
    pagination = {"native_page_size": executor.PAGE_SIZE, "tail_rows": tail,
                  "complete_under_native_static_full_nonfinal_page_contract": tail != 0,
                  "http_page_status_observed": False}
    evidence = {"lookup_rows": len(records), "pagination_proof": pagination, "uri_bound": uri}
    if tail == 0:
        return result(False, "native_completeness_unproven", **evidence)
    if any(not isinstance(row, dict) or not set(plan["schema_fields"]) <= row.keys() for row in records):
        return result(False, "native_fields_missing", **evidence)
    if any(not isinstance(row["id"], str) or not row["id"].strip() for row in records):
        return result(False, "native_identity_invalid", **evidence)
    if len({row["id"] for row in records}) != len(records):
        return result(False, "native_identity_not_unique", **evidence)
    if any(any(row[key] != value for key, value in scope.items()) for row in records):
        return result(False, "native_scope_mismatch", **evidence)
    if any(isinstance(row[column["field"]], (dict, list)) for row in records for column in shape["columns"]):
        return result(False, "nonflat_native_detail_value", **evidence)
    return result(True, "verified_same_scope_detail_object_count", **evidence,
                  scope=scope, total_count=len(records), total_count_role=plan["total_count_role"],
                  plan_sha256=_plan_digest(plan),
                  count_grain="one native resource per unique id; not distinct projected values",
                  null_detail_values_preserved=True)
