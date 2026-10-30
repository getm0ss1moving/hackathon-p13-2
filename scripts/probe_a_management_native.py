"""隔离验证A管理VM新合同的真实采集/投影/SQL；不注册模板、不调用模型或评分。"""
import argparse
from contextlib import closing
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'implementation'), str(ROOT/'scripts')]
from check_official_integrity import require_official_files
from runbook_issue3 import NativeReader, _local_readonly_identity


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', required=True)
    parser.add_argument('--question', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT/'experiments/issue3_management_vm_20261030'
    manifest = json.loads((source/'MANIFEST.json').read_text())
    files = {source/'MANIFEST.json': sha(source/'MANIFEST.json')}
    for name, expected in manifest['files'].items():
        path = source/name
        if sha(path) != expected:
            raise ValueError('A management source changed: '+name)
        files[path] = expected
    for path in [Path(__file__), ROOT/'implementation/runbook_issue3.py',
                 ROOT/'implementation/runbook_executor.py',
                 ROOT/'experiments/b_issue3_runtime_20261031/SOURCE_MANIFEST.json']:
        files[path] = sha(path)
    report = {'mode': 'isolated_A_contract_native_probe_not_B_query_or_model_score',
              'model_requests': 0, 'template_registered': False, 'production_enabled': False,
              'official_integrity': require_official_files(ROOT),
              'source_sha256': {str(p.relative_to(ROOT)): value for p, value in files.items()}}
    with zipfile.ZipFile(out/'source.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(path.relative_to(ROOT)))
    spec = importlib.util.spec_from_file_location('_B_management_native_probe', source/'candidate.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    params = {'view': module.VIEW, 'logicalRegionName': args.region, 'ip_role': 'both_raw',
              'capacity_mode': 'per_volume_raw_and_numeric_summary'}
    preparation = {}
    plan = module.prepare_candidate(args.question,
        {'id': module.FAMILY_ID, 'family_id': module.FAMILY_ID}, params, preparation)
    report.update(question=args.question, parameters=params, preparation=preparation)
    if plan is None:
        report['status'] = 'original_question_rejected'
    else:
        (out/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
        execution = {}; receipts = {}; reader = NativeReader(execution)
        try:
            if plan['transport']['status'] != 'within_local_core_bound':
                raise ValueError('A_expanded_core_length_blocked')
            before = _local_readonly_identity(reader.base)
            for call in plan['api_call']:
                snap = reader.fetch(call)
                receipts[snap['ci']] = {'ok': True, 'http_status': 200,
                    'request': snap['request'], 'schema': snap['columns'],
                    'schema_verified': True, 'pages': snap['pages']}
            if _local_readonly_identity(reader.base) != before:
                raise ValueError('native_service_source_changed')
            tables, diagnostics = module.preflight(params, receipts)
            columns = plan['prepared_schema'][module.TABLE]
            integer_fields = {'management', 'declared_values_complete',
                              'unknown_service_link_count', 'unknown_size_reference_count'}
            with closing(sqlite3.connect(':memory:')) as connection:
                connection.execute('CREATE TABLE '+module.TABLE+' ('+','.join(
                    '"'+column+'" '+('INTEGER' if column in integer_fields else 'TEXT')
                    for column in columns)+')')
                connection.executemany('INSERT INTO '+module.TABLE+' VALUES ('+
                    ','.join('?' for _ in columns)+')',
                    [[row[column] for column in columns] for row in tables[module.TABLE]])
                cursor = connection.execute(plan['sql'])
                names = [column[0] for column in cursor.description]
                rows = [dict(zip(names, row)) for row in cursor.fetchall()]
            if names != list(module.OUTPUT):
                raise ValueError('A_result_columns_changed')
            if _local_readonly_identity(reader.base) != before:
                raise ValueError('native_service_source_changed_after_SQL')
            report.update(status='native_preflight_and_SQL_passed', SQL_executed=True,
                          projection_loaded_not_raw=True, source_snapshot=before,
                          diagnostics=diagnostics, row_count=len(rows), columns=names,
                          declared_complete_VM_count=sum(row['declared_values_complete'] for row in rows))
            (out/'native_result.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
        except Exception as error:
            report.update(status='blocked', error_type=type(error).__name__, reason=str(error))
        finally:
            reader.close(); report['execution'] = execution
            with gzip.open(out/'actual_receipts.json.gz', 'wt', encoding='utf-8') as stream:
                json.dump(receipts, stream, ensure_ascii=False)
    (out/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items()
                     if key not in {'source_sha256', 'official_integrity', 'execution', 'columns', 'question'}},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
