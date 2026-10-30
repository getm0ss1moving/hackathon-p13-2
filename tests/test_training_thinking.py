"""DeepSeek模式请求合同与用量诊断，合成SDK对象、零网络。"""

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m


class ThinkingContractTests(unittest.TestCase):
    def response(self,finish="stop",reasoning="internal fixture",details=True):
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=30,completion_tokens=20,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=16) if details else None),
            system_fingerprint="fixture-config",choices=[SimpleNamespace(finish_reason=finish,
            message=SimpleNamespace(content="SELECT 1",reasoning_content=reasoning))])

    def call(self,mode,response):
        create=Mock(return_value=response)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.dict(os.environ,{"RUNBOOK_THINKING_MODE":mode,"RUNBOOK_MAX_LLM_CALLS":"1",
                "RUNBOOK_MAX_OUTPUT_TOKENS":"1024"}),patch.object(m,"get_llm",return_value=client), \
                patch.object(m,"_llm_events",[]):
            result=m.llm_ask("synthetic prompt",stage="refine")
            events=m.get_llm_events()
        return result,events[0],create.call_args.kwargs

    def test_disabled_adds_only_official_thinking_option(self):
        result,event,options=self.call("disabled",self.response())
        self.assertEqual(options["extra_body"],{"thinking":{"type":"disabled"}})
        self.assertEqual((options["model"],options["max_tokens"],options["stream"]),(m.DEEPSEEK_MODEL,1024,False))
        self.assertEqual(result,"SELECT 1")
        self.assertEqual(event["reasoning_tokens"],16)
        self.assertEqual(event["completion_tokens"],20)  # reasoning明细不能重复相加。
        self.assertEqual(event["reasoning_content_chars"],16)
        self.assertNotIn("internal fixture",str(event))

    def test_provider_default_sends_no_override(self):
        _,event,options=self.call("provider_default",self.response(reasoning=None,details=False))
        self.assertNotIn("extra_body",options)
        self.assertIsNone(event["reasoning_tokens"])
        self.assertIsNone(event["reasoning_content_chars"])

    def test_unset_mode_explicitly_disables_thinking(self):
        create=Mock(return_value=self.response(reasoning=None,details=False))
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.dict(os.environ,{"RUNBOOK_MAX_LLM_CALLS":"1"}), \
                patch.object(m,"get_llm",return_value=client),patch.object(m,"_llm_events",[]):
            os.environ.pop("RUNBOOK_THINKING_MODE",None)
            m.llm_ask("synthetic default-mode prompt",stage="select")
            self.assertEqual(create.call_args.kwargs["extra_body"],{"thinking":{"type":"disabled"}})
            self.assertEqual(m.get_llm_events()[0]["thinking_mode"],"disabled")

    def test_invalid_mode_fails_before_client_or_budget_event(self):
        with patch.dict(os.environ,{"RUNBOOK_THINKING_MODE":"unknown"}),patch.object(m,"get_llm") as client,patch.object(m,"_llm_events",[]):
            with self.assertRaises(ValueError):m.llm_ask("synthetic")
            client.assert_not_called()
            self.assertEqual(m.get_llm_events(),[])

    def test_truncation_preserves_usage_and_counts_once(self):
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=self.response("length")))))
        with patch.dict(os.environ,{"RUNBOOK_THINKING_MODE":"disabled","RUNBOOK_MAX_LLM_CALLS":"1"}), \
                patch.object(m,"get_llm",return_value=client),patch.object(m,"_llm_events",[]):
            with self.assertRaises(m.ModelOutputError):m.llm_ask("synthetic")
            event=m.get_llm_events()[0]
            self.assertEqual((event["status"],event["finish_reason"],event["completion_tokens"]),("error","length",20))
            with self.assertRaises(RuntimeError):m.llm_ask("second")
            self.assertEqual(client.chat.completions.create.call_count,1)


if __name__=="__main__":unittest.main()
