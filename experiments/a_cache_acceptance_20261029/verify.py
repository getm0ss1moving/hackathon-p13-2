"""A 的文档词频缓存独立验收；只加载检索/模板快照，不导入执行器或评分器。"""
import argparse
import ast
from collections import Counter
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
import tracemalloc
import types

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('result-rerun.json')
BASE, PARENT, CANDIDATE = '3b99aaf', '1a72007', '1928514'
# 与历史A输入逐字节相同的交付副本；原本机输入和旧result.json保持原样。
INPUT = Path(__file__).with_name('queries.json')
INPUT_SHA = '37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0'
CAPS = [None, 0, 3, 5, 10, 15]
EXPECTED_FIXED = {
    'implementation/evaluator.py': 'c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22',
    'implementation/runbook_executor.py': '4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def snapshot(commit, path):
    return git('show', f'{commit}:{path}')


def module(commit):
    name = 'independent_retriever_' + commit
    loaded = types.ModuleType(name)
    loaded.__file__ = f'git:{commit}:implementation/runbook_retriever.py'
    sys.modules[name] = loaded  # dataclass 查类型所属模块
    exec(compile(snapshot(commit, 'implementation/runbook_retriever.py'), loaded.__file__, 'exec'), loaded.__dict__)
    return loaded


def items(commit):
    tree = ast.parse(snapshot(commit, 'implementation/runbook_items.py'))
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'RUNBOOK_ITEMS' for t in n.targets))
    return ast.literal_eval(assignment.value)


def fixed_files():
    names = git('ls-tree', '-r', '-z', '--name-only', 'd79c316').decode().rstrip('\0').split('\0')
    names = [p for p in names if p.startswith('output-server/') or p in EXPECTED_FIXED
             or p == 'CMDB用例集-白盒200.json']
    result = []
    for path in names:
        reference = digest(snapshot('d79c316', path))
        current = digest((ROOT / path).read_bytes()) if (ROOT / path).is_file() else None
        result.append({'path': path, 'baseline_sha256': reference, 'current_sha256': current,
                       'equal': current == reference})
    return result


def packed(candidates):
    # 外层顺序保留，行字段为 id/tier/score/coverage；不同模块的 dataclass 不按类型比较。
    return [[c.id, c.tier, c.score, c.coverage] for c in candidates]


def index_fingerprint(index):
    state = {'docs': [[doc.item_id, doc.tokens] for doc in index._docs],
             'cached_tf': [sorted(tf.items()) for tf in getattr(index, '_doc_tfs', [])]}
    return digest(json.dumps(state, ensure_ascii=False, sort_keys=True).encode())


def latency_summary(values):
    values = sorted(values)
    return {'n': len(values), 'median_ms': statistics.median(values) / 1e6,
            'p95_ms': values[math.ceil(.95 * len(values)) - 1] / 1e6,
            'max_ms': values[-1] / 1e6}


