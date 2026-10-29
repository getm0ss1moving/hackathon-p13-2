#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Runbook 查询系统主入口。

流程：
  1. 加载 runbook items
  2. 构建 BM25 检索器
  3. 接收用户问题 → BM25 检索 → LLM 选择 → 参数填充 → 执行器执行
"""

import json
import logging
import os
import sys
import time

from runbook_retriever import RunbookRetriever
from runbook_matcher import match_runbook, _warm_schema_cache, get_llm, get_llm_events
from runbook_executor import execute
from runbook_items import RUNBOOK_ITEMS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class RunbookQuerySystem:
    def __init__(self):
        get_llm()  # 仅检查客户端配置，不发送模型请求。
        self.items = RUNBOOK_ITEMS
        started = time.perf_counter()
        self.retriever = RunbookRetriever(self.items)
        indexed_at = time.perf_counter()
        _warm_schema_cache()
        self.initialization_metrics = {
            "index_seconds": round(indexed_at - started, 6),
            "schema_warm_seconds": round(time.perf_counter() - indexed_at, 6),
            "template_count": len(self.items),
        }

    def query(self, user_question: str) -> dict:
        """
        查询入口：用户问题 → 结果。

        返回：
          {
            "question": 用户问题,
            "matched_runbook": 命中的runbook名称 或 None,
            "sql": 执行的SQL,
            "result": {"columns": [...], "rows": [...], "row_count": N},
            "error": None 或 错误信息
          }
        """
        started = time.perf_counter()
        first_event = len(get_llm_events())
        # 1. BM25 检索 + LLM 选择 + 参数填充
        match_details = {}
        runbook_item = match_runbook(user_question, self.items, self.retriever, match_details)
        matched_at = time.perf_counter()
        diagnostics = {
            "match_seconds": round(matched_at - started, 4),
            "execute_seconds": 0.0,
            "llm_calls": get_llm_events()[first_event:],
            "matching": match_details,
        }

        if runbook_item is None:
            return {
                "question": user_question,
                "matched_runbook": None,
                "sql": None,
                "result": None,
                "error": "未命中任何查询手册",
                "diagnostics": diagnostics,
            }

        logger.info(f"命中 runbook: {runbook_item['name']}")

        # 2. 执行
        result = execute(runbook_item)
        diagnostics["execute_seconds"] = round(time.perf_counter() - matched_at, 4)

        return {
            "question": user_question,
            "matched_runbook": runbook_item["name"],
            "api_call": runbook_item.get("api_call"),
            "sql": result["sql"],
            "result": result["result"],
            "error": result["error"],
            "diagnostics": diagnostics,
        }


if __name__ == "__main__":
    system = RunbookQuerySystem()
    print(f"已加载 {len(system.items)} 个 runbook items")

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"\n问题: {question}")
        result = system.query(question)
        print(f"命中: {result['matched_runbook']}")
        print("诊断: " + json.dumps(result["diagnostics"], ensure_ascii=False))
        if result["error"]:
            print(f"错误: {result['error']}")
        elif result["result"]:
            r = result["result"]
            if isinstance(r, dict):
                print(f"行数: {r.get('row_count', 0)}")
                if r.get("rows"):
                    print(f"列: {r['columns']}")
                    for row in r["rows"][:5]:
                        print(f"  {row}")
            elif isinstance(r, list):
                for i, sub in enumerate(r):
                    print(f"步骤{i+1}: {sub.get('row_count', 0)} 行")
    else:
        # 交互模式
        while True:
            try:
                question = input("\n请输入查询问题（q退出）: ").strip()
                if question.lower() in ("q", "quit", "exit"):
                    break
                if not question:
                    continue
                result = system.query(question)
                print(f"命中: {result['matched_runbook']}")
                if result["error"]:
                    print(f"错误: {result['error']}")
                elif result["result"]:
                    r = result["result"]
                    if isinstance(r, dict):
                        print(f"行数: {r.get('row_count', 0)}")
                        if r.get("rows"):
                            print(f"列: {r['columns']}")
                            for row in r["rows"][:5]:
                                print(f"  {row}")
                    elif isinstance(r, list):
                        for i, sub in enumerate(r):
                            print(f"步骤{i+1}: {sub.get('row_count', 0)} 行")
            except KeyboardInterrupt:
                break
