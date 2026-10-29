#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM 选择 + 参数填充 + SQL精调 — 选手可修改此文件来优化匹配准确率。

流程：
  1. BM25 检索候选 runbook items
  2. LLM 从候选中选择最匹配的 item
  3. LLM 从用户问题中提取参数值，填充占位符
  4. LLM 根据用户问题精调SQL（调整GROUP BY/SELECT/WHERE/ORDER BY等）
"""

import copy
import json
import logging
import os
import re
import ssl
from typing import List, Optional

import httpx
import requests
from openai import OpenAI

from runbook_retriever import RunbookRetriever, Candidate

logger = logging.getLogger(__name__)

SCHEMA_BASE_URL = "http://127.0.0.1:8080"

_ORIG_TO_DESENS = {
    "CLOUD_VM_NOVA": "VM_NOVA", "CLOUD_HOST": "HOST", "CLOUD_VOLUME": "VOLUME",
    "CLOUD_FLAVOR": "FLAVOR", "CLOUD_ELB": "ELB", "CLOUD_ROUTER": "ROUTER",
    "CLOUD_SUBNET": "SUBNET", "CLOUD_PORT": "PORT", "CLOUD_FLOATING_IPS": "FLOATING_IPS",
    "CLOUD_SECURITY_GROUP": "SECURITY_GROUP", "CLOUD_SECURITY_GROUP_RULE": "SECURITY_GROUP_RULE",
    "CLOUD_CLUSTER": "CLUSTER", "CLOUD_IMAGE": "IMAGE", "CLOUD_BMS": "BMS",
    "CLOUD_OBS_BUCKET": "OBS_BUCKET", "CLOUD_STORAGE_POOL": "STORAGE_POOL",
    "CLOUD_GAUSSDB_INSTANCE": "GAUSSDB_INSTANCE", "CLOUD_GAUSSDB_NODE": "GAUSSDB_NODE",
    "CLOUD_NETWORK": "NETWORK", "CLOUD_VFW": "VFW", "CLOUD_NET_NODE": "NET_NODE",
    "CLOUD_CCE_CLUSTER": "CCE_CLUSTER", "CLOUD_CCE_NODE": "CCE_NODE",
    "CLOUD_CCE_POD": "CCE_POD", "CLOUD_CCE_CONTAINER": "CCE_CONTAINER",
    "CLOUD_CCE_WORKLOAD": "CCE_WORKLOAD", "CLOUD_MIDDLEWARE": "MIDDLEWARE",
    "CLOUD_MIDDLEWARE_CLUSTER": "MIDDLEWARE_CLUSTER",
    "CLOUD_MODELARTS_INF_SERVICE": "MODELARTS_INF_SERVICE",
    "CLOUD_MODELARTS_INF_POOL": "MODELARTS_INF_POOL",
    "CLOUD_MODELARTS_INF_NODE": "MODELARTS_INF_NODE",
    "CLOUD_MODELARTS_INF_MODEL": "MODELARTS_INF_MODEL",
    "CLOUD_MODELARTS_TRAINING_JOB": "MODELARTS_TRAINING_JOB",
    "CLOUD_Application": "Application", "CLOUD_ApplicationModule": "ApplicationModule",
    "CLOUD_ApplicationModuleIns": "ApplicationModuleIns",
    "CLOUD_AZONE": "AZONE", "CLOUD_VM": "VM",
    "CLOUD_ELB_POOL": "ELB_POOL", "CLOUD_ELB_POOL_MEMBERS": "ELB_POOL_MEMBERS",
    "CLOUD_VOLUME_TYPE": "VOLUME_TYPE", "CLOUD_LISTENER": "LISTENER",
    "CLOUD_WORKSPACE_SERVICE": "WORKSPACE_SERVICE",
    "SYS_X86Server": "S_X86Server", "SYS_DeployNode": "S_DeployNode",
    "SYS_DeployNodeIP": "S_DeployNodeIP", "SYS_DeployInstance": "S_DeployInstance",
    "SYS_DeployComponent": "S_DeployComponent", "SYS_Service": "S_Service",
    "SYS_CloudService": "S_CloudService", "SYS_Device": "S_Device",
    "SYS_Switch": "S_Switch", "SYS_StorDevice": "S_StorDevice",
    "SYS_Router": "S_Router", "SYS_BusinessRegion": "S_BusinessRegion",
    "SYS_VM": "S_VM", "SYS_ResourcePool": "S_ResourcePool",
    "M_ClusterContainsPhyHost": "M_ClusterContainsPhyHost",
    "M_VMUsesImage": "M_VMUsesImage",
    "R_VOLUME_MOUNTON_VM": "R_VOLUME_MOUNTON_VM",
    "R_PORT_IN_SUBNET": "R_PORT_IN_SUBNET",
    "R_PORT_USE_SECURITY_GROUP": "R_PORT_USE_SECURITY_GROUP",
}


def _extract_sql_tables(sql):
    tables = set()
    for m in re.finditer(r"FROM\s+(\w+)", sql, re.IGNORECASE):
        tables.add(m.group(1))
    for m in re.finditer(r"JOIN\s+(\w+)", sql, re.IGNORECASE):
        tables.add(m.group(1))
    return tables


_schema_cache = {}


def _warm_schema_cache():
    """预热schema缓存：查询所有表的结构。"""
    if _schema_cache:
        return
    for orig, desens in _ORIG_TO_DESENS.items():
        try:
            r = requests.get(f"{SCHEMA_BASE_URL}/rest/hackthon/db/schema/{desens}",
                             timeout=5)
            data = r.json()
            cols = data.get("columns", [])
            samples = data.get("sample_data", [])
            row_count = data.get("row_count", 0)
            col_str = ", ".join(cols)
            sample_str = ""
            if samples:
                s = samples[0]
                pairs = [f"{k}={v}" for k, v in list(s.items())[:8]]
                sample_str = " | 示例: " + ", ".join(pairs)
            _schema_cache[orig] = f"表 {orig} ({row_count}行): [{col_str}]{sample_str}"
        except Exception:
            _schema_cache[orig] = f"表 {orig}: (获取失败)"


def _get_table_schemas(sql):
    tables = _extract_sql_tables(sql)
    if not tables:
        return ""
    schemas = []
    for table in sorted(tables):
        if table in _schema_cache:
            schemas.append(_schema_cache[table])
            continue
        desens = _ORIG_TO_DESENS.get(table, table)
        try:
            r = requests.get(f"{SCHEMA_BASE_URL}/rest/hackthon/db/schema/{desens}",
                             timeout=5)
            data = r.json()
            cols = data.get("columns", [])
            samples = data.get("sample_data", [])
            row_count = data.get("row_count", 0)
            col_str = ", ".join(cols)
            sample_str = ""
            if samples:
                s = samples[0]
                pairs = [f"{k}={v}" for k, v in list(s.items())[:8]]
                sample_str = " | 示例: " + ", ".join(pairs)
            entry = f"表 {table} ({row_count}行): [{col_str}]{sample_str}"
            _schema_cache[table] = entry
            schemas.append(entry)
        except Exception as e:
            entry = f"表 {table}: (获取失败)"
            _schema_cache[table] = entry
            schemas.append(entry)
    return "\n".join(schemas)

# ── 配置 ──────────────────────────────────────────────

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ── LLM 客户端 ────────────────────────────────────────

_llm_client = None


def get_llm():
    global _llm_client
    if _llm_client is None:
        if not DEEPSEEK_API_KEY.strip():
            raise RuntimeError("未设置 DEEPSEEK_API_KEY，请先在本机配置环境变量后重新启动；不要将密钥写入代码或聊天。")
        ca_file = os.environ.get("SSL_CERT_FILE")
        verify = ssl.create_default_context(cafile=ca_file) if ca_file else True
        _llm_client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            http_client=httpx.Client(verify=verify, timeout=60.0, trust_env=False),
        )
    return _llm_client


def llm_ask(prompt: str) -> str:
    """调用 LLM，返回文本响应。"""
    resp = get_llm().chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你是一个查询手册匹配助手，严格按格式输出。"},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    return resp.choices[0].message.content.strip()


# ── Prompt 模板 ────────────────────────────────────────

SELECT_RUNBOOK_PROMPT = """从查询手册列表中选出与用户问题最匹配的编号，仅输出数字。

