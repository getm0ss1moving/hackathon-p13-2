import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import http.client
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from uuid import uuid4
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[2]
_LABEL = "白盒"
_DATASET = "white"
_DEFAULT_N = 20
_CASE_FILE = "CMDB用例集-白盒200.json"


class ModelRequestStop(BaseException):
    """Hard stop must pass through business-level Exception fallbacks."""


class RequestGuard:
    def __init__(self, client, base_url, limit):
        self.client = client
        self.endpoint = urlsplit(base_url)
        self.limit = limit
        self.events = []
        self.case_id = None
        self.hooks = client._client.event_hooks
        self.hooks.setdefault('request', []).append(self.before)
        self.hooks.setdefault('response', []).append(self.after)

    def before(self, request):
        target = urlsplit(str(request.url))
        if (target.scheme, target.hostname, target.port) != (self.endpoint.scheme, self.endpoint.hostname, self.endpoint.port) or target.scheme != 'https':
            raise ModelRequestStop('unexpected_model_endpoint')
        if request.method != 'POST' or not target.path.rstrip('/').endswith('/chat/completions'):
            raise ModelRequestStop('unexpected_model_operation')
        if len(self.events) >= self.limit:
            raise ModelRequestStop('model_http_limit_reached')
        payload = json.loads(request.content)
        self.events.append({'attempt': len(self.events)+1, 'case_id': self.case_id,
                            'model': payload.get('model'),
                            'max_output_tokens': payload.get('max_tokens', payload.get('max_completion_tokens', 'provider default')),
                            'temperature': payload.get('temperature', 'provider default'),
                            'thinking': payload.get('thinking', 'provider default'), 'status': None})

    def after(self, response):
        # Requests are synchronous; failed attempts without a response remain status=None.
        if self.events:
            self.events[-1]['status'] = response.status_code
            try:
                response.read()
                payload = response.json()
                self.events[-1]['response_model'] = payload.get('model')
                usage = payload.get('usage') or {}
                self.events[-1]['usage'] = {key: usage[key] for key in
                    ('prompt_tokens', 'completion_tokens', 'total_tokens') if key in usage}
            except (ValueError, AttributeError):
                pass  # Non-JSON errors still count as HTTP attempts; SDK handles their response.

    def detach(self):
        self.hooks['request'].remove(self.before)
        self.hooks['response'].remove(self.after)


def _install_guard(limit):
    matcher = sys.modules.get('runbook_matcher')
    if matcher is None or not callable(getattr(matcher, 'get_llm', None)):
        raise RuntimeError('无法核实模型客户端，不能安装请求硬上限')
    return RequestGuard(matcher.get_llm(), matcher.DEEPSEEK_BASE_URL, limit)


def _peak_memory_mib():
    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged',
                    'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
            data = Counters()
            data.cb = ctypes.sizeof(data)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
            if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(data), data.cb):
                return None
            return round(data.peak_working / 1048576, 3)
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1048576 if sys.platform == 'darwin' else 1024), 3)
    except (ImportError, OSError, AttributeError):
        return None


def _redact(value):
    """Only persist selected diagnostic fields; mask the locally configured key."""
    if isinstance(value, str):
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        return value.replace(key, "[REDACTED]") if key else value
    if isinstance(value, dict):
        return {str(k): _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=_ROOT,
                                       stderr=subprocess.DEVNULL, timeout=5).decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _outcome(reason):
    # The official reason describes answer quality before time deductions.
    if "API条件不合规" in reason:
        return "api_condition_missing"
    for prefix, category in [("答案正确", "correct"), ("部分正确", "partial"),
                             ("答案错误", "wrong"), ("错误:", "execution_error"),
                             ("不回答", "abstained")]:
        if reason.startswith(prefix):
            return category
    return "unclassified"


