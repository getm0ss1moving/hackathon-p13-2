"""C's offline experiment assembly, evidence analysis, comparison and checks.

This file never imports a matcher, sends a model request or changes A/B code.
"""
import argparse
import ast
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WHITE = ROOT / 'CMDB用例集-白盒200.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))


def csv_save(path, rows, fields):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        for item in rows:
            row = {k: item.get(k) for k in fields}
            for k, v in row.items():
                if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                    row[k] = "'" + v
                elif isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, ensure_ascii=False)
            writer.writerow(row)


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1] if values else None


def outcome(reason):
    if 'API条件不合规' in reason:
        return 'api_condition_missing'
    for prefix, label in [('答案正确', 'correct'), ('部分正确', 'partial'), ('答案错误', 'wrong'),
                          ('错误:', 'execution_error'), ('不回答', 'abstained')]:
        if reason.startswith(prefix):
            return label
    return 'unclassified'


def row_record(row):
    evaluation = row.get('evaluation', row)
    output = row.get('output', row)
    reason = evaluation.get('reason', '')
    penalty_match = re.search(r'\[超时>[^\]]*,\s*-(\d+)\]', reason)
    penalty = int(penalty_match.group(1)) if penalty_match else row.get('time_penalty', 0)
    score = evaluation['score']
    return {
        'case_id': row['case_id'], 'repeat': row.get('repeat', 1),
        'question': row.get('question', ''), 'score': score,
        'untimed_score': row.get('score_without_time_penalty', score + penalty),
        'elapsed': row.get('elapsed_s', row.get('elapsed_seconds', evaluation.get('elapsed', 0))),
        'reason': reason, 'outcome': outcome(reason), 'penalty': penalty,
        'matched_runbook': output.get('matched_runbook'), 'api_call': output.get('api_call'),
        'sql': output.get('sql'), 'result': output.get('result'),
        'diagnostics': output.get('diagnostics') or {}, 'candidates': row.get('candidates'),
    }


