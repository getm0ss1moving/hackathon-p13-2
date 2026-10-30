"""从固定SQL库已证name/nativeId输出角色补列；不改过滤、JOIN或行粒度。"""

from collections import defaultdict
import hashlib
import re

import runbook_matcher as m


_ID = r"[A-Za-z_][A-Za-z0-9_]*"
_STOP_ALIAS = {"ON","INNER","LEFT","RIGHT","FULL","OUTER","CROSS","JOIN","WHERE","GROUP",
               "ORDER","LIMIT","HAVING","UNION","INTERSECT","EXCEPT"}


def _normalize(value):
    return re.sub(r"_", "", value).casefold()


def _role(alias):
    match = re.fullmatch(r"(.+)_(name|id)",alias,re.I)
    return (_normalize(match[1]),match[2].casefold()) if match and _normalize(match[1]) else None


def _mask(sql):
    return re.sub(r"'(?:''|[^'])*'|--[^\n]*|/\*[\s\S]*?\*/",lambda match:" "*len(match[0]),sql)


def _parse(sql, detail):
    """只解析平面SELECT的简单字段及别名，保留原字符串插入位置。"""
    if not isinstance(sql,str):
        return None
    masked = _mask(sql)
    body = masked.strip().rstrip(';').strip()
    if (len(re.findall(r"\bSELECT\b",body,re.I)) != 1 or re.search(r'["`\[\]]',body)
            or re.search(r"\b(?:UNION|INTERSECT|EXCEPT|WITH|OVER)\b",body,re.I) or ';' in body):
        return None
    select = re.match(r"\s*SELECT\s+(?P<distinct>DISTINCT\s+)?(?P<projection>.+?)\s+FROM\b",masked,re.I|re.S)
    if not select or detail and (select["distinct"] or re.search(
            r"\b(?:GROUP|HAVING|LIMIT)\b|\b(?:COUNT|SUM|AVG|MIN|MAX|TOTAL|GROUP_CONCAT)\s*\(",body,re.I)):
        return None
    known = {table.casefold():(table,ci) for table,ci in m._ORIG_TO_DESENS.items()}
    bindings = []
    references = {}
    for match in re.finditer(r"\b(?:FROM|JOIN)\s+(?P<table>"+_ID+r")(?:\s+(?:AS\s+)?(?P<alias>"+_ID+r"))?",body,re.I):
        table = match["table"]
        if table.casefold() not in known:
            return None
        alias = match["alias"]
        if alias and alias.upper() in _STOP_ALIAS:
            alias = None
        canonical,ci = known[table.casefold()]
        binding = {"index":len(bindings),"table":canonical,"ci":ci,"reference":alias or table}
        bindings.append(binding)
        for reference in {table.casefold(),(alias or table).casefold()}:
            references[reference] = binding if reference not in references else None
    if not bindings:
        return None
    projection = select["projection"]
    pieces,depth,start = [],0,0
    for index,character in enumerate(projection):
        depth += (character == '(') - (character == ')')
        if depth < 0:
            return None
        if character == ',' and depth == 0:
            pieces.append(projection[start:index].strip());start = index+1
    if depth:
        return None
    pieces.append(projection[start:].strip())
    columns,labels = [],[]
    for piece in pieces:
        if re.fullmatch(r"(?:"+_ID+r"\.)?\*",piece):
            return None
        alias = re.fullmatch(r"(?P<value>.+?)\s+AS\s+(?P<alias>"+_ID+r")",piece,re.I|re.S)
        value = alias["value"].strip() if alias else piece
        simple = re.fullmatch(r"(?:(?P<prefix>"+_ID+r")\.)?(?P<field>"+_ID+r")",value)
        label = alias["alias"] if alias else simple["field"] if simple else None
        if label:
            labels.append(label)
        if not simple:
            continue
        prefix = simple["prefix"]
        binding = references.get(prefix.casefold()) if prefix else bindings[0] if len(bindings) == 1 else None
        if binding is None:
            continue
        columns.append({**binding,"field":simple["field"],"alias":label,
                        "reference":prefix or binding["reference"]})
    if len({_normalize(label) for label in labels}) != len(labels):
        return None
    return {"columns":columns,"labels":labels,"projection_end":select.end("projection"),"masked":masked}


