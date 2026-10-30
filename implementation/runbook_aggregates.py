"""已证同区域的网络资源按VDC独立计数；只组合原api_call+sql。"""

import json
import re
import sqlite3
from contextlib import closing

import runbook_matcher as m


_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_NETWORK = {
    "ROUTER": {"table": "CLOUD_ROUTER", "alias": "vpc_count", "words": ["vpc", "云路由器"]},
    "SUBNET": {"table": "CLOUD_SUBNET", "alias": "subnet_count", "words": ["子网", "subnet"]},
    "FLOATING_IPS": {"table": "CLOUD_FLOATING_IPS", "alias": "eip_count", "words": ["弹性ip", "floating", "eip"]},
    "SECURITY_GROUP": {"table": "CLOUD_SECURITY_GROUP", "alias": "sg_count", "words": ["安全组", "security_group"]},
    "ELB": {"table": "CLOUD_ELB", "alias": "elb_count", "words": ["elb", "负载均衡"]},
}
_TABLE_TO_CI = {value["table"].casefold(): ci for ci,value in _NETWORK.items()}
_API = re.compile(r"/rest/hackthon/db/instances/([^/?]+)(?:\?[^#]*)?")


def _shape(sql):
    """识别单表、一个VDC键和COUNT(*)；不猜表达式等价或复杂分组。"""
    text = m._sql_structure(sql or "").strip().rstrip(";").strip()
    field = r"(?:"+_IDENTIFIER+r"\.)?vdcName"
    match = re.fullmatch(
        r"SELECT\s+(?P<key>"+field+r")(?:\s+AS\s+(?P<key_alias>"+_IDENTIFIER+r"))?\s*,\s*"
        r"COUNT\s*\(\s*\*\s*\)\s+AS\s+(?P<count_alias>"+_IDENTIFIER+r")\s+"
        r"FROM\s+(?P<table>"+_IDENTIFIER+r")(?:\s+(?:AS\s+)?(?P<table_alias>"+_IDENTIFIER+r"))?\s+"
        r"GROUP\s+BY\s+(?P<group>(?:"+_IDENTIFIER+r"\.)?"+_IDENTIFIER+r")", text, re.I)
    if not match:
        return None
    values = match.groupdict()
    ci = _TABLE_TO_CI.get(values["table"].casefold())
    if not ci:
        return None
    prefixes = {values["table"].casefold()}
    if values["table_alias"]:
        prefixes.add(values["table_alias"].casefold())
    key_alias = values["key_alias"] or "vdcName"
    if key_alias.casefold() == values["count_alias"].casefold():
        return None
    for role in ["key", "group"]:
        expression = values[role].casefold()
        prefix, separator, name = expression.rpartition(".")
        if name != "vdcname" or separator and prefix not in prefixes:
            return None
    if "vdcName" not in m._schema_columns.get(ci,[]):
        return None
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute('CREATE TABLE '+_NETWORK[ci]["table"]+' (vdcName TEXT)')
            connection.execute(sql.strip().rstrip(';'))
    except sqlite3.Error:
        return None
    return {"base_ci": ci, "base_table": _NETWORK[ci]["table"], "group_field": "vdcName",
            "group_alias": key_alias, "count_alias": values["count_alias"]}


def _indexed_calls(item):
    calls = item.get("api_call")
    if not isinstance(calls,list) or "from step" in json.dumps(calls,ensure_ascii=False).lower():
        return None
    indexed = {}
    for call in calls:
        if not isinstance(call,dict) or call.get("method","GET") != "GET":
            return None
        resource = _API.fullmatch(call.get("url", ""))
        ci = resource[1] if resource else None
        if ci not in _NETWORK or ci in indexed:
            return None
        indexed[ci] = call
    return indexed


