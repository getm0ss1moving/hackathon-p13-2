"""冻结本轮问题分组，复现内存检索消融并通过原执行器复核；模型请求为零。"""
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import resource
import socket
import subprocess
import sys
import time
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'implementation'))
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import RunbookRetriever, _Doc, tokenize
from run_model_baseline import start_service


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def exec_key(item):
    return canonical({k: item.get(k) for k in ['api_call', 'sql', 'default_params']})


def sql_shape(sql):
    sql = re.sub(r"'(?:''|[^'])*'", "'<literal>'", sql)
    sql = re.sub(r'\b\d+(?:\.\d+)?\b', '<number>', sql)
    return re.sub(r'\s+', ' ', sql).strip().lower()


def api_shape(obj):
    if isinstance(obj, list):
        return [api_shape(step) for step in obj]
    constraints = obj.get('condition', {}).get('constraint', [])
    return {'method': obj.get('method', 'GET'), 'url': obj['url'].split('?')[0],
            'conditions': [{'name': c.get('simple', {}).get('name'),
                            'operator': c.get('simple', {}).get('operator', 'equal'),
                            'logOp': c.get('logOp', 'and'),
                            'dependency': c.get('simple', {}).get('value')
                            if 'from step' in str(c.get('simple', {}).get('value')) else '<value>'}
                           for c in constraints]}


def features(case):
    steps = case['api_call'] if isinstance(case['api_call'], list) else [case['api_call']]
    operation = ('group' if re.search(r'\bGROUP\s+BY\b', case['sql'], re.I) else
                 'aggregate' if re.search(r'\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(', case['sql'], re.I) else
                 'detail' if any(c.get('simple', {}).get('name') in {'name', 'id', 'nativeId'}
                                 for step in steps for c in step.get('condition', {}).get('constraint', []))
                 else 'list')
    return {'resources': sorted({step['url'].split('/')[-1].split('?')[0] for step in steps}),
            'operation': operation, 'api_steps': len(steps),
            'sql_statements': len([s for s in case['sql'].split(';') if s.strip()])}


