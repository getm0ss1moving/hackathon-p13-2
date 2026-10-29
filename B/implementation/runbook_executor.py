#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通用 Runbook 执行器 — 选手不可修改此文件。

执行流程：
  1. 接收已填好参数的 RunbookItem（含 api_call 模板 + sql）
  2. 替换 api_call 中残留的 {{placeholder}}
  3. 调用 output-server API（自动翻页）
  4. 将结果载入内存 SQLite
  5. 执行 SQL，返回结果

执行器只认 api_call + sql，不关心 runbook 是怎么被选中的。
"""

import json
import re
import sqlite3
import logging
from urllib.parse import quote
from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8080"
PAGE_SIZE = 10000

# CI 名称映射：脱敏名 → CLOUD_ 原始名（SQL 中用原始名）
CI_NAME_MAP = {}
ORIG_TO_DESENS = {}
_pairs = [
    ("CLOUD_VM_NOVA", "VM_NOVA"), ("CLOUD_HOST", "HOST"), ("CLOUD_VOLUME", "VOLUME"),
    ("CLOUD_FLAVOR", "FLAVOR"), ("CLOUD_ELB", "ELB"), ("CLOUD_ROUTER", "ROUTER"),
    ("CLOUD_SUBNET", "SUBNET"), ("CLOUD_PORT", "PORT"), ("CLOUD_FLOATING_IPS", "FLOATING_IPS"),
    ("CLOUD_SECURITY_GROUP", "SECURITY_GROUP"), ("CLOUD_SECURITY_GROUP_RULE", "SECURITY_GROUP_RULE"),
    ("CLOUD_CLUSTER", "CLUSTER"), ("CLOUD_IMAGE", "IMAGE"), ("CLOUD_BMS", "BMS"),
    ("CLOUD_OBS_BUCKET", "OBS_BUCKET"), ("CLOUD_STORAGE_POOL", "STORAGE_POOL"),
    ("CLOUD_GAUSSDB_INSTANCE", "GAUSSDB_INSTANCE"), ("CLOUD_GAUSSDB_NODE", "GAUSSDB_NODE"),
    ("CLOUD_NETWORK", "NETWORK"), ("CLOUD_VFW", "VFW"), ("CLOUD_NET_NODE", "NET_NODE"),
    ("CLOUD_CCE_CLUSTER", "CCE_CLUSTER"), ("CLOUD_CCE_NODE", "CCE_NODE"),
    ("CLOUD_CCE_POD", "CCE_POD"), ("CLOUD_CCE_CONTAINER", "CCE_CONTAINER"),
    ("CLOUD_CCE_WORKLOAD", "CCE_WORKLOAD"), ("CLOUD_MIDDLEWARE", "MIDDLEWARE"),
    ("CLOUD_MIDDLEWARE_CLUSTER", "MIDDLEWARE_CLUSTER"),
    ("CLOUD_MODELARTS_INF_SERVICE", "MODELARTS_INF_SERVICE"),
    ("CLOUD_MODELARTS_INF_POOL", "MODELARTS_INF_POOL"),
    ("CLOUD_MODELARTS_INF_NODE", "MODELARTS_INF_NODE"),
    ("CLOUD_MODELARTS_INF_MODEL", "MODELARTS_INF_MODEL"),
    ("CLOUD_MODELARTS_TRAINING_JOB", "MODELARTS_TRAINING_JOB"),
    ("CLOUD_Application", "Application"), ("CLOUD_ApplicationModule", "ApplicationModule"),
    ("CLOUD_ApplicationModuleIns", "ApplicationModuleIns"),
    ("CLOUD_AZONE", "AZONE"), ("CLOUD_VM", "VM"),
    ("CLOUD_ELB_POOL", "ELB_POOL"), ("CLOUD_ELB_POOL_MEMBERS", "ELB_POOL_MEMBERS"),
    ("CLOUD_VOLUME_TYPE", "VOLUME_TYPE"), ("CLOUD_LISTENER", "LISTENER"),
    ("CLOUD_WORKSPACE_SERVICE", "WORKSPACE_SERVICE"),
    ("SYS_X86Server", "S_X86Server"), ("SYS_DeployNode", "S_DeployNode"),
    ("SYS_DeployNodeIP", "S_DeployNodeIP"), ("SYS_DeployInstance", "S_DeployInstance"),
    ("SYS_DeployComponent", "S_DeployComponent"), ("SYS_Service", "S_Service"),
    ("SYS_CloudService", "S_CloudService"), ("SYS_Device", "S_Device"),
    ("SYS_Switch", "S_Switch"), ("SYS_StorDevice", "S_StorDevice"),
    ("SYS_Router", "S_Router"), ("SYS_BusinessRegion", "S_BusinessRegion"),
    ("SYS_VM", "S_VM"), ("SYS_ResourcePool", "S_ResourcePool"),
    ("M_ClusterContainsPhyHost", "M_ClusterContainsPhyHost"),
    ("M_VMUsesImage", "M_VMUsesImage"),
    ("R_VOLUME_MOUNTON_VM", "R_VOLUME_MOUNTON_VM"),
    ("R_PORT_IN_SUBNET", "R_PORT_IN_SUBNET"),
    ("R_PORT_USE_SECURITY_GROUP", "R_PORT_USE_SECURITY_GROUP"),
]
for orig, desens in _pairs:
    CI_NAME_MAP[desens] = orig
    ORIG_TO_DESENS[orig] = desens


# ── API 调用层 ──────────────────────────────────────────────

_cache: Dict[str, list] = {}


def _is_relation(name: str) -> bool:
    return name.startswith("R_") or name.startswith("M_")


def _query_server(ci_desens: str, conditions: list = None) -> list:
    """调用 output-server，自动翻页取完所有数据。"""
    cache_key = ci_desens + "::" + json.dumps(conditions or [], sort_keys=True)
    if cache_key in _cache:
        return _cache[cache_key]

    endpoint = "relations" if _is_relation(ci_desens) else "instances"
    all_records = []
    page_no = 1
    while True:
        url = f"{BASE_URL}/rest/hackthon/db/{endpoint}/{ci_desens}?pageNo={page_no}&pageSize={PAGE_SIZE}"
        if conditions:
            cond_json = {"constraint": []}
            for i, c in enumerate(conditions):
                item = {"simple": {"name": c["key"], "value": c["value"], "operator": c.get("operator", "equal")}}
                if i > 0:
                    item["logOp"] = "and"
                cond_json["constraint"].append(item)
            url += "&condition=" + quote(json.dumps(cond_json, ensure_ascii=False))
        try:
            r = requests.get(url, timeout=120, verify=False)
            data = r.json()
        except Exception as e:
            logger.error(f"API error: {ci_desens} page {page_no}: {e}")
            break
        records = data.get("objList", [])
        all_records.extend(records)
        total_pages = data.get("totalPageNo", 0)
        if page_no >= total_pages or len(records) < PAGE_SIZE:
            break
        page_no += 1

    _cache[cache_key] = all_records
    return all_records


# ── SQLite 内存执行层 ───────────────────────────────────────

def _infer_type(values: list) -> str:
    for val in values:
        if val is None:
            continue
        if isinstance(val, bool):
            return "TEXT"
        if isinstance(val, int):
            return "INTEGER"
        if isinstance(val, float):
            return "REAL"
        return "TEXT"
    return "TEXT"


def _to_sqlite_val(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, (int, float)):
        return val
    return str(val)


def load_into_sqlite(tables_dict: Dict[str, list]) -> sqlite3.Connection:
    """将 {table_name: [records]} 载入内存 SQLite，返回连接。"""
    conn = sqlite3.connect(":memory:")
    for table_name, records in tables_dict.items():
        if not records:
            conn.execute(f'CREATE TABLE "{table_name}" ("_empty" TEXT)')
            conn.execute(f'INSERT INTO "{table_name}" VALUES ("")')
            continue
        all_keys = sorted({k for r in records for k in r})
        col_types = {}
        for key in all_keys:
            samples = [r.get(key) for r in records if key in r]
            col_types[key] = _infer_type(samples)
        col_defs = ", ".join(f'"{k}" {col_types[k]}' for k in all_keys)
        conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
        placeholders = ", ".join(["?"] * len(all_keys))
        rows = [tuple(_to_sqlite_val(r.get(k)) for k in all_keys) for r in records]
        conn.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', rows)
    conn.commit()
    return conn


def _extract_sql_tables(sql: str) -> set:
    tables = set()
    for m in re.finditer(r"FROM\s+(\w+)", sql, re.IGNORECASE):
        tables.add(m.group(1))
    for m in re.finditer(r"JOIN\s+(\w+)", sql, re.IGNORECASE):
        tables.add(m.group(1))
    tables.discard("SELECT")
    return tables


# ── api_call 执行层 ─────────────────────────────────────────

def _replace_placeholders(obj, values: dict):
    """递归替换 obj 中的 {{placeholder}}。"""
    if isinstance(obj, str):
        for key, val in values.items():
            if val:
                obj = obj.replace(f"{{{{{key}}}}}", val)
        return obj
    if isinstance(obj, dict):
        return {k: _replace_placeholders(v, values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_placeholders(i, values) for i in obj]
    return obj


def _execute_single_api_call(api_call: dict, prev_step_records: list = None) -> Tuple[list, str]:
    """执行单个 api_call 步骤，返回 (records, orig_table_name)。"""
    url_path = api_call["url"]
    desens_name = url_path.split("/")[-1].split("?")[0]
    orig_name = CI_NAME_MAP.get(desens_name, desens_name)

    conditions = []
    cond = api_call.get("condition")
    if cond:
        for c in cond.get("constraint", []):
            simple = c.get("simple", {})
            key = simple.get("name", "")
            value = simple.get("value", "")
            operator = simple.get("operator", "equal")
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                field_name = value.replace("{{", "").replace("}}", "").strip()
                if "from step" in field_name.lower():
                    field_name = re.sub(r"\s*from step.*", "", field_name).strip()
                if prev_step_records and field_name:
                    vals = list(set(r.get(field_name, "") for r in prev_step_records if r.get(field_name)))
                    if vals:
                        if len(vals) == 1:
                            conditions.append({"key": key, "value": vals[0], "operator": "in" if operator == "in" else "equal"})
                        else:
                            conditions.append({"key": key, "value": vals, "operator": "in"})
                continue
            conditions.append({"key": key, "value": value, "operator": operator})

    records = _query_server(desens_name, conditions)
    return records, orig_name


def _execute_api_call(api_call) -> Dict[str, list]:
    """执行 api_call（单个或列表），返回 {orig_table_name: records}。"""
    if isinstance(api_call, list):
        all_records = {}
        prev_step_records = None
        for step in api_call:
            step_records, step_name = _execute_single_api_call(step, prev_step_records)
            if step_name:
                all_records[step_name] = step_records
            prev_step_records = step_records
        return all_records
    else:
        records, name = _execute_single_api_call(api_call)
        return {name: records} if name else {}


# ── 公共执行入口 ────────────────────────────────────────────

def execute(runbook_item: dict) -> dict:
    """
    执行一个已填好参数的 runbook item，返回执行结果。

    输入 runbook_item 结构：
      {
        "id": "...",
        "name": "...",
        "api_call": {...} 或 [...],   # 含已填充的 API 调用模板
        "sql": "SELECT ...",          # 要在内存 SQLite 上执行的 SQL
        "params": {...}               # 已填充的参数（用于替换残留占位符）
      }

    返回：
      {
        "sql": "执行的SQL",
        "result": {"columns": [...], "rows": [...], "row_count": N},
        "error": None 或 错误信息
      }
    """
    api_call = runbook_item.get("api_call")
    sql = runbook_item.get("sql", "")
    params = runbook_item.get("params", {})

    # 替换 api_call 和 sql 中可能残留的占位符
    param_values = {}
    if isinstance(params, dict):
        cond_list = params.get("condition", [])
        if isinstance(cond_list, list):
            for c in cond_list:
                if isinstance(c, dict):
                    name = c.get("name", "")
                    value = c.get("value", "")
                    if isinstance(value, str) and not value.startswith("{{"):
                        param_values[name] = value
    api_call = _replace_placeholders(api_call, param_values)
    sql = _replace_placeholders(sql, param_values)

    # 执行 API 调用
    tables_dict = _execute_api_call(api_call)

    # 补充 SQL 中引用但 api_call 未覆盖的表
    sql_tables = _extract_sql_tables(sql)
    for table in sql_tables:
        if table in tables_dict:
            continue
        desens = ORIG_TO_DESENS.get(table, table)
        tables_dict[table] = _query_server(desens)

    # 载入 SQLite 并执行 SQL
    try:
        conn = load_into_sqlite(tables_dict)
        sqls = [s.strip() for s in sql.split(";") if s.strip()]
        results = []
        for s in sqls:
            try:
                cursor = conn.execute(s)
                cols = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
            except sqlite3.OperationalError as e:
                if "no such column" in str(e):
                    cols = []
                    rows = []
                else:
                    raise
            if rows:
                result_rows = [
                    {cols[i]: (row[i] if not isinstance(row[i], bytes) else str(row[i])) for i in range(len(cols))}
                    for row in rows
                ]
                results.append({"columns": cols, "rows": result_rows, "row_count": len(result_rows)})
            else:
                results.append({"columns": cols, "rows": [], "row_count": 0})
        conn.close()
        answer = results[0] if len(results) == 1 else results
        return {"sql": sql, "result": answer, "error": None}
    except Exception as e:
        return {"sql": sql, "result": None, "error": str(e)}