def plan_groups(question, item):
    """只有各VDC网络数量、相同显式区域和已知独立API才允许补全。"""
    shape = _shape(item.get("sql"))
    visible = re.sub(r'["“‘「][^"”’」]*["”’」]', " ", question).lower()
    if (not shape or not re.search(r"各\s*vdc|按\s*vdc", visible, re.I)
            or not re.search(r"数量|总数|多少", visible)
            or re.search(r"列表|详情|分布|对应|关联|挂载|明细|最多|最大|最少|最小|比例|比率|排名|容量|大小|内存|核数|规格|规则|实例|节点|物理|交换机|防火墙|数据库", visible)):
        return None
    dimensions = list(re.finditer(r"(?:各|按)\s*vdc",visible,re.I))
    if len(dimensions) != 1:
        return None
    tail = visible[dimensions[0].end():].strip()
    tail = re.sub(r"^(?:的|下|中|统计|汇总)\s*", "", tail, count=1)
    count = re.search(r"(?:的)?(?:数量|总数)(?:汇总|统计)?[。?？]?\s*$",tail)
    if not count:
        return None
    parts = re.split(r"\s*(?:、|,|，|和|与|及|/)\s*",tail[:count.start()].strip())
    requested = []
    for part in parts:
        candidates = [ci for ci,value in _NETWORK.items() if part.strip() in value["words"]]
        if len(candidates) != 1 or candidates[0] in requested:
            return None
        requested.append(candidates[0])
    if (shape["base_ci"] not in requested or len(requested)<2
            or any(ci not in requested and any(m._mentions_resource(visible,word) for word in words)
                   for words,ci in m._RESOURCE_CHECKS)):
        return None
    scopes = {}
    m._auto_fill_params(question, scopes, ["logicalRegionName","tenantName","vdcName","azoneName"], item)
    if set(scopes) != {"logicalRegionName"}:
        return None
    indexed = _indexed_calls(item)
    if indexed is None or not set(requested) <= indexed.keys():
        return None
    for ci,call in indexed.items():
        columns = m._schema_columns.get(ci, [])
        constraints = call.get("condition", {}).get("constraint", [])
        if "vdcName" not in columns or "logicalRegionName" not in columns or len(constraints) != 1:
            return None
        constraint = constraints[0]
        simple = constraint.get("simple", {})
        if (constraint.get("logOp", "and") != "and" or simple.get("operator", "equal") != "equal"
                or simple.get("name") != "logicalRegionName"
                or simple.get("value") not in [scopes["logicalRegionName"], "{{logicalRegionName}}"]):
            return None
    resources = [{"ci":shape["base_ci"],"table":shape["base_table"],"alias":shape["count_alias"]}]
    additions = [{"ci":ci,"table":_NETWORK[ci]["table"],"alias":_NETWORK[ci]["alias"]}
                 for ci in requested if ci != shape["base_ci"]]
    aliases = [shape["group_alias"],shape["count_alias"]]+[entry["alias"] for entry in additions]
    if len({name.casefold() for name in aliases}) != len(aliases):
        return None
    return {**shape,"base_tables":[shape["base_table"]],"scope_values":scopes,
            "resources":resources+additions,"additions":additions}


def validate_groups(question, item, plan):
    """真实GET证明资源非空和键字段；保留NULL/空串桶，不把哑行当资源。"""
    if plan_groups(question,item) != plan or re.search(r"\{\{[^{}]+\}\}",json.dumps(item.get("api_call"))):
        return {"valid":False,"reason":"group_scope_changed_or_unresolved"}
    indexed = _indexed_calls(item)
    checks = []
    for resource in plan["resources"]:
        ci,table = resource["ci"],resource["table"]
        records,actual = m._execute_lookup_api(indexed[ci])
        if actual.casefold() != table.casefold():
            return {"valid":False,"reason":"group_resource_mismatch","tables":checks,"ci":ci}
        if not records:
            return {"valid":False,"reason":"empty_group_resource","tables":checks,"ci":ci}
        if any("vdcName" not in record for record in records):
            return {"valid":False,"reason":"missing_group_field","tables":checks,"ci":ci}
        if any(record["vdcName"] is not None and not isinstance(record["vdcName"],str) for record in records):
            return {"valid":False,"reason":"invalid_group_key_type","tables":checks,"ci":ci}
        checks.append({"ci":ci,"table":table,"rows":len(records),
                       "group_count":len({record["vdcName"] for record in records}),
                       "null_key_rows":sum(record["vdcName"] is None for record in records),
                       "empty_key_rows":sum(record["vdcName"] == "" for record in records)})
    return {"valid":True,"reason":"verified_independent_group_resources","tables":checks}


def compose_groups(sql, plan):
    """按完整资源键域组合已分组计数；禁止明细表直接乘积。"""
    shape = _shape(sql)
    if not shape or any(shape[key].casefold() != plan[key].casefold() for key in shape):
        return None
    resources = plan["resources"]
    if (not resources or resources[0]["ci"] != plan["base_ci"]
            or len({entry["ci"] for entry in resources}) != len(resources)
            or any(entry["ci"] not in _NETWORK or entry["table"] != _NETWORK[entry["ci"]]["table"]
                   or not re.fullmatch(_IDENTIFIER,entry["alias"]) for entry in resources)):
        return None
    aliases = [plan["group_alias"]]+[entry["alias"] for entry in resources]
    if len({name.casefold() for name in aliases}) != len(aliases):
        return None
    domain = " UNION ".join("SELECT vdcName FROM "+entry["table"] for entry in resources)
    columns = ['group_domain.vdcName AS "'+plan["group_alias"]+'"',
               'COALESCE(group_base."'+plan["count_alias"]+'",0) AS "'+plan["count_alias"]+'"']
    joins = []
    for index,entry in enumerate(resources[1:]):
        name = "group_part_"+str(index)
        alias = entry["alias"]
        columns.append('COALESCE('+name+'."'+alias+'",0) AS "'+alias+'"')
        joins.append(' LEFT JOIN (SELECT vdcName,COUNT(*) AS "'+alias+'" FROM '+entry["table"]+
                     ' GROUP BY vdcName) AS '+name+' ON group_domain.vdcName IS '+name+'.vdcName')
    return ('SELECT '+', '.join(columns)+' FROM ('+domain+') AS group_domain LEFT JOIN ('+sql.strip().rstrip(';')+
            ') AS group_base ON group_domain.vdcName IS group_base."'+plan["group_alias"]+'"'+''.join(joins))
