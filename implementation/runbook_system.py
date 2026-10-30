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
                         lookup_sources=()):
    """B 实验编排：真实 GET → 稳定键并集 → 原装载函数 → 一次原 SQL；不注入执行器缓存。"""
    if not (32 <= request_line_limit <= 65536 and 1 <= max_values <= 500
            and 1 <= max_batches <= 64 and 1 <= max_http_requests <= 128
            and max_records > 0 and seconds_limit > 0 and 1 <= page_size <= 10000):
        raise ValueError("分批资源边界无效")
    diagnostics.update(http_requests=0, steps=[], sql_executed=False, max_request_line_bytes=0)
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
            if (not isinstance(objects, list) or not all(isinstance(record, dict) for record in objects)
                    or type(total) is not int or total < 0 or type(pages) is not int or pages < 0
                    or payload.get("currentPage") != page or payload.get("pageSize") != page_size
                    or pages != (total + page_size - 1) // page_size or len(objects) > page_size):
                raise RuntimeError(f"本地数据响应/分页格式异常：{ci}")
            if expected_total is not None and expected_total != total:
                raise RuntimeError(f"本地数据分页期间总量变化：{ci}")
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
                        simple_inner = (previous_table.casefold() in sql_tables and len(re.findall(r"\bSELECT\b", structure, re.I)) == 1
                                        and not re.search(r"\b(?:LEFT|RIGHT|FULL|UNION)\b", structure, re.I))
                        if not simple_inner:
                            raise _APIPlanRefusal("empty_dependency_source")
                        for folded, name in sql_tables.items():
                            canonical = next((table for table in executor.ORIG_TO_DESENS if table.casefold() == folded), None)
                            if canonical is None:
                                raise _APIPlanRefusal("unknown_empty_table_schema")
                            tables[canonical] = []
                        diagnostics["short_circuit"] = "empty_inner_join_input"
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
            if len(planned) > 1 and table_name(ci).casefold() not in sql_tables:
                raise _APIPlanRefusal("batched_resource_not_consumed_by_sql")
            if len(planned) > 1 and "id" not in matcher._schema_columns.get(ci, []):
                raise _APIPlanRefusal("unverified_batch_merge_key")
            combined, by_id, key_type = [], {}, None
            for batch in planned:
                records = fetch(ci, batch)
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


class RunbookQuerySystem:
    def __init__(self):
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
                "error": "未命中任何查询手册",
                "diagnostics": diagnostics,
            }

        logger.info(f"命中 runbook: {runbook_item['name']}")

        # 2. 执行
        diagnostics["execution"] = {"status": "started", "input_sql": runbook_item.get("sql")}
        if bounded:
            execution = diagnostics.setdefault("bounded_api", {})
            lookup = match_details.get("resource_coverage", {})
            sources = [lookup["lookup"]["source_table"]] if lookup.get("covered_by_lookup") else []
            try:
                result = _execute_bounded_api(runbook_item, execution, lookup_sources=sources)
            except _APIPlanRefusal as error:
                execution["refusal_reason"] = error.reason
                diagnostics["execute_seconds"] = round(time.perf_counter() - matched_at, 4)
                return {"question": user_question, "matched_runbook": None, "sql": None, "result": None,
                        "error": "数据依赖或输出合同未满足：" + error.reason, "diagnostics": diagnostics}
        else:
            result = execute(runbook_item)
        diagnostics["execute_seconds"] = round(time.perf_counter() - matched_at, 4)
        diagnostics["execution"].update(status="finished", sql=result["sql"], error=result["error"])

        return {
            "question": user_question,
            "matched_runbook": runbook_item["name"],
            "api_call": runbook_item.get("api_call"),
            "sql": result["sql"],
            "result": result["result"],
            "error": result["error"],
            "diagnostics": diagnostics,
        }


if __name__ == "__main__":
    system = RunbookQuerySystem()
    print(f"已加载 {len(system.items)} 个 runbook items")

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"\n问题: {question}")
        result = system.query(question)
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
        while True:
            try:
                question = input("\n请输入查询问题（q退出）: ").strip()
                if question.lower() in ("q", "quit", "exit"):
                    break
                if not question:
                    continue
                result = system.query(question)
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