def _diagnostics(output):
    raw = output.get("diagnostics") or {}
    if not isinstance(raw, dict):
        return None
    result = {k: raw[k] for k in ("match_seconds", "execute_seconds")
              if type(raw.get(k)) in (int, float) and math.isfinite(raw[k])}
    calls = raw.get("llm_calls")
    if isinstance(calls, list):
        result["llm_calls"] = [
            {k: event[k] for k in ("stage", "status", "seconds", "prompt_tokens", "completion_tokens")
             if k in event} for event in calls if isinstance(event, dict)]
    matching = raw.get("matching")
    if isinstance(matching, dict):
        fields = ("retrieval_seconds", "candidate_ids", "candidates", "selected_template", "template_sql",
                  "filled_parameter_names", "parameter_sources", "sql_before_refine", "sql_after_refine",
                  "reason", "resource_coverage", "resource_lookup", "projection_contract")
        result["matching"] = {key: matching[key] for key in fields if key in matching}
    return result or None


def _row_counts(answer):
    if isinstance(answer, dict):
        return answer.get("row_count", len(answer.get("rows", [])))
    if isinstance(answer, list):
        return [_row_counts(part) for part in answer]
    return None


def _detail(case, output, result, elapsed):
    output = output if isinstance(output, dict) else {}
    reason = result["reason"]
    return _redact({
        "case_id": case["case_id"], "question": case["question"],
        "score": result["score"], "reason": reason, "outcome": _outcome(reason),
        "elapsed_seconds": round(elapsed, 6),
        "time_penalty": (3 if elapsed > 6 else 1) if "[超时>" in reason else 0,
        "matched_runbook": output.get("matched_runbook"),
        "api_call": output.get("api_call"), "sql": output.get("sql"),
        "expected_row_count": _row_counts(case.get("answer")),
        "actual_row_count": _row_counts(output.get("result")),
        "actual_columns": (output.get("result") or {}).get("columns") if isinstance(output.get("result"), dict) else None,
        "diagnostics": _diagnostics(output),
    })


def _summary(details, requested):
    times = sorted(d["elapsed_seconds"] for d in details)
    count = len(details)
    score = round(sum(d["score"] for d in details), 3)
    call_lists = [d["diagnostics"]["llm_calls"] for d in details
                  if isinstance(d.get("diagnostics"), dict)
                  and isinstance(d["diagnostics"].get("llm_calls"), list)]
    return {
        "requested_cases": requested, "completed_cases": count, "total_score": score,
        "max_score_completed": count * 5,
        "score_percent_completed": round(score / (count * 5) * 100, 3) if count else None,
        "outcomes": dict(Counter(d["outcome"] for d in details)),
        "time_penalized_cases": sum(d["time_penalty"] > 0 for d in details),
        "time_penalty_points": sum(d["time_penalty"] for d in details),
        "mean_seconds": round(sum(times) / count, 6) if count else None,
        "p95_seconds": times[math.ceil(count * .95) - 1] if count else None,
        "max_seconds": times[-1] if count else None,
        "p50_seconds": times[math.ceil(count * .5) - 1] if count else None,
        "over_4s": sum(t > 4 for t in times), "over_6s": sum(t > 6 for t in times),
        "full_credit_answers_untimed": sum(d["score"] + d["time_penalty"] == 5 for d in details),
        "cases_with_llm_call_diagnostics": len(call_lists),
        "recorded_llm_calls": sum(map(len, call_lists)) if call_lists else None,
    }