匹配规则：
1. 资源类型必须匹配。ECS/虚拟机/VM_NOVA是同一类型，VPC/ROUTER是同一类型，云硬盘/VOLUME是同一类型。
2. 查询结构应一致，但以下差异不影响匹配：
   - 区域名不同（如region_guian2 vs region_guian4）是参数值差异，不是结构差异
   - 租户名不同（如Tenant_A vs Tenant_B）是参数值差异
   - 可用区不同（如az0.dc0 vs az1.dc0）是参数值差异
   - 资源名称不同（如vm-001 vs vm-002）是参数值差异
   - 同义词视为相同：统计=分布=汇总，列表=清单，数量=总数，异常=错误
   - "各租户"和"各VDC"在涉及ECS/VPC等资源时视为相同维度
3. 只要资源类型和查询目的（查数量/查列表/查详情/查统计）一致就应匹配。
4. 尽量选择最接近的，不确定时选最相似的而非返回0。

0=确实完全不匹配（资源类型和查询目的都不同）

用户问题：{user_question}

查询手册列表：
{runbook_list}

输出编号："""


FILL_PARAMS_PROMPT = """从用户问题中提取以下参数的值，每行一个，格式：参数名=值。提取不到的留空。

查询手册示例（{{}}内为参数占位，对照示例从用户问题中提取对应值）：
{examples}

参数列表：
{placeholder_list}

用户问题：{user_question}

