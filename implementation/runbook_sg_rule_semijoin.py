"""Pure, closed SQL profile for SG -> rule API semijoin pushdown.

This proves the relational scope of a plan, not HTTP completeness or key types.
No question, template ID, example, entity, default parameter or answer is read.
"""
import copy
import re
from urllib.parse import parse_qsl, urlsplit


_ID = r"[A-Za-z_][A-Za-z0-9_]*"
_QCOL = rf"{_ID}\s*\.\s*{_ID}"
_DEPENDENCY = "{{id from step 1}}"
_ROOT_CI = "SECURITY_GROUP"
_CHILD_CI = "SECURITY_GROUP_RULE"
_ROOT_TABLE = "CLOUD_SECURITY_GROUP"
_CHILD_TABLE = "CLOUD_SECURITY_GROUP_RULE"
_RESERVED = {"select", "from", "join", "inner", "left", "outer", "right", "full",
             "cross", "on", "where", "group", "by", "order", "having", "limit", "offset",
             "union", "intersect", "except", "and", "or", "as", "distinct", "count"}
_ALIAS = rf"(?!(?:{'|'.join(sorted(_RESERVED))})\b){_ID}"


def _no(reason):
    return {"eligible": False, "reason": reason}


def _sql_proof(sql, schema_columns):
    if not isinstance(sql, str) or not sql.strip():
        return _no("missing_sql")
    # Deliberately reject quoted identifiers, comments, literal expressions and
    # all unsupported syntax. Stripping them could accidentally hide scope.
    if any(character in sql for character in "'\"`[]") or "--" in sql or "/*" in sql or "*/" in sql:
        return _no("quoted_or_comment_sql_not_supported")
    text = sql.strip()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    if ";" in text or "{{" in text:
        return _no("multiple_or_unfilled_sql")
    grammar = (
        rf"SELECT\s+(?P<select>.+?)\s+FROM\s+(?P<root>{_ID})"
        rf"(?:\s+(?:AS\s+)?(?P<root_alias>{_ALIAS}))?\s+"
        rf"(?P<join>INNER\s+JOIN|LEFT(?:\s+OUTER)?\s+JOIN|JOIN)\s+(?P<child>{_ID})"
        rf"(?:\s+(?:AS\s+)?(?P<child_alias>{_ALIAS}))?\s+ON\s+"
        rf"(?P<on_left>{_QCOL})\s*=\s*(?P<on_right>{_QCOL})"
        rf"(?:\s+GROUP\s+BY\s+(?P<group>.+?))?"
        rf"(?:\s+ORDER\s+BY\s+(?P<order>.+?))?"
    )
    matched = re.fullmatch(grammar, text, re.I | re.S)
    if not matched:
        return _no("sql_not_single_two_table_join_profile")
    if (matched["root"].casefold() != _ROOT_TABLE.casefold()
            or matched["child"].casefold() != _CHILD_TABLE.casefold()):
        return _no("unsupported_join_tables_or_direction")
    root_alias = matched["root_alias"] or matched["root"]
    child_alias = matched["child_alias"] or matched["child"]
    if (root_alias.casefold() == child_alias.casefold()
            or root_alias.casefold() in _RESERVED or child_alias.casefold() in _RESERVED
            or (matched["root_alias"] and root_alias.casefold() == _CHILD_TABLE.casefold())
            or (matched["child_alias"] and child_alias.casefold() == _ROOT_TABLE.casefold())):
        return _no("ambiguous_or_reserved_table_alias")
    aliases = {root_alias.casefold(): _ROOT_CI, child_alias.casefold(): _CHILD_CI}

    def column(token):
        pieces = re.fullmatch(rf"\s*({_ID})\s*\.\s*({_ID})\s*", token)
        if not pieces:
            return None
        owner = aliases.get(pieces[1].casefold())
        if owner is None:
            return None
        columns = [name for name in schema_columns[owner]
                   if isinstance(name, str) and name.casefold() == pieces[2].casefold()]
        if len(columns) != 1:
            return None
        if owner == _CHILD_CI and columns[0] not in {"id", "securityGroupId"}:
            # Other child fields may have mixed raw Python types. Changing
            # batch order can change the original loader's first-nonnull type
            # inference, so scope equivalence alone would be insufficient.
            return None
        return (owner, columns[0])

    left, right = column(matched["on_left"]), column(matched["on_right"])
    expected = {(_ROOT_CI, "id"), (_CHILD_CI, "securityGroupId")}
    if left is None or right is None or {left, right} != expected:
        return _no("join_keys_not_documented_parent_child_equality")
    selected_aliases = set()
    nonaggregate_columns = []
    has_count = False
    projection_terms = matched["select"].split(",")
    if not projection_terms:
        return _no("no_projection")
    for term in projection_terms:
        projected = re.fullmatch(
            rf"\s*(?P<expr>{_QCOL}|COUNT\s*\(\s*(?:DISTINCT\s+)?(?:{_QCOL}|\*)\s*\))"
            rf"(?:\s+(?:AS\s+)?(?P<alias>{_ID}))?\s*", term, re.I)
        if not projected:
            return _no("projection_outside_direct_column_or_count_profile")
        expression, alias = projected["expr"], projected["alias"]
        aggregate = re.fullmatch(r"COUNT\s*\(\s*(?:DISTINCT\s+)?(.+?)\s*\)", expression, re.I)
        token = aggregate[1] if aggregate else expression
        if token == "*" and re.search(r"\bDISTINCT\b", expression, re.I):
            return _no("invalid_distinct_star_count")
        if token != "*" and column(token) is None:
            return _no("projection_field_or_owner_not_in_schema")
        if aggregate:
            has_count = True
        else:
            nonaggregate_columns.append(column(token))
        if alias:
            if alias.casefold() in _RESERVED or alias.casefold() in selected_aliases:
                return _no("ambiguous_or_reserved_projection_alias")
            selected_aliases.add(alias.casefold())
    grouped_columns = set()
    if matched["group"]:
        parsed_groups = [column(term) for term in matched["group"].split(",")]
        if any(value is None for value in parsed_groups):
            return _no("grouping_outside_qualified_known_columns")
        grouped_columns = set(parsed_groups)
    if (has_count or matched["group"]) and not set(nonaggregate_columns) <= grouped_columns:
        # SQLite's permissive bare columns can depend on physical row order,
        # which batching may change even when the logical join set is equal.
        return _no("ungrouped_bare_projection_not_stable_under_batching")
    if matched["order"]:
        for term in matched["order"].split(","):
            ordered = re.fullmatch(rf"\s*({_QCOL}|{_ID})(?:\s+(?:ASC|DESC))?\s*", term, re.I)
            if not ordered or not (column(ordered[1]) is not None or ordered[1].casefold() in selected_aliases):
                return _no("ordering_outside_known_columns_or_projection_aliases")
    return {"eligible": True, "reason": "single_parent_child_join_proved",
            "join_type": "left" if matched["join"].upper().startswith("LEFT") else "inner",
            "root_alias": root_alias, "child_alias": child_alias}


