"""主agent认领：只合086/087的隔离199候选独立检验；不改生产，不调用模型。"""
import ast
from collections import Counter
import copy
import hashlib
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / '.a-vocab-gt4hyfg2'
STEM = Path(__file__).with_suffix('')
REPORT, RAW = STEM.with_suffix('.json'), STEM.with_suffix('.jsonl')
CANDIDATE = A / 'candidate_merge_086_items.json'
LOCKS = {'queries.json': '37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0',
         'candidate_merge_086_items.json': '7aa441b426f3d5e1ae3160cb347285b70be4240337231fc662d12ce73f2a55a8',
         'strict_capability_raw.jsonl': '69ef2a4ad0431af01e542a37b68b7c3b03f685f7aa08332c832981fc23d5c6d6',
         'strict_capability_result.json': '4bf890f58b7e1a0f8b774b40d58b14616d81b446f461c1e6fe02416075b47bce',
         'merge_086.json': '40f533958e35938331b80b1fff8022d1e5ffab02c5e81080da318bb350c821c3'}
FIXED = {'implementation/runbook_executor.py': '4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92',
         'implementation/evaluator.py': 'c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def root_items():
    return ast.literal_eval(ast.parse((ROOT / 'implementation/runbook_items.py').read_text()).body[0].value)


def protected():
    names = subprocess.check_output(['git', 'ls-tree', '-r', '-z', '--name-only', 'd79c316'], cwd=ROOT).decode().rstrip('\0').split('\0')
    names = [p for p in names if p.startswith('output-server/') or p in FIXED or p == 'CMDB用例集-白盒200.json']
    result = {p: sha((ROOT / p).read_bytes()) for p in names}
    assert len(result) == 236
    assert all(result[p] == sha(subprocess.check_output(['git', 'show', 'd79c316:' + p], cwd=ROOT)) for p in result)
    assert all(result[p] == value for p, value in FIXED.items())
    return result


def worker():
    """每次自然新进程原生导入；服务仅调用，不管理其生命周期。"""
    request = json.load(sys.stdin)
    row = {'kind': request['kind'], 'control_id': request['control_id'], 'pid': __import__('os').getpid(),
           'request': request, 'status': 'FAIL'}
    try:
        sys.path.insert(0, str(ROOT / 'implementation'))
        import runbook_executor as executor
        import evaluator
        assert executor.BASE_URL == 'http://127.0.0.1:8080'
        assert Path(executor.__file__).resolve() == ROOT / 'implementation/runbook_executor.py'
        assert Path(evaluator.__file__).resolve() == ROOT / 'implementation/evaluator.py'
        before = {p: sha((ROOT / p).read_bytes()) for p in FIXED}
        assert before == FIXED
        item = copy.deepcopy(request['input'])
        if request['kind'] == 'candidate_execution':
            item['api_call'] = executor._replace_placeholders(item['api_call'], request['verified_params'])
            assert item['api_call'] == request['expected_case']['api_call']
        row['native_execute_input'] = copy.deepcopy(item)
        start = time.perf_counter()
        output = executor.execute(item)
        elapsed = time.perf_counter() - start
        row.update(native_output=output, elapsed_s=elapsed,
                   native_modules={'executor': executor.__file__, 'evaluator': evaluator.__file__, 'base_url': executor.BASE_URL})
        assert output['error'] is None and output['result']['row_count'] > 0
        if request['kind'] == 'candidate_execution':
            system_output = dict(output, matched_runbook=item['name'], question=request['expected_case']['question'], api_call=item['api_call'])
            row['evaluator_input'] = system_output
            row['score'] = evaluator.evaluate_case(request['expected_case'], system_output, elapsed)
            assert row['score']['score'] == 5
        else:
            row['score'] = None  # 参考答案生成，不对自身生成结果宣称独立答题正确率。
        row['fixed_before'] = before
        row['fixed_after'] = {p: sha((ROOT / p).read_bytes()) for p in FIXED}
        assert row['fixed_before'] == row['fixed_after']
        row['status'] = 'PASS'
    except Exception as exc:
        row.update(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
    print(json.dumps(row, ensure_ascii=False))
    return 0 if row['status'] == 'PASS' else 1


def main():
    assert Path.cwd().resolve() == ROOT
    assert not REPORT.exists() and not RAW.exists(), '已有独立结果，拒绝覆盖'
    report = {'status': 'FAIL', 'model_requests': 0, 'production_changed': False, 'candidate_isolated': True,
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'script_sha256': sha(Path(__file__).read_bytes()), 'failures': [], 'affected_questions': [],
              'regressions': {}, 'controls': [], 'old_original_evidence_reused': []}
    raw_file = RAW.open('x')
    def emit(value):
        raw_file.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n'); raw_file.flush()
    try:
        before = protected(); report['protected_before'] = before
        source_hashes = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted((ROOT / 'implementation').glob('*.py'))}
        for name, value in LOCKS.items():
            assert sha((A / name).read_bytes()) == value, name
        report['locked_inputs'] = LOCKS
        baseline, candidate = root_items(), json.loads(CANDIDATE.read_text())
        old, new = {t['id']: t for t in baseline}, {t['id']: t for t in candidate}
        assert len(baseline) == len(old) == 200 and len(candidate) == len(new) == 199
        assert set(old) - set(new) == {'rb_087'} and not set(new) - set(old)
        assert [t['id'] for t in candidate] == [t['id'] for t in baseline if t['id'] != 'rb_087']
        assert all(old[t] == new[t] for t in new if t != 'rb_086')
        for field in ['api_call', 'sql', 'default_params']:
            assert old['rb_086'].get(field) == old['rb_087'].get(field) == new['rb_086'].get(field)
        changed_fields = [k for k in set(old['rb_086']) | set(new['rb_086']) if old['rb_086'].get(k) != new['rb_086'].get(k)]
        assert set(changed_fields) <= {'description', 'examples'}
        texts = set(new['rb_086']['examples'] + [new['rb_086']['description']])
        assert set(old['rb_086']['examples'] + old['rb_087']['examples'] + [old['rb_086']['description'], old['rb_087']['description']]) <= texts
        report['candidate_structure'] = {'baseline_n': 200, 'candidate_n': 199, 'delta_n': -1,
            'removed': ['rb_087'], 'retained_086_changed_fields': changed_fields, 'other_198_templates_equal': True,
            'order_preserved': True, 'api_sql_defaults_equal': True, 'valuable_original_text_preserved': True,
            'quantity_term_if_official_formula_applies': {'baseline': -50, 'candidate': -49, 'conditional_delta': 1},
            'official_score_delta': None}
        sys.path.insert(0, str(ROOT / 'implementation'))
        from runbook_retriever import RunbookRetriever
        a_index, b_index = RunbookRetriever(baseline), RunbookRetriever(candidate)
        # 只抽取原matcher纯文本函数/常量，避免导入其密钥配置和模型客户端。
        matcher_source = (ROOT / 'implementation/runbook_matcher.py').read_text()
        tree = ast.parse(matcher_source)
        formatter = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_format_runbook_list')
        namespace = {}; exec(compile(ast.Module(body=[formatter], type_ignores=[]), '<root-prompt-formatter>', 'exec'), namespace)
        format_items = namespace['_format_runbook_list']
        constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                     if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                     and n.targets[0].id in ['SELECT_RUNBOOK_PROMPT', 'FILL_PARAMS_PROMPT']}
        report['prompt_method'] = {'format_function_sha256': sha(ast.get_source_segment(matcher_source, formatter).encode()),
                                  'source': 'root matcher pure formatter and prompt literals only; matcher module not imported'}
        def canon_id(value):
            return 'rb_086' if value == 'rb_087' else value
        def observe(index, mapping, q):
            candidates = [vars(c) for c in index.retrieve(q['question'])]
            labels = {canon_id(x) for x in q['expected']}
            ranks = [i + 1 for i, c in enumerate(candidates) if canon_id(c['id']) in labels]
            good = [c['score'] for c in candidates if canon_id(c['id']) in labels]
            other = [c['score'] for c in candidates if canon_id(c['id']) not in labels]
            prompt = constants['SELECT_RUNBOOK_PROMPT'].format(user_question=q['question'], runbook_list=format_items([mapping[c['id']] for c in candidates]))
            return {'candidates': candidates, 'first_label_rank': min(ranks) if ranks else None,
                    'label_recalled': bool(ranks), 'top1_in_label_set': bool(candidates and canon_id(candidates[0]['id']) in labels),
                    'top1': candidates[0]['id'] if candidates else None, 'canonical_top1': canon_id(candidates[0]['id']) if candidates else None,
                    'canonical_order': [canon_id(c['id']) for c in candidates],
                    'best_label_minus_other_score': max(good) - max(other) if good and other else None,
                    'outside_label_count': len(candidates) - len(ranks),
                    'selection_prompt_sha256': sha(prompt.encode()), 'selection_prompt_utf8_bytes': len(prompt.encode())}
        queries = json.loads((A / 'queries.json').read_text()); assert len(queries) == 1075
        counts = {v: Counter() for v in sorted({q['scope'] for q in queries})}
        regression_keys = {k: [] for k in ['lost_label_recall', 'top1_label_lost', 'label_rank_worsened', 'score_margin_decreased', 'outside_label_count_increased']}
        changes = Counter()
        for q in queries:
            a, b = observe(a_index, old, q), observe(b_index, new, q)
            row = {'event': 'retrieval_pair', 'input': q, 'equivalent_labels': sorted({canon_id(x) for x in q['expected']}), 'baseline': a, 'candidate': b}
            flags = {'lost_label_recall': a['label_recalled'] and not b['label_recalled'],
                     'top1_label_lost': a['top1_in_label_set'] and not b['top1_in_label_set'],
                     'label_rank_worsened': a['first_label_rank'] is not None and b['first_label_rank'] is not None and b['first_label_rank'] > a['first_label_rank'],
                     'score_margin_decreased': a['best_label_minus_other_score'] is not None and b['best_label_minus_other_score'] is not None and b['best_label_minus_other_score'] < a['best_label_minus_other_score'] - 1e-9,
                     'outside_label_count_increased': b['outside_label_count'] > a['outside_label_count']}
            row['diagnostic_regression_flags'] = flags
            row['changes'] = {'raw_candidates': a['candidates'] != b['candidates'], 'canonical_order': a['canonical_order'] != b['canonical_order'],
                              'raw_top1': a['top1'] != b['top1'], 'canonical_top1': a['canonical_top1'] != b['canonical_top1'],
                              'selection_prompt': a['selection_prompt_sha256'] != b['selection_prompt_sha256']}
            emit(row)
            for k, flag in flags.items():
                if flag: regression_keys[k].append(q['key'])
            for k, flag in row['changes'].items(): changes[k] += int(flag)
            for label, value in [('baseline_recall', a['label_recalled']), ('candidate_recall', b['label_recalled']),
                                 ('baseline_top1', a['top1_in_label_set']), ('candidate_top1', b['top1_in_label_set'])]: counts[q['scope']][label] += int(value)
            counts[q['scope']]['n'] += 1
            if any(row['changes'].values()) or any(flags.values()):
                report['affected_questions'].append({'key': q['key'], 'question': q['question'], 'scope': q['scope'],
                    'first_rank_before_after': [a['first_label_rank'], b['first_label_rank']],
                    'top1_before_after': [a['top1'], b['top1']], 'margin_before_after': [a['best_label_minus_other_score'], b['best_label_minus_other_score']],
                    'changes': row['changes'], 'diagnostic_regression_flags': flags})
        report['retrieval_summary'] = {k: dict(v) for k, v in counts.items()}
        report['changes'] = dict(changes); report['regressions'] = regression_keys
        report['label_limit'] = '087->086 equivalence only in offline labels; label sets incomplete; non-label candidates/margin changes are risks, not proved answer errors; BM25 scores are not probabilities'
        # 参数契约完全相同；填参prompt独立比较，不把选择prompt变化误称执行语义变化。
        fill_context = lambda t: constants['FILL_PARAMS_PROMPT'].format(examples='\n'.join('- '+x for x in t['examples']), placeholder_list='1. {{logicalRegionName}}', user_question='<same question>')
        report['parameter_and_fill_prompt'] = {'placeholder_names': ['logicalRegionName'], 'contract_equal': True,
            '086_fill_context_changed': fill_context(old['rb_086']) != fill_context(new['rb_086']),
            '087_to_086_fill_context_changed': fill_context(old['rb_087']) != fill_context(new['rb_086']),
            'selected_template_name_087_removed': True, 'selection_prompt_changed_queries': changes['selection_prompt']}
        strict_rows = [json.loads(s)['record'] for s in (A / 'strict_capability_raw.jsonl').read_text().splitlines() if json.loads(s)['event'] == 'worker']
        for template in ['rb_086', 'rb_087']:
            pair = [r for r in strict_rows if r['template'] == template]
            assert len(pair) == 2 and pair[0]['native_output'] == pair[1]['native_output']
            assert all(r['input']['native_execute_input']['api_call'] == r['input']['standard_case']['api_call'] for r in pair)
            assert all(r['input']['native_execute_input']['sql'] == new['rb_086']['sql'] for r in pair)
            assert all(r['input']['selected_template']['api_call'] == new['rb_086']['api_call'] and r['input']['selected_template']['default_params'] == new['rb_086']['default_params'] for r in pair)
            report['old_original_evidence_reused'].append({'template': template, 'case_id': pair[0]['score']['case_id'], 'both_scores': [r['score'] for r in pair],
                'raw_sha256': LOCKS['strict_capability_raw.jsonl'], 'new_execution': False,
                'reuse_scope': 'API/SQL/default contract and fixed parameter execution only; no selector, no new score attribution'})
        # 读取真实数据只确定合法替换值；新答案仍必须从原参考API+SQL重新执行生成。
        values = Counter()
        for path in sorted((ROOT / 'output-server').rglob('VOLUME-*.json')):
            data = json.loads(path.read_text()); rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
            values.update(str(row['logicalRegionName']) for row in rows if row.get('logicalRegionName'))
        old_value = old['rb_086']['default_params']['logicalRegionName']
        replacement = next(v for v in sorted(values) if v != old_value)
        report['actual_region_values'] = dict(values)
        connection = http.client.HTTPConnection('127.0.0.1', 8080, timeout=3)
        try:
            connection.request('GET', '/rest/hackthon/db/schema/VOLUME')
            response = connection.getresponse(); schema = json.loads(response.read())
            assert response.status == 200 and schema['ci_name'] == 'VOLUME' and schema['row_count'] > 0
            emit({'event': 'shared_service_preflight', 'status': response.status, 'schema': schema, 'lifecycle': 'coordinator-owned; only call, never start/stop'})
        finally: connection.close()
        all_cases = {c['case_id']: c for c in json.loads((ROOT / 'CMDB用例集-白盒200.json').read_text())['cases']}
        controls = [('entity130', 'CMDB-130', all_cases['CMDB-130']['question'].replace(old_value, replacement)),
                    ('entity132_rephrase', 'CMDB-132', f'请在区域{replacement}内，按VDC分别汇总云硬盘的块数和容量合计。')]
        def call(payload):
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'], input=json.dumps(payload, ensure_ascii=False),
                                  cwd=ROOT, capture_output=True, text=True, timeout=120)
            event = {'event': 'native_worker', 'control_id': payload['control_id'], 'kind': payload['kind'],
                     'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
            try: event['record'] = json.loads(proc.stdout)
            except ValueError: event['parse_failed'] = True
            emit(event)
            assert proc.returncode == 0 and event.get('record', {}).get('status') == 'PASS', event
            return event['record']
        for control_id, case_id, question in controls:
            source = {k: copy.deepcopy(v) for k,v in all_cases[case_id].items() if k != 'answer'}
            reference_api = copy.deepcopy(source['api_call'])
            condition = reference_api['condition']['constraint'][0]['simple']
            assert condition['name'] == 'logicalRegionName' and condition['value'] == old_value
            condition['value'] = replacement
            reference = call({'kind': 'reference_generation', 'control_id': control_id,
                'input': {'api_call': reference_api, 'sql': source['sql']}, 'source_without_old_answer': source, 'question': question})
            derived = dict(source, case_id=control_id, question=question, api_call=reference_api, answer=reference['native_output']['result'])
            actual = call({'kind': 'candidate_execution', 'control_id': control_id, 'input': new['rb_086'],
                'verified_params': {'logicalRegionName': replacement}, 'expected_case': derived})
            assert actual['native_output'] == reference['native_output']
            q = {'key': control_id, 'question': question, 'expected': ['rb_086']}
            a, b = observe(a_index, old, q), observe(b_index, new, q)
            emit({'event': 'derived_control_retrieval', 'control_id': control_id, 'baseline': a, 'candidate': b})
            report['controls'].append({'id': control_id, 'source': case_id, 'question': question, 'old_value': old_value, 'new_value': replacement,
                'fresh_reference_expected': True, 'old_answer_reused': False, 'native_outputs_equal': True, 'score': actual['score'],
                'reference_pid': reference['pid'], 'candidate_pid': actual['pid'], 'baseline_retrieval': a, 'candidate_retrieval': b})
        report['controls_limit'] = '2 different questions share 1 real replacement region; source questions are duplicates; not 2 independent entity samples or selector/generalization proof'
        report['protected_after'] = protected(); assert report['protected_after'] == before
        assert {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted((ROOT / 'implementation').glob('*.py'))} == source_hashes
        assert all(sha((A / name).read_bytes()) == value for name,value in LOCKS.items())
        report['status'] = 'PASS_OFFLINE_ONLY'
        report['decision'] = 'retain isolated 199 candidate; production remains 200; do not merge or push without real selector/end-to-end paired evidence'
    except Exception as exc:
        report['failures'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
        emit({'event': 'failure', **report['failures'][-1]})
    finally:
        report['not_run'] = ['LLM selector/parameter extraction/SQL refinement', 'paired complete score and official total', 'production merge/push/install/deploy']
        report['shared_service_lifecycle_changed'] = False
        emit({'event': 'finish', 'status': report['status'], 'failures': report['failures']})
        raw_file.close(); report['raw_sha256'] = sha(RAW.read_bytes())
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'changes': report.get('changes'), 'regression_counts': {k:len(v) for k,v in report['regressions'].items()},
                          'controls': len(report['controls']), 'failures': report['failures']}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS_OFFLINE_ONLY' else 1


if __name__ == '__main__':
    sys.exit(worker() if sys.argv[1:] == ['--worker'] else main())