def _library_roles(library):
    """不读取模板ID、examples、题文、默认参数或实体，只使用SQL投影。"""
    fields = defaultdict(set)
    pairs = defaultdict(list)
    for item in library:
        sql = item.get("sql") if isinstance(item,dict) else None
        parsed = _parse(sql,detail=False)
        if parsed is None:
            continue
        local = defaultdict(list)
        for column in parsed["columns"]:
            role = _role(column["alias"])
            if role is None:
                continue
            prefix,kind = role
            fields[(column["ci"],prefix,kind)].add(column["field"].casefold())
            local[(column["index"],prefix)].append((kind,column))
        for (_,prefix),entries in local.items():
            names = [column for kind,column in entries if kind == "name" and column["field"].casefold() == "name"]
            ids = [column for kind,column in entries if kind == "id" and column["field"].casefold() == "nativeid"]
            if len(names) == len(ids) == 1:
                pairs[(names[0]["ci"],prefix)].append({"name_alias":names[0]["alias"],"id_alias":ids[0]["alias"],
                    "sql_sha256":hashlib.sha256(sql.encode()).hexdigest()})
    roles = {}
    for (ci,prefix),sources in pairs.items():
        if (fields[(ci,prefix,"name")] != {"name"} or fields[(ci,prefix,"id")] != {"nativeid"}
                or len({source["id_alias"].casefold() for source in sources}) != 1):
            continue
        roles[(ci,prefix)] = {"id_alias":sources[0]["id_alias"],"sources":sources}
    return roles


def complete_identity_projection(question, item, library):
    """返回补列SQL及结构证据；未知、冲突或非明细时原样返回。"""
    sql = item.get("sql")
    identity = r"(?:实例\s*(?:的)?\s*(?:ID|编号)|(?<![A-Za-z0-9_@.\-])nativeId(?![A-Za-z0-9_@.\-]))"
    explicit_identity = bool(re.search(identity, question, re.I))
    entity_list = bool(re.search(r"实例\s*(?:的)?\s*(?:详细)?(?:列表|明细)", question))
    if ((not explicit_identity and not entity_list) or re.search(
            r"(?:不要|无需|不需要|不返回|不显示|不输出|不包括|不含)\s*(?:包含|显示|输出|返回)?\s*"+identity, question, re.I)):
        return sql,[]
    if not explicit_identity and re.search(r"只要|只返回|只显示|只输出|仅返回|仅显示|仅输出|仅需|仅要", question):
        return sql,[]
    parsed = _parse(sql,detail=True)
    if parsed is None:
        return sql,[]
    roles = _library_roles(library)
    present = {_normalize(label) for label in parsed["labels"]}
    native_bindings = {column["index"] for column in parsed["columns"] if column["field"].casefold() == "nativeid"}
    candidates = []
    for column in parsed["columns"]:
        role = _role(column["alias"])
        if role is None or role[1] != "name" or column["field"].casefold() != "name" or column["index"] in native_bindings:
            continue
        known = roles.get((column["ci"],role[0]))
        schema = m._schema_columns.get(column["ci"],[])
        if known is None or "name" not in schema or "nativeId" not in schema:
            continue
        alias = known["id_alias"]
        if _normalize(alias) in present:
            continue
        order = re.search(r"\bORDER\s+BY\b(.+)$",parsed["masked"],re.I|re.S)
        if order and re.search(r"(?<![A-Za-z0-9_.])"+re.escape(alias)+r"(?![A-Za-z0-9_])",order[1],re.I):
            return sql,[]  # 新SELECT别名不能改变已有ORDER BY的解析。
        candidates.append({"ci":column["ci"],"table":column["table"],"field":"nativeId",
            "name_alias":column["alias"],"id_alias":alias,"reference":column["reference"],
            "role_prefix":role[0],"source":"co_projected_name_and_nativeId",
            "intent":"explicit_identity" if explicit_identity else "entity_list_identity",
            "supporting_sql_sha256":sorted({source["sql_sha256"] for source in known["sources"]})})
    if (not candidates or len({_normalize(entry["id_alias"]) for entry in candidates}) != len(candidates)):
        return sql,[]
    additions = [entry["reference"]+'.nativeId AS '+entry["id_alias"] for entry in candidates]
    end = parsed["projection_end"]
    return sql[:end]+', '+', '.join(additions)+sql[end:],candidates
