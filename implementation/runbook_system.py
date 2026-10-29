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

from runbook_retriever import RunbookRetriever
from runbook_matcher import match_runbook, _warm_schema_cache, get_llm
from runbook_executor import execute
from runbook_items import RUNBOOK_ITEMS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class RunbookQuerySystem:
    def __init__(self):
        get_llm()  # 启动时检查配置，不发送模型请求，避免评估时把缺密钥误记为弃权。
        self.items = RUNBOOK_ITEMS
        self.retriever = RunbookRetriever(self.items)
        _warm_schema_cache()

    def query(self, user_question: str, diagnostics: dict = None) -> dict:
        """
        查询入口：用户问题 → 结果。
        diagnostics 为可选的本次查询诊断字典；默认用法和返回结构不变。

        返回：
          {
            "question": 用户问题,
            "matched_runbook": 命中的runbook名称 或 None,
            "sql": 执行的SQL,
            "result": {"columns": [...], "rows": [...], "row_count": N},
            "error": None 或 错误信息
          }
        """
        # 1. BM25 检索 + LLM 选择 + 参数填充
        if diagnostics is None:
            runbook_item = match_runbook(user_question, self.items, self.retriever)
        else:
            runbook_item = match_runbook(user_question, self.items, self.retriever,
                                        diagnostics=diagnostics)

        if runbook_item is None:
            return {
                "question": user_question,
                "matched_runbook": None,
                "sql": None,
                "result": None,
                "error": "未命中任何查询手册",
            }

        logger.info(f"命中 runbook: {runbook_item['name']}")

        # 2. 执行
        if diagnostics is not None:
            diagnostics['execution'] = {'status': 'started', 'input_sql': runbook_item.get('sql')}
        result = execute(runbook_item)
        if diagnostics is not None:
            diagnostics['execution'].update(status='finished', sql=result['sql'], error=result['error'])

        return {
            "question": user_question,
            "matched_runbook": runbook_item["name"],
            "api_call": runbook_item.get("api_call"),
            "sql": result["sql"],
            "result": result["result"],
            "error": result["error"],
        }


if __name__ == "__main__":
    system = RunbookQuerySystem()
    print(f"已加载 {len(system.items)} 个 runbook items")

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"\n问题: {question}")
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
