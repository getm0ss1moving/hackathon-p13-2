"""运行并保存仅训练范围的免费单元检查；禁止真实网络，旧输出不覆盖。"""
import argparse
import contextlib
import json
import logging
import re
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bounded", action="store_true", help="额外运行原分批执行器16项合成检查")
    parser.add_argument("--test-module", action="append", help="只跑指定training测试模块/类/方法，可重复；省略时保持原免费全套")
    args = parser.parse_args()
    if args.test_module and any(not re.fullmatch(r'test_training_[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){0,2}', name) for name in args.test_module):
        parser.error('仅允许指定已有test_training_模块、类或方法')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "implementation"), str(ROOT / "scripts")]
    suite = (unittest.defaultTestLoader.loadTestsFromNames(args.test_module) if args.test_module else
             unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_training_*.py"))
    if args.bounded:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName("test_bounded_api"))
    attempts = []
    def blocked(*values, **options):
        attempts.append(True)
        raise AssertionError("免费检查禁止真实网络")
    root_logger = logging.getLogger()
    old_handlers = root_logger.handlers[:]
    runtime_log = logging.FileHandler(out / "runtime.log", mode="x")
    root_logger.handlers = [runtime_log]
    try:
        with (out / "unittest.log").open("x") as stream, (out / "console.log").open("x") as console:
            with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console), patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked), patch.object(socket, "create_connection", blocked):
                result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        root_logger.handlers = old_handlers
        runtime_log.close()
    summary = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "socket_attempts": len(attempts),
               "model_requests": 0, "success": result.wasSuccessful() and not attempts,
               "command": [sys.executable, *sys.argv], "project": str(ROOT)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