def _api_resource(call):
    if (not isinstance(call, dict) or set(call) - {"method", "url", "autoPagination", "condition"}
            or call.get("method", "GET") != "GET" or not isinstance(call.get("url"), str)
            or call.get("autoPagination", True) is not True):
        return None
    parsed = urlsplit(call["url"])
    resource = re.fullmatch(r"/rest/hackthon/db/instances/(SECURITY_GROUP|SECURITY_GROUP_RULE)", parsed.path)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if (parsed.scheme or parsed.netloc or parsed.fragment or not resource
            or len({key for key, _ in query}) != len(query)
            or any(key not in {"pageNo", "pageSize"} for key, _ in query)
            or any(not re.fullmatch(r"[1-9][0-9]*", value) for _, value in query)
            or dict(query).get("pageNo", "1") != "1"
            or int(dict(query).get("pageSize", "10000")) > 10000):
        return None
    return resource[1]


def _root_conditions_proved(call, schema_columns):
    condition = call.get("condition", {})
    if not isinstance(condition, dict) or set(condition) - {"constraint"}:
        return False
    constraints = condition.get("constraint", [])
    if not isinstance(constraints, list):
        return False
    for constraint in constraints:
        if (not isinstance(constraint, dict) or set(constraint) - {"simple", "logOp"}
                or constraint.get("logOp", "and") != "and"):
            return False
        simple = constraint.get("simple")
        if not isinstance(simple, dict) or set(simple) - {"name", "value", "operator"}:
            return False
        if simple.get("name") not in schema_columns[_ROOT_CI]:
            return False
        operator, value = simple.get("operator", "equal"), simple.get("value")
        if operator not in {"equal", "contain", "in"}:
            return False
        values = value if isinstance(value, list) else [value]
        if (not values or (isinstance(value, list) and operator != "in")
                or (operator == "in" and not isinstance(value, list))
                or any(type(part) not in {str, int} or part == "" or "{{" in str(part) for part in values)):
            return False
    return True