输出："""


JOIN_RELATIONS = """可用JOIN关系（表A的字段 = 表B的字段）:
- CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id (虚拟机→规格)
- CLOUD_VM_NOVA.hostId = CLOUD_HOST.id (虚拟机→宿主机)
- CLOUD_VM_NOVA.clusterId = CLOUD_CLUSTER.id (虚拟机→集群)
- CLOUD_VM_NOVA.resId = CLOUD_PORT.devId (虚拟机→端口)
- CLOUD_VM_NOVA.id = SYS_DeployNode.vmId (虚拟机→部署节点)
- CLOUD_HOST.serverId = SYS_X86Server.id (宿主机→物理服务器)
- CLOUD_VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId, R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id (虚拟机→云硬盘)
- CLOUD_VM_NOVA.id = M_VMUsesImage.source_Instance_Id, M_VMUsesImage.target_Instance_Id = CLOUD_IMAGE.id (虚拟机→镜像)
- CLOUD_CLUSTER.id = M_ClusterContainsPhyHost.source_Instance_Id, M_ClusterContainsPhyHost.target_Instance_Id = CLOUD_HOST.id (集群→宿主机)
- CLOUD_ROUTER.nativeId = CLOUD_PORT.devNativeId (VPC→端口)
- CLOUD_PORT.id = R_PORT_IN_SUBNET.portId, R_PORT_IN_SUBNET.subnetId = CLOUD_SUBNET.id (端口→子网)
- CLOUD_PORT.id = R_PORT_USE_SECURITY_GROUP.portId, R_PORT_USE_SECURITY_GROUP.sgId = CLOUD_SECURITY_GROUP.id (端口→安全组)
- CLOUD_ELB.id = CLOUD_LISTENER.elbId (ELB→监听器)
- CLOUD_SECURITY_GROUP.id = CLOUD_SECURITY_GROUP_RULE.securityGroupId (安全组→规则)
- CLOUD_GAUSSDB_INSTANCE.id = CLOUD_GAUSSDB_NODE.ref_instanceId (GaussDB实例→节点)
- CLOUD_MODELARTS_INF_SERVICE.ref_poolId = CLOUD_MODELARTS_INF_POOL.id (推理服务→资源池)
- CLOUD_Application.id = CLOUD_ApplicationModule.appId (应用→模块)
- CLOUD_ApplicationModule.id = CLOUD_ApplicationModuleIns.appModuleId (模块→实例)
- SYS_Service.cloudServiceId = SYS_CloudService.id (服务→云服务)
- SYS_DeployComponent.serviceId = SYS_Service.id (部署组件→服务)
- SYS_DeployInstance.deployComponentId = SYS_DeployComponent.id (部署实例→组件)
- SYS_DeployInstance.deployNodeId = SYS_DeployNode.id (部署实例→节点)"""


REFINE_SQL_PROMPT = """你是SQL精调助手。根据用户问题调整SQL，使其精确回答问题。

调整规则：
1. SELECT列：问题要什么字段就SELECT什么，去掉多余的列，补充缺少的列。只能使用下方表结构中存在的列名。
2. GROUP BY：问题按什么维度分组就GROUP BY什么字段，不多不少。问"各区域/各租户/各可用区"必须加GROUP BY对应字段。
3. 聚合函数：问"数量/总数"用COUNT(*)或COUNT(DISTINCT col)；问"总容量/总量"用SUM()；问"平均"用AVG()；问"最大/最小"用MAX()/MIN()
4. 排序：问"最多/最大"加ORDER BY ... DESC；问"最少/最小"加ORDER BY ... ASC。禁止使用LIMIT！
5. 禁止添加WHERE子句！所有筛选条件已通过API条件实现，不要在SQL中加WHERE。
6. 不改表名(CLOUD_*/M_*/R_*/SYS_*格式)。可以增减JOIN，但JOIN条件必须使用下方JOIN关系参考中的正确关联字段。
7. 使用SQLite方言语法。
8. 如果当前SQL已经正确回答问题，原样返回，不要画蛇添足。

{join_relations}

表结构信息：
{schemas}

用户问题：{question}
当前SQL：{sql}