def _write_report(path, report):
    """Checkpoint after each question, outside the official query timer."""
    report["summary"] = _summary(report["details"], report["requested_cases"])
    report['summary']['peak_process_memory_mib'] = _peak_memory_mib()
    report['summary']['process_cpu_seconds'] = round(time.process_time() - report['cpu_start_seconds'], 6) if 'cpu_start_seconds' in report else None
    report['summary']['memory_scope'] = 'evaluation process high-water RSS/working set; separate data service excluded'
    if "requests" in report:
        report['http_attempts'] = len(report['requests'])
        report['response_models'] = sorted({e['response_model'] for e in report['requests'] if e.get('response_model')})
        if report['requests']:
            first = report['requests'][0]
            for key in ('model', 'max_output_tokens', 'temperature', 'thinking'):
                report[key] = first[key]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(_redact(report), ensure_ascii=False, indent=2,
                                    allow_nan=False), encoding="utf-8")
    temporary.replace(path)
    csv_path = path.with_name(path.stem + "-failures.csv")
    temporary_csv = csv_path.with_name(csv_path.name + ".tmp")
    fields = ["case_id", "question", "outcome", "score", "elapsed_seconds", "time_penalty",
              "reason", "matched_runbook", "expected_row_count", "actual_row_count"]
    with temporary_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for detail in report["details"]:
            if detail["score"] == 5:
                continue
            row = {field: detail.get(field) for field in fields}
            # Keep diagnostic text as text when opened in a spreadsheet.
            for field, value in row.items():
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                    row[field] = "'" + value
            writer.writerow(row)
    temporary_csv.replace(csv_path)


