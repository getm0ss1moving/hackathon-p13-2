"""冻结 A 的 1928514 与 B 快照作独立兼容检查；不替换 B 文件，不调用外部模型。"""

import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import requests

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "implementation"))
import runbook_matcher as matcher
import runbook_system as system_module
from runbook_items import RUNBOOK_ITEMS


def git_file(ref, path):
    return subprocess.check_output(["git", "show", ref + ":" + path], cwd=HERE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_module(name, source):
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, name, "exec"), module.__dict__)
    return module


def quantile(values, q):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * q) - 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "experiments/a_cache_20261029_integration.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖已有集成记录")
    old_source = git_file("5b677ef", "B/implementation/runbook_retriever.py")
    a_source = git_file("1928514", "implementation/runbook_retriever.py")
    items_source = (HERE / "implementation/runbook_items.py").read_bytes()
    if items_source != git_file("1928514", "implementation/runbook_items.py"):
        parser.error("A 与 B 模板库不同，不能将差异只归于缓存")
    query_source = git_file("1a72007", "experiments/round3/queries.json")
    queries = json.loads(query_source)
    plan_source = (HERE / "experiments/resource_gate_20261029_plan.json").read_bytes()
    for case in json.loads(plan_source)["derived_cases"]:
        queries.append({"id": case["case_id"], "question": case["question"], "kind": "B_derived_control"})
    baseline = load_module("b_frozen_retriever", old_source)
    candidate = load_module("a_frozen_cached_retriever", a_source)
    retrievers = {"B_snapshot": baseline.RunbookRetriever(RUNBOOK_ITEMS),
                  "A_1928514": candidate.RunbookRetriever(RUNBOOK_ITEMS)}
    item_by_id = {item["id"]: item for item in RUNBOOK_ITEMS}
    before = {name: sha(json.dumps([doc.tokens for doc in obj._docs]).encode()) for name, obj in retrievers.items()}
    comparisons = []
    for query in queries:
        results = {name: [asdict(c) for c in obj.retrieve(query["question"])] for name, obj in retrievers.items()}
        prompts = [matcher._format_runbook_list([item_by_id[c["id"]] for c in results[name]]) for name in retrievers]
        comparisons.append({"query_id": query["id"], "kind": query["kind"],
                            "same_candidates": results["B_snapshot"] == results["A_1928514"],
                            "same_candidate_prompt": prompts[0] == prompts[1], "candidates": results["A_1928514"]})

    # 固定八轮，交替先后顺序；仅测本机检索，不与先前真实模型运行并发。
    timings = {name: [] for name in retrievers}
    round_totals = {name: [] for name in retrievers}
    for round_index in range(8):
        order = list(retrievers) if round_index % 2 == 0 else list(reversed(retrievers))
        for name in order:
            durations = []
            for query in queries:
                t0 = time.perf_counter()
                retrievers[name].retrieve(query["question"])
                durations.append(time.perf_counter() - t0)
            timings[name].extend(durations)
            round_totals[name].append(sum(durations))
    immutable = all(before[name] == sha(json.dumps([doc.tokens for doc in obj._docs]).encode()) for name, obj in retrievers.items())

    # 在进程内只替换 B 系统的检索器类，原 B 文件、manifest 和模型复测基线保持原样。
    # 允许本地数据服务以及内存 MockTransport，拒绝真实外部 HTTP，代理亦不能绕过目标 URL 检查。
    blocked = []
    original_send = httpx.Client.send
    original_request = requests.Session.request

    def local(url):
        parsed = urlparse(str(url))
        return parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 8080

    def guarded_send(client, request, *call_args, **call_kwargs):
        if not isinstance(client._transport, httpx.MockTransport) and not local(request.url):
            blocked.append({"library": "httpx", "host": request.url.host})
            raise AssertionError("集成回归禁止外部网络")
        return original_send(client, request, *call_args, **call_kwargs)

    def guarded_request(session, method, url, *call_args, **call_kwargs):
        if not local(url):
            blocked.append({"library": "requests", "host": urlparse(str(url)).hostname})
            raise AssertionError("集成回归禁止外部网络")
        return original_request(session, method, url, *call_args, **call_kwargs)

    captured = io.StringIO()
    items_before = sha(json.dumps(RUNBOOK_ITEMS, ensure_ascii=False).encode())
    with patch.object(system_module, "RunbookRetriever", candidate.RunbookRetriever), \
         patch.object(httpx.Client, "send", guarded_send), patch.object(requests.Session, "request", guarded_request), \
         redirect_stdout(captured):
        suite = unittest.defaultTestLoader.discover(str(HERE / "tests"))
        tested = unittest.TextTestRunner(stream=captured, verbosity=1).run(suite)
    benchmark = {name: {"observations": len(values), "rounds": 8,
                        "p50_ms": statistics.median(values) * 1000, "p95_ms": quantile(values, .95) * 1000,
                        "max_ms": max(values) * 1000, "round_total_seconds": round_totals[name]}
                 for name, values in timings.items()}
    summary = {"queries": len(queries), "identical_candidates": sum(row["same_candidates"] for row in comparisons),
               "identical_candidate_prompts": sum(row["same_candidate_prompt"] for row in comparisons),
               "document_tokens_unchanged": immutable,
               "template_objects_unchanged": items_before == sha(json.dumps(RUNBOOK_ITEMS, ensure_ascii=False).encode()),
               "unit_tests": tested.testsRun, "unit_failures": len(tested.failures), "unit_errors": len(tested.errors),
               "unit_skipped": len(tested.skipped), "blocked_external_attempts": blocked,
               "external_model_network_requests": 0}
    summary["compatible_in_tested_scope"] = (
        summary["identical_candidates"] == len(queries) and summary["identical_candidate_prompts"] == len(queries)
        and immutable and summary["template_objects_unchanged"] and tested.wasSuccessful() and not tested.skipped and not blocked)
    result = {"baseline_ref": "5b677ef:B/implementation/runbook_retriever.py", "a_ref": "1928514:implementation/runbook_retriever.py",
              "b_matcher_sha256": sha((HERE / "implementation/runbook_matcher.py").read_bytes()),
              "baseline_retriever_sha256": sha(old_source), "a_retriever_sha256": sha(a_source),
              "template_sha256": sha(items_source), "a_frozen_queries_sha256": sha(query_source),
              "b_derived_plan_sha256": sha(plan_source), "script_sha256": sha(Path(__file__).read_bytes()),
              "runtime_injection": "A retriever class in B system during mocked-model tests only; no B implementation files changed",
              "summary": summary, "benchmark": benchmark, "comparisons": comparisons, "unit_output": captured.getvalue(),
              "limitations": "Frozen known queries; compatibility and local retrieval microbenchmark only; no fresh model or end-to-end performance claim; not official blackbox."}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False))
    print(json.dumps(benchmark, ensure_ascii=False))
    return 0 if summary["compatible_in_tested_scope"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