def plan_security_group_rule_semijoin(item, *, schema_columns, ci_name_map):
    """Return a new double-API plan only for the closed two-table SQL profile.

    The caller must separately enforce the returned runtime obligations. This
    function makes no HTTP/model calls, evaluates no query, and edits no input.
    Already-prepared exact plans are re-proved and returned idempotently.
    """
    if not isinstance(item, dict) or not isinstance(schema_columns, dict) or not isinstance(ci_name_map, dict):
        return _no("unsupported_input")
    if (ci_name_map.get(_ROOT_CI) != _ROOT_TABLE or ci_name_map.get(_CHILD_CI) != _CHILD_TABLE):
        return _no("unproved_ci_mapping")
    if any(not isinstance(schema_columns.get(ci), (list, tuple)) or not schema_columns[ci]
           for ci in (_ROOT_CI, _CHILD_CI)):
        return _no("missing_schema")
    if ("id" not in schema_columns[_ROOT_CI] or "securityGroupId" not in schema_columns[_CHILD_CI]
            or "id" not in schema_columns[_CHILD_CI]):
        return _no("missing_required_join_or_batch_identity_key")
    sql_proof = _sql_proof(item.get("sql"), schema_columns)
    if not sql_proof["eligible"]:
        return sql_proof
    calls = item.get("api_call")
    calls = calls if isinstance(calls, list) else [calls]
    if len(calls) not in {1, 2} or _api_resource(calls[0]) != _ROOT_CI:
        return _no("api_not_single_root_followed_by_optional_rule_read")
    if not _root_conditions_proved(calls[0], schema_columns):
        return _no("root_condition_scope_unproved_or_unfilled")
    already_prepared = False
    prepared_condition = {"constraint": [{"simple": {
        "name": "securityGroupId", "operator": "in", "value": _DEPENDENCY}}]}
    if len(calls) == 2:
        if _api_resource(calls[1]) != _CHILD_CI:
            return _no("api_not_single_root_followed_by_optional_rule_read")
        condition = calls[1].get("condition", {})
        if condition == prepared_condition:
            already_prepared = True
        elif condition not in ({}, {"constraint": []}):
            return _no("existing_child_scope_or_dependency_not_supported")
    prepared = copy.deepcopy(item)
    root_call = copy.deepcopy(calls[0])
    child_call = (copy.deepcopy(calls[1]) if len(calls) == 2 else {
        "method": "GET", "url": "/rest/hackthon/db/instances/SECURITY_GROUP_RULE?pageNo=1&pageSize=10000",
        "autoPagination": True})
    child_call["condition"] = prepared_condition
    prepared["api_call"] = [root_call, child_call]
    return {"eligible": True, "reason": "already_prepared" if already_prepared else "proved_join_semijoin_pushdown",
            "item": prepared, "proof": {
                "join_type": sql_proof["join_type"], "root_ci": _ROOT_CI, "root_table": _ROOT_TABLE,
                "child_ci": _CHILD_CI, "child_table": _CHILD_TABLE,
                "parent_field": "id", "child_field": "securityGroupId", "dependency": _DEPENDENCY,
                "already_prepared": already_prepared,
                "empty_root_policy": "typed_empty_both_then_execute_original_sql",
                "sql_preserved": True, "parent_api_preserved": True,
                "runtime_obligations": ["complete_parent_pages", "complete_child_pages_per_batch",
                    "stable_snapshot", "scalar_string_join_keys_no_sql_affinity_coercion",
                    "stable_unique_child_id_for_batch_union", "execute_original_sql_once_after_union",
                    "record_actual_bound_requests_not_unresolved_plan"]}}
