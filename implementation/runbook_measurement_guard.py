"""空schema编译门禁：阻止用时钟、随机数或SQLite环境伪造CMDB测量。"""

import re
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass


_TEMPORAL = {"date", "time", "datetime", "julianday", "unixepoch", "strftime", "timediff"}
_RUNTIME = {
    "current_date": "clock", "current_time": "clock", "current_timestamp": "clock",
    "random": "random", "randomblob": "random", "changes": "sqlite_environment",
    "total_changes": "sqlite_environment", "last_insert_rowid": "sqlite_environment",
    "sqlite_version": "sqlite_environment", "sqlite_source_id": "sqlite_environment",
    "sqlite_compileoption_get": "sqlite_environment", "sqlite_compileoption_used": "sqlite_environment",
    "sqlite_offset": "sqlite_environment", "load_extension": "sqlite_environment",
}
_IMPLICIT_NOW = {"now", "subsec", "subsecond"}


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    start: int
    end: int


def _tokens(sql):
    """仅词法分界，不用关键词搜索猜调用；真正函数/字段由SQLite authorizer确认。"""
    result, index = [], 0
    while index < len(sql):
        ch, start = sql[index], index
        if ch.isspace():
            index += 1; continue
        if sql.startswith("--", index):
            stop = sql.find("\n", index + 2)
            index = len(sql) if stop < 0 else stop + 1
            continue
        if sql.startswith("/*", index):
            stop = sql.find("*/", index + 2)
            index = len(sql) if stop < 0 else stop + 2
            continue
        if ch in "'\"`[":
            close = "]" if ch == "[" else ch
            index += 1; value = []
            while index < len(sql):
                if sql[index] == close:
                    if ch != "[" and index + 1 < len(sql) and sql[index + 1] == close:
                        value.append(close); index += 2; continue
                    index += 1; break
                value.append(sql[index]); index += 1
            else:
                raise ValueError("unterminated_quote")
            kind = "string" if ch == "'" else "double_ident" if ch == '"' else "ident"
            result.append(_Token(kind, "".join(value), start, index)); continue
        if ch.isalpha() or ch == "_":
            index += 1
            while index < len(sql) and (sql[index].isalnum() or sql[index] in "_$"):
                index += 1
            result.append(_Token("ident", sql[start:index], start, index)); continue
        number = re.match(r"(?:0[xX][0-9a-fA-F]+|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", sql[index:])
        if number:
            index += len(number[0]); result.append(_Token("number", number[0], start, index)); continue
        index += 2 if sql.startswith("||", index) else 1
        result.append(_Token("punct", sql[start:index], start, index))
    return result


def _paren_map(tokens):
    stack, pairs = [], {}
    for index, token in enumerate(tokens):
        if token.kind == "punct" and token.value == "(":
            stack.append(index)
        elif token.kind == "punct" and token.value == ")":
            if not stack: raise ValueError("unbalanced_parentheses")
            pairs[stack.pop()] = index
    if stack: raise ValueError("unbalanced_parentheses")
    return pairs


def _arguments(tokens):
    if not tokens: return []
    result, depth, start = [], 0, 0
    for index, token in enumerate(tokens):
        if token.kind != "punct": continue
        if token.value == "(": depth += 1
        elif token.value == ")": depth -= 1
        elif token.value == "," and depth == 0:
            result.append(tokens[start:index]); start = index + 1
    result.append(tokens[start:])
    return result


def _unwrap(tokens):
    while len(tokens) >= 2 and tokens[0].kind == "punct" and tokens[0].value == "(":
        pairs = _paren_map(tokens)
        if pairs.get(0) != len(tokens) - 1: break
        tokens = tokens[1:-1]
    return tokens


def _call(tokens):
    tokens = _unwrap(tokens)
    if (len(tokens) < 3 or tokens[0].kind not in {"ident", "double_ident", "string"}
            or tokens[1].value != "(" or tokens[1].kind != "punct"
            or _paren_map(tokens).get(1) != len(tokens) - 1):
        return None
    return tokens[0].value.casefold(), _arguments(tokens[2:-1])


