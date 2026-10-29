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

_ROOT = Path(__file__).resolve().parents[2]
_LABEL = "白盒"
_DATASET = "white"
_DEFAULT_N = 20
_CASE_FILE = "CMDB用例集-白盒200.json"


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
        "cases_with_llm_call_diagnostics": len(call_lists),
        "recorded_llm_calls": sum(map(len, call_lists)) if call_lists else None,
    }


def _write_report(path, report):
    """Checkpoint after each question, outside the official query timer."""
    report["summary"] = _summary(report["details"], report["requested_cases"])
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
    parser.add_argument("N", nargs="?", type=int, default=_DEFAULT_N, help=f"运行前 N 题，默认 {_DEFAULT_N}")
    parser.add_argument("--implementation-dir", type=Path, default=_ROOT / "implementation",
                        help="待评测实现目录；默认仓库根 implementation，可指定 B/implementation")
    parser.add_argument("--report", type=Path, help="JSON 报告路径；同时生成失败 CSV，默认存入 C/reports")
    args = parser.parse_args(argv)
    if args.N < 1:
        parser.error("N 必须为正整数")

    test_file = _ROOT / _CASE_FILE
    if not os.path.isfile(test_file):
        parser.error(f"{_LABEL}用例文件缺失: {test_file}；当前不能运行{_LABEL}评估")
    try:
        with open(test_file, encoding="utf-8") as f:
            all_cases = json.load(f)["cases"]
    except (OSError, ValueError, KeyError) as exc:
        parser.error(f"无法加载{_LABEL}用例: {exc}")
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
        "format_version": 1, "kind": "local_single_run_diagnostic", "dataset": _DATASET,
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
        "template_count": None,
        "limits": "每题一次；未应用正式重复平均、黑白加权或模板数量分；不自动推断 A/B 根因。",
        "details": [],
    }
    if not _checkpoint(report_path, report):
        return 1
    try:
        system = RunbookQuerySystem()
    except Exception as exc:
        report.update(status="aborted", abort={"phase": "initialization", "exception_type": type(exc).__name__},
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
        _checkpoint(report_path, report)
        print(f"系统初始化失败（{type(exc).__name__}），评估未开始", file=sys.stderr)
        return 1
    report["template_count"] = len(system.items) if hasattr(system, "items") else None

    print(f"待评测实现：{implementation_dir}")
    print(f"报告：{report_path}")
    print(f"本地诊断：{_LABEL}前 {len(cases)} 题，每题 1 次；不含正式重复平均、黑白加权或模板数量分。")
    for index, case in enumerate(cases):
        t0 = time.perf_counter()
        phase = "query"
        try:
            output = system.query(case["question"])
            elapsed = time.perf_counter() - t0
            phase = "grading"
            result = evaluate_case(case, output, elapsed)
            detail = _detail(case, output, result, elapsed)
        except (Exception, KeyboardInterrupt) as exc:
            report.update(status="aborted", abort={"phase": phase, "case_id": case["case_id"],
                          "exception_type": type(exc).__name__},
                          finished_at_utc=datetime.now(timezone.utc).isoformat())
            _checkpoint(report_path, report)
            print(f"{case['case_id']}: 查询异常（{type(exc).__name__}）；评估中止，已完成 {index}/{len(cases)} 题，未生成完整基线", file=sys.stderr)
            return 130 if isinstance(exc, KeyboardInterrupt) else 1
        report["details"].append(detail)
        if not _checkpoint(report_path, report):
            return 1
        print(f"{case['case_id']}: {result['score']:+} ({detail['reason'][:70]}) [{elapsed:.1f}s]")

    report.update(status="completed", finished_at_utc=datetime.now(timezone.utc).isoformat())
    if not _checkpoint(report_path, report):
        return 1
    summary = report["summary"]
    print(f"\n=== {len(cases)} cases: score={summary['total_score']}/{len(cases)*5}, "
          f"outcomes={summary['outcomes']}, time_penalized={summary['time_penalized_cases']}, "
          f"pct={summary['score_percent_completed']:.1f}% ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
