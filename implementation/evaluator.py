import json, re, time, os, sys, logging
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.WARNING)

# ── 路径配置 ──────────────────────────────────────────────
IMPL_DIR = os.path.dirname(os.path.abspath(__file__))
HACKATHON_DIR = os.path.dirname(IMPL_DIR)
BLACK_BOX_FILE = os.path.join(HACKATHON_DIR, "CMDB用例集-黑盒100.json")

sys.path.insert(0, IMPL_DIR)

# ── 评估器 ──────────────────────────────────────────────

def _normalize_val(v):
    """统一值类型：数字转int/float，None保留，其他转str。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v == int(v) else v
    s = str(v).strip()
    try:
        i = int(s)
        return i
    except ValueError:
        pass
    try:
        f = float(s)
        return f
    except ValueError:
        pass
    return s


def _get_col_key(name: str) -> str:
    """列名归一化：小写、去下划线/连字符/空格，用于列匹配。"""
    return name.lower().replace('_', '').replace('-', '').replace(' ', '')


def _vals_equal(v1, v2) -> bool:
    """比较两个值是否相等，含百分比/小数容差和浮点容差。"""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False
    if v1 == v2:
        return True
    if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
        if abs(v1 - v2) < 0.01:
            return True
        if v1 != 0 and v2 != 0:
            ratio = max(abs(v1), abs(v2)) / min(abs(v1), abs(v2))
            if abs(ratio - 1.0) < 0.1:
                return True
    if str(v1).strip() == str(v2).strip():
        return True
    return False


def _tuples_match(t1: tuple, t2: tuple) -> bool:
    """比较两个值元组是否匹配（含容差）。"""
    if len(t1) != len(t2):
        return False
    return all(_vals_equal(a, b) for a, b in zip(t1, t2))


def _extract_cols_rows(answer):
    """从 answer 中提取 (columns, rows)。
    
    answer 可以是:
      - {"columns": [...], "rows": [...], "row_count": N}
      - [{"columns": [...], "rows": [...]}, ...]  (多SQL)
    """
    if answer is None:
        return [], []
    if isinstance(answer, list):
        all_rows = []
        columns = []
        for sub in answer:
            if isinstance(sub, dict):
                if not columns:
                    columns = sub.get("columns", [])
                for row in sub.get("rows", []):
                    if isinstance(row, dict):
                        all_rows.append(row)
        return columns, all_rows
    if isinstance(answer, dict):
        cols = answer.get("columns", [])
        rows = [r for r in answer.get("rows", []) if isinstance(r, dict)]
        return cols, rows
    return [], []


def _row_to_sorted_tuple(row: dict) -> tuple:
    """将一行数据转为排序后的值元组（忽略列名）——旧接口，保留兼容。"""
    vals = [_normalize_val(v) for v in row.values()]
    vals.sort(key=lambda x: (str(type(x)), str(x)))
    return tuple(vals)


def _extract_answer_values(answer) -> List[tuple]:
    """从标准答案或系统输出中提取行值列表——旧接口，保留兼容。"""
    if answer is None:
        return []
    if isinstance(answer, list):
        result = []
        for sub in answer:
            if isinstance(sub, dict):
                for row in sub.get("rows", []):
                    if isinstance(row, dict):
                        result.append(_row_to_sorted_tuple(row))
        return result
    if isinstance(answer, dict):
        rows = answer.get("rows", [])
        return [_row_to_sorted_tuple(r) for r in rows if isinstance(r, dict)]
    return []


def _compare_answers(std_answer, sys_result) -> Tuple[bool, float]:
    """比较标准答案和系统输出。
    
    策略：按列名匹配，只比较标准答案要求的列。
    系统多出的列忽略。数值含百分比/小数容差。
    用 row_count 做行数比对，多了少了都扣分。
    
    返回 (是否完全匹配, 匹配比例 0.0~1.0)。
    """
    std_cols, std_rows = _extract_cols_rows(std_answer)
    sys_cols, sys_rows = _extract_cols_rows(sys_result)
    
    # 用 row_count 而非 len(rows)，因为标准答案可能截断了行数
    std_row_count = std_answer.get("row_count", len(std_rows)) if isinstance(std_answer, dict) else len(std_rows)
    sys_row_count = sys_result.get("row_count", len(sys_rows)) if isinstance(sys_result, dict) else len(sys_rows)
    
    if not std_rows and not sys_rows:
        if std_row_count == 0 and sys_row_count == 0:
            return True, 1.0
        return False, 0.0
    if not std_rows or not sys_rows:
        return False, 0.0
    
    std_col_map = {_get_col_key(c): c for c in std_cols}
    sys_col_map = {_get_col_key(c): c for c in sys_cols}
    
    std_keys = sorted(std_col_map.keys())
    
    def row_to_tuple(row, col_map, keys):
        return tuple(_normalize_val(row.get(col_map[k])) for k in keys)
    
    std_tuples = [row_to_tuple(r, std_col_map, std_keys) for r in std_rows]
    
    if not std_col_map:
        std_tuples = [_row_to_sorted_tuple(r) for r in std_rows]
        sys_tuples = [_row_to_sorted_tuple(r) for r in sys_rows]
        matched = _count_matches(std_tuples, sys_tuples)
        # 行数匹配且所有行匹配 → 正确
        if std_row_count == sys_row_count and matched == len(std_tuples):
            return True, 1.0
        # 否则按 max(标准行数, 系统行数) 计算比例
        total = max(std_row_count, sys_row_count)
        ratio = matched / total if total > 0 else 0.0
        return False, ratio
    
    available_keys = set(std_col_map.keys()) & set(sys_col_map.keys())
    
    if available_keys != set(std_col_map.keys()):
        if not available_keys:
            return False, 0.0
        avail_sorted = sorted(available_keys)
        std_avail = [row_to_tuple(r, std_col_map, avail_sorted) for r in std_rows]
        sys_avail = [row_to_tuple(r, sys_col_map, avail_sorted) for r in sys_rows]
        matched = _count_matches(std_avail, sys_avail)
        col_coverage = len(available_keys) / len(std_col_map)
        # 行数匹配且所有行匹配 → 按列覆盖率算
        if std_row_count == sys_row_count and matched == len(std_tuples):
            return False, col_coverage
        total = max(std_row_count, sys_row_count)
        row_match = matched / total if total > 0 else 0.0
        ratio = col_coverage * row_match
        return False, ratio
    
    sys_tuples = [row_to_tuple(r, sys_col_map, std_keys) for r in sys_rows]
    
    matched = _count_matches(std_tuples, sys_tuples)
    
    # 行数匹配且所有存储的标准行都匹配 → 正确
    if std_row_count == sys_row_count and matched == len(std_tuples):
        return True, 1.0
    
    # 否则按 max(标准行数, 系统行数) 计算比例，多了少了都扣分
    total = max(std_row_count, sys_row_count)
    ratio = matched / total if total > 0 else 0.0
    return False, ratio


def _count_matches(std_list, sys_list) -> int:
    """统计 std_list 中有多少行能在 sys_list 中找到匹配（含容差，一对一消耗）。"""
    sys_remaining = list(sys_list)
    matched = 0
    for st in std_list:
        for i, sy in enumerate(sys_remaining):
            if _tuples_match(st, sy):
                matched += 1
                sys_remaining.pop(i)
                break
    return matched


# ── API 条件检查 ──────────────────────────────────────────

def _extract_condition_fields(api_call) -> set:
    """从 api_call 中提取所有条件字段名。
    
    api_call 可以是 dict 或 list（多步骤）。
    """
    fields = set()
    calls = api_call if isinstance(api_call, list) else [api_call]
    for call in calls:
        if not isinstance(call, dict):
            continue
        cond = call.get("condition")
        if not cond:
            continue
        for c in cond.get("constraint", []):
            simple = c.get("simple", {})
            name = simple.get("name", "")
            value = simple.get("value", "")
            # 排除占位符和空值
            if name and value and not (isinstance(value, str) and value.startswith("{{")):
                fields.add(name)
    return fields


def _check_api_conditions(std_case: dict, sys_output: dict) -> Tuple[bool, str]:
    """检查系统是否在API层使用了相关条件。
    
    返回 (是否通过, 原因)。
    规则：如果标准答案有条件，系统也必须有条件（不能全量load+SQL过滤）。
    """
    std_api_call = std_case.get("api_call")
    sys_api_call = sys_output.get("api_call")
    
    std_fields = _extract_condition_fields(std_api_call)
    
    # 标准答案无条件 → 不要求系统有条件
    if not std_fields:
        return True, "标准无条件，系统无需条件"
    
    # 标准答案有条件 → 系统也必须有条件
    sys_fields = _extract_condition_fields(sys_api_call)
    
    if not sys_fields:
        return False, f"标准答案有条件{std_fields}但系统无API条件（疑似全量load+SQL处理）"
    
    return True, f"系统API条件: {sys_fields}"


# ── SQL 结构检查 ──────────────────────────────────────────

def _parse_sql_features(sql: str) -> dict:
    """从SQL中提取结构特征：SELECT字段、GROUP BY、COUNT等。"""
    if not sql:
        return {"select_cols": set(), "has_group_by": False, "has_count": False,
                "has_aggregation": False, "tables": set()}
    
    sql_upper = sql.upper()
    
    # 提取GROUP BY
    has_group_by = bool(re.search(r"\bGROUP\s+BY\b", sql_upper))
    
    # 提取COUNT
    has_count = bool(re.search(r"\bCOUNT\s*\(", sql_upper))
    
    # 提取其他聚合函数
    has_aggregation = has_count or bool(re.search(
        r"\b(SUM|AVG|MAX|MIN|COUNT)\s*\(", sql_upper))
    
    # 提取SELECT字段（简化版）
    select_match = re.search(r"\bSELECT\s+(.+?)\s+FROM\b", sql, re.IGNORECASE | re.DOTALL)
    select_cols = set()
    if select_match:
        select_text = select_match.group(1)
        # 分割字段
        parts = _split_sql_fields(select_text)
        for p in parts:
            p = p.strip()
            # 提取字段名或别名
            alias_match = re.search(r"\bAS\s+(\w+)", p, re.IGNORECASE)
            if alias_match:
                select_cols.add(alias_match.group(1).lower())
            else:
                # 去掉表名前缀
                col = re.sub(r"^.*\.", "", p).strip().lower()
                col = re.sub(r"\s*ASC\s*$|\s*DESC\s*$", "", col, flags=re.IGNORECASE).strip()
                if col and col != "*":
                    select_cols.add(col)
    
    # 提取表名
    tables = set()
    for m in re.finditer(r"\bFROM\s+(\w+)", sql, re.IGNORECASE):
        tables.add(m.group(1).upper())
    for m in re.finditer(r"\bJOIN\s+(\w+)", sql, re.IGNORECASE):
        tables.add(m.group(1).upper())
    
    return {
        "select_cols": select_cols,
        "has_group_by": has_group_by,
        "has_count": has_count,
        "has_aggregation": has_aggregation,
        "tables": tables,
    }


def _split_sql_fields(text: str) -> list:
    """简单分割SQL字段列表，处理括号嵌套。"""
    parts = []
    depth = 0
    current = []
    for c in text:
        if c == '(':
            depth += 1
            current.append(c)
        elif c == ')':
            depth -= 1
            current.append(c)
        elif c == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(c)
    if current:
        parts.append(''.join(current))
    return parts


def _check_sql_structure(std_case: dict, sys_output: dict) -> Tuple[bool, str]:
    """检查SQL结构：SELECT字段、GROUP BY、COUNT。"""
    std_sql = std_case.get("sql", "")
    sys_sql = sys_output.get("sql", "")
    
    if not sys_sql:
        return False, "系统未产出SQL"
    
    std_feat = _parse_sql_features(std_sql)
    sys_feat = _parse_sql_features(sys_sql)
    
    reasons = []
    
    # 检查GROUP BY
    if std_feat["has_group_by"] and not sys_feat["has_group_by"]:
        reasons.append(f"缺少GROUP BY（标准答案需要）")
    
    # 检查COUNT/聚合
    if std_feat["has_count"] and not sys_feat["has_count"] and not sys_feat["has_aggregation"]:
        reasons.append(f"缺少COUNT/聚合（标准答案需要）")
    
    # 检查SELECT字段覆盖
    # 从标准答案的columns推断需要哪些字段
    std_answer = std_case.get("answer", {})
    if isinstance(std_answer, dict):
        std_cols = set(c.lower() for c in std_answer.get("columns", []))
    else:
        std_cols = set()
    
    # 标准SQL中的SELECT字段
    std_select = std_feat["select_cols"]
    
    # 如果标准SQL有明确的SELECT字段，检查系统是否也SELECT了类似字段
    # 这里只做宽松检查：如果标准SELECT了特定字段（非COUNT(*)），系统也应该有类似字段
    if std_select and std_select != {'count'} and std_select != {'*'}:
        # 检查系统SQL是否SELECT了至少一些相同语义的字段
        # 不要求完全匹配，只要有合理的覆盖
        if sys_feat["has_count"] and sys_feat["select_cols"] <= {'count', 'total'}:
            if std_cols and not (std_cols <= {'count', 'total'}):
                reasons.append(f"SELECT字段不足：标准需要{std_cols}，系统仅返回COUNT")
    
    if reasons:
        return False, "; ".join(reasons)
    return True, "SQL结构检查通过"


# ── 评估主逻辑 ──────────────────────────────────────────

def evaluate_case(std_case: dict, sys_output: dict, elapsed_time: float) -> dict:
    """评估单个用例，返回评分详情。"""
    case_id = std_case.get("case_id", "")
    result = {
        "case_id": case_id,
        "question": std_case.get("question", "")[:60],
        "elapsed": round(elapsed_time, 2),
        "score": 0,
        "reason": "",
    }
    
    # 1. 不回答（弃权）
    if sys_output is None:
        result["reason"] = "不回答（系统未产出）"
        return result
    
    if sys_output.get("matched_runbook") is None:
        result["reason"] = "不回答（未命中runbook）"
        return result
    
    if sys_output.get("error"):
        result["score"] = -1
        result["reason"] = f"错误: {sys_output['error'][:80]}"
        _apply_time_penalty(result, elapsed_time)
        return result
    
    # 2. API条件检查（硬门槛）
    api_ok, api_reason = _check_api_conditions(std_case, sys_output)
    if not api_ok:
        result["score"] = 0
        result["reason"] = f"弃权（API条件不合规: {api_reason}）"
        return result
    
    # 3. SQL结构检查（软检查，不覆盖答案分数）
    sql_ok, sql_reason = _check_sql_structure(std_case, sys_output)
    sql_note = "" if sql_ok else f" [SQL结构提示: {sql_reason}]"
    
    # 4. 答案值比较
    std_answer = std_case.get("answer")
    sys_result = sys_output.get("result")
    
    all_match, ratio = _compare_answers(std_answer, sys_result)
    
    if all_match:
        result["score"] = 5
        result["reason"] = f"答案正确{sql_note}"
    elif ratio >= 0.5:
        result["score"] = round(5 * ratio, 1)
        result["reason"] = f"部分正确({ratio*100:.0f}%){sql_note}"
    else:
        result["score"] = -1
        result["reason"] = f"答案错误{sql_note}"
    
    # 5. 时间扣分
    _apply_time_penalty(result, elapsed_time)
    
    return result


def _apply_time_penalty(result: dict, elapsed_time: float):
    """应用超时扣分（最高档，不叠加）。"""
    if elapsed_time > 6:
        result["score"] -= 3
        result["reason"] += f" [超时>{elapsed_time:.0f}s, -3]"
    elif elapsed_time > 4:
        result["score"] -= 1
        result["reason"] += f" [超时>{elapsed_time:.0f}s, -1]"


# ── 批量评估入口 ──────────────────────────────────────────

def run_evaluation(test_file: str, system, limit: int = None, verbose: bool = True):
    """运行批量评估。
    
    Args:
        test_file: 黑盒用例文件路径
        system: RunbookQuerySystem 实例
        limit: 限制测试数量（用于快速验证）
        verbose: 是否打印每条结果
    
    Returns:
        评估结果摘要
    """
    with open(test_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"]
    if limit:
        cases = cases[:limit]
    
    total_score = 0
    correct = 0
    wrong = 0
    no_answer = 0
    partial = 0
    timeout_deducted = 0
    
    details = []
    
    for i, case in enumerate(cases):
        cid = case["case_id"]
        question = case["question"]
        
        if verbose:
            print(f"[{i+1}/{len(cases)}] {cid}: {question[:50]}...", end=" ", flush=True)
        
        # 运行系统，计时
        t0 = time.time()
        try:
            sys_output = system.query(question)
        except Exception as e:
            sys_output = {"matched_runbook": None, "error": str(e)}
        elapsed = time.time() - t0
        
        # 评估
        result = evaluate_case(case, sys_output, elapsed)
        total_score += result["score"]
        
        if result["score"] == 5:
            correct += 1
        elif result["score"] == 0:
            no_answer += 1
        elif result["score"] == -1 or result["score"] < 0:
            wrong += 1
        elif 0 < result["score"] < 5:
            partial += 1
        
        if "超时" in result["reason"]:
            timeout_deducted += 1
        
        details.append(result)
        
        if verbose:
            print(f"{result['score']:+.1f} ({result['reason']})")
    
    # 汇总
    summary = {
        "total_cases": len(cases),
        "total_score": round(total_score, 1),
        "max_possible_score": len(cases) * 5,
        "score_rate": f"{total_score / (len(cases) * 5) * 100:.1f}%",
        "correct_5pts": correct,
        "partial": partial,
        "wrong_-1": wrong,
        "no_answer_0pts": no_answer,
        "timeout_deducted": timeout_deducted,
        "avg_time": round(sum(d["elapsed"] for d in details) / len(details), 2),
    }
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"评估完成")
        print(f"{'='*60}")
        print(f"用例总数:       {summary['total_cases']}")
        print(f"总分:           {summary['total_score']} / {summary['max_possible_score']} ({summary['score_rate']})")
        print(f"正确(+5):       {correct}")
        print(f"部分正确:        {partial}")
        print(f"错误(-1):       {wrong}")
        print(f"不回答(0):      {no_answer}")
        print(f"超时扣分用例:    {timeout_deducted}")
        print(f"平均响应时间:    {summary['avg_time']}s")
        
        # 保存详细结果
        out_file = os.path.join(IMPL_DIR, "evaluation_result.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "details": details}, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果已保存: {out_file}")
    
    return summary


if __name__ == "__main__":
    from runbook_system import RunbookQuerySystem
    
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    system = RunbookQuerySystem()
    print(f"已加载 {len(system.items)} 个 runbook items")
    print(f"评估文件: {BLACK_BOX_FILE}")
    print()
    
    run_evaluation(BLACK_BOX_FILE, system, limit=limit)
