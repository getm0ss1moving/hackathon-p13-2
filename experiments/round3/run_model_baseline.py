"""在原 quick_eval 上限量运行；不改变选择、填参、SQL 或评分逻辑。"""
import argparse
import contextlib
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import platform
import shlex
import ssl
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


class StopRun(BaseException):
    """穿透业务层的 Exception 回退，防止超预算后继续查询。"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_local_key():
    if os.environ.get('DEEPSEEK_API_KEY', '').strip():
        return
    for line in (ROOT / '.env.local').read_text().splitlines():
        line = line.strip().removeprefix('export ')
        if not line.startswith('DEEPSEEK_API_KEY='):
            continue
        values = shlex.split(line.split('=', 1)[1], comments=True)
        if len(values) != 1 or not values[0].strip():
            raise ValueError('本机密钥配置格式无效（内容已隐藏）')
        os.environ['DEEPSEEK_API_KEY'] = values[0]
        return
    raise ValueError('本机密钥配置缺失（不显示文件内容）')


def ready():
    conn = http.client.HTTPConnection('127.0.0.1', 8080, timeout=2)
    try:
        conn.request('GET', '/rest/hackthon/db/schema/VM_NOVA')
        response = conn.getresponse()
        data = json.loads(response.read())
        return response.status == 200 and data.get('ci_name') == 'VM_NOVA'
    except (OSError, ValueError):
        return False
    finally:
        conn.close()


def start_service():
    if ready():
        return None
    proc = subprocess.Popen([sys.executable, str(ROOT / 'output-server/data_server.py'),
                             '--host', '127.0.0.1', '--port', '8080'], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError('本任务数据服务启动失败；未关闭其他进程')
        if ready():
            return proc
        time.sleep(0.2)
    proc.terminate()
    proc.wait(timeout=10)
    raise RuntimeError('本任务数据服务启动超时')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-20', action='store_true', help='仅在用户已批准本轮20题后使用')
    parser.add_argument('--self-check', action='store_true', help='仅运行零网络预算守卫检查')
    args = parser.parse_args()
    import httpx

    class BudgetTransport(httpx.BaseTransport):
        def __init__(self, inner, limit=60):
            self.inner, self.limit = inner, limit
            self.attempts, self.failures = [], 0

        def handle_request(self, request):
            if request.url.scheme != 'https' or request.url.host != 'api.deepseek.com':
                raise StopRun('模型目标地址不在本轮批准范围')
            if len(self.attempts) >= self.limit:
                raise StopRun('已到60次HTTP尝试上限')
            record = {'attempt': len(self.attempts) + 1, 'case_id': active.get('case_id')}
            self.attempts.append(record)
            try:
                response = self.inner.handle_request(request)
                response.read()
            except Exception as exc:
                record['error_type'] = type(exc).__name__
                self.failures += 1
                if self.failures >= 3:
                    raise StopRun('连续3次模型网络故障') from None
                raise
            record['status'] = response.status_code
            self.failures = 0 if 200 <= response.status_code < 300 else self.failures + 1
            if response.is_success:
                try:
                    body = response.json()
                    record['model'] = body.get('model')
                    record['usage'] = {k: v for k, v in body.get('usage', {}).items()
                                       if isinstance(v, (int, float))}
                except ValueError:
                    record['usage_unavailable'] = True
            if self.failures >= 3:
                raise StopRun('连续3次模型HTTP错误')
            return response

        def close(self):
            self.inner.close()

    active = {}
    if args.self_check:
        count = []
        transport = BudgetTransport(httpx.MockTransport(lambda r: (count.append(1) or
                                    httpx.Response(200, json={'usage': {'total_tokens': 1}}))), limit=2)
        request = httpx.Request('POST', 'https://api.deepseek.com/chat/completions')
        transport.handle_request(request)
        transport.handle_request(request)
        try:
            transport.handle_request(request)
            raise AssertionError('上限未阻断')
        except StopRun:
            assert len(count) == 2
        try:
            transport.handle_request(httpx.Request('POST', 'http://example.invalid'))
            raise AssertionError('错误目标未阻断')
        except StopRun:
            assert len(count) == 2
        faulty = BudgetTransport(httpx.MockTransport(lambda r: httpx.Response(503)))
        faulty.handle_request(request)
        faulty.handle_request(request)
        try:
            faulty.handle_request(request)
            raise AssertionError('连续故障未阻断')
        except StopRun:
            assert len(faulty.attempts) == 3
        print('预算上限、错误目标、连续故障：3项零网络检查通过')
        return 0
    if not args.approved_20:
        parser.error('缺少本轮20题调用批准标记')
    if Path.cwd().resolve() != ROOT:
        parser.error('必须从指定仓库根目录运行')
    load_local_key()
    sys.path.insert(0, str(ROOT / 'implementation'))
    import runbook_matcher as matcher
    import runbook_system as system_module
    import evaluator
    import quick_eval
    original_client = matcher.get_llm()
    ca_file = os.environ.get('SSL_CERT_FILE')
    verify = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
    assert verify.check_hostname and verify.verify_mode == ssl.CERT_REQUIRED
    transport = BudgetTransport(httpx.HTTPTransport(verify=verify, retries=0))
    client = httpx.Client(transport=transport, timeout=60.0, trust_env=False)
    matcher._llm_client = original_client.with_options(http_client=client)
    cases = json.loads((ROOT / 'CMDB用例集-白盒200.json').read_text())['cases'][:20]
    query_original = system_module.RunbookQuerySystem.query
    evaluate_original = evaluator.evaluate_case
    rows = []

    def query(system, question):
        index = len(rows)
        active['case_id'] = cases[index]['case_id']
        active['requests_start'] = len(transport.attempts)
        retrieve_original = system.retriever.retrieve
        def retrieve(*args, **kwargs):
            candidates = retrieve_original(*args, **kwargs)
            active['candidates'] = [vars(c) for c in candidates]
            return candidates
        system.retriever.retrieve = retrieve
        try:
            return query_original(system, question)
        finally:
            system.retriever.retrieve = retrieve_original

    def evaluate(case, output, elapsed):
        result = evaluate_original(case, output, elapsed)
        rows.append({'case_id': case['case_id'], 'question': case['question'],
                     'elapsed_s': elapsed, 'evaluation': result, 'output': output,
                     'candidates': active['candidates'],
                     'http_attempts': len(transport.attempts) - active['requests_start']})
        return result

    system_module.RunbookQuerySystem.query = query
    evaluator.evaluate_case = evaluate
    proc, exit_code, stop_reason = None, 1, None
    text_output = io.StringIO()
    started = time.time()
    try:
        proc = start_service()
        with contextlib.redirect_stdout(text_output), contextlib.redirect_stderr(text_output):
            exit_code = quick_eval.main(['20'])
    except StopRun as exc:
        stop_reason = str(exc)
    except Exception as exc:
        stop_reason = type(exc).__name__  # 不打印可能包含认证配置的异常内容
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)
        matcher._llm_client.close()
        original_client.close()
    status = 'complete' if exit_code == 0 and len(rows) == 20 else 'interrupted'
    report = {'status': status, 'stop_reason': stop_reason, 'completed': len(rows),
              'planned': 20, 'http_limit': 60, 'http_attempts': len(transport.attempts),
              'http_count_semantics': 'transport admitted attempts; connection failures included; SDK retries counted',
              'model': matcher.DEEPSEEK_MODEL, 'base_url': matcher.DEEPSEEK_BASE_URL,
              'tls_verified': True, 'python': platform.python_version(),
              'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'started_unix': started, 'wall_s': time.time() - started,
              'case_file_sha256': digest(ROOT / 'CMDB用例集-白盒200.json'),
              'implementation_sha256': {p.name: digest(p) for p in sorted((ROOT / 'implementation').glob('*.py'))},
              'runner_sha256': digest(Path(__file__)),
              'query_timing': 'original quick_eval timer; startup excluded; minimal capture overhead included',
              'cache': 'new process; schema warmed; executor API cache reused across ordered cases',
              'score_sum': sum(row['evaluation']['score'] for row in rows),
              'cases': rows, 'requests': transport.attempts,
              'official_score': False}
    (Path(__file__).parent / 'model20.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    # 原入口日志仅含逐题分数，不包含请求/响应原文；不保存认证头、prompt 或密钥。
    (Path(__file__).parent / 'model20.txt').write_text(text_output.getvalue())
    print(json.dumps({k: report[k] for k in ['status', 'completed', 'http_attempts', 'score_sum', 'stop_reason']}, ensure_ascii=False))
    return 0 if status == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
