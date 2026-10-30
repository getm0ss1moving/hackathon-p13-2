#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Runbook 查询系统主入口。

流程：
  1. 加载 runbook items
  2. 构建 BM25 检索器
  3. 接收用户问题 → BM25 检索 → LLM 选择 → 参数填充 → 执行器执行
"""

import copy
from contextlib import closing
import json
import logging
import os
import re
import sqlite3
import sys
import time
from urllib.parse import quote

import requests

import runbook_executor as executor
import runbook_matcher as matcher
from runbook_retriever import RunbookRetriever
from runbook_matcher import match_runbook, _warm_schema_cache, get_llm, get_llm_events
from runbook_executor import execute
from runbook_items import RUNBOOK_ITEMS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class _APIPlanRefusal(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _data_url(ci, conditions, page, page_size):
    endpoint = "relations" if ci.startswith(("R_", "M_")) else "instances"
    url = f"{executor.BASE_URL}/rest/hackthon/db/{endpoint}/{ci}?pageNo={page}&pageSize={page_size}"
    if conditions:
        constraints = []
        for index, condition in enumerate(conditions):
            entry = {"simple": {"name": condition["key"], "value": condition["value"], "operator": condition["operator"]}}
            if index:
                entry["logOp"] = "and"
            constraints.append(entry)
        url += "&condition=" + quote(json.dumps({"constraint": constraints}, ensure_ascii=False))
    prepared = requests.Request("GET", url).prepare()
    request_bytes = len(("GET " + prepared.path_url + " HTTP/1.1\r\n").encode("utf-8"))
    return prepared.url, request_bytes


def _execute_bounded_api(item, diagnostics, *, session=None, request_line_limit=60000,
                         max_values=500, max_batches=64, max_http_requests=128,
                         max_records=1000000, seconds_limit=15, page_size=10000,
                         lookup_sources=(), empty_root_only=False, sg_rule_semijoin=False):
    """B 实验编排：真实 GET → 稳定键并集 → 原装载函数 → 一次原 SQL；不注入执行器缓存。"""
    if not (32 <= request_line_limit <= 65536 and 1 <= max_values <= 500
            and 1 <= max_batches <= 64 and 1 <= max_http_requests <= 128
            and max_records > 0 and seconds_limit > 0 and 1 <= page_size <= 10000):
        raise ValueError("分批资源边界无效")
    diagnostics.update(http_requests=0, steps=[], sql_executed=False, max_request_line_bytes=0)
    def stable_text_key(value):
        # 排除数字文本：SQLite可能依另一列的affinity将其与不同的服务端TEXT值判等。
        return isinstance(value, str) and bool(
            re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value)
            or (re.fullmatch(r"[0-9a-fA-F]{32}", value) and re.search(r"[a-dfA-DF]", value)))

    semijoin_root = None
    if sg_rule_semijoin:
        from runbook_sg_rule_semijoin import plan_security_group_rule_semijoin
        proof = plan_security_group_rule_semijoin(item, schema_columns=matcher._schema_columns,
                                                  ci_name_map=executor.CI_NAME_MAP)
        if empty_root_only or not proof["eligible"] or not proof["proof"]["already_prepared"]:
            raise _APIPlanRefusal("unverified_semijoin_plan")
        semijoin_root = proof["proof"]["root_table"]
        diagnostics["bound_api_calls"] = []
    deadline = time.perf_counter() + seconds_limit
    total_received = 0
    sql = item.get("sql", "")
    structure = matcher._sql_structure(sql).strip().rstrip(";").strip()
    if not re.match(r"^SELECT\b", structure, re.I) or ";" in structure or "{{" in sql or matcher._get_placeholders(item):
        raise _APIPlanRefusal("unsupported_or_unfilled_sql")
    sql_tables = {table.casefold(): table for table in matcher._extract_sql_tables(structure)}
    if not sql_tables:
        raise _APIPlanRefusal("sql_has_no_resource_table")
    calls = item.get("api_call") or []
    calls = calls if isinstance(calls, list) else [calls]
    dependencies = {}
    resources = []
    for step, call in enumerate(calls, 1):
        checked_call = copy.deepcopy(call)
        found = re.fullmatch(r"/rest/hackthon/db/(?:instances|relations)/([^/?]+)(?:\?[^#]*)?", call.get("url", ""))
        if call.get("method", "GET") != "GET" or not found or found[1] not in executor.CI_NAME_MAP:
            raise _APIPlanRefusal("unsupported_api_resource")
        ci = found[1]
        resources.append(ci)
        for index, constraint in enumerate(call.get("condition", {}).get("constraint", [])):
            simple = constraint.get("simple", {})
            field, value = simple.get("name"), simple.get("value")
            if (constraint.get("logOp", "and") != "and" or simple.get("operator", "equal") not in {"equal", "contain", "in"}
                    or field not in matcher._schema_columns.get(ci, [])):
                raise _APIPlanRefusal("unverified_api_condition")
            if "{{" in json.dumps(value):
                reference = re.fullmatch(r"\{\{\s*([A-Za-z_]\w*)\s+from step\s+([1-9]\d*)\s*\}\}", value) if isinstance(value, str) else None
                if not reference or step == 1 or int(reference[2]) != step - 1:
                    raise _APIPlanRefusal("nonadjacent_or_invalid_dependency")
                native_field = re.sub(r"\s*from step.*", "", value[2:-2].strip()).strip()
                if native_field != reference[1] or reference[1] not in matcher._schema_columns.get(resources[step - 2], []):
                    raise _APIPlanRefusal("unverified_dependency_field")
                dependencies[(step, index)] = reference[1]
                checked_call["condition"]["constraint"][index]["simple"]["value"] = "checked dependency"
            elif not matcher._valid_parameter_value(field, value, {"api_call": call}):
                raise _APIPlanRefusal("invalid_api_condition_value")
        if "{{" in json.dumps(checked_call):
            raise _APIPlanRefusal("unsupported_dependency_location")
    if empty_root_only and (
            len(resources) != 1 or executor.CI_NAME_MAP[resources[0]].casefold() not in sql_tables
            or len(re.findall(r"\bSELECT\b", structure, re.I)) != 1
            or re.search(r"\b(?:LEFT|RIGHT|FULL|UNION|INTERSECT|EXCEPT|WITH)\b", structure, re.I)):
        raise _APIPlanRefusal("empty_root_mode_requires_single_mandatory_root")
    tables = {}
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.trust_env = False
        session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))

    def check_time():
        if time.perf_counter() >= deadline:
            raise RuntimeError("本地数据读取/SQL 总耗时超限")

    def fetch(ci, conditions):
        nonlocal total_received
        page, records, expected_total = 1, [], None
        while True:
            check_time()
            url, size = _data_url(ci, conditions, page, page_size)
            if size > request_line_limit:
                raise _APIPlanRefusal("unsplittable_request_line")
            if diagnostics["http_requests"] >= max_http_requests:
                raise RuntimeError("本地数据 HTTP 次数超限，未发送后续请求")
            diagnostics["http_requests"] += 1
            diagnostics["max_request_line_bytes"] = max(diagnostics["max_request_line_bytes"], size)
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise RuntimeError("本地数据读取/SQL 总耗时超限")
            response = session.get(url, timeout=min(5, remaining), allow_redirects=False)
            if response.status_code != 200:
                raise RuntimeError(f"本地数据 HTTP {response.status_code}：{ci}")
            payload = response.json()
            objects = payload.get("objList") if isinstance(payload, dict) else None
            total = payload.get("totalNum") if isinstance(payload, dict) else None
            pages = payload.get("totalPageNo") if isinstance(payload, dict) else None
            if (not isinstance(payload, dict) or payload.get("error") is not None
                    or payload.get("success") is False
                    or not isinstance(objects, list) or not all(isinstance(record, dict) for record in objects)
                    or type(total) is not int or total < 0 or type(pages) is not int or pages < 0
                    or type(payload.get("currentPage")) is not int or type(payload.get("pageSize")) is not int
                    or payload.get("currentPage") != page or payload.get("pageSize") != page_size
                    or pages != (total + page_size - 1) // page_size or len(objects) > page_size):
                raise RuntimeError(f"本地数据响应/分页格式异常：{ci}")
            if expected_total is not None and expected_total != total:
                raise RuntimeError(f"本地数据分页期间总量变化：{ci}")
            if sg_rule_semijoin:
                endpoint = "relations" if ci.startswith(("R_", "M_")) else "instances"
                actual_call = {"method": "GET", "url": f"/rest/hackthon/db/{endpoint}/{ci}?pageNo={page}&pageSize={page_size}"}
                if conditions:
                    actual_call["condition"] = {"constraint": [
                        {"simple": {"name": condition["key"], "operator": condition["operator"],
                                    "value": copy.deepcopy(condition["value"])}, **({"logOp": "and"} if index else {})}
                        for index, condition in enumerate(conditions)]}
                diagnostics["bound_api_calls"].append(actual_call)
            expected_total = total
            records.extend(objects)
            total_received += len(objects)
            if total_received > max_records:
                raise RuntimeError("本地数据记录数超限")
            if page >= max(1, pages):
                if len(records) != total:
                    raise RuntimeError(f"本地数据分页不完整：{ci}")
                return records
            if len(objects) != page_size:
                raise RuntimeError(f"本地数据提前结束分页：{ci}")
            page += 1

    def batches(ci, conditions):
        pending, planned = [copy.deepcopy(conditions)], []
        while pending:
            current = pending.pop(0)
            candidates = [(len(c["value"]), index) for index, c in enumerate(current)
                          if c["operator"] == "in" and isinstance(c["value"], list) and len(c["value"]) > 1]
            too_many = any(length > max_values for length, _ in candidates)
            if not too_many and _data_url(ci, current, 1, page_size)[1] <= request_line_limit:
                planned.append(current)
                continue
            if not candidates:
                raise _APIPlanRefusal("unsplittable_request_line")
            _, index = max(candidates)
            values = current[index]["value"]
            middle = len(values) // 2
            halves = [copy.deepcopy(current), copy.deepcopy(current)]
            halves[0][index]["value"], halves[1][index]["value"] = values[:middle], values[middle:]
            pending[0:0] = halves
            if len(pending) + len(planned) > max_batches:
                raise _APIPlanRefusal("too_many_api_batches")
        return planned

    def table_name(ci):
        return executor.CI_NAME_MAP[ci]

    def sql_result():
        check_time()
        missing = set(sql_tables) - {name.casefold() for name in tables}
        if missing:
            raise _APIPlanRefusal("sql_resource_not_loaded")
        with closing(executor.load_into_sqlite({name: rows for name, rows in tables.items() if rows})) as connection:
            for name, rows in tables.items():
                if rows:
                    continue
                ci = executor.ORIG_TO_DESENS.get(name, name)
                columns = matcher._schema_columns.get(ci)
                if not columns:
                    raise _APIPlanRefusal("unknown_empty_table_schema")
                quote_name = lambda text: '"' + text.replace('"', '""') + '"'
                connection.execute("CREATE TABLE " + quote_name(name) + " (" + ",".join(quote_name(c) + " TEXT" for c in columns) + ")")
            connection.set_progress_handler(lambda: int(time.perf_counter() >= deadline), 1000)
            try:
                cursor = connection.execute(sql)
                columns = [column[0] for column in cursor.description]
                answer_rows = []
                while True:
                    chunk = cursor.fetchmany(1000)
                    if not chunk:
                        break
                    answer_rows.extend(dict(zip(columns, row)) for row in chunk)
                    if len(answer_rows) > max_records:
                        raise RuntimeError("SQL 结果记录数超限")
                check_time()
            except sqlite3.OperationalError as error:
                if "no such column" in str(error):
                    raise _APIPlanRefusal("required_sql_field_unavailable") from error
                raise
        diagnostics["sql_executed"] = True
        return {"sql": sql, "result": {"columns": columns, "rows": answer_rows, "row_count": len(answer_rows)}, "error": None}

    previous, previous_table = None, None
    try:
        for step, (call, ci) in enumerate(zip(calls, resources), 1):
            conditions = []
            for index, constraint in enumerate(call.get("condition", {}).get("constraint", [])):
                simple = constraint["simple"]
                field, value, operator = simple["name"], simple.get("value"), simple.get("operator", "equal")
                dependency = dependencies.get((step, index))
                if dependency:
                    if not previous:
                        if previous_table in lookup_sources:
                            raise _APIPlanRefusal("empty_lookup_source")
                        # 原执行器以最后一次同CI读取覆盖表；空前步若还会被覆盖，不能推出最终空域。
                        later_tables = {table_name(resource).casefold() for resource in resources[step - 1:]}
                        if previous_table.casefold() in later_tables:
                            raise _APIPlanRefusal("empty_dependency_source_overwritten")
                        simple_inner = (previous_table.casefold() in sql_tables and len(re.findall(r"\bSELECT\b", structure, re.I)) == 1
                                        and not re.search(r"\b(?:LEFT|RIGHT|FULL|UNION)\b", structure, re.I))
                        verified_join_root = semijoin_root == previous_table and step == 2
                        if not simple_inner and not verified_join_root:
                            raise _APIPlanRefusal("empty_dependency_source")
                        for folded, name in sql_tables.items():
                            canonical = next((table for table in executor.ORIG_TO_DESENS if table.casefold() == folded), None)
                            if canonical is None:
                                raise _APIPlanRefusal("unknown_empty_table_schema")
                            tables[canonical] = []
                        diagnostics["short_circuit"] = ("empty_verified_semijoin_root" if verified_join_root
                                                        else "empty_inner_join_input")
                        diagnostics["derived_empty_tables"] = sorted(tables)
                        return sql_result()
                    values = []
                    for record in previous:
                        part = record.get(dependency)
                        if matcher._missing_parameter(part):
                            raise _APIPlanRefusal("missing_dependency_values")
                        if isinstance(part, bool) or not isinstance(part, (str, int)):
                            raise _APIPlanRefusal("unusable_dependency_value")
                        if part not in values:
                            values.append(part)
                    if not values:
                        raise _APIPlanRefusal("missing_dependency_values")
                    value = values if len(values) > 1 or operator == "in" else values[0]
                    operator = "in" if isinstance(value, list) else "equal"  # 与原执行器的单键/多键转换一致。
                if isinstance(value, list) and operator != "in":
                    raise _APIPlanRefusal("list_requires_in_operator")
                conditions.append({"key": field, "value": value, "operator": operator})
            planned = batches(ci, conditions)
            if sg_rule_semijoin and step == 1 and len(planned) > 1:
                # 根表重复行也参与原JOIN；通用按id并集可能改变它的重数，首版不优化分批根读取。
                diagnostics["semijoin_outcome"] = "unsupported_root_batches_defer_to_original_executor"
                return None
            if len(planned) > 1 and table_name(ci).casefold() not in sql_tables:
                raise _APIPlanRefusal("batched_resource_not_consumed_by_sql")
            if len(planned) > 1 and "id" not in matcher._schema_columns.get(ci, []):
                raise _APIPlanRefusal("unverified_batch_merge_key")
            combined, by_id, key_type = [], {}, None
            semijoin_child_ids = set()
            for batch in planned:
                records = fetch(ci, batch)
                if sg_rule_semijoin and step == 2:
                    requested_parent_ids = set(batch[0]["value"])
                    for record in records:
                        parent_id = record.get("securityGroupId")
                        if not isinstance(parent_id, str) or parent_id not in requested_parent_ids:
                            raise _APIPlanRefusal("semijoin_child_outside_requested_parent_ids")
                        identity = record.get("id")
                        if not stable_text_key(identity):
                            diagnostics["semijoin_outcome"] = "unsupported_key_defer_to_original_executor"
                            return None
                        key = (type(identity), identity)
                        if key in semijoin_child_ids:
                            raise _APIPlanRefusal("duplicate_semijoin_child_key")
                        semijoin_child_ids.add(key)
                if len(planned) == 1:
                    combined = records
                    continue
                for record in records:
                    identity = record.get("id")
                    if isinstance(identity, bool) or not isinstance(identity, (str, int)) or matcher._missing_parameter(identity):
                        raise _APIPlanRefusal("unverified_batch_merge_key")
                    key_type = key_type or type(identity)
                    if type(identity) is not key_type:
                        raise _APIPlanRefusal("inconsistent_batch_merge_key_type")
                    if identity in by_id:
                        if by_id[identity] != record:
                            raise _APIPlanRefusal("conflicting_batch_record")
                    else:
                        by_id[identity] = record
                        combined.append(record)
            tables[table_name(ci)] = combined  # 后一逻辑步骤覆盖同名表，保持原执行器语义。
            previous, previous_table = combined, table_name(ci)
            diagnostics["steps"].append({"step": step, "ci": ci, "batches": len(planned), "rows": len(combined)})
            if sg_rule_semijoin and step == 1 and combined:
                # 非数字文本标识避免原SQLite JOIN与服务端TEXT IN在混合类型下发生不同的数值强制转换。
                if not all(stable_text_key(record.get("id")) for record in combined):
                    diagnostics["semijoin_outcome"] = "unsupported_key_defer_to_original_executor"
                    return None
            if empty_root_only:
                if combined:
                    diagnostics["empty_root_outcome"] = "nonempty_defer_to_original_executor"
                    return None
                # 此模式的调用方须先证明题文根条件；只在单GET根表真实为空时推导INNER域为空。
                for folded in sql_tables:
                    canonical = next((table for table in executor.ORIG_TO_DESENS if table.casefold() == folded), None)
                    if canonical is None:
                        raise _APIPlanRefusal("unknown_empty_table_schema")
                    tables[canonical] = []
                diagnostics["short_circuit"] = "verified_empty_root"
                diagnostics["derived_empty_tables"] = sorted(tables)
                return sql_result()
        for folded, name in sql_tables.items():
            if any(table.casefold() == folded for table in tables):
                continue
            ci = next((desens for table, desens in executor.ORIG_TO_DESENS.items() if table.casefold() == folded), None)
            if ci is None:
                raise _APIPlanRefusal("unsupported_sql_resource")
            tables[table_name(ci)] = fetch(ci, [])
        return sql_result()
    finally:
        if own_session:
            session.close()


def _single_ci_empty_eligibility(item):
    """单次已填参GET只消费同一张真实表；不认证题意，只证明空表执行域。"""
    calls = item.get("api_call") or []
    calls = calls if isinstance(calls, list) else [calls]
    if len(calls) != 1 or not isinstance(calls[0], dict) or calls[0].get("method", "GET") != "GET":
        return {"eligible": False, "reason": "not_one_get"}
    resource = re.fullmatch(r"/rest/hackthon/db/(?:instances|relations)/([^/?]+)(?:\?[^#]*)?", calls[0].get("url", ""))
    ci = resource[1] if resource else None
    table = executor.CI_NAME_MAP.get(ci)
    if not table or not matcher._schema_columns.get(ci) or matcher._get_placeholders(item):
        return {"eligible": False, "reason": "unknown_schema_or_parameters"}
    structure = matcher._sql_structure(item.get("sql", ""))
    if (not re.match(r"^\s*SELECT\b", structure, re.I)
            or len(re.findall(r"\bSELECT\b", structure, re.I)) != 1
            or re.search(r"\b(?:JOIN|WITH|UNION|INTERSECT|EXCEPT)\b", structure, re.I)
            or not re.search(r"\bFROM\s+" + re.escape(table) + r"\s*(?:;|$|WHERE\b|GROUP\b|HAVING\b|ORDER\b|LIMIT\b)", structure, re.I)
            or {name.casefold() for name in matcher._extract_sql_tables(structure)} != {table.casefold()}):
        return {"eligible": False, "reason": "not_one_direct_table"}
    return {"eligible": True, "reason": "same_single_get_sql_domain", "resource": ci, "table": table}


def _execution_has_result_columns(result):
    """原executor吞掉缺列错误会返回空columns；合法空SELECT仍有列名。"""
    if isinstance(result, list):
        return bool(result) and all(_execution_has_result_columns(part) for part in result)
    if not isinstance(result, dict):
        return False
    columns = result.get("columns")
    return (isinstance(columns, list) and bool(columns)
            and all(isinstance(name, str) and bool(name.strip()) for name in columns))


def _apply_empty_answer_fallback(output):
    """用户选择的计分策略：无法作答时猜空，保留失败证据，不声称已证真空。"""
    if os.environ.get("RUNBOOK_EMPTY_ANSWER_FALLBACK", "1") != "1":
        return output
    if output.get("matched_runbook") is not None and not output.get("error"):
        return output
    diagnostics = output.setdefault("diagnostics", {})
    diagnostics["empty_answer_fallback"] = {
        "policy": "empty_on_abstention_or_error",
        "answer_is_guess": True,
        "source_result_verified": False,
        "original_matched_runbook": output.get("matched_runbook"),
        "original_error": output.get("error"),
        "original_sql": output.get("sql"),
        "original_result": output.get("result"),
        "additional_model_requests": 0,
        "additional_http_requests": 0,
    }
    # 固定空SELECT仅用于提交猜测；不查询或推断任何业务资源。
    sql = "SELECT NULL AS value WHERE 0"
    with closing(sqlite3.connect(":memory:")) as connection:
        cursor = connection.execute(sql)
        result = {"columns": [column[0] for column in cursor.description],
                  "rows": cursor.fetchall(), "row_count": 0}
    return {**output, "matched_runbook": "empty_answer_fallback",
            "api_call": output.get("api_call"), "sql": sql,
            "result": result, "error": None, "diagnostics": diagnostics}


def _dependent_count_eligibility(item):
    """仅把已有相邻依赖COUNT计划交给有界执行器，保留其API和SQL。"""
    calls = item.get("api_call") or []
    if not isinstance(calls, list) or len(calls) < 2 or not any("from step" in json.dumps(call) for call in calls):
        return False
    structure = matcher._sql_structure(item.get("sql", ""))
    if (not re.match(r"^\s*SELECT\s+COUNT\s*\(\s*(?:\*|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)\s+(?:AS\s+)?[A-Za-z_]\w*\s+FROM\b", structure, re.I)
            or len(re.findall(r"\bSELECT\b", structure, re.I)) != 1
            or re.search(r"\b(?:LEFT|RIGHT|FULL|GROUP|HAVING|UNION|INTERSECT|EXCEPT|WITH)\b", structure, re.I)):
        return False
    return all(isinstance(call, dict) and call.get("method", "GET") == "GET" for call in calls)


class RunbookQuerySystem:
    def __init__(self):
        if len(RUNBOOK_ITEMS) == 132:
            matcher._verify_a132_sources()
            os.environ.setdefault('RUNBOOK_A132_CANDIDATE', '1')
            from runbook_issue3 import source_files,VERIFIED_PROFILES
            source_files()
            os.environ.setdefault('RUNBOOK_ISSUE3_CONTRACTS','1')
            os.environ.setdefault('RUNBOOK_ISSUE3_PROFILES',json.dumps(list(VERIFIED_PROFILES)))
        get_llm()  # 仅检查客户端配置，不发送模型请求。
        self.items = RUNBOOK_ITEMS
        started = time.perf_counter()
        self.retriever = RunbookRetriever(self.items)
        indexed_at = time.perf_counter()
        _warm_schema_cache()
        self.initialization_metrics = {
            "index_seconds": round(indexed_at - started, 6),
            "schema_warm_seconds": round(time.perf_counter() - indexed_at, 6),
            "template_count": len(self.items),
        }

    def query(self, user_question: str, diagnostics: dict = None) -> dict:
        """正常执行优先；按用户策略，将最后的拒答/显式错误转为空答案猜测。"""
        if os.environ.get('RUNBOOK_A132_CANDIDATE') == '1':
            obligations = self.retriever.retrieve_obligations(user_question)
            if len(obligations) > 1:
                return _apply_empty_answer_fallback(self._query_obligations(user_question, obligations, diagnostics))
        return _apply_empty_answer_fallback(self._query(user_question, diagnostics))

    def _query_obligations(self, question, obligations, diagnostics=None):
        """只执行r4给出的完整独立原文子句；同族不同view/实体不去重。"""
        diagnostics = diagnostics if diagnostics is not None else {}
        diagnostics.clear()
        first_event = len(get_llm_events())
        diagnostics.update(reason='matching_obligations', obligations=[], llm_calls=[],
                           api_execution_scope='independent_native_plans; top_level_api_is_execution_ledger')
        results, calls, statements, names = [], [], [], []
        previous_end = 0
        for obligation in obligations:
            start, end = obligation['start'], obligation['end']
            if (type(start) is not int or type(end) is not int or not previous_end <= start < end <= len(question)
                    or question[start:end] != obligation['text']):
                diagnostics['rejection'] = {'stage': 'retrieval', 'reason': 'invalid_obligation_span'}
                break
            previous_end = end
            part_diagnostics = {}
            output = self._query(obligation['text'], part_diagnostics)
            part_calls = output.get('api_call') or []
            calls.extend(part_calls if isinstance(part_calls, list) else [part_calls])
            if isinstance(output.get('sql'), str): statements.append(output['sql'])
            diagnostics['obligations'].append({'start': start, 'end': end, 'text': obligation['text'],
                'profile_ids': [c.id for c in obligation.get('candidates', [])],
                'matched_runbook': output.get('matched_runbook'), 'diagnostics': part_diagnostics})
            if output.get('matched_runbook') is None or output.get('error'):
                diagnostics['rejection'] = {'stage': 'obligation', 'reason': 'incomplete_obligation',
                                             'failed_index': len(diagnostics['obligations']) - 1}
                break
            names.append(output['matched_runbook'])
            result = output['result']
            results.extend(result if isinstance(result, list) else [result])
        diagnostics['llm_calls'] = get_llm_events()[first_event:]
        diagnostics['selected_templates'] = [p['diagnostics'].get('selected_template') for p in diagnostics['obligations']]
        diagnostics['match_seconds'] = round(sum(p['diagnostics'].get('match_seconds', 0) for p in diagnostics['obligations']), 4)
        diagnostics['execute_seconds'] = round(sum(p['diagnostics'].get('execute_seconds', 0) for p in diagnostics['obligations']), 4)
        if len(names) != len(obligations):
            diagnostics['reason'] = 'incomplete_obligation'
            return {'question': question, 'matched_runbook': None, 'api_call': calls, 'sql': None,
                    'result': None, 'error': None, 'diagnostics': diagnostics}
        diagnostics['reason'] = 'matched_composite'
        return {'question': question, 'matched_runbook': '+'.join(names), 'api_call': calls,
                'sql': '; '.join(statements), 'result': results, 'error': None, 'diagnostics': diagnostics}

    def _query(self, user_question: str, diagnostics: dict = None) -> dict:
        """
        查询入口：用户问题 → 结果。

        返回：
          {
            "question": 用户问题,
            "matched_runbook": 命中的runbook名称 或 None,
            "sql": 执行的SQL,
            "result": {"columns": [...], "rows": [...], "row_count": N},
            "error": None 或 错误信息
          }
        """
        started = time.perf_counter()
        first_event = len(get_llm_events())
        # 1. BM25 检索 + LLM 选择 + 参数填充
        match_details = {}
        diagnostics = diagnostics if diagnostics is not None else {}
        diagnostics.clear()
        diagnostics.update(match_seconds=0.0, execute_seconds=0.0, llm_calls=[], matching=match_details)
        bounded = os.environ.get("RUNBOOK_BOUNDED_API") == "1"
        try:
            if bounded:
                runbook_item = match_runbook(user_question, self.items, self.retriever, match_details, defer_api_validation=True)
            else:
                runbook_item = match_runbook(user_question, self.items, self.retriever, match_details)
        finally:
            # C的外传字典与B的结果内诊断共用事实；异常也保留已完成阶段。
            diagnostics.update(match_details)
            diagnostics["match_seconds"] = round(time.perf_counter() - started, 4)
            diagnostics["llm_calls"] = get_llm_events()[first_event:]
        matched_at = time.perf_counter()

        if runbook_item is None:
            return {
                "question": user_question,
                "matched_runbook": None,
                "sql": None,
                "result": None,
                "error": None,
                "diagnostics": diagnostics,
            }

        original_runbook_item = runbook_item
        if runbook_item.get('_issue3'):
            return self._query_issue3(user_question,runbook_item,diagnostics,matched_at)
        semijoin = False
        if os.environ.get("RUNBOOK_SG_RULE_SEMIJOIN") == "1":
            from runbook_sg_rule_semijoin import plan_security_group_rule_semijoin
            decision = plan_security_group_rule_semijoin(runbook_item, schema_columns=matcher._schema_columns,
                                                         ci_name_map=executor.CI_NAME_MAP)
            diagnostics["sg_rule_semijoin_plan"] = {key: value for key, value in decision.items() if key != "item"}
            if decision["eligible"]:
                runbook_item, semijoin = decision["item"], True

        logger.info(f"命中 runbook: {runbook_item['name']}")

        # 2. 执行
        diagnostics["execution"] = {"status": "started", "input_sql": runbook_item.get("sql")}
        execution = None
        sources = ()
        direct_empty = (_single_ci_empty_eligibility(runbook_item)
                        if os.environ.get("RUNBOOK_TYPED_EMPTY_ROOT") == "1" else None)
        dependent_count = (os.environ.get("RUNBOOK_TYPED_EMPTY_ROOT") == "1"
                           and _dependent_count_eligibility(runbook_item))
        independent_count = (os.environ.get("RUNBOOK_TYPED_EMPTY_ROOT") == "1"
                             and runbook_item.get("_closed_independent_count") is True)
        if semijoin:
            execution = diagnostics.setdefault("sg_rule_semijoin", {})
        elif bounded:
            execution = diagnostics.setdefault("bounded_api", {})
            lookup = match_details.get("resource_coverage", {})
            sources = [lookup["lookup"]["source_table"]] if lookup.get("covered_by_lookup") else []
        elif independent_count:
            execution = diagnostics.setdefault("typed_independent_count", {})
        elif runbook_item.get('_bounded_rule_details') is True:
            execution = diagnostics.setdefault('bounded_rule_details',{})
        elif direct_empty and direct_empty["eligible"]:
            diagnostics["typed_empty_root_eligibility"] = direct_empty
            execution = diagnostics.setdefault("typed_empty_root", {})
        elif dependent_count:
            execution = diagnostics.setdefault("typed_dependent_count", {})
            lookup = match_details.get("resource_coverage", {})
            sources = [lookup["lookup"]["source_table"]] if lookup.get("covered_by_lookup") else []
        elif os.environ.get("RUNBOOK_VERIFIED_EMPTY_ROOT") == "1":
            from runbook_empty_root import empty_root_eligibility
            schemas = {table: matcher._schema_columns.get(ci, []) for table, ci in executor.ORIG_TO_DESENS.items()}
            decision = empty_root_eligibility(user_question, runbook_item, schemas)
            diagnostics["verified_empty_root_eligibility"] = decision
            if decision["eligible"]:
                execution = diagnostics.setdefault("verified_empty_root", {})
        if execution is not None:
            try:
                options = {"lookup_sources": sources}
                if semijoin:
                    options["sg_rule_semijoin"] = True
                elif runbook_item.get('_bounded_rule_details') is True:
                    options.update(request_line_limit=4096,seconds_limit=60)
                elif not bounded and not dependent_count and not independent_count:
                    options["empty_root_only"] = True
                result = _execute_bounded_api(runbook_item, execution, **options)
            except _APIPlanRefusal as error:
                execution["refusal_reason"] = error.reason
                diagnostics["rejection"] = {"stage": "execution", "reason": error.reason}
                diagnostics["execute_seconds"] = round(time.perf_counter() - matched_at, 4)
                return {"question": user_question, "matched_runbook": None,
                        "api_call": None,  # 部分执行的完整计划不能冒充全部已执行API。
                        "sql": None, "result": None,
                        "error": None, "diagnostics": diagnostics}
            if result is None:
                # 当前受限优化没有完成证明时，使用原始未改计划；探测数据不写原缓存。
                runbook_item = original_runbook_item
                semijoin = False
                result = execute(runbook_item)
        else:
            result = execute(runbook_item)
        if (os.environ.get("RUNBOOK_TYPED_EMPTY_ROOT") == "1" and not semijoin and not bounded
                and result["error"] is None and not _execution_has_result_columns(result["result"])):
            recovery = diagnostics.setdefault("typed_result_recovery", {})
            try:
                recovered = _execute_bounded_api(runbook_item, recovery, lookup_sources=sources)
            except (_APIPlanRefusal, RuntimeError, ValueError, requests.RequestException, sqlite3.Error) as exc:
                recovery.update(status="unverified", error_type=type(exc).__name__, reason=str(exc))
            else:
                if recovered is not None and _execution_has_result_columns(recovered.get("result")):
                    result = recovered
                    recovery["status"] = "verified_original_plan_reexecuted"
        diagnostics["execute_seconds"] = round(time.perf_counter() - matched_at, 4)
        diagnostics["execution"].update(status="finished", sql=result["sql"], error=result["error"])
        if result["error"] is None and not _execution_has_result_columns(result["result"]):
            diagnostics["execution"].update(status="rejected", reason="unverified_result_schema")
            diagnostics["rejection"] = {"stage": "execution", "reason": "unverified_result_schema"}
            return {"question": user_question, "matched_runbook": None, "sql": None, "result": None,
                    "api_call": runbook_item.get("api_call"), "error": None, "diagnostics": diagnostics}

        expected_columns = runbook_item.get("_expected_result_columns")
        if (result["error"] is None and expected_columns is not None
                and (not isinstance(result["result"], dict)
                     or result["result"].get("columns") != expected_columns)):
            diagnostics["execution"].update(status="rejected", reason="closed_family_result_schema_mismatch",
                                           expected_columns=expected_columns)
            diagnostics["rejection"] = {"stage": "execution", "reason": "closed_family_result_schema_mismatch"}
            return {"question": user_question, "matched_runbook": None, "sql": None, "result": None,
                    "api_call": runbook_item.get("api_call"), "error": None, "diagnostics": diagnostics}

        response_api_call = (execution["bound_api_calls"] if semijoin
                             else runbook_item.get("api_call"))
        return {
            "question": user_question,
            "matched_runbook": runbook_item["name"],
            "api_call": response_api_call,
            "sql": result["sql"],
            "result": result["result"],
            "error": result["error"],
            "diagnostics": diagnostics,
        }

    def _query_issue3(self,question,item,diagnostics,matched_at):
        from runbook_issue3 import execute_plan
        execution=diagnostics.setdefault('issue3_execution',{})
        try:
            result=execute_plan(item,self.items,execution)
        except (ValueError,RuntimeError,OSError,sqlite3.Error,requests.RequestException) as exc:
            execution.update(status='blocked',error_type=type(exc).__name__,reason=str(exc))
            diagnostics.update(execute_seconds=round(time.perf_counter()-matched_at,4),reason='issue3_native_contract_blocked',
                rejection={'stage':'execution','reason':'issue3_native_contract_blocked'})
            return {'question':question,'matched_runbook':None,'api_call':None,
                'sql':None,'result':None,'error':None,'diagnostics':diagnostics}
        execution['status']='executed'
        diagnostics.update(execute_seconds=round(time.perf_counter()-matched_at,4),
            answer_completeness=execution['answer_completeness'],reason='matched_issue3_contract')
        return {'question':question,'matched_runbook':item['name'],'api_call':execution['executed_api_calls'],
                'sql':result['sql'],'result':result['result'],'error':result['error'],'diagnostics':diagnostics}


if __name__ == "__main__":
    system = RunbookQuerySystem()
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = system.query(question)
        if result["matched_runbook"] is None:
            sys.exit(0)
        print(f"已加载 {len(system.items)} 个 runbook items")
        print(f"\n问题: {question}")
        print(f"命中: {result['matched_runbook']}")
        print("诊断: " + json.dumps(result["diagnostics"], ensure_ascii=False))
        if result["error"]:
            print(f"错误: {result['error']}")
        elif result["result"]:
            r = result["result"]
            if isinstance(r, dict):
                print(f"行数: {r.get('row_count', 0)}")
                if r.get("rows"):
                    print(f"列: {r['columns']}")
                    for row in r["rows"][:5]:
                        print(f"  {row}")
            elif isinstance(r, list):
                for i, sub in enumerate(r):
                    print(f"步骤{i+1}: {sub.get('row_count', 0)} 行")
    else:
        # 交互模式
        print(f"已加载 {len(system.items)} 个 runbook items")
        while True:
            try:
                question = input("\n请输入查询问题（q退出）: ").strip()
                if question.lower() in ("q", "quit", "exit"):
                    break
                if not question:
                    continue
                result = system.query(question)
                if result["matched_runbook"] is None:
                    continue
                print(f"命中: {result['matched_runbook']}")
                if result["error"]:
                    print(f"错误: {result['error']}")
                elif result["result"]:
                    r = result["result"]
                    if isinstance(r, dict):
                        print(f"行数: {r.get('row_count', 0)}")
                        if r.get("rows"):
                            print(f"列: {r['columns']}")
                            for row in r["rows"][:5]:
                                print(f"  {row}")
                    elif isinstance(r, list):
                        for i, sub in enumerate(r):
                            print(f"步骤{i+1}: {sub.get('row_count', 0)} 行")
            except KeyboardInterrupt:
                break
