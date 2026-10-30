"""Strict dedup checks. No model requests; --native uses the original loopback service.

Run from repository root. Historical questions, answers and sealed splits are not read.
"""
import argparse
import ast
import collections
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import types

BASE = '5f04481cb5daf7e969be76ac9735d279cd9c249f'
MAPPING = {'rb_054': 'rb_052', 'rb_087': 'rb_086'}


def library(source):
    tree = ast.parse(source)
    return ast.literal_eval(next(n.value for n in tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
        t.id == 'RUNBOOK_ITEMS' for t in n.targets)))


def module(name, source):
    result = types.ModuleType(name)
    sys.modules[name] = result
    exec(compile(source, '<frozen-retriever>', 'exec'), result.__dict__)
    return result


def normalized(candidates):
    seen, result = set(), []
    for c in candidates:
        item_id = MAPPING.get(c.id, c.id)
        if item_id not in seen:
            result.append((item_id, c.tier, c.score, c.coverage))
            seen.add(item_id)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    git = lambda *a: subprocess.check_output(['git', *a], cwd=root)
    base = git('rev-parse', args.base + '^{commit}').decode().strip()
    old_source = git('show', base + ':implementation/runbook_items.py')
    new_source = (root / 'implementation/runbook_items.py').read_bytes()
    old, new = library(old_source), library(new_source)
    old_by, new_by = {i['id']: i for i in old}, {i['id']: i for i in new}
    assert len(old) == len(old_by) == 200
    assert len(new) == len(new_by) == 198
    assert set(old_by) - set(new_by) == set(MAPPING)
    display = {'id', 'name', 'description', 'examples'}
    contract = lambda i: {k: v for k, v in i.items() if k not in display}
    groups = collections.defaultdict(list)
    for item in old:
        groups[json.dumps(contract(item), sort_keys=True)].append(item['id'])
    assert sorted(sorted(g) for g in groups.values() if len(g) > 1) == [
        ['rb_052', 'rb_054'], ['rb_086', 'rb_087']]
    for removed, retained in MAPPING.items():
        assert contract(old_by[removed]) == contract(old_by[retained])
    for item in new:
        assert {k: v for k, v in item.items() if k != 'retrieval_aliases'} == old_by[item['id']]
        for alias in item.get('retrieval_aliases', []):
            assert set(alias) == {'id', 'after_id', 'examples', 'description'}
            assert alias['id'] in MAPPING and MAPPING[alias['id']] == item['id']
    old_retriever = module('_dedup_old_retriever', git('show', base + ':implementation/runbook_retriever.py'))
    new_retriever = module('_dedup_new_retriever', (root / 'implementation/runbook_retriever.py').read_bytes())
    a, b = old_retriever.RunbookRetriever(old), new_retriever.RunbookRetriever(new)
    assert [(d.item_id, d.tokens) for d in a._docs] == [(d.item_id, d.tokens) for d in b._docs]
    assert (a._df, a._idf, a._avg_len) == (b._df, b._idf, b._avg_len)
    source = [s for i in old for s in [*i.get('examples', []), i.get('description', '')] if s]
    queries = [*source, *['不要' + s for s in source],
        *[re.sub(r'[A-Za-z][A-Za-z0-9_.-]*', 'ENTITY', s) for s in source],
        *[s + '；同时' + source[(i + 11) % len(source)] for i, s in enumerate(source)],
        '', '不存在的资源类型xyz', '天气怎么样', '统计巧克力数量']
    started = time.perf_counter()
    for query in queries:
        for k in [None, 1, 5, 10]:
            actual = b.retrieve(query, k)
            assert normalized(a.retrieve(query, k)) == [
                (c.id, c.tier, c.score, c.coverage) for c in actual]
            assert all(c.id in new_by for c in actual)
    # Exercise B's existing pure formatting/placeholder interfaces without models,
    # imports of B runtime, test answers or changes to its source.
    selector_checks = []
    for rel in ['implementation/runbook_matcher.py']:
        tree = ast.parse((root / rel).read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and
                     n.name in {'_format_runbook_list', '_get_placeholders'}]
        namespace = {'json': json, 're': re, 'List': list}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<pure-matcher-contract>', 'exec'), namespace)
        for query in source:
            candidates = [new_by[c.id] for c in b.retrieve(query)]
            text = namespace['_format_runbook_list'](candidates)
            assert 'retrieval_aliases' not in text
            for index, item in enumerate(candidates, 1):
                assert f'{index}. {item["name"]}' in text
                assert namespace['_get_placeholders'](item) == namespace['_get_placeholders'](old_by[item['id']])
        selector_checks.append({'module': rel, 'inputs': len(source), 'status': 'PASS_PURE_INTERFACE_ONLY'})
    protected = [p for p in git('ls-tree', '-rz', '--name-only', base).decode().split('\0') if p
                 if p.startswith('output-server/') or
                 p.rsplit('/', 1)[-1] in {'evaluator.py', 'runbook_executor.py'} or
                 (p.endswith('.json') and '/' not in p)]
    for rel in protected:
        assert (root / rel).read_bytes() == git('show', base + ':' + rel), rel
    native = []
    if args.native:
        # Each comparison gets a fresh, unmodified executor process. No clearing
        # or replacing its cache, globals, methods or returned values.
        child = ('import json,sys;sys.path.insert(0,sys.argv[1]);'
                 'import runbook_executor as e;'
                 'assert e.BASE_URL == "http://127.0.0.1:8080";'
                 'print(json.dumps(e.execute(json.load(sys.stdin)),ensure_ascii=False))')
        data_dir = root / 'output-server/CI+md数据-脱敏-最终-0924'
        for removed, retained in MAPPING.items():
            table = old_by[retained]['api_call']['url'].split('/instances/')[1].split('?')[0]
            regions = []
            for path in sorted(data_dir.glob(table + '-*.json')):
                for row in json.loads(path.read_text()).get('objList', []):
                    value = row.get('logicalRegionName')
                    if value and value not in regions:
                        regions.append(value)
            default = old_by[retained]['default_params']['logicalRegionName']
            alternative = next((v for v in regions if v != default), None)
            scopes = [('default', default), ('alternate_nonempty', alternative),
                      ('no_match', 'dedup-regression-nonexistent-region')]
            for label, value in scopes:
                if value is None:
                    native.append({'removed': removed, 'scope': label, 'status': 'NOT_RUN_NO_ALTERNATE_SCOPE'})
                    continue
                outputs = []
                for item in [old_by[removed], old_by[retained], new_by[retained]]:
                    filled = copy.deepcopy(item)
                    filled['params'] = {'condition': [{'name': 'logicalRegionName', 'value': value}]}
                    output = subprocess.check_output([sys.executable, '-c', child,
                        str(root / 'implementation')], input=json.dumps(filled).encode())
                    outputs.append(json.loads(output))
                assert outputs[0] == outputs[1] == outputs[2]
                assert outputs[0]['error'] is None
                result = outputs[0]['result']
                if label != 'no_match':
                    assert result['columns'] and result['rows'], 'Nonempty path must not silently fail'
                native.append({'removed': removed, 'retained': retained, 'scope': label,
                    'status': 'PASS_EXACT_NATIVE_OUTPUT_EQUALITY', 'row_count': result['row_count'],
                    'columns': result['columns'], 'nonempty_schema_verified': label != 'no_match'})
    result = {'status': 'PASS', 'base_commit': base,
        'source_sha256_before': hashlib.sha256(old_source).hexdigest(),
        'source_sha256_after': hashlib.sha256(new_source).hexdigest(),
        'N_before': len(old), 'N_after': len(new), 'retired_to_retained': MAPPING,
        'strict_duplicate_groups_exhaustively_scanned': 2,
        'retained_original_execution_payloads_unchanged': 198,
        'retrieval_inputs': len(queries), 'top_k_settings': [None, 1, 5, 10],
        'paired_retrieval_comparisons': len(queries) * 4, 'candidate_equivalence_failures': 0,
        'original_corpus_order_tokens_DF_IDF_avg_length_preserved': True,
        'index_document_count': b._doc_count, 'pure_selector_contracts': selector_checks,
        'protected_files_unchanged': len(protected), 'native_checks': native,
        'native_fresh_executor_processes': 3 * sum(c['status'].startswith('PASS') for c in native),
        'max_compact_item_bytes': max(len(json.dumps(i, ensure_ascii=False,
                                    separators=(',', ':')).encode()) for i in new),
        'elapsed_seconds': time.perf_counter() - started, 'model_calls': 0,
        'limits': ['检索变换只验证新旧一致性，不证明否定或未知输入已被正确理解。',
                   '未运行真实模型选择、填参或端到端评分，不把历史成绩归于198模板。',
                   'B已统一根目录，本次不修改其matcher/system/训练脚本或封存集。',
                   '原执行器对空数据缺列的吞错行为不属于本次修复。',
                   '4KB使用紧凑UTF-8 JSON检查；官方深度算法仍待明确。']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'limits'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