只输出调整后的SQL语句，不要解释："""


# ── 选择 + 填充 ────────────────────────────────────────

def _format_runbook_list(items: list) -> str:
    """格式化为 LLM prompt 中的编号列表。"""
    lines = []
    for i, item in enumerate(items):
        examples_str = "; ".join(item.get("examples", []))
        resources_str = "/".join(item.get("resources", []))
        lines.append(f"{i + 1}. {item['name']} - {item.get('description', '')} "
                     f"[资源类型：{resources_str}] (示例：{examples_str})")
    return "\n".join(lines)


def _get_placeholders(item: dict) -> List[str]:
    """提取 item 中所有 {{占位符}} 名称，去重保序。
    排除 'XXX from step N' 类型的占位符——这些由执行器自动填充。"""
    text = json.dumps({k: v for k, v in item.items()
                       if k in ("api_call", "sql", "params")},
                      ensure_ascii=False)
    placeholders = re.findall(r"\{\{(.+?)\}\}", text)
    seen = []
    for p in placeholders:
        if "from step" in p.lower():
            continue
        if p not in seen:
            seen.append(p)
    return seen


def _auto_fill_params(user_question: str, values: dict, placeholders: list):
    """从用户问题中自动提取常见参数值，填充LLM未填的占位符。"""
    
    if 'logicalRegionName' in placeholders and not values.get('logicalRegionName'):
        m = re.search(r'region_(\w+)', user_question)
        if m:
            values['logicalRegionName'] = 'region_' + m.group(1)
        elif '贵安' in user_question:
            values['logicalRegionName'] = 'region_guian4'
    
    if 'azoneName' in placeholders and not values.get('azoneName'):
        m = re.search(r'az\d+\.dc\d+', user_question)
        if m:
            values['azoneName'] = m.group(0)
        else:
            m = re.search(r'az\w+', user_question, re.IGNORECASE)
            if m and 'az' in m.group(0).lower():
                values['azoneName'] = m.group(0)
    
    if 'status' in placeholders and not values.get('status'):
        if any(k in user_question for k in ['运行中', '正在跑', 'ACTIVE', 'active']):
            values['status'] = 'active'
        elif any(k in user_question for k in ['异常', '错误', 'ERROR', 'error']):
            values['status'] = 'error'
        elif any(k in user_question for k in ['停机', '停止', 'SHUTOFF', 'shutoff']):
            values['status'] = 'shutoff'
    
    if 'privateIps' in placeholders and not values.get('privateIps'):
        m = re.search(r'@[\da-fA-F]+@[\da-fA-F]+@', user_question)
        if m:
            values['privateIps'] = m.group(0)
        else:
            m = re.search(r'@[\da-fA-F]+@', user_question)
            if m:
                values['privateIps'] = m.group(0)
            else:
                m = re.search(r'\d+\.\d+\.\d+\.\d+', user_question)
                if m:
                    values['privateIps'] = m.group(0)
    
    if 'bootable' in placeholders and not values.get('bootable'):
        if '可启动' in user_question:
            values['bootable'] = 'True'
    
    if 'assetStatus' in placeholders and not values.get('assetStatus'):
        if '报废' in user_question:
            values['assetStatus'] = 'scrapped'
        elif '运行' in user_question or '在网' in user_question:
            values['assetStatus'] = 'running'
    
    if 'name' in placeholders and not values.get('name'):
        for pattern, regex in [
            ('VPC', r'VPC\s*(\S+)'),
            ('集群', r'集群\s*(\S+)'),
            ('ECS', r'ECS\s*(\S+)'),
            ('ELB', r'ELB\s*(\S+)'),
        ]:
            m = re.search(regex, user_question)
            if m:
                candidate = m.group(1).rstrip('，。的')
                if candidate and len(candidate) > 2:
                    values['name'] = candidate
                    break
    
    if 'tenantName' in placeholders and not values.get('tenantName'):
        m = re.search(r'租户\s*(\S+)', user_question)
        if m:
            values['tenantName'] = m.group(1).rstrip('，。的')
    
    if 'vdcName' in placeholders and not values.get('vdcName'):
        m = re.search(r'VDC\s*(\S+)', user_question)
        if m:
            values['vdcName'] = m.group(1).rstrip('，。的')
    
    if 'hostName' in placeholders and not values.get('hostName'):
        m = re.search(r'宿主机\s*(\S+)', user_question)
        if m:
            values['hostName'] = m.group(1).rstrip('，。的')
        else:
            m = re.search(r'kvm[\w-]+', user_question)
            if m:
                values['hostName'] = m.group(0)
    
    if 'clusterName' in placeholders and not values.get('clusterName'):
        m = re.search(r'集群\s*(\S+)', user_question)
        if m:
            values['clusterName'] = m.group(1).rstrip('，。的')


def _fill_params(item: dict, values: dict, user_question: str = "") -> bool:
    """用 values 填充 item 中的 {{占位符}}。
    
    未填充的占位符替换为空字符串，并清理API条件和SQL中的空值。
    始终返回 True（支持可选参数）。
    """
    def replace(obj):
        if isinstance(obj, str):
            for key, val in values.items():
                if val:
                    obj = obj.replace(f"{{{{{key}}}}}", val)
        if isinstance(obj, dict):
            return {k: replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [replace(i) for i in obj]
        return obj

    def replace_unfilled(obj):
        """将残留的 {{xxx}} 占位符替换为空字符串（保留 from step 类型）。"""
        if isinstance(obj, str):
            def _replacer(m):
                inner = m.group(1)
                if "from step" in inner.lower():
                    return m.group(0)
                return ""
            return re.sub(r"\{\{(.+?)\}\}", _replacer, obj)
        if isinstance(obj, dict):
            return {k: replace_unfilled(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [replace_unfilled(i) for i in obj]
        return obj

    for field in ["params", "api_call", "sql"]:
        if field in item:
            item[field] = replace(item[field])

    remaining = re.findall(r"\{\{.+?\}\}", json.dumps(item, ensure_ascii=False))
    remaining = [r for r in remaining if "from step" not in r.lower()]

    if remaining:
        logger.info(f"可选参数未填充，清理空值: {remaining}")
        for field in ["params", "api_call", "sql"]:
            if field in item:
                item[field] = replace_unfilled(item[field])
        _cleanup_empty_api_conditions(item)
        if "sql" in item:
            item["sql"] = _cleanup_sql_empty_where(item["sql"])

    return True


def _fix_native_id_to_name(item: dict, parsed: dict):
    """如果api_call中nativeId条件的值不像UUID，改为name条件。"""
    native_val = parsed.get("nativeId", "")
    if not native_val:
        return
    # UUID格式: 8-4-4-4-12 或纯hex，长度>=32
    is_uuid = bool(re.match(r'^[0-9A-Fa-f-]{32,}$', native_val))
    if is_uuid:
        return
    # 值不像UUID（如kvm-10），改condition key从nativeId到name
    calls = item.get("api_call")
    if not calls:
        return
    if isinstance(calls, dict):
        calls = [calls]
    for call in calls:
        if not isinstance(call, dict):
            continue
        cond = call.get("condition")
        if not cond:
            continue
        for c in cond.get("constraint", []):
            simple = c.get("simple", {})
            if simple.get("name") == "nativeId" and simple.get("value") == native_val:
                simple["name"] = "name"
                logger.info(f"nativeId→name: {native_val}")


def _cleanup_empty_api_conditions(item: dict):
    """移除API条件中值为空的constraint。"""
    calls = item.get("api_call")
    if not calls:
        return
    if isinstance(calls, dict):
        calls = [calls]
    for call in calls:
        if not isinstance(call, dict):
            continue
        cond = call.get("condition")
        if not cond:
            continue
        constraints = cond.get("constraint", [])
        new_constraints = []
        for c in constraints:
            simple = c.get("simple", {})
            val = simple.get("value", "")
            if val:
                new_constraints.append(c)
        if new_constraints:
            cond["constraint"] = new_constraints
        else:
            call.pop("condition", None)


def _cleanup_sql_empty_where(sql: str) -> str:
    """清理SQL中值为空的WHERE条件。"""
    # 移除 col = '' 或 col = '' 的条件
    # 处理 WHERE col = '' AND other = 'val' → WHERE other = 'val'
    # 处理 WHERE col = '' → 移除整个WHERE
    # 处理 AND col = '' → 移除
    sql = re.sub(r"\s*=\s*''", " IS NOT NULL", sql, flags=re.IGNORECASE)
    return sql


def _diagnose(diagnostics, section, **facts):
    """仅填充本次查询传入的诊断字典，不影响选择或执行。"""
    if diagnostics is not None:
        diagnostics.setdefault(section, {}).update(facts)


def _parameter_changes(diagnostics, before, after, source):
    if diagnostics is None:
        return
    info = diagnostics.setdefault('parameters', {})
    sources = info.setdefault('sources', {})
    original_sources = dict(sources)
    changes = info.setdefault('changes', [])
    for name in dict.fromkeys([*before, *after]):
        if before.get(name) != after.get(name):
            changes.append({'name': name, 'before': before.get(name),
                            'after': after.get(name), 'source': source})
            if source in ('question_rule', 'template_default'):
                sources[name] = source
            elif source == 'region_to_azone_rule' and name == 'azoneName':
                sources[name] = original_sources.get('logicalRegionName', 'rule') + '+' + source
            else:
                sources[name] = sources.get(name, 'rule') + '+' + source


def match_runbook(user_question: str, runbook_items: list,
                  retriever: RunbookRetriever, diagnostics: Optional[dict] = None) -> Optional[dict]:
    """
    完整的 runbook 匹配流程：BM25 检索 → LLM 选择 → 参数填充。

    返回已填好参数的 runbook item（深拷贝），或 None（未命中）。
    diagnostics 为可选的单次查询记录，不改变原匹配策略。
    """
    if diagnostics is not None:
        diagnostics.clear()
    # 1. BM25 检索
    candidates = retriever.retrieve(user_question)
    if diagnostics is not None:
        _diagnose(diagnostics, 'retrieval', candidates=[
            {'rank': i + 1, 'id': c.id, 'tier': c.tier, 'score': c.score, 'coverage': c.coverage}
            for i, c in enumerate(candidates)])
    if not candidates:
        _diagnose(diagnostics, 'rejection', stage='retrieval', reason='no_candidates')
        logger.info("BM25 无候选，跳过 runbook")
        return None

    # 获取候选 items
    id_to_item = {item["id"]: item for item in runbook_items}
    candidate_items = []
    for c in candidates:
        raw = id_to_item.get(c.id)
        if raw:
            candidate_items.append(raw)

    if not candidate_items:
        _diagnose(diagnostics, 'rejection', stage='retrieval', reason='candidate_ids_not_in_library')
        return None
    _diagnose(diagnostics, 'selection', offered_ids=[item['id'] for item in candidate_items])

    # 2. LLM 选择
    runbook_str = _format_runbook_list(candidate_items)
    prompt = SELECT_RUNBOOK_PROMPT.format(
        user_question=user_question, runbook_list=runbook_str)
    answer = llm_ask(prompt).strip("`").strip()
    logger.info(f"LLM select runbook answer: {answer}")
    _diagnose(diagnostics, 'selection', model_answer=answer[:128])

    try:
        index = int(answer)
    except ValueError:
        _diagnose(diagnostics, 'rejection', stage='selection', reason='invalid_selector_output')
        logger.error(f"LLM 返回非数字: {answer}")
        return None

    _diagnose(diagnostics, 'selection', model_index=index, method='llm')
    if index == 0 or index < 0 or index > len(candidate_items):
        # LLM返回0，回退到BM25 top1（如果有强候选）
        if candidates and candidates[0].tier == "strong":
            logger.info(f"LLM未命中，回退BM25 top1: {candidate_items[0]['name']}")
            selected = copy.deepcopy(candidate_items[0])
            _diagnose(diagnostics, 'selection', method='strong_top1_fallback')
        else:
            _diagnose(diagnostics, 'rejection', stage='selection', reason='selector_declined_or_out_of_range')
            logger.info(f"未命中，index={index}")
            return None
    else:
        selected = copy.deepcopy(candidate_items[index - 1])
    logger.info(f"命中 runbook: {selected['name']}")
    _diagnose(diagnostics, 'selection', selected_id=selected['id'], selected_name=selected['name'])
    _diagnose(diagnostics, 'sql', template=selected.get('sql'))

    # 3.0 弃权检查：资源类型不匹配或问题问的字段不在SQL中（在参数填充前检查）
    if selected.get("sql"):
        sql_upper = selected["sql"].upper()
        q_lower = user_question.lower()
        _res_checks = [
            (["虚拟机", "ecs", "vm_", "vm实例"], "VM_NOVA"),
            (["云硬盘", "volume", "磁盘"], "VOLUME"),
            (["宿主机", "host", "物理机"], "HOST"),
            (["vpc", "路由器", "router"], "ROUTER"),
            (["elb", "负载均衡"], "ELB"),
            (["子网", "subnet"], "SUBNET"),
            (["端口", "port"], "PORT"),
            (["安全组", "security_group"], "SECURITY_GROUP"),
            (["gaussdb", " gauss"], "GAUSSDB"),
            (["弹性ip", "floating", "eip"], "FLOATING_IPS"),
            (["存储池", "storage_pool"], "STORAGE_POOL"),
        ]
        for keywords, table_name in _res_checks:
            if any(k in q_lower for k in keywords) and table_name not in sql_upper:
                _diagnose(diagnostics, 'rejection', stage='resource_gate', reason='resource_mismatch',
                          required_table=table_name)
                logger.info(f"资源类型不匹配: 问题提到{keywords[0]}但SQL无{table_name}，弃权")
                return None
        _field_checks = [
            (["nativeid", "原生id"], "nativeId"),
            (["ip地址", "ip是什么", "ip有哪些"], "Ip"),
        ]
        for keywords, field in _field_checks:
            if any(k in q_lower for k in keywords) and field.lower() not in sql_upper.lower():
                _diagnose(diagnostics, 'rejection', stage='field_gate', reason='requested_field_missing',
                          required_field=field)
                logger.info(f"问题问{field}但SQL无此字段，弃权")
                return None

    # 3. 参数填充
    placeholders = _get_placeholders(selected)
    _diagnose(diagnostics, 'parameters', placeholders=placeholders)
    if not placeholders:
        _diagnose(diagnostics, 'sql', before_refine=selected.get('sql'), after_refine=selected.get('sql'),
                  final=selected.get('sql'), refine_status='skipped_no_placeholders')
        return selected

    examples_str = "\n".join(f"- {ex}" for ex in selected.get("examples", []))
    placeholder_list = "\n".join(f"{i + 1}. {{{{{p}}}}}" for i, p in enumerate(placeholders))
    prompt = FILL_PARAMS_PROMPT.format(
        examples=examples_str,
        placeholder_list=placeholder_list,
        user_question=user_question)
    answer = llm_ask(prompt).strip("`").strip()
    logger.info(f"LLM fill params answer: {answer}")

    parsed = {}
    for line in answer.splitlines():
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().strip("{}")
        val = val.strip()
        if val:
            parsed[key] = val

    if diagnostics is not None:
        _diagnose(diagnostics, 'parameters', llm_extracted=dict(parsed),
                  sources={key: 'llm' for key in parsed})
    before_normalization = dict(parsed) if diagnostics is not None else None
    # 后处理：去除名称类参数中的常见前缀（ECS/VM/虚拟机/VPC/ELB等）
    for k, v in list(parsed.items()):
        # 清除垃圾值（含"的"、"各"等非实体词）
        if any(g in v for g in ('的', '各', '什么', '多少', '哪些')):
            parsed[k] = ''
            continue
        if any(t in k for t in ("名称", "name", "Name")):
            for prefix in ("ECS", "VM", "虚拟机", "VPC", "ELB", "云硬盘", "VDC"):
                if v.startswith(prefix) and len(v) > len(prefix):
                    v = v[len(prefix):]
            parsed[k] = v

    # 后处理：规范化status值（中文→英文）
    if 'status' in parsed:
        v = parsed['status'].lower()
        if v in ('正在跑', '运行中', 'active', 'running', '在运行'):
            parsed['status'] = 'active'
        elif v in ('异常', '错误', 'error', '故障'):
            parsed['status'] = 'error'
        elif v in ('停机', '停止', 'shutoff', 'stopped', '关机'):
            parsed['status'] = 'shutoff'
        elif v in ('暂停', 'paused'):
            parsed['status'] = 'paused'
        elif v in ('构建中', 'building', 'building'):
            parsed['status'] = 'building'

    # 后处理：规范化bootable值
    if 'bootable' in parsed:
        v = parsed['bootable'].lower()
        if v in ('true', '是', '可启动', '可启动的'):
            parsed['bootable'] = 'True'
        elif v in ('false', '否'):
            parsed['bootable'] = 'False'

    # 后处理：规范化assetStatus值
    if 'assetStatus' in parsed:
        v = parsed['assetStatus']
        if '报废' in v:
            parsed['assetStatus'] = 'scrapped'
        elif '运行' in v or '在网' in v:
            parsed['assetStatus'] = 'running'
        elif '闲置' in v:
            parsed['assetStatus'] = 'idle'

    _parameter_changes(diagnostics, before_normalization, parsed, 'normalization')
    before_rules = dict(parsed) if diagnostics is not None else None
    # 自动填充常见参数（LLM未提取的从用户问题中自动匹配）
    _auto_fill_params(user_question, parsed, placeholders)
    _parameter_changes(diagnostics, before_rules, parsed, 'question_rule')
    before_region_fix = dict(parsed) if diagnostics is not None else None

    # 后处理：logicalRegionName的值像azone(az\d+.dc\d+)时，迁移到azoneName
    if 'logicalRegionName' in parsed:
        val = parsed['logicalRegionName']
        if re.match(r'^az\d+\.dc\d+$', val):
            if 'azoneName' in placeholders:
                parsed['azoneName'] = val
                del parsed['logicalRegionName']
                logger.info(f"logicalRegionName({val})→azoneName")
            else:
                del parsed['logicalRegionName']
                logger.info(f"logicalRegionName值({val})像azone但模板无azoneName占位，清除")

    _parameter_changes(diagnostics, before_region_fix, parsed, 'region_to_azone_rule')
    before_defaults = dict(parsed) if diagnostics is not None else None
    # 兜底：仅在问题中提到相关关键词时才用default_params
    default_params = selected.get("default_params", {})
    _param_keywords = {
        'tenantName': ['租户', 'tenant'],
        'logicalRegionName': ['区域', 'region'],
        'vdcName': ['VDC', 'vdc'],
        'clusterName': ['集群', 'cluster'],
        'azoneName': ['可用区', 'az'],
        'hostName': ['宿主机', 'kvm'],
    }
    for p in placeholders:
        if p not in parsed or not parsed[p]:
            if p in default_params and default_params[p]:
                kws = _param_keywords.get(p, [])
                if kws and any(k in user_question for k in kws):
                    parsed[p] = default_params[p]
                    logger.info(f"问题提及关键词，使用默认参数: {p}={default_params[p]}")

    logger.info(f"最终参数: {parsed}")
    _parameter_changes(diagnostics, before_defaults, parsed, 'template_default')
    if diagnostics is not None:
        _diagnose(diagnostics, 'parameters', final=dict(parsed),
                  unfilled=[name for name in placeholders if not parsed.get(name)])

    if not _fill_params(selected, parsed, user_question):
        _diagnose(diagnostics, 'rejection', stage='parameters', reason='parameter_fill_failed')
        logger.error(f"参数填充不完整: {parsed}")
        return None

    # 3.5 后处理：nativeId值不像UUID时，改为name条件
    if diagnostics is not None:
        _diagnose(diagnostics, 'parameters', api_after_fill=copy.deepcopy(selected.get('api_call')))
    _fix_native_id_to_name(selected, parsed)
    _diagnose(diagnostics, 'sql', after_fill=selected.get('sql'))
    if diagnostics is not None:
        _diagnose(diagnostics, 'parameters', effective_api=copy.deepcopy(selected.get('api_call')))

    # 3.55 弃权检查：问题提到关键过滤条件但API无对应条件 → 弃权
    _api_cond_names = set()
    calls = selected.get("api_call")
    if calls:
        if isinstance(calls, dict):
            calls = [calls]
        for call in calls:
            if not isinstance(call, dict):
                continue
            cond = call.get("condition", {})
            if isinstance(cond, dict):
                for cs in cond.get("constraint", []):
                    s = cs.get("simple", {})
                    if s.get("name"):
                        _api_cond_names.add(s["name"])
    _q_lower = user_question.lower()
    _missing_checks = [
        (["active", "stopped", "shutoff", "error", "运行中", "停机", "停止", "停止", "异常", "故障", "构建中"], "status"),
        (["az0", "az1", "az\\d"], "azoneName"),
        (["@[\da-fA-F]+@", "\d+\.\d+\.\d+\.\d+", "ip地址", "ip是什么"], "privateIps"),
        (["ip地址", "ip是什么"], "ipAddress"),
    ]
    import re as _re
    for patterns, cond_name in _missing_checks:
        if cond_name not in _api_cond_names:
            if any(_re.search(p, _q_lower) for p in patterns):
                _diagnose(diagnostics, 'rejection', stage='api_condition_gate',
                          reason='required_api_condition_missing', required_condition=cond_name)
                logger.info(f"问题提到{cond_name}相关条件但API无{cond_name}，弃权")
                return None

    # 4. SQL精调 — 根据用户问题调整SELECT/GROUP BY/聚合函数
    if selected.get("sql"):
        original_sql = selected["sql"]
        _diagnose(diagnostics, 'sql', before_refine=original_sql)
        schemas = _get_table_schemas(original_sql)
        if diagnostics is None:
            refined = _refine_sql(user_question, original_sql, schemas)
        else:
            refined = _refine_sql(user_question, original_sql, schemas,
                                  diagnostics=diagnostics.setdefault('sql', {}))
        _diagnose(diagnostics, 'sql', after_refine=refined)
        if refined and refined != original_sql:
            # 精调后表集合变了（增减JOIN），说明模板结构不匹配，宁可不答
            orig_tables = _extract_sql_tables(original_sql)
            refined_tables = _extract_sql_tables(refined)
            if orig_tables != refined_tables:
                _diagnose(diagnostics, 'rejection', stage='sql_refinement', reason='refinement_changed_tables',
                          original_tables=sorted(orig_tables), refined_tables=sorted(refined_tables))
                logger.info(f"SQL精调改变了表集合({orig_tables}→{refined_tables})，放弃回答")
                return None
            selected["sql"] = refined
            logger.info(f"SQL refined: {refined[:120]}")
        else:
            logger.info("SQL unchanged")
    else:
        _diagnose(diagnostics, 'sql', refine_status='skipped_no_sql')

    # 5. 后处理：禁止LIMIT（标准答案通常返回全量结果）
    if selected.get("sql"):
        selected["sql"] = re.sub(r'\s+LIMIT\s+\d+', '', selected["sql"], flags=re.IGNORECASE)

    # 6. 后处理：UNION ALL弃权 + 列名修复
    if selected.get("sql"):
        # UNION ALL通常导致多资源混合结果，与标准答案不匹配
        if "UNION" in selected["sql"].upper():
            _diagnose(diagnostics, 'sql', final=selected['sql'])
            _diagnose(diagnostics, 'rejection', stage='sql_postprocess', reason='union_not_allowed')
            logger.info("SQL包含UNION，弃权")
            return None
        # COUNT(*) AS count → COUNT(*) AS total（标准答案常用total列名）
        if "GROUP BY" not in selected["sql"].upper():
            selected["sql"] = re.sub(
                r'COUNT\(\*\)\s+AS\s+count\b',
                'COUNT(*) AS total',
                selected["sql"],
                flags=re.IGNORECASE)

    _diagnose(diagnostics, 'sql', final=selected.get('sql'))
    return selected


def _refine_sql(question: str, sql: str, schemas: str = "", diagnostics: Optional[dict] = None) -> str:
    """用LLM根据用户问题精调SQL。返回调整后的SQL，失败时返回原SQL。"""
    prompt = REFINE_SQL_PROMPT.format(
        question=question, sql=sql, schemas=schemas or "(无)",
        join_relations=JOIN_RELATIONS)
    try:
        refined = llm_ask(prompt)
        refined = refined.strip().strip("`").strip()
        if refined.lower().startswith("sql"):
            refined = refined[3:].strip()
        if diagnostics is not None:
            diagnostics.update(model_proposal=refined, refine_status='pending')
        # 必须以SELECT开头，且是单条SQL（不含换行后的自然语言）
        if not refined.upper().startswith("SELECT"):
            if diagnostics is not None:
                diagnostics['refine_status'] = 'kept_original_not_select'
            logger.warning(f"LLM refine不以SELECT开头，保留原SQL: {refined[:80]}")
            return sql
        # 禁止包含WHERE
        if re.search(r"\bWHERE\b", refined, re.IGNORECASE):
            if diagnostics is not None:
                diagnostics['refine_status'] = 'kept_original_where'
            logger.warning("LLM refine包含WHERE，保留原SQL")
            return sql
        # 禁止包含UNION ALL（容易产生错误结果）
        if "UNION" in refined.upper():
            if diagnostics is not None:
                diagnostics['refine_status'] = 'kept_original_union'
            logger.warning("LLM refine包含UNION，保留原SQL")
            return sql
        # 禁止包含LIMIT
        if re.search(r"\bLIMIT\b", refined, re.IGNORECASE):
            refined = re.sub(r'\s+LIMIT\s+\d+', '', refined, flags=re.IGNORECASE)
        # 必须包含FROM
        if "FROM" not in refined.upper():
            if diagnostics is not None:
                diagnostics['refine_status'] = 'kept_original_no_from'
            logger.warning(f"LLM refine无FROM，保留原SQL: {refined[:80]}")
            return sql
        if diagnostics is not None:
            diagnostics['refine_status'] = 'changed' if refined != sql else 'unchanged'
        return refined
    except Exception as e:
        if diagnostics is not None:
            diagnostics.update(refine_status='kept_original_exception', error_type=type(e).__name__)
        logger.warning(f"LLM refine SQL异常: {e}")
        return sql
