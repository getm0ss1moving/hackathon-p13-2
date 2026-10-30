"""检查本地环境、只读快照与可选的数据服务；不调用大模型。"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import ssl
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-server", action="store_true")
    args = parser.parse_args()
    errors = []
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    for package in ("openai", "httpx", "requests"):
        try:
            print(f"{package}: {importlib.metadata.version(package)}")
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"缺少依赖：{package}")
    manifest = json.loads((HERE / "baseline_manifest.json").read_text(encoding="utf-8"))
    checked = 0
    for relative, expected in manifest["readonly_files"].items():
        path = HERE / relative
        if not path.is_file():
            errors.append(f"缺少文件：{relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"只读快照内容发生变化：{relative}")
        else:
            checked += 1
    print(f"只读快照校验：{checked}/{len(manifest['readonly_files'])}")
    for relative, source in manifest.get("component_sources", {}).items():
        print(f"已交接组件：{relative} ← {source['source_commit'][:7]}")
    print("DEEPSEEK_API_KEY：" + ("已配置（不显示）" if os.environ.get("DEEPSEEK_API_KEY") else "未配置"))
    try:
        import httpx
        with httpx.Client(verify=ssl.create_default_context(), trust_env=True):
            pass
        print("模型 HTTP 客户端：TLS/代理配置初始化成功（未发送请求）")
    except Exception as exc:
        errors.append(f"模型 HTTP 客户端初始化失败：{type(exc).__name__}")
    try:
        # 本地服务不经 HTTP 代理；仅进行只读 schema 请求。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8080/rest/hackthon/db/schema/VM_NOVA", timeout=2) as response:
            data = json.load(response)
        if data.get("ci_name") != "VM_NOVA" or not data.get("columns"):
            raise ValueError("8080 返回的不是预期 CMDB schema")
        print(f"数据服务：可用，VM_NOVA {data['row_count']} 行")
    except Exception as exc:
        print(f"数据服务：未就绪（{type(exc).__name__}）")
        if args.require_server:
            errors.append("请先启动 output-server/data_server.py")
    for error in errors:
        print("ERROR:", error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
