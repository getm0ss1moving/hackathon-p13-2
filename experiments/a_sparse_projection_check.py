"""No-model, native-service regression of rb_071's sparse projection.

Use the existing Python environment and the unchanged service on localhost:8080.
Only aggregates are emitted. The report must be outside this repository.
Each native case uses a fresh interpreter and a naturally empty executor cache.
"""
import argparse
import ast
import collections
import contextlib
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid


EXECUTOR_SHA = '4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92'
FIELDS = [('hostName', 'name'), ('hostIpAddress', 'ip_address'), ('hostType', 'type')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def multiset(rows):
    return collections.Counter(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in rows)


def offline(repo):
    sys.path.insert(0, str(repo / 'implementation'))
    ex = importlib.import_module('runbook_executor')
    assert sha(Path(ex.__file__)) == EXECUTOR_SHA
    items = ast.literal_eval(ast.parse((repo / 'implementation/runbook_items.py').read_text()).body[0].value)
    sql = next(t['sql'] for t in items if t['id'] == 'rb_071')
    row = {'id': 'synthetic-resource', 'hostName': 'synthetic-host',
           'hostIpAddress': '192.0.2.1', 'hostType': 'PM'}
    cases = [('complete', [row]), ('empty', []), ('all_fields_absent', [{'id': 'synthetic-resource'}]),
             ('multiple', [row, dict(row, id='synthetic-resource-2', hostName='synthetic-host-2')])]
    for field, _ in FIELDS:
        cases.append(('missing_' + field, [{k: v for k, v in row.items() if k != field}]))
        cases.append(('null_' + field, [dict(row, **{field: None})]))
    results = []
    for name, records in cases:
        conn = ex.load_into_sqlite({'SYS_X86Server': records})
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = [dict(zip(columns, values)) for values in cur.fetchall()]
        expected = [{out: rec.get(field) for field, out in FIELDS} for rec in records]
        passed = columns == ['name', 'ip_address', 'type'] and multiset(rows) == multiset(expected)
        results.append({'case': name, 'source_rows': len(records), 'output_rows': len(rows), 'PASS': passed})
        conn.close()
    assert all(x['PASS'] for x in results)
    return {'status': 'PASS', 'cases': results, 'network_calls': 0, 'model_calls': 0,
            'SQL_table_scanner': sorted(ex._extract_sql_tables(sql))}


def worker(repo):
    spec = json.load(sys.stdin)
    sys.path.insert(0, str(repo / 'implementation'))
    ex = importlib.import_module('runbook_executor')
    assert Path(ex.__file__).resolve() == repo / 'implementation/runbook_executor.py'
    assert sha(Path(ex.__file__)) == EXECUTOR_SHA
    assert ex.BASE_URL == 'http://127.0.0.1:8080' and not ex._cache
    import requests
    assert not requests.utils.get_environ_proxies(ex.BASE_URL)
    tree = ast.parse((repo / 'implementation/runbook_items.py').read_text())
    item = copy.deepcopy(next(t for t in ast.literal_eval(tree.body[0].value) if t['id'] == 'rb_071'))
    item['params'] = {'condition': [{'name': 'logicalRegionName', 'value': spec['region']}]}
    if spec['ids']:
        first = item['api_call'][0] if isinstance(item['api_call'], list) else item['api_call']
        first['condition']['constraint'].append({
            'simple': {'name': 'id', 'value': spec['ids'], 'operator': 'in'}, 'logOp': 'and'})
    calls = io.StringIO()
    with contextlib.redirect_stdout(calls), contextlib.redirect_stderr(calls):
        result = ex.execute(item)
    records = next(iter(ex._cache.values()))
    expected = [{out: ex._to_sqlite_val(row.get(field)) for field, out in FIELDS} for row in records]
    actual = result.get('result') or {}
    # Bypass the executor's error suppression for a separate SQL-only diagnostic.
    conn = ex.load_into_sqlite({'SYS_X86Server': records})
    sql_error = None
    try:
        cur = conn.execute(item['sql'])
        direct_columns = [d[0] for d in cur.description]
        direct_rows = [dict(zip(direct_columns, row)) for row in cur.fetchall()]
    except Exception as err:
        sql_error = type(err).__name__
        direct_rows, direct_columns = [], []
    finally:
        conn.close()
    conditions = json.loads(next(iter(ex._cache)).split('::', 1)[1])
    scope_exact = all(row.get('logicalRegionName') == spec['region'] for row in records)
    ids_exact = not spec['ids'] or all(row.get('id') in spec['ids'] for row in records)
    filters_exact = any(c['key'] == 'logicalRegionName' and c['value'] == spec['region']
                        for c in conditions)
    if spec['ids']:
        filters_exact = filters_exact and any(c['key'] == 'id' and c['operator'] == 'in'
                                              and c['value'] == spec['ids'] for c in conditions)
    out = {'case': spec['case'], 'source_rows': len(records),
           'expected_rows': spec['expected_count'], 'result_rows': actual.get('row_count'),
           'columns': actual.get('columns'), 'native_error_present': bool(result.get('error')),
           'SQL_error_unsuppressed': sql_error,
           'matches_source_projection': multiset(actual.get('rows', [])) == multiset(expected),
           'direct_SQL_matches': multiset(direct_rows) == multiset(expected),
           'scope_exact': scope_exact, 'IDs_exact': ids_exact, 'filters_exact': filters_exact,
           'source_missing_cells': sum(row.get(field) is None for row in records for field, _ in FIELDS),
           'result_null_cells': sum(value is None for row in actual.get('rows', []) for value in row.values()),
           'cache_naturally_cold': True, 'source_values_emitted': False}
    out['PASS'] = (not out['native_error_present'] and not sql_error and out['matches_source_projection']
                   and out['direct_SQL_matches'] and scope_exact and ids_exact and filters_exact
                   and out['result_rows'] == spec['expected_count']
                   and out['columns'] == ['name', 'ip_address', 'type'])
    print(json.dumps(out))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--report', type=Path)
    p.add_argument('--server-log', type=Path)
    p.add_argument('--offline-only', action='store_true', help='Synthetic in-memory SQL regression, no service needed')
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    root = args.repo.resolve()
    if args.worker:
        worker(root)
        return
    if not args.report or args.report.exists():
        p.error('Provide a new report path')
    if root in args.report.resolve().parents:
        p.error('Keep evidence outside the repository')
    paths = ['implementation/runbook_items.py', 'implementation/runbook_executor.py',
             'implementation/evaluator.py', 'output-server/data_server.py']
    before = {name: sha(root / name) for name in paths}
    assert before['implementation/runbook_executor.py'] == EXECUTOR_SHA
    if args.offline_only:
        report = offline(root)
        assert {name: sha(root / name) for name in paths} == before
        report['source_hashes'] = before
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'cases': len(report['cases']), 'network_calls': 0}))
        return
    data = root / 'output-server/CI+md数据-脱敏-最终-0924/S_X86Server-1.json'
    data_sha = sha(data)
    rows = json.loads(data.read_text())['objList']
    regions = sorted({row['logicalRegionName'] for row in rows})
    cases = [{'case': 'real_scope_' + str(j + 1), 'region': region, 'ids': [],
              'expected_count': sum(row['logicalRegionName'] == region for row in rows)}
             for j, region in enumerate(regions)]
    cases.append({'case': 'absent_scope', 'region': 'unmatched-' + uuid.uuid4().hex,
                  'ids': [], 'expected_count': 0})
    selected = [row for row in rows if row['logicalRegionName'] == regions[0]]
    for n in [1, 2]:
        cases.append({'case': 'ID_scope_' + str(n), 'region': regions[0],
                      'ids': [row['id'] for row in selected[:n]], 'expected_count': n})
    offset = args.server_log.stat().st_size if args.server_log else None
    results = []
    for case in cases:
        proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                               '--repo', str(root), '--worker'],
                              input=json.dumps(case), text=True, capture_output=True, timeout=150)
        if proc.returncode:
            raise RuntimeError('Native worker failed; inspect locally, no raw stderr published')
        results.append(json.loads(proc.stdout))
    statuses = []
    if args.server_log:
        with args.server_log.open('rb') as f:
            f.seek(offset)
            for request, status in re.findall(r'"([^"\n]*)" (\d{3}) ', f.read().decode(errors='replace')):
                match = re.search(r'/instances/([^? ]+)', request)
                statuses.append({'resource': match.group(1) if match else None,
                                 'status': int(status), 'condition_present': 'condition=' in request})
        assert len(statuses) == len(cases) and all(x == {'resource': 'S_X86Server', 'status': 200,
                                                        'condition_present': True} for x in statuses)
    assert {name: sha(root / name) for name in paths} == before and sha(data) == data_sha
    report = {'status': 'PASS' if all(x['PASS'] for x in results) else 'FAIL',
              'scope': 'Native fixed-parameter regression, not a model or competition score',
              'source_hashes': before, 'data_sha256': data_sha, 'cases': results,
              'HTTP_requests': statuses, 'model_calls': 0, 'runtime_patches': False,
              'cache_injection_or_reset': False, 'fixed_sources_and_data_unchanged': True}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'cases': len(cases), 'model_calls': 0}))
    if report['status'] != 'PASS':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
