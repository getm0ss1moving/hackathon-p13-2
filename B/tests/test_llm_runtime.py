"""请求边界和失败处理回归；使用内存 HTTP transport，不连接模型服务。"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as matcher


def completion(text="1", finish_reason="stop"):
    return {"id": "local-test", "object": "chat.completion", "created": 0,
            "model": "deepseek-chat",
            "choices": [{"index": 0, "finish_reason": finish_reason,
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        events = patch.object(matcher, "_llm_events", [])
        events.start()
        self.addCleanup(events.stop)

    def client(self, handler):
        client = OpenAI(api_key="local-test-only", base_url="https://local-test.invalid/v1",
                        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        replacement = patch.object(matcher, "_llm_client", client)
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_request_limit_blocks_before_next_request(self):
        requests_seen = []

        def handler(request):
            requests_seen.append(request)
            return httpx.Response(200, json=completion())

        self.client(handler)
        with patch.dict(os.environ, {"RUNBOOK_MAX_LLM_CALLS": "2"}):
            self.assertEqual(matcher.llm_ask("test", "select"), "1")
            matcher.llm_ask("test", "fill")
            with self.assertRaisesRegex(RuntimeError, "模型请求上限"):
                matcher.llm_ask("must not be sent", "refine")
        self.assertEqual(len(requests_seen), 2)
        self.assertEqual([e["stage"] for e in matcher.get_llm_events()], ["select", "fill"])

    def test_truncated_output_is_not_used(self):
        self.client(lambda request: httpx.Response(200, json=completion("SELECT", "length")))
        with patch.dict(os.environ, {"RUNBOOK_MAX_LLM_CALLS": "1"}):
            with self.assertRaisesRegex(RuntimeError, "截断"):
                matcher.llm_ask("test", "refine")
        self.assertEqual(matcher.get_llm_events()[0]["status"], "error")

    def test_failed_request_consumes_budget_without_retry(self):
        requests_seen = []

        def handler(request):
            requests_seen.append(request)
            return httpx.Response(503, json={"error": {"message": "local failure"}})

        self.client(handler)
        with patch.dict(os.environ, {"RUNBOOK_MAX_LLM_CALLS": "1"}):
            with self.assertRaises(Exception):
                matcher.llm_ask("test", "select")
            with self.assertRaisesRegex(RuntimeError, "模型请求上限"):
                matcher.llm_ask("must not be sent", "select")
        self.assertEqual(len(requests_seen), 1)
        self.assertEqual(matcher.get_llm_events()[0]["status"], "error")

    def test_missing_key_fails_before_network(self):
        with patch.object(matcher, "_llm_client", None), patch.object(matcher, "DEEPSEEK_API_KEY", ""):
            with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
                matcher.get_llm()
        self.assertEqual(matcher.get_llm_events(), [])


if __name__ == "__main__":
    unittest.main()