def _fixed(tokens):
    tokens = _unwrap(tokens)
    if len(tokens) == 1 and tokens[0].kind in {"string", "number"}:
        return True, tokens[0].value
    if len(tokens) == 1 and tokens[0].kind == "ident" and tokens[0].value.casefold() == "null":
        return True, None
    if len(tokens) == 2 and tokens[0].value in {"+", "-"} and tokens[1].kind == "number":
        return True, tokens[0].value + tokens[1].value
    return False, None


def _temporal_check(name, arguments, read_columns, depth=0):
    if depth > 32: return False, "temporal_expression_depth_unproven", "unproven"
    indices = [0, 1] if name == "timediff" else [1] if name == "strftime" else [0]
    for index in indices:
        if index >= len(arguments): return False, "omitted_time_value_uses_clock", "clock"
        valid, reason, source = _time_value(arguments[index], read_columns, depth + 1)
        if not valid: return valid, reason, source
    if name != "timediff":
        for argument in arguments[indices[0] + 1:]:
            valid, value = _fixed(argument)
            if not valid: return False, "computed_time_modifier_unproven", "unproven"
            if isinstance(value, str) and value.strip().casefold() in {"localtime", "utc"}:
                return False, "host_timezone_modifier", "sqlite_environment"
    return True, "column_or_fixed_time_value", None


def _time_value(tokens, read_columns, depth=0):
    tokens = _unwrap(tokens)
    fixed, value = _fixed(tokens)
    if fixed:
        if isinstance(value, str) and value.strip().casefold() in _IMPLICIT_NOW:
            return False, "literal_or_shortcut_time_value_uses_clock", "clock"
        return True, "fixed_time_value", None
    if (tokens and len(tokens) % 2 == 1 and all(
            token.kind in {"ident", "double_ident"} if index % 2 == 0
            else token.kind == "punct" and token.value == "." for index, token in enumerate(tokens))):
        column = tokens[-1].value.casefold()
        if column in read_columns: return True, "actual_cmdb_column", None
        # SQLite的double-quoted-string兼容模式可把未绑定双引号名称当字符串。
        if len(tokens) == 1 and tokens[0].kind == "double_ident":
            if column.strip() in _IMPLICIT_NOW: return False, "double_quoted_time_value_uses_clock", "clock"
            return True, "sqlite_double_quoted_fixed_literal", None
    called = _call(tokens)
    if called:
        name, arguments = called
        if name in _TEMPORAL: return _temporal_check(name, arguments, read_columns, depth + 1)
        if name in {"coalesce", "ifnull"}:
            for argument in arguments:
                valid, reason, source = _time_value(argument, read_columns, depth + 1)
                if not valid: return valid, reason, source
            return True, "proven_time_fallbacks", None
        if name == "nullif" and len(arguments) == 2:
            primary = _time_value(arguments[0], read_columns, depth + 1)
            if primary[0] and _fixed(arguments[1])[0]: return primary
        if name == "cast" and len(arguments) == 1:
            argument, level = arguments[0], 0
            for index, token in enumerate(argument):
                if token.kind == "punct" and token.value == "(": level += 1
                elif token.kind == "punct" and token.value == ")": level -= 1
                elif level == 0 and token.kind == "ident" and token.value.casefold() == "as":
                    return _time_value(argument[:index], read_columns, depth + 1)
    # 不执行未知常量表达式来猜结果；concat/CASE/任意函数可能拼出now，保守回退。
    return False, "computed_time_value_unproven", "unproven"


