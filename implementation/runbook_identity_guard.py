"""精调后的ID必须仍来自已证CI与同一行绑定；只判合同，不改写SQL。"""

import re

import runbook_matcher as m
import runbook_projection_roles as roles


_ID = r"[A-Za-z_][A-Za-z0-9_]*"
_TOKENS = re.compile(r"'(?:''|[^'])*'|--[^\n]*|/\*[\s\S]*?\*/|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|<=|>=|<>|!=|\|\||\S")


def _row_source(sql):
    """明确绑定按FROM/JOIN位置编号；仅接受别名重命名可证明的同一行源。"""
    masked = roles._mask(sql)
    start = re.search(r"\bFROM\b",masked,re.I)
    if start is None or re.search(r"\b(?:USING|NATURAL|INDEXED)\b|\b(?:FROM|JOIN)\s*\(",masked,re.I):
        return None
    order = re.search(r"\bORDER\s+BY\b",masked[start.start():],re.I)
    if order:
        end = start.start()+order.start()
    else:
        meaningful = [token for token in _TOKENS.finditer(sql) if not token[0].startswith(("--","/*"))]
        while meaningful and meaningful[-1][0] == ';':
            meaningful.pop()
        end = meaningful[-1].end() if meaningful else start.start()
    tail = masked[start.start():end]
    depth = 0
    for character in tail:
        depth += (character == '(') - (character == ')')
        if depth < 0 or character == ',' and depth == 0:
            return None  # 不把逗号连接误当只有一个CI的无歧义行源。
    if depth:
        return None
    known = {table.casefold():(table,ci) for table,ci in m._ORIG_TO_DESENS.items()}
    references,definitions = {},{}
    for index,match in enumerate(re.finditer(
            r"\b(?P<join>FROM|JOIN)\s+(?P<table>"+_ID+r")(?:\s+(?:AS\s+)?(?P<alias>"+_ID+r"))?",masked,re.I)):
        if match["table"].casefold() not in known:
            return None
        alias = match["alias"]
        if alias and alias.upper() in roles._STOP_ALIAS:
            alias = None
        table,ci = known[match["table"].casefold()]
        position = match.end("alias") if alias else match.end("table")
        definitions[match.start()] = (position,(match["join"].casefold(),table.casefold(),"@"+str(index)))
        for reference in {match["table"].casefold(),(alias or match["table"]).casefold()}:
            references[reference] = index if reference not in references else None
    tokens = [token for token in _TOKENS.finditer(sql,start.start(),end)
              if not token[0].startswith(("--","/*"))]
    result,index = [],0
    while index<len(tokens):
        token = tokens[index]
        definition = definitions.get(token.start())
        if definition:
            result.extend(definition[1])
            while index<len(tokens) and tokens[index].start()<definition[0]:
                index += 1
            continue
        value = token[0]
        if re.fullmatch(_ID,value) and index+1<len(tokens) and tokens[index+1][0] == '.':
            binding = references.get(value.casefold())
            if binding is None:
                return None
            result.append("@"+str(binding))
        else:
            result.append(value if value.startswith("'") else value.casefold())
        index += 1
    return tuple(result)


def _column(parsed,alias):
    matches = [column for column in parsed["columns"] if roles._normalize(column["alias"]) == roles._normalize(alias)]
    return matches[0] if len(matches) == 1 else None


def validate_identity_refinement(original, candidate, evidence):
    """证据由补列函数产生；拒绝时调用者回退含真实ID的original整体SQL。"""
    def reject(reason,**details):
        return {"valid":False,"reject":True,"reason":reason,**details}

    if not evidence:
        return {"valid":True,"reject":False,"reason":"no_proven_identity_to_protect","protected":[]}
    before,after = roles._parse(original,detail=True),roles._parse(candidate,detail=True)
    if before is None or after is None:
        return reject("identity_projection_shape_unknown")
    original_source,candidate_source = _row_source(original),_row_source(candidate)
    if original_source is None or candidate_source is None:
        return reject("identity_row_source_unknown")
    if original_source != candidate_source:
        return reject("identity_row_source_changed")
    protected,seen = [],set()
    for proof in evidence:
        if (not isinstance(proof,dict) or not all(isinstance(proof.get(key),str) for key in
                ["ci","table","field","name_alias","id_alias","reference"])
                or proof["field"].casefold() != "nativeid"):
            return reject("identity_evidence_invalid")
        label = roles._normalize(proof["id_alias"])
        if label in seen:
            return reject("identity_evidence_ambiguous")
        seen.add(label)
        old_name,old_id = _column(before,proof["name_alias"]),_column(before,proof["id_alias"])
        if (old_name is None or old_id is None or old_name["field"].casefold() != "name"
                or old_id["field"].casefold() != "nativeid" or old_name["index"] != old_id["index"]
                or old_name["ci"] != proof["ci"] or old_id["ci"] != proof["ci"]
                or old_id["table"].casefold() != proof["table"].casefold()
                or old_name["reference"].casefold() != proof["reference"].casefold()):
            return reject("identity_evidence_does_not_match_original",id_alias=proof["id_alias"])
        schema = m._schema_columns.get(proof["ci"],[])
        if "name" not in schema or "nativeId" not in schema:
            return reject("identity_schema_unknown",ci=proof["ci"])
        name,current = _column(after,proof["name_alias"]),_column(after,proof["id_alias"])
        if current is None or current["field"].casefold() != "nativeid":
            return reject("changed_proven_identity_field",id_alias=proof["id_alias"],
                          actual_field=current["field"] if current else None)
        if current["ci"] != old_id["ci"] or current["index"] != old_id["index"]:
            return reject("changed_proven_identity_binding",id_alias=proof["id_alias"])
        if (name is None or name["field"].casefold() != "name" or name["ci"] != old_name["ci"]
                or name["index"] != old_name["index"] or name["index"] != current["index"]):
            return reject("changed_proven_name_anchor",name_alias=proof["name_alias"])
        protected.append({"ci":current["ci"],"table":current["table"],"binding_index":current["index"],
                          "field":"nativeId","name_alias":proof["name_alias"],"id_alias":proof["id_alias"]})
    return {"valid":True,"reject":False,"reason":"proven_identity_projection_preserved","protected":protected}