def freeze_groups(cases, seed):
    parent = list(range(len(cases)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        parent[find(b)] = find(a)
    feats = [features(c) for c in cases]
    shapes = [canonical([api_shape(c['api_call']), sql_shape(c['sql'])]) for c in cases]
    # 分组时把有/无筛选视为同能力族，避免仅换条件的同构查询跨组；检索输入仍保留原条件。
    families = [canonical([[{'method': a.get('method', 'GET'), 'url': a['url'].split('?')[0]}
                            for a in (c['api_call'] if isinstance(c['api_call'], list) else [c['api_call']])],
                           sql_shape(c['sql'])]) for c in cases]
    tokens = [set(tokenize(re.sub(r'[A-Za-z0-9][A-Za-z0-9_.@#-]*', 'ENTITY', c['question']))) for c in cases]
    edges = []
    for i in range(len(cases)):
        for j in range(i):
            similarity = len(tokens[i] & tokens[j]) / max(len(tokens[i] | tokens[j]), 1)
            reason = ('same_query_family_ignoring_filter_values_and_presence' if families[i] == families[j] else
                      'same_text' if cases[i]['question'] == cases[j]['question'] else
                      'near_text_same_stratum' if feats[i] == feats[j] and similarity >= 0.80 else None)
            if reason:
                union(i, j)
                edges.append([cases[j]['case_id'], cases[i]['case_id'], reason])
    members = defaultdict(list)
    for i, case in enumerate(cases):
        members[find(i)].append(case['case_id'])
    split = {}
    groups = []
    for ids in sorted(members.values()):
        group_id = 'group_' + sha(canonical(ids).encode())[:12]
        role = 'regression' if int(sha(f'{seed}:{group_id}'.encode()), 16) % 5 == 0 else 'development'
        groups.append({'group_id': group_id, 'split': role, 'case_ids': ids})
        for case_id in ids:
            split[case_id] = (group_id, role)
    rows = [{'case_id': c['case_id'], 'question': c['question'], **features(c),
             'group_id': split[c['case_id']][0], 'split': split[c['case_id']][1],
             'reference_shape_sha256': sha(shapes[i].encode())} for i, c in enumerate(cases)]
    assert all(split[a] == split[b] for a, b, _ in edges)
    return {'seed': seed, 'method': 'API path/method sequence + literal-masked SQL (ignoring API filter presence/values for grouping) OR exact text OR token Jaccard>=0.80 within identical stratum; connected components; sha(seed:group)%5',
            'warning': 'heuristic grouping is frozen for leakage control, not proof of unseen generalization; all original questions occur in examples',
            'groups': groups, 'edges': edges, 'cases': rows}


class ExperimentRetriever(RunbookRetriever):
    """只替换送入原 BM25 的文本/词；排名、门禁和上限沿用原实现。"""
    def __init__(self, items, factor, heldout):
        self.factor, self.heldout = factor, heldout
        super().__init__(items)

    def _build_docs(self, items):
        docs = []
        for item in items:
            for field in ['examples', 'description']:
                if self.factor == 'without_' + field:
                    continue
                texts = item.get(field, []) if field == 'examples' else [item.get(field, '')]
                for text in texts:
                    if not text or self.factor == 'regression_text_holdout' and text in self.heldout:
                        continue
                    blocked = set()
                    if self.factor in {'index_count', 'both_count', field + '_count'}:
                        blocked = {'数量', '总数', '多少'}
                    elif self.factor == 'index_resource_alias':
                        blocked = {'ecs', '虚拟', '拟机'}
                    elif self.factor == 'index_status':
                        blocked = {'按状', '状态', '分布'}
                    docs.append(_Doc(item['id'], [t for t in tokenize(text) if t not in blocked]))
        return docs

    def retrieve(self, query, top_k=None):
        tokens = set(tokenize(query))
        if self.factor in {'query_count', 'both_count'}:
            tokens -= {'数量', '总数', '多少'}
        content, denominator = self._coverage_base(tokens)
        ranked = self._aggregate_items(tokens, content, denominator)
        results = self._assemble_results(ranked)
        return results[:top_k] if top_k is not None else results


def original_labels(case):
    ids = {item['id'] for item in RUNBOOK_ITEMS if case['question'] in item.get('examples', [])}
    signatures = {exec_key(t) for t in RUNBOOK_ITEMS if t['id'] in ids}
    return sorted({t['id'] for t in RUNBOOK_ITEMS if exec_key(t) in signatures})


def main():
    assert Path.cwd().resolve() == ROOT, '必须从指定仓库根目录运行'
    cases = json.loads((ROOT / 'CMDB用例集-白盒200.json').read_text())['cases']
    by_id = {c['case_id']: c for c in cases}
    controls = json.loads((OUT / 'controls.json').read_text())
    groups = freeze_groups(cases, controls['seed'])
    save('groups.json', groups)
    splits = {c['case_id']: c['split'] for c in groups['cases']}
    group_ids = {c['case_id']: c['group_id'] for c in groups['cases']}
    suite = [{'id': c['case_id'], 'source': c['case_id'], 'question': c['question'],
              'kind': 'original_linkage', 'accepted_ids': original_labels(c), 'review': 'example linkage plus exact execution duplicates; incomplete capability labels'} for c in cases]
    suite += [{'id': 'paraphrase_' + c['source'], 'kind': 'paraphrase_linkage',
               'accepted_ids': original_labels(by_id[c['source']]), **c} for c in controls['paraphrases']]
    for fragment in controls['fragments']:
        accepted = [t['id'] for t in RUNBOOK_ITEMS
                    if (fragment['resources'] is None or sorted(t['resources']) == sorted(fragment['resources']))
                    and re.search(fragment['sql_pattern'], t['sql'], re.I)]
        assert len(accepted) > 1, fragment['id']
        suite.append({**fragment, 'kind': 'fragment_family', 'accepted_ids': accepted})
    suite += [{**c, 'kind': 'negative_candidate_proxy', 'accepted_ids': []} for c in controls['out_of_library']]
    for row in suite:
        row['group_id'] = group_ids.get(row.get('source'), row['id'])
        row['split'] = splits.get(row.get('source'), 'diagnostic_control')
    manifest = {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=ROOT).strip(),
                'cwd': str(ROOT), 'python': platform.python_version(), 'platform': platform.platform(),
                'seed': controls['seed'], 'template_count': len(RUNBOOK_ITEMS),
                'template_execution_sha256': sha(canonical([exec_key(t) for t in RUNBOOK_ITEMS]).encode()),
                'whitebox_cases': len(cases), 'unique_questions': len({c['question'] for c in cases}),
                'sha256': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted([*(ROOT / 'implementation').glob('*.py'), *(ROOT / 'output-server').glob('*.py')])},
                'input_sha256': {p.name: sha(p.read_bytes()) for p in [ROOT / 'CMDB用例集-白盒200.json', OUT / 'controls.json', Path(__file__)]},
                'data_sha256': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted((ROOT / 'output-server').rglob('*.json'))},
                'model_http_requests': 0, 'score': 'retrieval diagnostics only; original executor checks reported separately',
                'grouping': groups['method'], 'acceptance': ['source hashes stable', 'baseline candidates exactly match original retriever',
                  'all connected cases and their paraphrases stay in one split', 'API/SQL/template count unchanged for lexical factors',
                  'fragments have set-valued capability labels', 'entity-derived expected results recomputed by original executor',
                  'no inference of final accuracy or deletion benefit from linkage hit rate']}
    if (OUT / 'model20.json').exists():
        manifest['input_sha256']['model20.json'] = sha((OUT / 'model20.json').read_bytes())
    save('manifest.json', manifest)
    # 阻断外部连接：仅允许原数据服务的本机端口，不导入匹配器或密钥。
    original_connect = socket.socket.connect
    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] != '127.0.0.1' or address[1] != 8080:
            raise RuntimeError('离线实验阻断外部网络')
        return original_connect(sock, address)
    socket.socket.connect = connect
    factors = ['baseline', 'index_count', 'query_count', 'both_count', 'description_count', 'examples_count',
               'index_resource_alias', 'index_status', 'without_description', 'without_examples', 'regression_text_holdout']
    heldout = {c['question'] for c in cases if splits[c['case_id']] == 'regression'}
    summaries, output_rows = {}, []
    production = RunbookRetriever(RUNBOOK_ITEMS)
    for factor in factors:
        items = copy.deepcopy(RUNBOOK_ITEMS)
        if factor == 'regression_text_holdout':
            for item in items:
                item.pop('default_params', None)  # 不影响检索，但消除后续能力实验的实体默认值先验
        start = time.perf_counter()
        retriever = ExperimentRetriever(items, factor, heldout)
        index_ms = (time.perf_counter() - start) * 1000
        assert canonical([(t['api_call'], t['sql']) for t in items]) == canonical([(t['api_call'], t['sql']) for t in RUNBOOK_ITEMS])
        per_kind = defaultdict(list)
        for query in suite:
            start = time.perf_counter()
            candidates = retriever.retrieve(query['question'])
            elapsed = (time.perf_counter() - start) * 1000
            if factor == 'baseline':
                assert candidates == production.retrieve(query['question'])
            accepted = set(query['accepted_ids'])
            ranks = [i + 1 for i, c in enumerate(candidates) if c.id in accepted]
            good = [c.score for c in candidates if c.id in accepted]
            other = [c.score for c in candidates if c.id not in accepted]
            row = {'factor': factor, 'query_id': query['id'], 'kind': query['kind'], 'split': query['split'],
                   'candidate_count': len(candidates), 'first_accepted_rank': min(ranks) if ranks else None,
                   'top1_in_label_set': bool(candidates and candidates[0].id in accepted),
                   'recall_label_at_3': any(rank <= 3 for rank in ranks), 'recall_label_at_5': any(rank <= 5 for rank in ranks),
                   'label_set_retrieved': bool(ranks), 'outside_label_count': len(candidates) - len(ranks),
                   'top2_score_gap': candidates[0].score - candidates[1].score if len(candidates) > 1 else None,
                   'accepted_vs_other_score_gap': max(good) - max(other) if good and other else None,
                   'retrieve_ms': elapsed,
                   'candidate_ids_scores': canonical([[c.id, c.score, c.tier, c.coverage] for c in candidates])}
            output_rows.append(row)
            per_kind[(query['kind'], query['split'])].append(row)
        summaries[factor] = {'index_ms': index_ms, 'index_docs': len(retriever._docs), 'subsets': {}}
        for (kind, split), rows in per_kind.items():
            latencies = sorted(r['retrieve_ms'] for r in rows)
            summaries[factor]['subsets'][kind + ':' + split] = {'n': len(rows),
                'label_recalled': sum(r['label_set_retrieved'] for r in rows),
                'top1_in_label_set': sum(r['top1_in_label_set'] for r in rows),
                'recall_at_3': sum(r['recall_label_at_3'] for r in rows), 'recall_at_5': sum(r['recall_label_at_5'] for r in rows),
                'candidate_nonempty': sum(r['candidate_count'] > 0 for r in rows),
                'retrieve_p95_ms': latencies[math.ceil(.95 * len(rows)) - 1], 'retrieve_max_ms': max(latencies)}
    with (OUT / 'retrieval.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    save('queries.json', suite)
    save('retrieval_summary.json', summaries)
    # 原参考查询与固定模板能力分开：不替换模板 SQL，不走模型选择/填参。
    import runbook_executor as executor
    from evaluator import evaluate_case
    proc = None
    checks, derived = [], []
    try:
        proc = start_service()
        capability_controls = list(controls['paraphrases'])
        model_path = OUT / 'model20.json'
        if model_path.exists():
            paid = json.loads(model_path.read_text())
            known = {c['source'] for c in capability_controls}
            capability_controls += [{'source': row['case_id']} for row in paid['cases']
                                    if row['evaluation']['score'] < 5 and row['case_id'] not in known]
        for control in capability_controls:
            case = by_id[control['source']]
            executor._cache.clear()
            started = time.perf_counter()
            reference = executor.execute({'api_call': copy.deepcopy(case['api_call']), 'sql': case['sql']})
            elapsed = time.perf_counter() - started
            reference['matched_runbook'] = 'offline_reference'
            reference['api_call'] = case['api_call']
            result = evaluate_case(case, reference, 0.0)
            labels = original_labels(case)
            item = copy.deepcopy(next(t for t in RUNBOOK_ITEMS if t['id'] == labels[0]))
            values = item.get('default_params', {})
            text = canonical({'api_call': item['api_call'], 'sql': item['sql']})
            for key, value in values.items():
                # JSON 级替换只用于现有默认字符串；不把参考 SQL 注入模板。
                text = text.replace('{{' + key + '}}', str(value))
            fixed = json.loads(text)
            fixed_result = executor.execute(fixed)
            fixed_result.update(matched_runbook=item['name'], api_call=fixed['api_call'])
            fixed_score = evaluate_case(case, fixed_result, 0.0)
            checks.append({'case_id': case['case_id'], 'reference_evaluation_at_elapsed0': result,
                           'reference_elapsed_s_cold_executor_cache': elapsed,
                           'reference_result_sha256': sha(canonical(reference['result']).encode()),
                           'fixed_template_id': item['id'], 'fixed_default_params': values,
                           'fixed_template_evaluation_at_elapsed0': fixed_score,
                           'warning': 'oracle template/defaults; no model selection or parameter accuracy; elapsed0 isolates answer comparison'})
        for control in controls['entity_controls']:
            source = by_id[control['source']]
            assert isinstance(source['api_call'], dict)
            api = copy.deepcopy(source['api_call'])
            conditions = api['condition']['constraint']
            target = next(c['simple'] for c in conditions if c['simple']['name'] == control['field'])
            old = target['value']
            table = api['url'].split('/')[-1].split('?')[0]
            all_records = executor._query_server(table)
            # 固定其他条件，优先选择能产生非空结果的新实体；排序后确定性取第一个。
            others = [c['simple'] for c in conditions if c['simple'] is not target]
            choices = sorted({str(r[control['field']]) for r in all_records if r.get(control['field']) not in (None, '', old)
                              and all(str(r.get(c['name'])) == str(c['value']) for c in others)})
            if not choices:
                derived.append({**control, 'status': 'unavailable', 'reason': '同表且满足其余原条件的新实体不存在；不编造答案'})
                continue
            target['value'] = choices[0]
            question = source['question'].replace(str(old), choices[0])
            assert question != source['question']
            result = executor.execute({'api_call': api, 'sql': source['sql']})
            assert result['error'] is None
            expected = result['result']
            derived_case = {**copy.deepcopy(source), 'case_id': 'entity_' + source['case_id'], 'question': question,
                            'api_call': api, 'answer': expected}
            # 仅检查原执行器重算产物可被原评分函数消费，不宣称独立正确性。
            probe = {**result, 'api_call': api, 'matched_runbook': 'offline_reference'}
            candidates = production.retrieve(question)
            accepted = original_labels(source)
            derived.append({**control, 'baseline_retrieval': {'candidates': [vars(c) for c in candidates],
                            'accepted_ids': accepted, 'first_accepted_rank': next((i + 1 for i, c in enumerate(candidates) if c.id in accepted), None)},
                            'status': 'generated', 'old_value': old, 'new_value': choices[0],
                            'group_id': group_ids[source['case_id']], 'split': splits[source['case_id']],
                            'case': derived_case, 'self_consistency_at_elapsed0': evaluate_case(derived_case, probe, 0.0),
                            'old_answer_reused': False,
                            'old_answer_equal': canonical(source['answer']) == canonical(expected)})
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)
    sql_replays = []
    if model_path.exists():
        try:
            proc = start_service()
            for row in paid['cases']:
                if row['evaluation']['score'] >= 5 or not row['output'].get('matched_runbook'):
                    continue
                item = next(t for t in RUNBOOK_ITEMS if t['name'] == row['output']['matched_runbook'])
                if item['sql'] == row['output']['sql']:
                    continue
                request = {'api_call': row['output']['api_call'], 'sql': item['sql']}
                result = executor.execute(request)
                result.update(matched_runbook=item['name'], api_call=request['api_call'])
                sql_replays.append({'case_id': row['case_id'], 'observed_score': row['evaluation']['score'],
                                    'fixed_api_template_sql_score_at_elapsed0': evaluate_case(by_id[row['case_id']], result, 0.0),
                                    'template_sql': item['sql'], 'observed_sql': row['output']['sql'],
                                    'model_requests': 0, 'note': 'counterfactual execution with observed API and original template SQL; not a revised model score'})
        finally:
            if proc is not None:
                proc.terminate()
                proc.wait(timeout=10)
    socket.socket.connect = original_connect
    save('reference_checks.json', {'reference_and_fixed': checks, 'entity_derived': derived, 'sql_counterfactuals': sql_replays,
                                   'model_http_requests': 0, 'score_kind': 'offline capability/data check, not end-to-end score'})
    final_hashes = {p: sha((ROOT / p).read_bytes()) for p in manifest['sha256']}
    assert final_hashes == manifest['sha256']
    assert all(sha((ROOT / p).read_bytes()) == value for p, value in manifest['data_sha256'].items())
    assert sha((ROOT / 'CMDB用例集-白盒200.json').read_bytes()) == manifest['input_sha256']['CMDB用例集-白盒200.json']
    memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    summary = {'query_rows': len(suite), 'retrieval_measurements': len(output_rows),
               'groups': len(groups['groups']), 'case_split': dict(Counter(c['split'] for c in groups['cases'])),
               'strata': dict(Counter(f"{c['operation']}:{'multi' if c['api_steps'] > 1 else 'single'}" for c in groups['cases'])),
               'reference_checks': len(checks), 'reference_answer_score5': sum(c['reference_evaluation_at_elapsed0']['score'] == 5 for c in checks),
               'fixed_template_answer_score5': sum(c['fixed_template_evaluation_at_elapsed0']['score'] == 5 for c in checks),
               'entity_generated': sum(c['status'] == 'generated' for c in derived),
               'process_peak_rss_bytes': memory if sys.platform == 'darwin' else memory * 1024,
               'resource_scope': 'single offline experiment process including original executor, excludes data-server child; Mac diagnostic only',
               'source_hashes_unchanged': True, 'model_http_requests': 0}
    save('offline_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