def load_run(path):
    path = Path(path)
    if path.suffix == '.jsonl':
        lines = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        plans = [x for x in lines if x.get('type') == 'plan']
        ends = [x for x in lines if x.get('type') == 'summary']
        if len(plans) != 1 or len(ends) != 1:
            raise ValueError('JSONL 必须有且只有一份 plan 和 summary；缺失结尾属于未完成证据')
        meta, summary = plans[0], ends[0]
        records = [row_record(x) for x in lines if x.get('type') == 'case']
        requests = [x for x in lines if x.get('type') == 'request']
        status = summary.get('status')
        planned = summary.get('planned_cases', meta.get('case_count', len(meta.get('scope', {}).get('case_ids', []))))
        dataset_sha = meta.get('dataset_sha256')
        source_hashes = meta.get('source_sha256', {})
        declared_score = summary.get('total_score', summary.get('score'))
        reported_requests = summary.get('generation_requests')
    else:
        document = read(path)
        meta, summary = document, document.get('summary', {})
        raw = document.get('details', document.get('cases'))
        if not isinstance(raw, list):
            raise ValueError('不支持的报告：缺少 details/cases')
        records = [row_record(x) for x in raw]
        requests = document.get('requests', document.get('llm_events', []))
        status = document.get('status')
        planned = document.get('planned', document.get('requested_cases', len(raw)))
        dataset_sha = document.get('dataset_sha256', document.get('case_file_sha256'))
        source_hashes = document.get('source_sha256', document.get('implementation_sha256', {}))
        declared_score = document.get('score_sum', document.get('total_score', summary.get('total_score')))
        reported_requests = document.get('http_attempts', document.get('generation_requests'))
    keys = [(r['case_id'], r['repeat']) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('重复的 case_id/repeat 记录，拒绝重复计分')
    issues = []
    if status not in ('complete', 'completed') or len(records) != planned:
        issues.append('incomplete_run')
    score_sum = round(sum(r['score'] for r in records), 5)
    if declared_score is not None and not math.isclose(score_sum, declared_score, abs_tol=.0001):
        issues.append('declared_score_mismatch')
    if reported_requests is not None and len(requests) != reported_requests:
        issues.append('request_count_mismatch')
    if summary.get('completed_cases', meta.get('completed', len(records))) != len(records):
        issues.append('completed_count_mismatch')
    scope = meta.get('scope') if isinstance(meta.get('scope'), dict) else {}
    config = {k: meta.get(k, scope.get(k)) for k in
              ('model', 'base_url', 'max_output_tokens', 'sdk_max_retries', 'thinking', 'temperature')}
    config['cache_policy'] = meta.get('cache_policy', meta.get('cache'))
    scorer = meta.get('scorer_sha256', source_hashes.get('evaluator.py'))
    return {'path': str(path), 'sha256': sha(path), 'meta': meta, 'declared_summary': summary,
            'records': records, 'requests': requests, 'planned': planned, 'status': status,
            'issues': issues, 'dataset_sha256': dataset_sha, 'scorer_sha256': scorer,
            'config': config, 'source_sha256': source_hashes, 'reported_requests': reported_requests}


def summarize(run):
    rows = run['records']
    times = [r['elapsed'] for r in rows]
    # Select one request evidence source. Never add event rows and duplicated per-case diagnostics.
    requests = run['requests']
    if not requests:
        calls = [r['diagnostics'].get('llm_calls') for r in rows]
        requests = [e for items in calls if isinstance(items, list) for e in items]
    usage_events = [e.get('usage', e) for e in requests
                    if 'prompt_tokens' in e.get('usage', e) or 'completion_tokens' in e.get('usage', e)]
    def tokens(key):
        return sum(e.get(key, 0) or 0 for e in usage_events) if usage_events else None
    stages = {}
    for stage in sorted({e.get('stage', 'unavailable') for e in requests}):
        items = [e for e in requests if e.get('stage', 'unavailable') == stage]
        durations = [e['seconds'] for e in items if isinstance(e.get('seconds'), (int, float))]
        stages[stage] = {'requests': len(items), 'seconds': round(sum(durations), 6),
                         'time_observed_requests': len(durations)}
    declared = run['declared_summary']
    return {
        'status': run['status'], 'integrity_issues': run['issues'], 'completed_cases': len(rows),
        'planned_cases': run['planned'], 'score': round(sum(r['score'] for r in rows), 3),
        'untimed_score': round(sum(r['untimed_score'] for r in rows), 3),
        'max_score_completed': len(rows) * 5,
        'answer_reason_counts': dict(Counter(r['outcome'] for r in rows)),
        'full_credit_answers_untimed': sum(r['untimed_score'] == 5 for r in rows),
        'time_penalty_points': sum(r['penalty'] for r in rows),
        'correct_but_timed': sum(r['outcome'] == 'correct' and r['penalty'] > 0 for r in rows),
        'over_4s': sum(t > 4 for t in times), 'over_6s': sum(t > 6 for t in times),
        'p50_seconds': percentile(times, .5), 'p95_seconds': percentile(times, .95),
        'max_seconds': max(times) if times else None, 'mean_seconds': statistics.mean(times) if times else None,
        'requests': len(requests) if requests else run.get('reported_requests'),
        'request_count_semantics': run['meta'].get('http_count_semantics',
            'HTTP attempts including SDK retries' if 'http_attempts' in run['meta'] else
            'original generation event stream; inspect sdk_max_retries before comparing'),
        'prompt_tokens': tokens('prompt_tokens'), 'completion_tokens': tokens('completion_tokens'),
        'request_stages': stages, 'model_config': run['config'],
        'template_count': run['meta'].get('template_count'),
        'cpu_seconds': declared.get('process_cpu_seconds'),
        'peak_evaluation_memory_mib': declared.get('peak_process_memory_mib', declared.get('peak_evaluation_process_mib')),
        'memory_scope': declared.get('memory_scope', '未记录；不认定为系统总内存'),
        'official_total': None,
        'limitations': ['单轮开发结果；不同目录或模型不能直接归并',
                        '阈值附近的舍入耗时不能用于重算罚分；罚分来自原记录',
                        '没有黑盒与正式重复合同，不计算官方总分'],
    }


def classify(row):
    matching = row['diagnostics'].get('matching') or {}
    reason = matching.get('reason')
    if row['outcome'] == 'correct' and row['penalty']:
        return 'correct_but_timed', 'B/C', 'observed', '答案正确；原评分器已扣时间分'
    if row['untimed_score'] == 5:
        return 'full_credit', 'C', 'observed', '无时延评分为5；保留为控制样本'
    if row['outcome'] == 'api_condition_missing':
        return 'api_condition_missing', 'A/B', 'observed_trigger', '原评分器API条件门槛未通过'
    triggers = {'resource_mismatch': ('resource_gate', 'B/C'),
                'missing_required_parameters': ('parameter_gate', 'A/B'),
                'missing_parameters': ('parameter_gate', 'A/B'),
                'missing_api_condition': ('api_condition_gate', 'A/B'),
                'missing_api_filter': ('api_condition_gate', 'A/B'),
                'invalid_model_output': ('model_output', 'B/C'),
                'invalid_model_output_fill': ('model_output', 'B/C'),
                'invalid_model_output_select': ('model_output', 'B/C'),
                'invalid_resource_lookup': ('resource_lookup_gate', 'B/C')}
    if reason in triggers:
        category, owner = triggers[reason]
        return category, owner, 'observed_trigger', '已观察门禁触发；合理拒答或误拒仍需复核'
    if row['outcome'] == 'abstained':
        if matching.get('candidate_ids') == []:
            return 'empty_candidates', 'A/C', 'observed_trigger', '候选为空；尚未证明库内存在可答模板'
        return 'abstention_needs_review', 'A/B/C', 'needs_review', '不能从未命中直接推断召回失败'
    if row['outcome'] == 'execution_error':
        return 'execution_failure', 'B/C', 'observed', '先排查API/SQL/环境，不归罪于检索'
    before, after = matching.get('sql_before_refine'), matching.get('sql_after_refine')
    if before and after and before != after:
        return 'sql_change_needs_replay', 'B/C', 'needs_review', 'SQL发生变化；需要原执行器配对回放证明退化'
    return 'answer_needs_review', 'A/B/C', 'needs_review', '按候选、选择、参数和结果逐层补证据'


def analyze(path, out):
    run = load_run(path)
    result = summarize(run)
    result.update(source=str(path), source_sha256=run['sha256'], dataset_sha256=run['dataset_sha256'],
                  source_sha256_modules=run['source_sha256'])
    failures, templates = [], defaultdict(lambda: {'selected': 0, 'answered': 0, 'score': 0, 'timed': 0})
    for row in run['records']:
        matching = row['diagnostics'].get('matching') or {}
        selected = matching.get('selected_template') or row['matched_runbook']
        if selected:
            item = templates[selected]
            item['selected'] += 1
            item['answered'] += row['matched_runbook'] is not None
            item['score'] += row['score']
            item['timed'] += row['penalty'] > 0
        if row['score'] < 5:
            category, owner, strength, explanation = classify(row)
            failures.append({**row, 'category': category, 'owner': owner, 'evidence_strength': strength,
                             'review_note': explanation, 'matching_reason': matching.get('reason'),
                             'sql_before': matching.get('sql_before_refine'),
                             'sql_after': matching.get('sql_after_refine')})
    result['failure_categories'] = dict(Counter(x['category'] for x in failures))
    result['templates'] = dict(templates)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    save(out / 'summary.json', result)
    csv_save(out / 'failure_queue.csv', failures,
             ['case_id', 'question', 'score', 'untimed_score', 'elapsed', 'category', 'owner',
              'evidence_strength', 'matching_reason', 'review_note', 'reason', 'matched_runbook',
              'api_call', 'sql_before', 'sql_after', 'sql'])
    csv_save(out / 'cases.csv', run['records'],
             ['case_id', 'score', 'untimed_score', 'elapsed', 'outcome', 'penalty', 'reason', 'matched_runbook'])
    lines = ['# C 开发评估验收报告', '', f'来源：{path}', f'原始证据 SHA-256：{run["sha256"]}', '',
             f'状态：{run["status"]}；完整性问题：{run["issues"] or "无"}',
             f'完成 {len(run["records"])}/{run["planned"]}；原分 {result["score"]}/{result["max_score_completed"]}；无时延诊断分 {result["untimed_score"]}',
             f'答案原因分类：{result["answer_reason_counts"]}',
             f'超时罚分 {result["time_penalty_points"]}；答对但超时 {result["correct_but_timed"]}',
             f'P50/P95：{result["p50_seconds"]}/{result["p95_seconds"]}秒',
             f'请求 {result["requests"]}；输入/输出token {result["prompt_tokens"]}/{result["completion_tokens"]}',
             '', '失败队列包含证据强度；触发阶段不等于已经证明根因。模板选中次数也不等于模板价值。',
             '完整结果与控制题见 cases.csv，失分交接见 failure_queue.csv。',
             '这是已有原始日志的离线复核，没有重新调用模型，不是官方总分。']
    (out / 'REPORT.md').write_bytes(('\n\n'.join(lines) + '\n').encode('utf-8'))
    return result


def compare(before, after, subset=False, descriptive=False):
    a, b = load_run(before), load_run(after)
    if a['issues'] or b['issues']:
        raise ValueError('未完成或完整性有问题的运行不进入版本验收比较')
    left = {(r['case_id'], r['repeat']): r for r in a['records']}
    right = {(r['case_id'], r['repeat']): r for r in b['records']}
    if subset:
        if not right or not set(right) <= set(left):
            raise ValueError('候选子集必须完整包含于基线，不能静默取交集')
        keys = list(right)
    else:
        if set(left) != set(right):
            raise ValueError('题集不同；仅在明确的开发子集对照中使用 --subset')
        keys = list(left)
    incompatible, missing = [], []
    for key in ('dataset_sha256', 'scorer_sha256'):
        if not a.get(key) or not b.get(key):
            missing.append(key)
        elif a[key] != b[key]:
            incompatible.append(key)
    for key in ('model', 'base_url', 'max_output_tokens', 'sdk_max_retries', 'thinking', 'temperature'):
        x, y = a['config'].get(key), b['config'].get(key)
        if x is None or y is None:
            missing.append(key)
        elif x != y:
            incompatible.append(key)
    if (incompatible or missing) and not descriptive:
        raise ValueError(f'实验合同不一致或缺失：different={incompatible}, unknown={missing}；需要 --descriptive 才能仅展示差值')
    rows = []
    for key in keys:
        x, y = left[key], right[key]
        rows.append({'case_id': key[0], 'repeat': key[1], 'before_score': x['score'],
                     'after_score': y['score'], 'score_delta': round(y['score'] - x['score'], 3),
                     'untimed_delta': round(y['untimed_score'] - x['untimed_score'], 3),
                     'before_seconds': x['elapsed'], 'after_seconds': y['elapsed'],
                     'before_template': x['matched_runbook'], 'after_template': y['matched_runbook'],
                     'control_score_regressed': x['untimed_score'] == 5 and y['score'] < x['score'],
                     'control_regressed': x['untimed_score'] == 5 and y['untimed_score'] < 5})
    order_changed = list(left) != list(right)
    return {'kind': 'development_subset_comparison' if subset else 'paired_development_comparison',
            'before': str(before), 'after': str(after), 'before_sha256': a['sha256'], 'after_sha256': b['sha256'],
            'cases': rows, 'count': len(rows), 'score_delta': round(sum(r['score_delta'] for r in rows), 3),
            'untimed_delta': round(sum(r['untimed_delta'] for r in rows), 3),
            'improved': sum(r['score_delta'] > 0 for r in rows),
            'regressed': sum(r['score_delta'] < 0 for r in rows),
            'control_regressions': [r['case_id'] for r in rows if r['control_score_regressed']],
            'answer_control_regressions': [r['case_id'] for r in rows if r['control_regressed']],
            'different_config': incompatible, 'unknown_config': missing,
            'order_or_scope_changed': order_changed,
            'cache_policy_equal': a['config'].get('cache_policy') == b['config'].get('cache_policy'),
            'causal_speedup_claim': False, 'official_improvement_claim': False,
            'decision': '仅作为开发证据；检查控制题与泛化，再完成固定回归，不由单轮子集自动验收'}


def build(out, groups_path=None):
    out = Path(out)
    groups_path = Path(groups_path or ROOT / 'experiments/round3/groups.json')
    cases = read(WHITE)['cases']
    by_id = {c['case_id']: c for c in cases}
    grouping = read(groups_path)
    tags = {c['case_id']: c for c in grouping['cases']}
    if len(by_id) != len(cases) or set(tags) != set(by_id):
        raise ValueError('分组没有完整且唯一地覆盖原白盒题目')
    frozen_manifest = read(ROOT / 'experiments/round3/manifest.json')
    if frozen_manifest['input_sha256'].get(WHITE.name) != sha(WHITE):
        raise ValueError('原用例已变化，不能继续使用旧分组和泛化参考答案')
    if any(tags[cid]['question'] != by_id[cid]['question'] for cid in by_id):
        raise ValueError('分组的问题文本与原文件不一致')
    declared = [cid for g in grouping['groups'] for cid in g['case_ids']]
    if len(declared) != len(set(declared)) or set(declared) != set(by_id):
        raise ValueError('组成员重复、遗漏或未知')
    texts = defaultdict(set)
    for case in cases:
        texts[re.sub(r'\s+', '', case['question']).lower()].add(tags[case['case_id']]['group_id'])
    if any(len(v) > 1 for v in texts.values()):
        raise ValueError('相同问题跨组，拒绝冻结')
    for group in grouping['groups']:
        if any(tags[cid]['group_id'] != group['group_id'] or tags[cid]['split'] != group['split']
               for cid in group['case_ids']):
            raise ValueError('组与题目标签不一致')
    development = [c['case_id'] for c in cases if tags[c['case_id']]['split'] == 'development']
    regression = [c['case_id'] for c in cases if tags[c['case_id']]['split'] == 'regression']
    ordered = sorted(development, key=lambda cid: hashlib.sha256(('20261029:' + cid).encode()).hexdigest())
    smoke, covered = [], set()
    while ordered and len(smoke) < 20:
        def features(cid):
            tag = tags[cid]
            return {*(('resource', r) for r in tag['resources']), ('operation', tag['operation']), ('steps', tag['api_steps'])}
        chosen = max(ordered, key=lambda cid: len(features(cid) - covered))
        ordered.remove(chosen)
        smoke.append(chosen)
        covered |= features(chosen)
    profiles = {'representative20': (smoke, 1), 'development': (development, 1),
                'regression': (regression, 2), 'whitebox_full': (list(by_id), 2)}
    for name, (ids, repeats) in profiles.items():
        save(out / (name + '.json'), {'profile': name, 'case_ids': ids, 'repeats': repeats,
             'dataset_sha256': sha(WHITE), 'groups_sha256': sha(groups_path),
             'model_execution_authorized': False, 'seed': 20261029,
             'note': '执行预算需另行确认；分组不证明真正未见泛化'})
    controls_path = ROOT / 'experiments/round3/controls.json'
    reference_path = ROOT / 'experiments/round3/reference_checks.json'
    controls, reference = read(controls_path), read(reference_path)
    derived = []
    for index, item in enumerate(controls['paraphrases']):
        case = copy.deepcopy(by_id[item['source']])
        case.update(case_id=f'paraphrase_{index+1:02d}', question=item['question'],
                    parent_case_id=item['source'], group_id=tags[item['source']]['group_id'],
                    split=tags[item['source']]['split'], variant='reviewed_paraphrase', review=item['review'])
        derived.append(case)
    for item in reference['entity_derived']:
        if item.get('status') != 'generated' or item.get('old_answer_reused') is not False:
            raise ValueError('实体派生缺少重新执行参考查询的证明')
        case = copy.deepcopy(item['case'])
        case.update(parent_case_id=item['source'], group_id=tags[item['source']]['group_id'],
                    split=tags[item['source']]['split'], variant='reference_recomputed_entity', review=item['review'])
        derived.append(case)
    save(out / 'generalization.json', {'kind': 'derived_controls_not_official_blackbox', 'cases': derived,
         'dataset_sha256': sha(WHITE), 'controls_sha256': sha(controls_path), 'reference_sha256': sha(reference_path),
         'warning': '尚未运行派生问题真实模型；改写语义复用既有人工复核，实体答案复用已重算证据'})
    save(out / 'rejection_controls.json', {'kind': 'out_of_library_rejection_diagnostic',
         'cases': controls['out_of_library'], 'score_policy': '单独统计拒答，不虚构每题+5的官方答案'})
    result = {'dataset_sha256': sha(WHITE), 'source_groups_sha256': sha(groups_path),
              'white_cases': len(cases), 'groups': len(grouping['groups']),
              'development': len(development), 'regression': len(regression),
              'representative': len(smoke), 'generalization_cases': len(derived),
              'rejection_controls': len(controls['out_of_library']), 'model_requests': 0,
              'warning': grouping['warning'], 'profiles': {n: {'cases': len(v[0]), 'repeats': v[1]} for n, v in profiles.items()}}
    save(out / 'manifest.json', result)
    return result


def depth(value):
    if isinstance(value, dict):
        return 1 + max((depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((depth(v) for v in value), default=0)
    return 0


def audit(implementation, baseline='d79c316', out=None):
    implementation = Path(implementation).resolve()
    tree = ast.parse((implementation / 'runbook_items.py').read_text(encoding='utf-8'))
    items = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'RUNBOOK_ITEMS' for t in n.targets)))
    sizes = [len(json.dumps(x, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) for x in items]
    depths = [depth(x) for x in items]
    listing = subprocess.check_output(['git', 'ls-tree', '-rz', baseline], cwd=ROOT).decode('utf-8')
    differences, checked = [], 0
    for line in listing.split('\0'):
        if not line:
            continue
        header, filename = line.split('\t', 1)
        if filename in ('implementation/evaluator.py', 'implementation/runbook_executor.py', WHITE.name) or filename.startswith('output-server/'):
            current = ROOT / filename
            checked += 1
            if not current.is_file():
                differences.append({'path': filename, 'reason': 'missing'})
            else:
                data = current.read_bytes()
                actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                if actual != header.split()[2]:
                    differences.append({'path': filename, 'reason': 'changed'})
        if filename in ('implementation/evaluator.py', 'implementation/runbook_executor.py') and implementation != (ROOT/'implementation').resolve():
            current = implementation / Path(filename).name
            checked += 1
            data = current.read_bytes() if current.is_file() else None
            if data is None or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() != header.split()[2]:
                differences.append({'path': str(current), 'reason': 'selected_implementation_protected_file_changed'})
    name = '_c_audit_retriever'
    spec = importlib.util.spec_from_file_location(name, implementation / 'runbook_retriever.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    start = time.perf_counter()
    retriever = module.RunbookRetriever(items)
    build_seconds = time.perf_counter() - start
    times = []
    for case in read(WHITE)['cases']:
        start = time.perf_counter()
        retriever.retrieve(case['question'])
        times.append((time.perf_counter() - start) * 1000)
    result = {'implementation': str(implementation), 'baseline': baseline,
              'repo_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
              'source_sha256': {name: sha(implementation/name) for name in
                               ('runbook_items.py', 'runbook_retriever.py', 'evaluator.py', 'runbook_executor.py')},
              'platform': platform.platform(), 'python': platform.python_version(),
              'protected_files_checked': checked, 'protected_differences': differences,
              'templates': len(items), 'unique_template_ids': len({x['id'] for x in items}),
              'template_quantity_component': 150-len(items), 'max_template_bytes': max(sizes, default=0),
              'over_4096_bytes': [items[i]['id'] for i, n in enumerate(sizes) if n > 4096],
              'depth_algorithm': 'dict/list containers count one, per item starts at one; submission array excluded',
              'max_container_depth': max(depths, default=0),
              'over_depth4_count': sum(n > 4 for n in depths),
              'depth_status': 'needs_official_counting_definition', 'index_seconds': build_seconds,
              'retrieval_p50_ms': percentile(times, .5), 'retrieval_p95_ms': percentile(times, .95),
              'retrieval_max_ms': max(times), 'model_requests': 0,
              'resource_scope': 'only index/retrieval measured here; model CPU and combined service memory not measured',
              'retrieval_limits_met_on_this_machine': build_seconds <= 60 and max(times) <= 200}
    if out:
        save(out, result)
    return result


def aggregate(white_paths, black_paths, template_count):
    if len(white_paths) != 2 or len(black_paths) != 2:
        raise ValueError('公式参考值要求白盒/黑盒各两份独立完整单轮；不重复使用同一份证据')
    all_paths = [*white_paths, *black_paths]
    if len({Path(p).resolve() for p in all_paths}) != 4:
        raise ValueError('不能将同一报告重复当作两轮')
    if len({sha(p) for p in all_paths}) != 4:
        raise ValueError('同一份证据改名后不能充当独立运行')
    whites, blacks = [load_run(p) for p in white_paths], [load_run(p) for p in black_paths]
    for runs, size in ((whites, 200), (blacks, 100)):
        for run in runs:
            if run['issues'] or len(run['records']) != size:
                raise ValueError('题数不全或记录不完整，不能计算正式公式参考值')
            if run['meta'].get('template_count') != template_count:
                raise ValueError('模板数量合同不一致')
        compare(runs[0]['path'], runs[1]['path'])
    ids = lambda run: {r['case_id'] for r in run['records']}
    if ids(whites[0]) & ids(blacks[0]) or whites[0]['dataset_sha256'] == blacks[0]['dataset_sha256']:
        raise ValueError('白盒与黑盒不能是相同或重叠的测试记录')
    if whites[0]['config'] != blacks[0]['config'] or whites[0]['scorer_sha256'] != blacks[0]['scorer_sha256']:
        raise ValueError('黑白模型/评分/缓存合同不一致')
    white_score = sum(sum(r['score'] for r in run['records']) for run in whites) / 2
    black_score = sum(sum(r['score'] for r in run['records']) for run in blacks) / 2
    return {'kind': 'formula_reference_only', 'white_mean_score': white_score, 'black_mean_score': black_score,
            'template_component': 150-template_count,
            'formula_reference': round(.3*white_score+.7*black_score+150-template_count, 4),
            'official_score_claim': False, 'note': '统一模型和正式评测合同仍须主办确认'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='C 离线实验与验收；所有子命令均不调用模型')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build'); p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('analyze'); p.add_argument('report', type=Path); p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('compare'); p.add_argument('baseline', type=Path); p.add_argument('candidate', type=Path)
    p.add_argument('--subset', action='store_true'); p.add_argument('--descriptive', action='store_true'); p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('audit'); p.add_argument('--implementation-dir', type=Path, default=ROOT/'implementation')
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('aggregate'); p.add_argument('--white', type=Path, nargs='+', required=True)
    p.add_argument('--black', type=Path, nargs='+', required=True); p.add_argument('--templates', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            result = build(args.out)
        elif args.command == 'analyze':
            result = analyze(args.report, args.out)
        elif args.command == 'compare':
            result = compare(args.baseline, args.candidate, args.subset, args.descriptive)
            save(args.out, result)
        elif args.command == 'audit':
            result = audit(args.implementation_dir, out=args.out)
        else:
            if args.templates < 0:
                raise ValueError('模板数量不能为负数')
            result = aggregate(args.white, args.black, args.templates)
            save(args.out, result)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
