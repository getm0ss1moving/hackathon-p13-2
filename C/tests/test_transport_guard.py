"""Exercise the actual installed SDK and HTTP hooks using in-memory transport."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

PATH = Path(__file__).resolve().parents[1] / 'implementation/quick_eval.py'
SPEC = importlib.util.spec_from_file_location('c_transport_guard', PATH)
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class TransportTests(unittest.TestCase):
    def test_sdk_retries_are_counted_and_stopped_before_excess_transport(self):
        transported = []
        def handler(request):
            transported.append(request)
            return httpx.Response(500, json={'error': {'message': 'fixture server failure'}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with OpenAI(api_key='fixture-never-sent', base_url='https://fixture.invalid',
                        max_retries=5, http_client=http) as client:
                guard = ENTRY.RequestGuard(client, 'https://fixture.invalid', 2)
                try:
                    with patch('time.sleep'), self.assertRaises(ENTRY.ModelRequestStop):
                        client.chat.completions.create(model='fixture', messages=[{'role': 'user', 'content': 'fixture'}])
                    self.assertEqual(len(transported), 2)
                    self.assertEqual(len(guard.events), 2)
                finally:
                    guard.detach()

    def test_real_response_hook_records_usage_without_response_text(self):
        body = {'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'fixture-response',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'not a persisted response'},
                             'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 4, 'completion_tokens': 3, 'total_tokens': 7}}
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as http:
            with OpenAI(api_key='fixture-never-sent', base_url='https://fixture.invalid',
                        max_retries=0, http_client=http) as client:
                guard = ENTRY.RequestGuard(client, 'https://fixture.invalid', 1)
                try:
                    response = client.chat.completions.create(model='fixture', max_tokens=12,
                        messages=[{'role': 'user', 'content': 'private fixture prompt'}])
                    self.assertEqual(response.choices[0].message.content, 'not a persisted response')
                    self.assertEqual(guard.events[0]['usage']['total_tokens'], 7)
                    self.assertEqual(guard.events[0]['max_output_tokens'], 12)
                    self.assertNotIn('private fixture prompt', str(guard.events))
                    self.assertNotIn('not a persisted response', str(guard.events))
                finally:
                    guard.detach()


if __name__ == '__main__':
    unittest.main()