def main():
    parser = argparse.ArgumentParser(description='历史缓存版本复测；输入变化时停止，不覆盖已有报告')
    parser.add_argument('--output', type=Path, default=OUT, help='新的结果JSON路径')
    out = parser.parse_args().output.resolve()
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('必须在指定仓库根目录执行')
    # 不把新实现误写成旧缓存版本的复测，也不覆盖历史证据。
    frozen_sources = {'implementation/runbook_retriever.py': CANDIDATE,
                      'implementation/runbook_items.py': PARENT}
    changed = [path for path, commit in frozen_sources.items()
               if (ROOT / path).read_bytes() != snapshot(commit, path)]
    if changed:
        print('历史验收输入已变化；未执行检索/性能测试，未写报告：' + ', '.join(changed), file=sys.stderr)
        return 2
    if out.exists():
        print('复测结果已存在；请先保留既有证据并选择新的输出文件名', file=sys.stderr)
        return 2
    history = []
    report = {'prior_attempts': history, 'status': 'FAIL', 'cwd': str(ROOT), 'python': platform.python_version(),
              'platform': platform.platform(), 'script_sha256': digest(Path(__file__).read_bytes()),
              'revisions': {key: git('rev-parse', value).decode().strip()
                            for key, value in [('baseline', BASE), ('parent', PARENT), ('candidate', CANDIDATE)]},
              'model_requests': 0, 'service_started': False, 'protected_modules_imported': False,
              'scope': 'retrieval output equality and local timing/index allocation only; no score inference',
              'checks': {}, 'failures': [], 'outputs': [], 'edge_outputs': []}
    try:
        before = fixed_files()
        report['protected_before'] = before
        assert len(before) == 236, len(before)
        assert all(r['equal'] for r in before)
        assert all(next(r for r in before if r['path'] == p)['current_sha256'] == h
                   for p, h in EXPECTED_FIXED.items())
        report['checks']['protected_initial'] = 'PASS'
        for path in ['implementation/runbook_retriever.py', 'implementation/runbook_items.py']:
            assert snapshot(BASE, path) == snapshot(PARENT, path), path
        changed = git('diff', '--name-only', PARENT, CANDIDATE).decode().splitlines()
        assert changed == ['implementation/runbook_retriever.py'], changed
        assert git('rev-parse', CANDIDATE + '^').strip() == git('rev-parse', PARENT).strip()
        assert snapshot(PARENT, 'implementation/runbook_items.py') == snapshot(CANDIDATE, 'implementation/runbook_items.py')
        assert (ROOT / changed[0]).read_bytes() == snapshot(CANDIDATE, changed[0])
        report['checks']['same_baseline_parent_retriever_and_templates'] = 'PASS'
        report['checks']['single_changed_file_and_parent'] = 'PASS'
        report['production_patch'] = git('diff', PARENT, CANDIDATE, '--', changed[0]).decode()
        query_bytes = INPUT.read_bytes()
        assert digest(query_bytes) == INPUT_SHA
        queries = json.loads(query_bytes)
        assert len(queries) == 1075
        report['input'] = {'path': str(INPUT.relative_to(ROOT)), 'sha256': INPUT_SHA, 'n': len(queries),
                           'scopes': dict(Counter(q['scope'] for q in queries)),
                           'dependency': 'tracked byte-identical frozen input; original A-owned input preserved'}
        baseline, candidate = module(BASE), module(CANDIDATE)
        templates = items(PARENT)
        assert len(templates) == 200
        base_index, candidate_index = baseline.RunbookRetriever(templates), candidate.RunbookRetriever(templates)
        assert len(candidate_index._docs) == len(candidate_index._doc_tfs) == 400
        assert all(tf == Counter(doc.tokens) for doc, tf in zip(candidate_index._docs, candidate_index._doc_tfs))
        fingerprints = [index_fingerprint(base_index), index_fingerprint(candidate_index)]
        comparisons = 0
        for q in queries:
            observation = {'key': q['key'], 'question': q['question'], 'scope': q['scope'], 'caps': []}
            for cap in CAPS:
                a = packed(base_index.retrieve(q['question'], top_k=cap))
                b = packed(candidate_index.retrieve(q['question'], top_k=cap))
                equal = a == b
                observation['caps'].append({'top_k': cap, 'baseline': a, 'candidate': b, 'equal': equal})
                if not equal:
                    report['failures'].append({'phase': 'fixed', 'key': q['key'], 'top_k': cap, 'baseline': a, 'candidate': b})
                comparisons += 1
            report['outputs'].append(observation)
        report['fixed_comparisons'] = comparisons
        assert comparisons == 6450
        report['checks']['frozen_1075_x_6_fields_order'] = 'PASS' if not report['failures'] else 'FAIL'
        synthetic = [
            ('empty_index', []),
            ('no_text', [{'id': 'empty', 'examples': [], 'description': ''}]),
            ('empty_token_docs', [{'id': 'punct', 'examples': ['', '！！！', '...']}]),
            ('small_index', [{'id': 'alpha', 'description': 'ECS 状态 ECS', 'examples': ['实例ECS 按状态数量', '']},
                             {'id': 'beta', 'description': '云硬盘 存储容量', 'examples': ['云硬盘数量状态']},
                             {'id': 'alpha', 'description': '多文档归并', 'examples': ['ECS云硬盘']}]),
            ('ties', [{'id': 'tie1', 'description': 'same same VM status', 'examples': ['same VM status']},
                      {'id': 'tie2', 'description': 'same same VM status', 'examples': ['same VM status']}]),
            ('production', templates),
        ]
        options = [{}, {'coverage_strong': .7, 'coverage_weak': .2, 'unseen_weight_ratio': 0.0},
                   {'coverage_strong': 0.0, 'coverage_weak': 0.0, 'unseen_weight_ratio': 1.0},
                   {'coverage_strong': .95, 'coverage_weak': .9, 'unseen_weight_ratio': .6}]
        edge_queries = ['', '！？，。。!?', 'qzxv_unknown_778899', '000123 9999 42', 'ECS ECS', '状态 分布',
                        '云硬盘数量', '💡🚀', '虚拟机', 'same VM status', '的了和吗呢吧啊', '123.456',
                        'VM_NOVA new_region_42', 'vpc.example-01']
        edge_count = 0
        for name, sample in synthetic:
            for config in options:
                a_index, b_index = baseline.RunbookRetriever(sample, **config), candidate.RunbookRetriever(sample, **config)
                for query in edge_queries:
                    for cap in CAPS:
                        a, b = packed(a_index.retrieve(query, top_k=cap)), packed(b_index.retrieve(query, top_k=cap))
                        result = {'index': name, 'config': config, 'question': query, 'top_k': cap,
                                  'baseline': a, 'candidate': b, 'equal': a == b}
                        report['edge_outputs'].append(result)
                        if a != b:
                            report['failures'].append({'phase': 'edge', **result})
                        edge_count += 1
        report['edge_comparisons'] = edge_count
        report['checks']['edge_and_nondefault_parameters'] = 'PASS' if all(r['equal'] for r in report['edge_outputs']) else 'FAIL'
        assert fingerprints == [index_fingerprint(base_index), index_fingerprint(candidate_index)]
        report['checks']['index_docs_and_tf_unchanged_after_queries'] = 'PASS'
        # 只读 AST 检查根调用点；不导入matcher/system，不接触模型或执行器。
        references, calls = [], []
        for path in sorted((ROOT / 'implementation').glob('*.py')):
            if path.name == 'runbook_retriever.py':
                continue
            code = path.read_text()
            for node in ast.walk(ast.parse(code)):
                if isinstance(node, ast.Attribute) and node.attr in {'_docs', '_doc_tfs', 'tokens'}:
                    references.append({'path': str(path.relative_to(ROOT)), 'line': node.lineno, 'attribute': node.attr})
                if isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name) and node.func.id == 'RunbookRetriever'
                    or isinstance(node.func, ast.Attribute) and node.func.attr == 'retrieve'):
                    calls.append({'path': str(path.relative_to(ROOT)), 'line': node.lineno,
                                  'source': ast.get_source_segment(code, node)})
        report['callsite_audit'] = {'internal_doc_references_outside_retriever': references, 'constructor_or_retrieve_calls': calls,
                                   'limit': 'static root Python audit; not proof against future reflection/private mutation'}
        assert not references
        report['checks']['root_does_not_mutate_index_documents'] = 'PASS'
        # 3轮配对交错；计时只包含retrieve，排除输出打包和初始化，不比较跨配置分数。
        seed, repetitions = 20261029, 3
        rng, raw_timing = random.Random(seed), []
        for q in queries[:10]:
            base_index.retrieve(q['question']); candidate_index.retrieve(q['question'])
        for repeat in range(repetitions):
            order = list(range(len(queries))); rng.shuffle(order)
            for i in order:
                pair = [('baseline', base_index), ('candidate', candidate_index)]
                if rng.randrange(2):
                    pair.reverse()
                sample = {'repeat': repeat, 'key': queries[i]['key'], 'order': [v[0] for v in pair]}
                for name, index in pair:
                    started = time.perf_counter_ns()
                    index.retrieve(queries[i]['question'])
                    sample[name + '_ns'] = time.perf_counter_ns() - started
                raw_timing.append(sample)
        report['timing'] = {'seed': seed, 'repetitions': repetitions, 'top_k': None,
                            'warmup_queries_per_version': 10, 'raw_pairs': raw_timing,
                            **{name: latency_summary([r[name + '_ns'] for r in raw_timing]) for name in ['baseline', 'candidate']},
                            'limit': 'same-process warm Mac run; local scheduler/cache/order effects; not model or official end-to-end timing'}
        # 新建索引的tracemalloc增量，不包含已加载源/模板及数据服务；轮间交错构建次序。
        build_samples = []
        for repeat in range(5):
            for name, loaded in ([('baseline', baseline), ('candidate', candidate)] if repeat % 2 == 0
                                 else [('candidate', candidate), ('baseline', baseline)]):
                gc.collect(); tracemalloc.start()
                before_bytes = tracemalloc.get_traced_memory()[0]
                started = time.perf_counter_ns(); index = loaded.RunbookRetriever(templates)
                elapsed_ns = time.perf_counter_ns() - started
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                build_samples.append({'repeat': repeat, 'version': name, 'build_ns_with_tracemalloc': elapsed_ns,
                                      'live_index_bytes': current - before_bytes, 'peak_bytes': peak - before_bytes,
                                      'documents': len(index._docs), 'cached_counters': len(getattr(index, '_doc_tfs', []))})
                del index
        report['index_cost'] = {'raw': build_samples, 'limit': 'tracemalloc incremental live allocations, not RSS or total system memory; tracing slows construction'}
        report['protected_after'] = fixed_files()
        assert report['protected_after'] == before
        assert all(r['equal'] for r in report['protected_after'])
        assert digest(INPUT.read_bytes()) == INPUT_SHA
        assert (ROOT / 'implementation/runbook_retriever.py').read_bytes() == snapshot(CANDIDATE, 'implementation/runbook_retriever.py')
        assert (ROOT / 'implementation/runbook_items.py').read_bytes() == snapshot(PARENT, 'implementation/runbook_items.py')
        assert not {'evaluator', 'runbook_executor', 'runbook_matcher', 'openai'} & set(sys.modules)
        report['checks']['protected_final_236'] = 'PASS'
        assert all(v == 'PASS' for v in report['checks'].values())
        assert not report['failures']
        report['status'] = 'PASS'
    except Exception as exc:
        report['failures'].append({'phase': 'exception', 'type': type(exc).__name__, 'message': str(exc)})
    finally:
        report['not_run'] = ['model selection/parameter filling/SQL refinement/end-to-end scoring',
                             'official blackbox and total score', 'lexical/alias/198-template paired model evaluation',
                             'old capability.py or fixed-module monkeypatch', 'network/service/API/install/push/deploy']
        with out.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n')
        print(json.dumps({k: report.get(k) for k in ['status', 'fixed_comparisons', 'edge_comparisons', 'checks', 'failures']}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