def inspect_measurement_sources(sql, schemas):
    functions, reads, hazards, denied = [], set(), [], []
    result = {"compiled": False, "valid": False, "functions": [], "reads": [], "hazards": []}
    if (not isinstance(sql, str) or not isinstance(schemas, dict) or not schemas
            or any(not isinstance(table, str) or not isinstance(columns, (list, tuple)) or not columns
                   or any(not isinstance(column, str) for column in columns) for table, columns in schemas.items())):
        return dict(result, reason="measurement_schema_or_sql_unproven")
    tables = {name.casefold() for name in schemas}
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorize(action, first, second, database, trigger):
        if action == sqlite3.SQLITE_FUNCTION:
            functions.append((second or first or "").casefold())
        elif action == sqlite3.SQLITE_READ:
            reads.add((first, second))
            if (first or "").casefold() not in tables:
                denied.append("read_outside_cmdb_schema"); return sqlite3.SQLITE_DENY
        if action not in allowed:
            denied.append("non_select_authorizer_action"); return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        with closing(sqlite3.connect(":memory:")) as db:
            for table, columns in schemas.items():
                db.execute('CREATE TABLE "' + table.replace('"', '""') + '" (' +
                           ','.join('"' + column.replace('"', '""') + '" TEXT' for column in columns) + ')')
            db.set_authorizer(authorize)
            db.execute("EXPLAIN " + sql).fetchall()
        tokens = _tokens(sql); pairs = _paren_map(tokens)
        read_columns = {(column or "").casefold() for _, column in reads if column}
        for function in sorted(set(functions)):
            if function in _RUNTIME or function.startswith("sqlite_"):
                hazards.append({"function": function, "source": _RUNTIME.get(function, "sqlite_environment"), "reason": "actual_runtime_function"})
        found_temporal = set()
        for index, token in enumerate(tokens[:-1]):
            name = token.value.casefold()
            if (name not in _TEMPORAL or name not in functions or token.kind not in {"ident", "double_ident", "string"}
                    or tokens[index + 1].kind != "punct" or tokens[index + 1].value != "("):
                continue
            stop = pairs.get(index + 1)
            if stop is None: raise ValueError("temporal_call_unbalanced")
            found_temporal.add(name)
            valid, reason, source = _temporal_check(name, _arguments(tokens[index + 2:stop]), read_columns)
            if not valid:
                hazards.append({"function": name, "source": source, "reason": reason, "start": token.start, "end": tokens[stop].end})
        for function in sorted(set(functions) & _TEMPORAL - found_temporal):
            hazards.append({"function": function, "source": "unproven", "reason": "temporal_call_syntax_unproven"})
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return dict(result, reason="measurement_sql_compile_or_authorization_failed", error_type=type(exc).__name__,
                    functions=sorted(set(functions)), reads=[{"table": table, "column": column} for table, column in sorted(reads)], denied=denied)
    return {"compiled": True, "valid": not hazards, "reason": "runtime_or_unproven_temporal_source" if hazards else "no_runtime_measurement_source",
            "functions": sorted(set(functions)), "reads": [{"table": table, "column": column} for table, column in sorted(reads)], "hazards": hazards}


def measurement_source_contract(original, candidate, schemas):
    """检查两份SQL；未知时间表达式失败关闭，不放宽父级投影/粒度/表集合等合同。"""
    before = inspect_measurement_sources(original, schemas)
    after = inspect_measurement_sources(candidate, schemas)
    key = lambda hazard: (hazard["function"], hazard["source"], hazard["reason"])
    old = Counter(key(hazard) for hazard in before["hazards"])
    new = Counter(key(hazard) for hazard in after["hazards"])
    added = new - old
    return {"reject": not before["compiled"] or not after["valid"],
            "reason": "candidate_runtime_or_unproven_measurement_source" if not after["valid"] else
                      "original_measurement_sql_unproven" if not before["compiled"] else "measurement_sources_preserved",
            "original_requires_review": not before["valid"], "safe_original_fallback": before["valid"],
            "original": before, "candidate": after,
            "new_source_counts": [{"function": function, "source": source, "reason": reason, "count": count}
                                  for (function, source, reason), count in sorted(added.items())],
            "scope": "runtime_source_guard_not_full_numeric_lineage_or_answer_correctness"}
