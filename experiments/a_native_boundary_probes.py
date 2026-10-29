"""Local, no-model reproduction of dependency and GET-length boundaries.

Start the original local service separately. Use a quiet service/log window.
Run each command in a fresh interpreter; this never clears or injects a cache.
Only aggregate measurements are written, never entity values or raw URLs.
"""
import argparse
import ast
import copy
import contextlib
import hashlib
import importlib
import io
import json
import platform
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit
import uuid


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--mode', choices=['empty-step', 'long-url', 'native'], required=True)
    parser.add_argument('--template-id', required=True)
    parser.add_argument('--empty-param')
    parser.add_argument('--params-json', type=Path, help='Optional local parameter dictionary; never published')
    parser.add_argument('--server-log', type=Path, help='Original service access log, exclusive measurement window')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error('Refuse to overwrite evidence')
    root = args.repo.resolve()
    impl = root / 'implementation'
    paths = [impl / 'runbook_items.py', impl / 'runbook_executor.py', root / 'output-server/data_server.py']
    before = {str(p.relative_to(root)): sha(p) for p in paths}
    if before['implementation/runbook_executor.py'] != '4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92':
        raise RuntimeError('This reproducer is pinned to the documented original executor')
    tree = ast.parse(paths[0].read_text(encoding='utf-8'))
    node = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'RUNBOOK_ITEMS' for t in n.targets))
    item = copy.deepcopy(next(i for i in ast.literal_eval(node) if i['id'] == args.template_id))
    bindings = dict(item.get('default_params', {}))
    if args.params_json:
        bindings.update(json.loads(args.params_json.read_text(encoding='utf-8')))
    if args.mode == 'empty-step':
        if not args.empty_param:
            parser.error('--empty-param is required for empty-step')
        assert '{{' + args.empty_param + '}}' in json.dumps(item['api_call'][0])
        bindings[args.empty_param] = 'unmatched-a-probe-' + uuid.uuid4().hex
    if not all(isinstance(v, str) for v in bindings.values()):
        raise ValueError('Native reproduction requires explicitly encoded string parameters')
    sys.path.insert(0, str(impl))
    executor = importlib.import_module('runbook_executor')
    assert Path(executor.__file__).resolve() == impl / 'runbook_executor.py'
    assert executor.BASE_URL == 'http://127.0.0.1:8080' and len(executor._cache) == 0
    import requests
    if requests.utils.get_environ_proxies(executor.BASE_URL):
        raise RuntimeError('Refuse to route local data through an environment proxy')
    item['params'] = {'condition': [{'name': k, 'value': v} for k, v in bindings.items()]}
    item['api_call'] = executor._replace_placeholders(item['api_call'], bindings)
    offset = args.server_log.stat().st_size if args.server_log else None
    report = {'mode': args.mode, 'template': args.template_id, 'model_calls': 0,
              'source_hashes': before, 'runtime_patches': False, 'cache_reset_or_injection': False,
              'client_versions': {'python': platform.python_version(), 'requests': requests.__version__},
              'effective_environment_proxy_present': False,
              'competition_score': 'NOT COMPUTED; no reference answer is embedded'}
    native_logs = io.StringIO()

    def native_execute(payload):
        with contextlib.redirect_stderr(native_logs), contextlib.redirect_stdout(native_logs):
            return executor.execute(payload)

    if args.mode != 'long-url':
        output = native_execute(item)
        report.update(native_execute_calls=1, native_error_present=bool(output.get('error')),
                      result_row_count=(output.get('result') or {}).get('row_count'))
        observations = []
        for key, records in executor._cache.items():
            ci, raw = key.split('::', 1)
            conditions = json.loads(raw)
            observations.append({'resource': ci, 'condition_fields': [c['key'] for c in conditions],
                                 'condition_count': len(conditions), 'records': len(records)})
        report['passive_native_cache_observations'] = observations
    else:
        calls = item['api_call']
        if not isinstance(calls, list) or len(calls) < 2:
            raise ValueError('A dependent second API is required')
        ci = calls[0]['url'].split('/')[-1].split('?')[0]
        table = executor.CI_NAME_MAP.get(ci, ci)
        first = native_execute({'api_call': calls[0], 'sql': 'SELECT * FROM ' + table})
        if first.get('error'):
            raise RuntimeError('First native projection failed')
        records = first['result']['rows']
        constraints = []
        sizes = {}
        for entry in (calls[1].get('condition') or {}).get('constraint', []):
            simple = entry.get('simple', {})
            value, operator = simple.get('value', ''), simple.get('operator', 'equal')
            match = re.fullmatch(r'\{\{(.+?)\s+from\s+step\s+1\}\}', str(value), re.I)
            if match:
                values = list(set(r[match.group(1)] for r in records if r.get(match.group(1))))
                if not values:
                    raise RuntimeError('No nonempty dependency values for URL reproduction')
                sizes[simple['name']] = len(values)
                value = values if len(values) > 1 else values[0]
                operator = 'in' if len(values) > 1 or operator == 'in' else 'equal'
            elif '{{' in str(value):
                raise RuntimeError('Unresolved parameter; refusing a broader request')
            clause = {'simple': {'name': simple['name'], 'value': value, 'operator': operator}}
            if constraints:
                clause['logOp'] = 'and'
            constraints.append(clause)
        ci2 = calls[1]['url'].split('/')[-1].split('?')[0]
        endpoint = 'relations' if ci2.startswith(('R_', 'M_')) else 'instances'
        url = (executor.BASE_URL + '/rest/hackthon/db/' + endpoint + '/' + ci2
               + '?pageNo=1&pageSize=' + str(executor.PAGE_SIZE)
               + '&condition=' + quote(json.dumps({'constraint': constraints}, ensure_ascii=False)))
        import requests
        prepared = requests.Request('GET', url).prepare()
        target = urlsplit(prepared.url).path + '?' + urlsplit(prepared.url).query
        response = requests.get(prepared.url, timeout=15)
        report.update(native_execute_calls=1, direct_GET_calls=1, HTTP_status=response.status_code,
                      condition_fields=[c['simple']['name'] for c in constraints],
                      condition_count=len(constraints), dependency_value_counts=sizes,
                      encoded_absolute_URL_bytes=len(prepared.url.encode('utf-8')),
                      encoded_request_target_bytes=len(target.encode('utf-8')),
                      request_line_bytes=len(('GET ' + target + ' HTTP/1.1\r\n').encode('utf-8')),
                      effective_environment_proxy_present=bool(requests.utils.get_environ_proxies(prepared.url)))
    if args.server_log:
        with args.server_log.open('rb') as f:
            f.seek(offset)
            text = f.read().decode('utf-8', errors='replace')
        requests_seen = []
        for line, status in re.findall(r'"([^"\n]*)" (\d{3}) ', text):
            resource = re.search(r'/(?:instances|relations)/([^? ]+)', line)
            requests_seen.append({'resource': resource.group(1) if resource else None,
                                  'status': int(status), 'has_condition': 'condition=' in line})
        report['actual_service_requests'] = requests_seen
        report['HTTP_count_scope'] = 'Exclusive access-log window required; rejected long URI can have no parsed resource'
    else:
        report['HTTP_count_scope'] = 'NOT MEASURED; no service log provided'
    assert {str(p.relative_to(root)): sha(p) for p in paths} == before
    report['native_log_lines_captured_without_raw_output'] = len(native_logs.getvalue().splitlines())
    report['fixed_sources_unchanged'] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'written': True, 'mode': args.mode, 'model_calls': 0,
                      'source_unchanged': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
