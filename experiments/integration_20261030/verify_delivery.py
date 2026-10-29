"""同步后的无网络交付复核；不查询模型/数据服务，不重写历史实验结果。"""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path('/Users/duanzeyu/Downloads/hackathon-p13-2')
OUT = Path(__file__).with_name('receipt.json')
WHITE = ROOT / 'CMDB用例集-白盒200.json'
FIXED = ('implementation/evaluator.py', 'implementation/runbook_executor.py')
network_events = []


def deny_network(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo'}:
        network_events.append(event)
        raise RuntimeError('offline verification forbids network')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def frozen_files():
    names = git('ls-tree', '-r', '-z', '--name-only', 'd79c316').decode().strip('\0').split('\0')
    names = [p for p in names if p.startswith('output-server/') or p in FIXED
             or p == WHITE.name]
    current = {p: sha((ROOT / p).read_bytes()) for p in names}
    mismatches = [p for p in names if current[p] != sha(git('show', 'd79c316:' + p))]
    return current, mismatches


def cli(path, args, expected, text):
    # 子进程同样阻止网络；不加载.env.local，移除继承的密钥环境变量。
    code = ("import runpy,sys\n"
            "def block(event,args):\n"
            " if event in {'socket.connect','socket.bind','socket.getaddrinfo'}: raise RuntimeError('network forbidden')\n"
            "sys.addaudithook(block)\n"
            f"sys.argv={repr([str(ROOT / path), *args])}\n"
            f"runpy.run_path({repr(str(ROOT / path))},run_name='__main__')\n")
    env = dict(os.environ)
    env.pop('DEEPSEEK_API_KEY', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    done = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=15)
    combined = done.stdout + done.stderr
    return {'path': path, 'args': args, 'returncode': done.returncode,
            'expected_returncode': expected, 'passed': done.returncode == expected and text in combined,
            'stdout': done.stdout, 'stderr': done.stderr}


def main():
    assert Path.cwd().resolve() == ROOT
    assert Path(__file__).resolve().parents[2] == ROOT
    if OUT.exists():
        raise FileExistsError('保留既有receipt.json；复核不覆盖旧证据')
    sys.addaudithook(deny_network)
    os.environ.pop('DEEPSEEK_API_KEY', None)
    report = {'status': 'FAIL', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'cwd': str(ROOT), 'head': git('rev-parse', 'HEAD').decode().strip(),
              'remote_snapshot': git('rev-parse', 'origin/simple/official-starter').decode().strip(),
              'script_sha256': sha(Path(__file__).read_bytes()), 'checks': {},
              'new_model_http_requests': 0, 'service_started': False, 'key_file_read': False,
              'score_scope': 'historical saved-output replay only; no current-version model score'}
    history = sorted((ROOT / 'experiments/round3').glob('*'))
    history += [ROOT / 'experiments/a_cache_acceptance_20261029/result.json',
                ROOT / 'experiments/a_merge_086_check_20261029.json',
                ROOT / 'experiments/a_merge_086_check_20261029.jsonl',
                ROOT / 'experiments/a_merge_086_negative_region_20261029.json']
    history_before = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in history if p.is_file()}
    sources = sorted((ROOT / 'implementation').glob('*.py'))
    source_before = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}
    try:
        protected, mismatches = frozen_files()
        report['protected'] = {'count': len(protected), 'mismatches': mismatches,
            'manifest_sha256': sha(json.dumps(protected, ensure_ascii=False, sort_keys=True,
                                               separators=(',', ':')).encode()),
            'fixed_modules': {p: protected[p] for p in FIXED}}
        report['checks']['protected_236_match_original'] = len(protected) == 236 and not mismatches
        syntax = sources + sorted((ROOT / 'output-server').glob('*.py'))
        for p in syntax:
            ast.parse(p.read_bytes(), filename=str(p))
        report['syntax_paths'] = [str(p.relative_to(ROOT)) for p in syntax]
        report['source_sha256'] = source_before
        report['checks']['current_root_syntax'] = True

        data = json.loads(WHITE.read_text())['cases']
        saved = json.loads((ROOT / 'experiments/round3/model20.json').read_text())
        summary = json.loads((ROOT / 'experiments/round3/model20_summary.json').read_text())
        sys.path.insert(0, str(ROOT / 'implementation'))
        import evaluator
        from eval_report import EvaluationReport
        assert Path(evaluator.__file__).resolve() == ROOT / FIXED[0]
        evaluations = [evaluator.evaluate_case(case, old['output'], old['elapsed_s'])
                       for case, old in zip(data[:20], saved['cases'])]
        originals = [old['evaluation'] for old in saved['cases']]
        source_matches = all(sha(git('show', saved['base_commit'] + ':implementation/' + p)) == h
                             for p, h in saved['implementation_sha256'].items())
        same_order = [c['case_id'] for c in data[:20]] == [c['case_id'] for c in saved['cases']]
        requests = saved['requests']
        token_sum = sum(r['usage']['total_tokens'] for r in requests)
        report['historical_model20'] = {
            'base_commit': saved['base_commit'], 'complete': saved['status'] == 'complete',
            'cases': len(evaluations), 'replayed_score': sum(e['score'] for e in evaluations),
            'full_evaluation_dicts_equal': evaluations == originals, 'case_order_equal': same_order,
            'frozen_sources_match_git_objects': source_matches,
            'case_file_sha256_equal': saved['case_file_sha256'] == sha(WHITE.read_bytes()),
            'http_attempts': len(requests), 'http_limit': saved['http_limit'],
            'http_status_counts': dict(Counter(str(r['status']) for r in requests)),
            'requested_model': saved['model'],
            'reported_model_counts': dict(Counter(r['model'] for r in requests)),
            'total_tokens_recounted': token_sum, 'tls_verified': saved['tls_verified'],
            'current_implementation_differs': source_before != {
                'implementation/' + p: h for p, h in saved['implementation_sha256'].items()},
            'official_score': False, 'new_model_requests': 0}
        report['checks']['saved_20_scores_and_request_totals'] = all([
            same_order, source_matches, evaluations == originals, saved['completed'] == 20,
            len(requests) == saved['http_attempts'] == summary['http_attempts'] == 53,
            token_sum == summary['token_usage']['total_tokens'] == 51505,
            sum(e['score'] for e in evaluations) == summary['score_sum'] == 75.5,
            saved['tls_verified'], saved['status'] == 'complete',
            saved['case_file_sha256'] == sha(WHITE.read_bytes())])

        with tempfile.TemporaryDirectory(prefix='p13-report-replay-') as tmp:
            full, stopped = Path(tmp) / 'complete.jsonl', Path(tmp) / 'incomplete.jsonl'
            with EvaluationReport(full, WHITE, 20) as handle:
                for case, old, evaluation in zip(data[:20], saved['cases'], evaluations):
                    handle.record(case, old['output'], evaluation, old['elapsed_s'],
                                  diagnostics={'historical_saved_output_replay': True})
                handle.complete()
            raw = full.read_bytes()
            lines = [json.loads(line) for line in raw.decode().splitlines()]
            try:
                with EvaluationReport(full, WHITE, 20):
                    raise AssertionError('existing report was reopened')
            except FileExistsError:
                pass
            with EvaluationReport(stopped, WHITE, 20) as handle:
                handle.record(data[0], saved['cases'][0]['output'], evaluations[0], saved['cases'][0]['elapsed_s'])
                handle.stop_reason = 'offline_replay_stop_test'
            partial = json.loads(stopped.read_text().splitlines()[-1])
            report['report_writer_replay'] = {
                'complete_records': len(lines), 'summary': lines[-1], 'incomplete_summary': partial,
                'existing_report_preserved': full.read_bytes() == raw,
                'recorded_evaluations_equal': [r['evaluation'] for r in lines if r['type'] == 'case'] == evaluations,
                'temporary_reports_removed': True, 'current_model_run': False}
            report['checks']['current_report_complete_incomplete_and_no_overwrite'] = all([
                len(lines) == 22, lines[-1]['status'] == 'complete',
                lines[-1]['total_score'] == 75.5, lines[-1]['completed_cases'] == 20,
                partial['status'] == 'incomplete', partial['completed_cases'] == 1,
                partial['max_score'] == 5, full.read_bytes() == raw,
                report['report_writer_replay']['recorded_evaluations_equal']])

        specs = [('implementation/quick_eval.py', ['--help'], 0, '--report'),
                 ('implementation/blackbox_eval.py', ['--help'], 0, '--report'),
                 ('implementation/quick_eval.py', ['0'], 2, 'N 必须为正整数'),
                 ('implementation/quick_eval.py', ['201'], 2, '超过实际用例数'),
                 ('implementation/quick_eval.py', ['20'], 2, 'DEEPSEEK_API_KEY'),
                 ('implementation/blackbox_eval.py', ['1'], 2, '黑盒用例文件缺失'),
                 ('experiments/a_cache_acceptance_20261029/verify.py', [], 2, '历史验收输入已变化')]
        report['cli'] = [cli(*spec) for spec in specs]
        report['checks']['changed_entrypoints_fail_safely_without_network'] = all(r['passed'] for r in report['cli'])
        archive = ROOT / 'experiments/a_cache_acceptance_20261029/queries.json'
        expected = '37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0'
        report['cache_input_archive'] = {'path': str(archive.relative_to(ROOT)),
            'sha256': sha(archive.read_bytes()), 'rows': len(json.loads(archive.read_text())),
            'original_input_untouched': sha((ROOT / '.a-vocab-gt4hyfg2/queries.json').read_bytes()) == expected,
            'old_result_preserved': True, 'performance_reexecuted': False}
        report['checks']['tracked_cache_input_matches_frozen_hash'] = sha(archive.read_bytes()) == expected
        after, mismatches = frozen_files()
        report['checks']['protected_and_business_sources_unchanged'] = protected == after and not mismatches and all(
            sha((ROOT / p).read_bytes()) == h for p, h in source_before.items())
        report['checks']['historical_evidence_unchanged'] = all(
            sha((ROOT / p).read_bytes()) == h for p, h in history_before.items())
        report['historical_sha256'] = history_before
        report['checks']['network_attempts_zero'] = not network_events
        report['status'] = 'PASS_SCOPED_OFFLINE_INTEGRATION' if all(report['checks'].values()) else 'FAIL'
    except Exception as exc:
        report['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
    report['network_events'] = network_events
    report['not_run'] = ['current-version model evaluation', 'full 200 model questions', 'official blackbox',
                         'new retrieval/performance suite', 'service/API tests', 'official score aggregation']
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({k: report[k] for k in ('status', 'checks', 'new_model_http_requests')}, ensure_ascii=False))
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
