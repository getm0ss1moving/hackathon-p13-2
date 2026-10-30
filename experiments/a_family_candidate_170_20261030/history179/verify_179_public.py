"""Offline public controls; no model, service, matcher import or Git mutation."""
import argparse
import ast
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base180', type=Path, required=True)
    parser.add_argument('--candidate179', type=Path, required=True)
    parser.add_argument('--retriever', type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / 'MANIFEST.json').read_text())
    for path, expected in manifest['package_files'].items():
        assert hashlib.sha256((package / path).read_bytes()).hexdigest() == expected, path
    for path, expected in [(args.base180, manifest['base180_sha256']),
                           (args.candidate179, manifest['candidate179_sha256']),
                           (args.retriever, manifest['retriever_sha256'])]:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, path.name
    old, new = json.loads(args.base180.read_text()), json.loads(args.candidate179.read_text())
    assert len(old) == len({x['id'] for x in old}) == 180
    assert len(new) == len({x['id'] for x in new}) == 179
    assert [x for x in old if x['id'] not in {'rb_099', 'rb_101'}] == [
        x for x in new if x['id'] != 'family_f27']
    engine_spec = importlib.util.spec_from_file_location('_public179_bm25', args.retriever)
    module = importlib.util.module_from_spec(engine_spec)
    sys.modules[engine_spec.name] = module
    engine_spec.loader.exec_module(module)
    before, after = module.RunbookRetriever(old), module.RunbookRetriever(new)
    assert [(d.item_id, d.tokens) for d in before._docs] == [(d.item_id, d.tokens) for d in after._docs]
    assert (before._df, before._idf, before._tau, before._avg_len, before._doc_tfs) == (
        after._df, after._idf, after._tau, after._avg_len, after._doc_tfs)

    def mapped(results):
        seen, result = set(), []
        for c in results:
            owner = 'family_f27' if c.id in {'rb_099', 'rb_101'} else c.id
            if owner not in seen:
                result.append((owner, c.tier, c.score, c.coverage)); seen.add(owner)
        return result

    controls = [
        '查询区域 Region-A 下的OBS桶列表',
        '按租户统计区域 Region-A 的OBS桶数量',
        '查询区域 Region-B 对象存储桶的名称和托管状态',
        '统计区域 Region-B 各租户的OBS桶数量',
        '查询区域 Region-A 的OBS桶列表以及按租户统计这些桶的数量',
        '查询区域 Region-A 的OBS桶列表和共享网络列表',
        '统计区域 Region-A 各租户OBS桶数量和各VDC云硬盘数量',
        '列出区域 Region-A OBS桶列表、ECS状态分布与弹性IP租户状态分布',
    ]
    for question in controls:
        for k in [None, 1, 5, 10]:
            assert mapped(before.retrieve(question, k)) == [
                (c.id, c.tier, c.score, c.coverage) for c in after.retrieve(question, k)]
    source = (package / 'materialization_reference.py').read_text()
    tree = ast.parse(source)
    assert all(isinstance(n, (ast.Import, ast.Assign, ast.FunctionDef, ast.Expr)) for n in tree.body)
    namespace = {}
    exec(compile(tree, '<reviewed-pure-materializer>', 'exec'), namespace)
    materialize = namespace['_materialize_family']
    family = next(x for x in new if x['id'] == 'family_f27')
    contracts = json.loads((package / 'OLD_TO_NEW.json').read_text())['mappings']
    old_by = {x['id']: x for x in old}
    datasets = [[], [('a', 'one', 'active', 'T1'), ('b', 'two', 'active', 'T2')],
                [('a', 'same', 'active', 'T1')] * 3 + [('n', 'null', 'active', None), ('e', 'empty', 'active', '')]]
    for contract in contracts:
        assert old_by[contract['old_id']]['api_call'] == contract['api_contract']
        assert old_by[contract['old_id']]['sql'] == contract['sql_contract']
        parameters = copy.deepcopy(contract['parameters'])
        parameters['filters']['logicalRegionName'] = 'Region-Synthetic'
        item = materialize(family, parameters)
        expected_api = json.loads(json.dumps(contract['api_contract']).replace('{{logicalRegionName}}', 'Region-Synthetic'))
        assert item['api_call'] == expected_api and item['sql'] == contract['sql_contract']
        for dataset in datasets:
            with sqlite3.connect(':memory:') as connection:
                connection.execute('CREATE TABLE CLOUD_OBS_BUCKET(name TEXT,bucketName TEXT,managedStatus TEXT,tenantName TEXT)')
                connection.executemany('INSERT INTO CLOUD_OBS_BUCKET VALUES (?,?,?,?)', dataset)
                actual = connection.execute(item['sql']).fetchall()
                if parameters['view'] == 'rows':
                    assert actual == [row[:3] for row in dataset]
                else:
                    assert dict(actual) == dict(Counter(row[3] for row in dataset))
                    assert sum(value for _, value in actual) == len(dataset)
    parameters = {'scope': 'filtered', 'view': 'rows',
                  'filters': {'logicalRegionName': 'Region-Synthetic'},
                  'required_filters': ['logicalRegionName']}
    invalid = [{'view': 'capacity'}, {'metrics': 'sum'},
               {'scope': 'global', 'filters': {}, 'required_filters': []},
               {'filters': {'logicalRegionName': 'Region-Synthetic', 'tenantName': 'T1'},
                'required_filters': ['logicalRegionName', 'tenantName']},
               {'view': ['rows', 'tenant_count']}, {'filters': {'logicalRegionName': False}}]
    for update in invalid:
        case = copy.deepcopy(parameters); case.update(update)
        try:
            materialize(family, case)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError('Unsupported configuration accepted')
    print(json.dumps({'status': 'PASS_PUBLIC_OFFLINE_CONTROLS', 'active_templates': 179,
        'paired_retrieval_checks': 32, 'SQL_API_fixtures': 6, 'invalid_configs_rejected': 6,
        'model_calls': 0, 'service_calls': 0, 'production_activated': False,
        'B_port_required': True, 'bucket_uniqueness_or_pagination_proved': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
