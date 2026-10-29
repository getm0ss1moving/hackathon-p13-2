"""Bounded native interface experiment, not production orchestration.

Run once in a fresh interpreter and an exclusively reserved original-service log
window. No model calls, executor patching, cache clearing or raw entity output.
"""
import argparse
from collections import Counter
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urlsplit
import uuid


def read_records(root, ci):
    paths = sorted((root / 'output-server/CI+md数据-脱敏-最终-0924').glob(ci + '-*.json'))
    assert paths, 'local_data_missing'
    return [r for p in paths for r in json.loads(p.read_text())['objList']], [
        hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def query_item(ci, table, field, value, output_fields):
    nulls = ', '.join('NULL AS ' + f for f in output_fields + ['_empty'])
    columns = ', '.join('x.' + f + ' AS ' + f for f in output_fields)
    return {'api_call': {'method': 'GET', 'url': '/rest/hackthon/db/instances/' + ci + '?pageNo=1&pageSize=10000',
                         'condition': {'constraint': [{'simple': {'name': field, 'value': value, 'operator': 'equal'}}]}},
            'sql': ('SELECT DISTINCT ' if ci == 'AZONE' else 'SELECT ') + columns +
                   ' FROM (SELECT *, ' + nulls + ' FROM ' + table + ') AS x WHERE x._empty IS NULL'}


def checked_result(output, columns):
    assert output.get('error') is None, 'executor_reported_error'
    result = output.get('result')
    assert isinstance(result, dict) and result.get('columns') == columns, 'missing_or_swallowed_sql_schema'
    rows = result.get('rows')
    assert isinstance(rows, list) and result.get('row_count') == len(rows), 'invalid_result_shape'
    assert all(isinstance(r, dict) and set(r) == set(columns) for r in rows), 'invalid_row_shape'
    return rows


def unique_valid_id(rows):
    if not rows:
        return None, 'empty_catalog'
    values = {r.get('logicalRegionId') for r in rows}
    if len(values) != 1:
        return None, 'ambiguous_catalog'
    value = next(iter(values))
    if not isinstance(value, str) or value != value.strip() or len(value) not in (32, 36):
        return None, 'invalid_id'
    try:
        if uuid.UUID(value).int == 0:
            return None, 'invalid_id'
    except ValueError:
        return None, 'invalid_id'
    return value, 'unique_valid_id'


class LogWindow:
    def __init__(self, path):
        self.path = path
        stat = path.stat()
        self.inode, self.start, self.offset = stat.st_ino, stat.st_size, stat.st_size
        self.events = []

    def idle(self):
        first = self.path.stat()
        time.sleep(1)
        last = self.path.stat()
        assert first.st_ino == last.st_ino == self.inode and first.st_size == last.st_size == self.offset, 'service_log_active_or_rotated'

    def collect(self, ci, field, value):
        deadline = time.monotonic() + 1
        while self.path.stat().st_size == self.offset and time.monotonic() < deadline:
            time.sleep(.02)
        stat = self.path.stat()
        assert stat.st_ino == self.inode and stat.st_size >= self.offset, 'service_log_rotated'
        with self.path.open('rb') as handle:
            handle.seek(self.offset)
            text = handle.read().decode('utf-8', errors='replace')
        self.offset = stat.st_size
        matches = re.findall(r'"([A-Z]+) ([^"\s]+) HTTP/[^"\s]+"\s+(\d+)', text)
        assert len(matches) == 1, 'unexpected_http_count_or_concurrent_activity'
        method, target, status = matches[0]
        url = urlsplit(target)
        query = parse_qs(url.query)
        condition = json.loads(query.get('condition', ['{}'])[0])
        constraints = condition.get('constraint', [])
        filtered = bool(constraints)
        event = {'ci': ci, 'status': int(status), 'unconditional': not filtered,
                 'filter_field': field, 'operator': 'equal'}
        self.events.append(event)
        assert method == 'GET' and url.path == '/rest/hackthon/db/instances/' + ci, 'foreign_http_activity'
        assert len(constraints) == 1 and constraints[0].get('simple') == {
            'name': field, 'value': value, 'operator': 'equal'}, 'wrong_wire_filter'
        assert int(status) == 200, 'http_not_200'
        assert len(self.events) <= 10, 'request_budget_exceeded'
        return event


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--server-log', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert not args.report.exists(), 'preserve_existing_evidence'
    root = args.repo.resolve()
    assert root not in args.report.resolve().parents, 'keep_evidence_outside_repository'
    assert hashlib.sha256((root / 'implementation/runbook_executor.py').read_bytes()).hexdigest() == '4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92', 'unexpected_executor'
    report = {'kind': 'two_stage_location_interface_probe', 'production_integration': False,
              'production_templates_modified': False, 'executor_cache_or_B_patched': False,
              'model_calls': 0, 'maximum_http_requests': 10, 'cases': [], 'passed': False}
    window = None
    try:
        local, hashes = {}, {}
        for ci in ['AZONE', 'S_CloudService', 'S_DeployNode']:
            local[ci], hashes[ci] = read_records(root, ci)
            assert len(local[ci]) < 10000 and all('_empty' not in r for r in local[ci]), 'unbounded_or_reserved_schema'
            assert all(r.get('id') not in (None, '') for r in local[ci]), 'source_id_missing'
        catalog = local['AZONE']
        assert all(r.get('logicalRegionName') and r.get('logicalRegionId') for r in catalog), 'catalog_fields_missing'
        names = sorted({r['logicalRegionName'] for r in catalog})
        assert len(names) == 2, 'scope_not_exactly_two_regions'
        for name in names:
            values = {r['logicalRegionId'] for r in catalog if r['logicalRegionName'] == name}
            assert len(values) == 1 and unique_valid_id([{'logicalRegionId': next(iter(values))}])[0], 'local_catalog_not_unique_valid'
        unknown = 'unresolved-' + uuid.uuid4().hex
        assert unknown not in names
        report['data_sha256'] = hashes
        report['catalog_schema_verified'] = {'ci': 'AZONE', 'fields': ['logicalRegionName', 'logicalRegionId'],
                                              'rows': len(catalog), 'scopes': 2, 'unique_id_per_scope': True}
        report['records_without_logical_region_id'] = {ci: sum(r.get('logicalRegionId') in (None, '') for r in local[ci])
                                                       for ci in ['S_CloudService', 'S_DeployNode']}
        spec = importlib.util.spec_from_file_location('original_location_probe_executor', root / 'implementation/runbook_executor.py')
        executor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(executor)
        assert executor.BASE_URL == 'http://127.0.0.1:8080' and executor.PAGE_SIZE >= max(map(len, local.values())), 'unexpected_original_service_contract'
        report['executor_sha256'] = hashlib.sha256((root / 'implementation/runbook_executor.py').read_bytes()).hexdigest()
        report['sql'] = {'catalog': query_item('AZONE', 'CLOUD_AZONE', 'logicalRegionName', '', ['logicalRegionId'])['sql'],
                         **{ci: query_item(ci, executor.CI_NAME_MAP[ci], 'logicalRegionId', '', ['id', 'logicalRegionId'])['sql']
                            for ci in ['S_CloudService', 'S_DeployNode']}}
        window = LogWindow(args.server_log)
        window.idle()

        def execute_once(ci, field, value, output_fields):
            assert len(window.events) < 10, 'request_budget_exhausted'
            item = query_item(ci, executor.CI_NAME_MAP[ci], field, value, output_fields)
            assert executor._extract_sql_tables(item['sql']) == {executor.CI_NAME_MAP[ci]}, 'extra_sql_api_table'
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                output = executor.execute(item)
            window.collect(ci, field, value)
            assert not stderr.getvalue(), 'executor_emitted_error'
            return checked_result(output, output_fields)

        for index, name in enumerate(names + [unknown], 1):
            is_unknown = name == unknown
            case = {'scope': 'synthetic_unknown' if is_unknown else 'scope_' + str(index),
                    'stage1_http': 0, 'stage2_http': 0, 'targets': []}
            report['cases'].append(case)
            first = execute_once('AZONE', 'logicalRegionName', name, ['logicalRegionId'])
            case['stage1_http'] = 1
            resolved, reason = unique_valid_id(first)
            expected_ids = {r['logicalRegionId'] for r in catalog if r['logicalRegionName'] == name}
            assert {r['logicalRegionId'] for r in first} == expected_ids, 'catalog_result_mismatch'
            case.update(stage1_sql_columns_verified=True, catalog_unique_ids=len(expected_ids), resolution=reason)
            if resolved is None:
                assert is_unknown and not expected_ids, 'unexpected_resolution_failure'
                case['stage2_skipped'] = True
                continue
            assert not is_unknown and expected_ids == {resolved}, 'unexpected_resolution_success'
            for ci in ['S_CloudService', 'S_DeployNode']:
                actual = execute_once(ci, 'logicalRegionId', resolved, ['id', 'logicalRegionId'])
                case['stage2_http'] += 1
                expected = [r for r in local[ci] if r.get('logicalRegionId') == resolved]
                actual_keys = Counter((str(r['id']), str(r['logicalRegionId'])) for r in actual)
                expected_keys = Counter((str(r['id']), str(r['logicalRegionId'])) for r in expected)
                assert actual_keys == expected_keys and len(actual) == len(expected), 'target_membership_or_multiplicity_mismatch'
                case['targets'].append({'ci': ci, 'expected_rows': len(expected), 'actual_rows': len(actual),
                                        'id_set_and_multiplicity_equal': True, 'all_rows_match_resolved_id': True})
        window.idle()
        assert len(window.events) == 7 and report['cases'][-1]['stage2_http'] == 0, 'unexpected_total_or_unknown_http'
        report['passed'] = True
    except Exception as exc:
        report['failure_category'] = str(exc) if isinstance(exc, AssertionError) else type(exc).__name__
    finally:
        events = window.events if window is not None else []
        report['wire_summary'] = {'http_requests': len(events), 'status_counts': dict(Counter(str(e['status']) for e in events)),
                                  'unconditional_requests': sum(e['unconditional'] for e in events),
                                  'by_ci': dict(Counter(e['ci'] for e in events))}
        report['wire_events_without_values_or_urls'] = events
        report['limits'] = ['AZONE is the observed local name-to-ID catalog, not proven globally authoritative or complete.',
                            'Six DeployNode records have no logicalRegionId and remain unassigned; no AZ inference was applied.',
                            'The original executor can collapse failures into empty records; this experiment additionally requires successful wire status, no captured error, verified SQL columns and independent local membership checks.',
                            'B still needs explicit resolution, uniqueness/type validation and fail-closed orchestration before the ID-filtered call. This experiment does not integrate those steps into production.',
                            'No model selection, parameter extraction or full-question answer scoring was run.']
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'wire_summary': report['wire_summary'],
                          'cases': report['cases'], 'failure_category': report.get('failure_category')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
