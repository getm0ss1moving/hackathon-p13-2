"""加载本机132配置运行官方入口，或显式复用C的逐题诊断；--check不调用模型。"""

import argparse
import ast
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

from check_official_integrity import require_official_files


ROOT = Path(__file__).resolve().parents[1]


def read_environment(path, allowed):
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, raw = line.partition("=")
        name = name.strip().removeprefix("export ")
        if not separator or not allowed(name):
            continue
        parts = shlex.split(raw, comments=True)
        if len(parts) > 1:
            raise ValueError(f"配置项 {name} 需要用引号包裹含空格的值")
        values[name] = parts[0] if parts else ""
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="?", type=int, default=200, help="原白盒前N题，默认200")
    parser.add_argument("--check", action="store_true", help="只检查132模板、依赖、密钥配置和本地服务")
    parser.add_argument("--diagnostics", action="store_true",
                        help="改用既有C诊断入口保存完整逐题JSONL；评分仍用原evaluate_case")
    args = parser.parse_args()
    if not 1 <= args.cases <= 200:
        parser.error("题数必须在1至200之间")

    try:
        for package in ("openai", "httpx", "requests"):
            if importlib.util.find_spec(package) is None:
                raise ValueError("缺少查询依赖，请使用项目的 .venv/bin/python")
        require_official_files(ROOT)
        tree = ast.parse((ROOT / "implementation/runbook_items.py").read_text(encoding="utf-8"))
        items = next(ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "RUNBOOK_ITEMS"
                             for target in node.targets))
        if len(items) != 132 or len({item["id"] for item in items}) != 132:
            raise ValueError("当前目录未加载132条唯一模板，评测未启动")
        sys.path.insert(0,str(ROOT/'implementation'))
        from runbook_matcher import _verify_a132_sources
        from runbook_bootable_native import sources as bootable_sources
        _,_,runtime_variant=_verify_a132_sources(ROOT)
        bootable_sources()
        environment = os.environ.copy()
        environment.update(read_environment(ROOT / ".env.local", lambda name: name in {
            "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}))
        environment.update(read_environment(ROOT / "configs/train150_v18.env", lambda name:
                                            name.startswith(("RUNBOOK_", "DEEPSEEK_"))))
        environment.update({
            "RUNBOOK_A132_CANDIDATE": "1",
            "RUNBOOK_MAX_LLM_CALLS": str(min(args.cases * 3,450)),
            "RUNBOOK_COMPLETE_DETAIL_COUNT": "1",
            "RUNBOOK_GROUND_SQL_MEASURES": "1",
            "RUNBOOK_PARTIAL_STORAGE_POOLS": "1",
            "RUNBOOK_SG_RULE_SEMIJOIN": "1",
            "RUNBOOK_VERIFIED_EMPTY_ROOT": "1",
            "RUNBOOK_TYPED_EMPTY_ROOT": "1",
            "RUNBOOK_EMPTY_ANSWER_FALLBACK": "1",
            "RUNBOOK_PRESERVE_SPARSE_NULLS": "0",
            "RUNBOOK_BIND_DEPLOY_NODE_REGION": "1",
            "RUNBOOK_ISSUE3_CONTRACTS": "1",
            "RUNBOOK_ISSUE3_PROFILES": json.dumps(["namespace_counts","tenant_lists","vdc_network"]),
            "RUNBOOK_A132_NATIVE_BOOTABLE": "1",
        })
        if not environment.get("DEEPSEEK_API_KEY", "").strip():
            raise ValueError("本机未配置DEEPSEEK_API_KEY，请在.env.local配置；不要发送密钥")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8080/rest/hackthon/db/schema/VM_NOVA", timeout=3) as response:
            schema = json.load(response)
        if schema.get("ci_name") != "VM_NOVA" or not schema.get("columns"):
            raise ValueError("8080端口不是预期的原版数据服务")
    except (ValueError, OSError, StopIteration, SyntaxError) as exc:
        # 不输出第三方异常正文，避免意外回显配置内容。
        safe_message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        print(f"预检未通过：{safe_message}", file=sys.stderr)
        print("如服务未启动，请另开终端执行：.venv/bin/python output-server/data_server.py --host 127.0.0.1 --port 8080", file=sys.stderr)
        return 1

    description = (f"132模板；原白盒前{args.cases}题；{environment['DEEPSEEK_MODEL']}；"
                   f"thinking={environment['RUNBOOK_THINKING_MODE']}；"
                   f"最多{environment['RUNBOOK_MAX_LLM_CALLS']}次模型请求；猜空兜底开启")
    print(description, flush=True)
    print('检索配对：'+runtime_variant,flush=True)
    print("入口：" + ("C诊断（原评分函数）" if args.diagnostics else "官方quick_eval（原文件）"), flush=True)
    print("A合同启用：" + ", ".join(json.loads(environment["RUNBOOK_ISSUE3_PROFILES"])), flush=True)
    print("原生bootable合同：开启（保留原文region/AZ；不转换管理VM布尔类型）", flush=True)
    if args.check:
        print("预检通过，未调用模型。", flush=True)
        return 0

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S_%f")
    log_path = reports / f"a132_whitebox{args.cases}_{timestamp}.log"
    print(f"结果日志：{log_path}", flush=True)
    command = [sys.executable, "-u", "-B", str(ROOT / "implementation/quick_eval.py"), str(args.cases)]
    if args.diagnostics:
        detail_path = reports / f"a132_whitebox{args.cases}_{timestamp}.jsonl"
        command = [sys.executable, "-u", "-B", str(ROOT / "C/quick_eval_diagnostics.py"),
                   str(args.cases), "--report", str(detail_path)]
        print(f"逐题诊断：{detail_path}", flush=True)
    with log_path.open("x", encoding="utf-8") as log:
        log.write(description + "\n")
        log.flush()
        child = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        try:
            for line in child.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return child.wait()
        except KeyboardInterrupt:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
            child.wait()
            print(f"\n评测已中断，已有日志保留：{log_path}", file=sys.stderr)
            return 130
        finally:
            child.stdout.close()


if __name__ == "__main__":
    raise SystemExit(main())
