"""分析原评估入口的 JSONL / 文本结果，可与上一轮比较；不调用模型。"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
CASE = re.compile(r'^([\w-]+):\s*([+-]?\d+(?:\.\d+)?)\s+\((.*)\)\s+\[(\d+(?:\.\d+)?)s\]$')
FOOTER = re.compile(r'^===\s*(\d+)\s+cases:\s*score=([+-]?[\d.eE+-]+)/(\d+)')
HEADER = re.compile(r'本地诊断：[白黑]盒前\s*(\d+)\s*题')
CSV_FIELDS = ['case_id', 'question', 'score', 'elapsed_seconds', 'category', 'reason',
              'matched_runbook', 'api_call', 'sql', 'error', 'candidates', 'selected_id',
              'selection_method', 'parameter_values', 'parameter_sources', 'parameter_changes',
              'unfilled_parameters', 'api_after_fill', 'api_after_field_fix',
              'sql_before_refine', 'sql_model_proposal', 'sql_after_refine',
              'sql_final', 'refine_status', 'rejection_stage', 'rejection_reason', 'review_hint']


def redact(text):
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    return text.replace(key, '[REDACTED]') if key else text


def read_log(path):
    data = Path(path).read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('gb18030')


def category(reason):
    if 'API条件不合规' in reason:
        return 'API条件不合规'
    for prefix, name in [('答案正确', '答案正确'), ('部分正确', '部分正确'),
                         ('答案错误', '答案错误'), ('错误:', '执行错误'), ('不回答', '拒答')]:
        if reason.startswith(prefix):
            return name
    return '待复核'


def review_hint(row):
    rejection = (row.get('diagnostics') or {}).get('rejection', {})
    if rejection:
        return {'no_candidates': 'A：BM25候选为空；检查检索门禁与模板覆盖，不等于已证明库内无能力',
                'candidate_ids_not_in_library': 'A/B：候选ID无法映射到当前模板库',
                'invalid_selector_output': 'B：模型选择输出不能解析为序号',
                'selector_declined_or_out_of_range': 'B：有候选但模型未选中，且未触发强候选回退',
                'resource_mismatch': 'B：资源门禁拒答，核对问题资源与所选模板',
                'requested_field_missing': 'B：字段门禁拒答，核对所需字段',
                'parameter_fill_failed': 'B：填参流程返回失败，检查参数来源与变更',
                'required_api_condition_missing': 'B：API条件门禁拒答，检查所缺条件与填参',
                'refinement_changed_tables': 'B：精调改变表集合，触发拒答；对照精调前后SQL',
                'union_not_allowed': 'B：SQL后处理因UNION拒答'}.get(rejection.get('reason'), 'C：按已记录的拒答阶段复核')
    if row['category'] == '答案正确' and row['score'] < 5:
        return 'B/C：答案正确但失分，检查耗时和超时扣分'
    sql = (row.get('diagnostics') or {}).get('sql', {})
    if row['score'] < 5 and sql.get('refine_status') == 'changed':
        return 'B：精调SQL有变化；对照前后结果验证，尚不能仅凭变化认定精调退化'
    return {'部分正确': 'B：核对结果列、行数、过滤条件和SQL',
            '答案错误': 'A/B：核对选中模板、API参数和SQL；不能仅凭分数认定召回失败',
            '执行错误': 'B：检查实际API、SQL、错误和数据服务',
            '拒答': 'A/B：检查候选、选择与门禁；未记录候选时不能区分召回和选择问题',
            'API条件不合规': 'B：检查API条件与填参'}.get(row['category'], 'C：结合详细结果复核原因')


def diagnostic_fields(diagnostics):
    diagnostics = diagnostics or {}
    parameters = diagnostics.get('parameters', {})
    selection = diagnostics.get('selection', {})
    sql = diagnostics.get('sql', {})
    rejection = diagnostics.get('rejection', {})
    final = parameters.get('final', {})
    return {'candidates': diagnostics.get('retrieval', {}).get('candidates', ''),
            'selected_id': selection.get('selected_id', ''),
            'selection_method': selection.get('method', ''),
            'parameter_values': final,
            'parameter_sources': {name: parameters.get('sources', {}).get(name, 'unknown') for name in final},
            'parameter_changes': parameters.get('changes', []),
            'unfilled_parameters': parameters.get('unfilled', []),
            'api_after_fill': parameters.get('api_after_fill', ''),
            'api_after_field_fix': parameters.get('effective_api', ''),
            'sql_before_refine': sql.get('before_refine', ''),
            'sql_model_proposal': sql.get('model_proposal', ''),
            'sql_after_refine': sql.get('after_refine', ''), 'sql_final': sql.get('final', ''),
            'refine_status': sql.get('refine_status', ''),
            'rejection_stage': rejection.get('stage', ''), 'rejection_reason': rejection.get('reason', '')}


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * fraction
    low = math.floor(index)
    high = math.ceil(index)
    return round(values[low] + (values[high] - values[low]) * (index - low), 4)


def parse(text, expected=None, exit_code=None, questions=None):
    """保持原评分；中止、缺题或汇总不一致均不作为完整成绩。"""
    text = redact(text)
    rows, issues, header, footer, metadata = [], [], None, None, {}
    query_errors = []
    detailed = text.lstrip().startswith('{')
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if detailed:
            record = json.loads(line)
            kind = record['type']
            if footer is not None:
                issues.append('最终汇总之后仍有记录，请勿拼接多轮结果')
            if kind == 'run':
                if header is not None or rows:
                    issues.append('存在多次运行或开始记录顺序异常')
                metadata = record
                header = int(record['planned_cases'])
            elif kind == 'case':
                evaluation = record['evaluation']
                output = record.get('output') or {}
                rows.append({'case_id': record['case_id'], 'question': record['question'],
                             'score': float(evaluation['score']), 'reason': evaluation['reason'],
                             'elapsed_seconds': float(record['elapsed_seconds']), **output,
                             'diagnostics': record.get('diagnostics')})
            elif kind == 'query_error':
                query_errors.append(record)
            elif kind == 'summary':
                footer = {'count': record['completed_cases'], 'score': record['total_score'],
                          'max_score': record['max_score']}
                if record['status'] != 'complete':
                    issues.append('原评估未完成：' + record.get('stop_reason', '原因未记录'))
            else:
                raise ValueError(f'未知记录类型：{kind}')
        else:
            match = HEADER.search(line)
            if match:
                if header is not None:
                    issues.append('日志中有多次运行')
                header = int(match.group(1))
            match = CASE.fullmatch(line)
            if match:
                case_id, score, reason, elapsed = match.groups()
                rows.append({'case_id': case_id, 'question': (questions or {}).get(case_id, ''),
                             'score': float(score), 'reason': reason, 'elapsed_seconds': float(elapsed)})
            match = FOOTER.match(line)
            if match:
                if footer is not None:
                    issues.append('日志中有多份最终汇总')
                footer = {'count': int(match.group(1)), 'score': float(match.group(2)),
                          'max_score': int(match.group(3))}
    for row in rows:
        if not math.isfinite(row['score']) or not math.isfinite(row['elapsed_seconds']) or row['elapsed_seconds'] < 0:
            raise ValueError('分数或耗时不是有效数值')
        row['category'] = category(row['reason'])
        row.update(diagnostic_fields(row.get('diagnostics')))
        row['review_hint'] = review_hint(row)
    planned = expected if expected is not None else header if header is not None else footer['count'] if footer else None
    if len({r['case_id'] for r in rows}) != len(rows):
        issues.append('重复题号')
    if not rows or planned is None or len(rows) != planned:
        issues.append('逐题记录数与计划题数不符或计划未知')
    if header is not None and planned != header:
        issues.append('开始记录与指定题数不符')
    if detailed and header is None:
        issues.append('缺少运行开始记录')
    score = round(sum(r['score'] for r in rows), 6)
    if footer is None:
        issues.append('缺少原评估最终汇总')
    elif (footer['count'] != len(rows) or footer['max_score'] != len(rows) * 5
          or not math.isclose(footer['score'], score, abs_tol=.00001)):
        issues.append('原汇总与逐题记录不一致')
    if exit_code not in (None, 0):
        issues.append(f'原进程退出码为{exit_code}')
    if query_errors:
        issues.append('存在未评分的查询异常，详见query_errors')
    complete = not issues
    times = [r['elapsed_seconds'] for r in rows]
    return {'status': 'complete' if complete else 'incomplete', 'issues': issues,
            'planned_cases': planned, 'recorded_cases': len(rows), 'observed_score': score,
            'max_score_recorded': len(rows) * 5,
            'score_percent': round(score / (len(rows) * 5) * 100, 3) if complete else None,
            'score_counts': {'full': sum(r['score'] == 5 for r in rows),
                             'partial': sum(0 < r['score'] < 5 for r in rows),
                             'negative': sum(r['score'] < 0 for r in rows),
                             'zero': sum(r['score'] == 0 for r in rows)},
            'reason_categories': dict(Counter(r['category'] for r in rows)),
            'correct_but_lost_points': sum(r['category'] == '答案正确' and r['score'] < 5 for r in rows),
            'mean_seconds': round(statistics.mean(times), 4) if times else None,
            'p50_seconds': percentile(times, .5), 'p95_seconds': percentile(times, .95),
            'timeout_penalty_cases': sum('超时' in r['reason'] for r in rows),
            'timing_precision': 'query原始计时' if detailed else '原文本显示值，通常只有一位小数',
            'diagnostics_cases': sum(bool(r.get('diagnostics')) for r in rows),
            'rejection_stages': dict(Counter(r['rejection_stage'] for r in rows if r['rejection_stage'])),
            'refinement_statuses': dict(Counter(r['refine_status'] for r in rows if r['refine_status'])),
            'run_metadata': metadata, 'query_errors': query_errors, 'cases': rows}


def load(path, expected=None, exit_code=None, case_file=None):
    text = read_log(path)
    questions = {}
    if case_file is not None or not text.lstrip().startswith('{'):
        case_file = Path(case_file) if case_file else ROOT / 'CMDB用例集-白盒200.json'
        questions = {c['case_id']: c['question'] for c in json.loads(case_file.read_text(encoding='utf-8'))['cases']}
    result = parse(text, expected, exit_code, questions)
    result['source_log'] = str(Path(path).resolve())
    result['source_log_sha256'] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return result


def write_csv(path, rows, fields=CSV_FIELDS):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            cleaned = {}
            for key in fields:
                value = row.get(key, '')
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                if isinstance(value, str):
                    value = redact(value)
                    if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                        value = "'" + value
                cleaned[key] = value
            writer.writerow(cleaned)


def analyze(log_path, output_dir=None, expected=None, exit_code=None, case_file=None, baseline=None):
    log_path = Path(log_path).resolve()
    output = Path(output_dir).resolve() if output_dir else log_path.parent / (log_path.stem + '-analysis')
    if any((output / name).exists() for name in ('results.json', 'cases.csv', 'failures.csv', 'REPORT.md', 'comparison.csv')):
        raise ValueError('报告已存在，请用 --output-dir 指定新目录')
    result = load(log_path, expected, exit_code, case_file)
    comparison = None
    if baseline:
        previous = load(baseline, case_file=case_file)
        old = {row['case_id']: row for row in previous['cases']}
        if (result['status'] != 'complete' or previous['status'] != 'complete'
                or set(old) != {row['case_id'] for row in result['cases']}
                or any(row['question'] != old[row['case_id']]['question'] for row in result['cases'])):
            raise ValueError('对照要求两次完整运行，且题号和问题一致')
        comparison = [{'case_id': row['case_id'], 'question': row['question'],
                       'old_score': old[row['case_id']]['score'], 'new_score': row['score'],
                       'score_delta': round(row['score'] - old[row['case_id']]['score'], 4),
                       'old_seconds': old[row['case_id']]['elapsed_seconds'],
                       'new_seconds': row['elapsed_seconds']} for row in result['cases']]
        result['comparison'] = {'baseline': str(Path(baseline).resolve()),
                                'score_delta': round(result['observed_score'] - previous['observed_score'], 4),
                                'improved_cases': sum(r['score_delta'] > 0 for r in comparison),
                                'regressed_cases': sum(r['score_delta'] < 0 for r in comparison),
                                'note': '仅描述两次实测差异；请人工核对模型、配置和运行环境是否一致'}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_bytes(redact(json.dumps(result, ensure_ascii=False, indent=2)).encode('utf-8'))
    write_csv(output / 'cases.csv', result['cases'])
    failures = [r for r in result['cases'] if r['score'] < 5]
    write_csv(output / 'failures.csv', failures)
    if comparison is not None:
        write_csv(output / 'comparison.csv', comparison, list(comparison[0]))
    lines = ['# 根目录评估结果', f'来源：{log_path}',
             f'状态：{result["status"]}；完成 {result["recorded_cases"]}/{result["planned_cases"]} 题',
             f'原评分合计：{result["observed_score"]}/{result["max_score_recorded"]}；得分率：{result["score_percent"]}',
             f'得分计数（full满分 / partial部分正分 / negative负分 / zero零分）：{result["score_counts"]}',
             f'原评分原因：{result["reason_categories"]}',
             f'平均 / P50 / P95：{result["mean_seconds"]} / {result["p50_seconds"]} / {result["p95_seconds"]} 秒',
             f'计时精度：{result["timing_precision"]}；评分原因含超时扣分：{result["timeout_penalty_cases"]}题',
             f'答对但失分：{result["correct_but_lost_points"]}题；需复核失分题：{len(failures)}题',
             f'含链路诊断：{result["diagnostics_cases"]}题；拒答阶段：{result["rejection_stages"]}',
             f'SQL精调状态：{result["refinement_statuses"]}；未评分查询异常：{len(result["query_errors"])}题',
             f'完整性问题：{result["issues"] or "无"}',
             'cases.csv 是逐题表；failures.csv 含失分题、实际模板/API/SQL/错误和排查提示；完整执行结果在 results.json。',
             '详细记录包含候选ID/分数/覆盖率、选择结果、参数来源与变更、精调前/模型建议/精调后/最终SQL及拒答原因。旧日志没有诊断时字段留空。',
             '候选coverage是检索器的词覆盖率，不是正确召回率；SQL发生变化不证明导致退化，仍需验证前后结果。',
             '分数来自原评分器，C不重新评分；未完成题不补零。本地单次诊断不等于正式成绩。',
             '此入口未采集模型请求数、token、CPU和内存，不推测这些数据。']
    if comparison is not None:
        lines.extend([f'前后对照：{result["comparison"]}', '逐题增退分见 comparison.csv。'])
    (output / 'REPORT.md').write_bytes(redact('\n\n'.join(lines) + '\n').encode('utf-8'))
    return result, output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--expected', type=int)
    parser.add_argument('--exit-code', type=int)
    parser.add_argument('--cases', type=Path, help='旧文本日志对应的用例文件，默认白盒200题')
    parser.add_argument('--baseline', type=Path, help='上一轮 JSONL / 文本结果，只做描述性比较')
    args = parser.parse_args(argv)
    if args.expected is not None and args.expected < 1:
        parser.error('--expected 必须为正整数')
    try:
        result, output = analyze(args.log, args.output_dir, args.expected, args.exit_code, args.cases, args.baseline)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(redact(str(exc)))
    print(f'分析已保存：{output}')
    print(f"状态：{result['status']}；完成 {result['recorded_cases']} 题；原评分合计 {result['observed_score']}")
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