def _checkpoint(path, report):
    try:
        _write_report(path, report)
        return True
    except (OSError, TypeError, ValueError) as exc:
        print(f"报告保存失败（{type(exc).__name__}），已停止评估；请检查输出路径", file=sys.stderr)
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{_LABEL}单次本地诊断，不代表正式成绩")
    parser.add_argument("N", nargs="?", type=int, help=f"运行前 N 题，默认 {_DEFAULT_N}；指定 case-set 时运行完整集合")
    parser.add_argument("--implementation-dir", type=Path, default=_ROOT / "implementation",
                        help="待评测实现目录；默认仓库根 implementation，可指定 B/implementation")
    parser.add_argument("--report", type=Path, help="JSON 报告路径；同时生成失败 CSV，默认存入 C/reports")
    parser.add_argument("--cases-file", type=Path, help="独立派生用例文件，原用例不覆盖")
    parser.add_argument("--case-set", type=Path, help="冻结的 case_ids JSON，保持其顺序")
    parser.add_argument("--round", type=int, help="多轮冻结清单的本轮编号；每轮单独启动、单独报告")
    parser.add_argument("--max-requests", type=int, help="实际模型 HTTP 尝试硬上限，SDK 重试也计数")
    args = parser.parse_args(argv)
    if args.N is not None and args.N < 1:
        parser.error("N 必须为正整数")
    if args.round is not None and not args.case_set:
        parser.error('--round 仅与冻结的 --case-set 一起使用')

    test_file = args.cases_file or _ROOT / _CASE_FILE
    if not os.path.isfile(test_file):
        parser.error(f"{_LABEL}用例文件缺失: {test_file}；当前不能运行{_LABEL}评估")
    try:
        with open(test_file, encoding="utf-8") as f:
            all_cases = json.load(f)["cases"]
    except (OSError, ValueError, KeyError) as exc:
        parser.error(f"无法加载{_LABEL}用例: {exc}")
    if len({case["case_id"] for case in all_cases}) != len(all_cases):
        parser.error("用例文件包含重复 case_id")
    if args.case_set:
        try:
            selection = json.loads(args.case_set.read_text(encoding="utf-8"))
            ids = selection["case_ids"]
            case_map = {case["case_id"]: case for case in all_cases}
            if not ids or len(set(ids)) != len(ids) or not set(ids) <= set(case_map):
                raise ValueError("题目ID为空、重复或不存在")
            if selection.get("dataset_sha256") != _sha256(test_file):
                raise ValueError("冻结题集与实际用例的哈希不一致")
            if args.N is not None:
                raise ValueError("N 与 --case-set 不能同时指定")
            rounds = selection.get('repeats', 1)
            if rounds > 1 and (args.round is None or not 1 <= args.round <= rounds):
                raise ValueError(f"此清单要求{rounds}轮，请用 --round 1..{rounds} 分别启动并保留独立报告")
            if rounds == 1 and args.round not in (None, 1):
                raise ValueError("此清单只计划1轮")
            all_cases = [case_map[cid] for cid in ids]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f"冻结题集加载失败: {exc}")
    args.N = len(all_cases) if args.case_set else (args.N if args.N is not None else _DEFAULT_N)
    if args.N > len(all_cases):
        parser.error(f"N={args.N} 超过实际用例数 {len(all_cases)}")
    cases = all_cases[:args.N]

    implementation_dir = args.implementation_dir.resolve()
    if not (implementation_dir / "runbook_system.py").is_file():
        parser.error(f"待评测实现缺少 runbook_system.py: {implementation_dir}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = (args.report or _ROOT / "C" / "reports" / f"{_DATASET}-{stamp}-{uuid4().hex[:8]}.json").resolve()
    if report_path.suffix.lower() != ".json":
        parser.error("--report 必须使用 .json 扩展名")
    if report_path.exists() or report_path.with_name(report_path.stem + "-failures.csv").exists():
        parser.error("报告文件已存在，请使用新文件名保留前后结果")
    # Always grade with the unchanged official scorer from the repository root.
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("c_official_evaluator", _ROOT / "implementation" / "evaluator.py")
    evaluator = module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    evaluate_case = evaluator.evaluate_case
    sys.path.insert(0, str(implementation_dir))

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        parser.error("请先在本机配置 DEEPSEEK_API_KEY；不要在聊天、代码或日志中发送密钥")
    if args.max_requests is None or args.max_requests < 1:
        parser.error("真实模型运行必须显式指定正整数 --max-requests；该参数不是调用授权")

    connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=2)
    try:
        connection.request("GET", "/rest/hackthon/db/schema/VM_NOVA")
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("schema HTTP 状态异常")
        schema = json.loads(response.read())
        if (not isinstance(schema, dict) or schema.get("ci_name") != "VM_NOVA"
                or not isinstance(schema.get("columns"), list) or not schema["columns"]
                or not all(isinstance(column, str) for column in schema["columns"])
                or type(schema.get("row_count")) is not int or schema["row_count"] < 0):
            raise ValueError("schema 结构异常")
    except (OSError, http.client.HTTPException, ValueError, TypeError) as exc:
        print(f"本地数据服务未就绪（{type(exc).__name__}），评估未开始；请先启动 127.0.0.1:8080 的原数据服务", file=sys.stderr)
        return 1
    finally:
        connection.close()

    try:
        from runbook_system import RunbookQuerySystem
    except ImportError as exc:
        parser.error(f"查询依赖导入失败: {exc}；请使用已安装依赖的虚拟环境")

    logging.disable(logging.CRITICAL)
    sources = ["runbook_system.py", "runbook_matcher.py", "runbook_items.py", "runbook_retriever.py"]
    dependencies = {}
    for package in ("openai", "httpx", "requests"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    worktree = _git("status", "--porcelain")
    report = {
        "format_version": 1, "kind": "local_single_run_diagnostic", "dataset": "derived" if args.cases_file else _DATASET,
        "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_cases": len(cases), "repeats_per_case": 1,
        "case_ids": [case["case_id"] for case in cases],
        "implementation_dir": str(implementation_dir), "python_version": platform.python_version(),
        "dependencies": dependencies,
        "git_commit": _git("rev-parse", "HEAD"), "git_branch": _git("branch", "--show-current"),
        "git_worktree_dirty": bool(worktree) if worktree is not None else None,
        "source_sha256": {name: _sha256(implementation_dir / name) for name in sources},
        "dataset_sha256": _sha256(test_file), "runner_sha256": _sha256(Path(__file__)),
        "scorer_sha256": _sha256(_ROOT / "implementation" / "evaluator.py"),
        "case_set_sha256": _sha256(args.case_set) if args.case_set else None,
        "round_index": args.round or 1,
        "planned_rounds": selection.get('repeats', 1) if args.case_set else 1,
        "http_limit": args.max_requests,
        "cache_policy": "one system process; schema warmup excluded; executor API cache shared in recorded case order",
        "template_count": None,
        "cpu_start_seconds": time.process_time(),
        "limits": "每题一次；未应用正式重复平均、黑白加权或模板数量分；不自动推断 A/B 根因。",
        "details": [],
    }
    if not _checkpoint(report_path, report):
        return 1
    guard = None
    try:
        guard = _install_guard(args.max_requests)
        report['requests'] = guard.events
        system = RunbookQuerySystem()
    except (Exception, ModelRequestStop) as exc:
        report.update(status="aborted", abort={"phase": "initialization", "exception_type": type(exc).__name__,
                      "stop_reason": str(exc) if isinstance(exc, ModelRequestStop) else None},
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
        _checkpoint(report_path, report)
        if guard:
            guard.detach()
        print(f"系统初始化失败（{type(exc).__name__}），评估未开始", file=sys.stderr)
        return 1
    report["template_count"] = len(system.items) if hasattr(system, "items") else None
    matcher = sys.modules.get("runbook_matcher")
    report["model"] = getattr(matcher, "DEEPSEEK_MODEL", None)
    report["base_url"] = getattr(matcher, "DEEPSEEK_BASE_URL", None)
    report["thinking"] = "provider default"
    report["temperature"] = "provider default"
    report["max_output_tokens"] = None  # Set from observed request payload; do not guess from env.
    client = getattr(matcher, "_llm_client", None)
    report["sdk_max_retries"] = getattr(client, "max_retries", None)
    report["request_limit_declared"] = os.environ.get("RUNBOOK_MAX_LLM_CALLS")

    print(f"待评测实现：{implementation_dir}")
    print(f"报告：{report_path}")
    print(f"本地诊断：{_LABEL}前 {len(cases)} 题，每题 1 次；不含正式重复平均、黑白加权或模板数量分。")
    for index, case in enumerate(cases):
        guard.case_id = case['case_id']
        t0 = time.perf_counter()
        phase = "query"
        try:
            output = system.query(case["question"])
            elapsed = time.perf_counter() - t0
            phase = "grading"
            result = evaluate_case(case, output, elapsed)
            detail = _detail(case, output, result, elapsed)
        except (Exception, KeyboardInterrupt, ModelRequestStop) as exc:
            report.update(status="aborted", abort={"phase": phase, "case_id": case["case_id"],
                          "exception_type": type(exc).__name__,
                          "stop_reason": str(exc) if isinstance(exc, ModelRequestStop) else None},
                          finished_at_utc=datetime.now(timezone.utc).isoformat())
            _checkpoint(report_path, report)
            guard.detach()
            print(f"{case['case_id']}: 查询异常（{type(exc).__name__}）；评估中止，已完成 {index}/{len(cases)} 题，未生成完整基线", file=sys.stderr)
            return 130 if isinstance(exc, KeyboardInterrupt) else 1
        report["details"].append(detail)
        if not _checkpoint(report_path, report):
            guard.detach()
            return 1
        print(f"{case['case_id']}: {result['score']:+} ({detail['reason'][:70]}) [{elapsed:.1f}s]")

    report.update(status="completed", finished_at_utc=datetime.now(timezone.utc).isoformat())
    if not _checkpoint(report_path, report):
        guard.detach()
        return 1
    guard.detach()
    summary = report["summary"]
    print(f"\n=== {len(cases)} cases: score={summary['total_score']}/{len(cases)*5}, "
          f"outcomes={summary['outcomes']}, time_penalized={summary['time_penalized_cases']}, "
          f"pct={summary['score_percent_completed']:.1f}% ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
