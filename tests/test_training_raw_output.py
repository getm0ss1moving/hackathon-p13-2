"""完整输出归档与旧日志兼容检查；合成数据，无模型或网络。"""
import copy
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from analyze_whitebox_batches import combine_batches, read_batch
from run_whitebox import result_preview
from training_raw_output import RAW_OUTPUT_POLICY, save_raw_output, verify_raw_output
import test_training_whitebox_batches as batch_fixtures


class RawOutputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = {"matched_runbook": "合成模板", "api_call": [], "sql": "SELECT * FROM T",
                       "result": {"columns": ["value"], "row_count": 6,
                                  "rows": [[None], [""], [True], [1], ["1"], ["最后一行"]]},
                       "diagnostics": {"nested": {"unknown": None, "flag": False}},
                       "additional_output_field": ["未知扩展字段也保存"]}
        self.row = {"case_id": "SYNTH-1", "case_index": 1,
                    **{k: self.output[k] for k in ["matched_runbook", "api_call", "sql", "diagnostics"]},
                    "result": result_preview(self.output["result"])}

    def save(self):
        self.row["raw_output"] = save_raw_output(self.root/"live.jsonl", 1, "SYNTH-1", self.output)
        return self.root/self.row["raw_output"]["path"]

    def test_complete_rows_native_types_and_extra_fields_survive_without_mutation(self):
        before = copy.deepcopy(self.output); self.save()
        restored = verify_raw_output(self.root, self.row)
        self.assertEqual(restored, before); self.assertEqual(self.output, before)
        self.assertEqual(len(restored["result"]["rows"]), 6)
        self.assertIs(restored["result"]["rows"][2][0], True)
        self.assertEqual(len(self.row["result"]["rows_preview"]), 3)

    def test_existing_output_never_overwritten(self):
        path = self.save(); before = path.read_bytes()
        with self.assertRaises(FileExistsError): self.save()
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_or_missing_archive_rejected(self):
        path = self.save(); path.write_bytes(path.read_bytes()+b"corrupt")
        with self.assertRaisesRegex(ValueError, "指纹"): verify_raw_output(self.root, self.row)
        path.unlink()
        with self.assertRaises(FileNotFoundError): verify_raw_output(self.root, self.row)

    def test_wrong_case_and_changed_preview_rejected_even_with_valid_archive(self):
        self.save(); self.row["case_id"] = "SYNTH-2"
        with self.assertRaisesRegex(ValueError, "身份"): verify_raw_output(self.root, self.row)
        self.row["case_id"] = "SYNTH-1"; self.row["result"]["rows_preview"][2] = [1]
        with self.assertRaisesRegex(ValueError, "预览"): verify_raw_output(self.root, self.row)

    def test_outside_run_path_rejected(self):
        self.save(); self.row["raw_output"]["path"] = "../another-run/data.json.gz"
        with self.assertRaisesRegex(ValueError, "目录"): verify_raw_output(self.root, self.row)

    def test_invalid_json_output_does_not_create_an_archive(self):
        self.output["non_json_number"] = float("nan")
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(list(self.root.rglob("*.gz")))


class RawOutputBatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = batch_fixtures.WhiteboxBatchReportTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def promote(self, directory):
        plan = json.loads((directory/"plan.json").read_text())
        rows = json.loads((directory/"case_results.json").read_text())
        trace = [json.loads(line) for line in (directory/"live.jsonl").read_text().splitlines()]
        for row in rows:
            output = {"matched_runbook": row["matched_runbook"], "diagnostics": {},
                      "result": {"columns": ["v"], "row_count": 5, "rows": [[i] for i in range(5)]}}
            row["result"] = result_preview(output["result"])
            row["raw_output"] = save_raw_output(directory/"live.jsonl",row["case_index"],row["case_id"],output)
        plan["raw_output_policy"] = RAW_OUTPUT_POLICY
        trace = [plan, *[r for r in trace if r.get("type")=="request"], *rows, trace[-1]]
        (directory/"plan.json").write_text(json.dumps(plan))
        (directory/"case_results.json").write_text(json.dumps(rows))
        (directory/"live.jsonl").write_text("\n".join(json.dumps(r) for r in trace)+"\n")
        return rows

    def test_all200_complete_output_checked_without_rescoring(self):
        for path in [self.fixture.one, self.fixture.two]: self.promote(path)
        report, rows = combine_batches([self.fixture.one, self.fixture.two])
        self.assertEqual(report["raw_output_policy"], RAW_OUTPUT_POLICY)
        self.assertFalse(report["source_rows_rescored"])
        self.assertEqual(len(rows), 200)

    def test_legacy_reports_remain_readable_but_not_claimed_complete_output(self):
        report, _ = combine_batches([self.fixture.one,self.fixture.two])
        self.assertIsNone(report["raw_output_policy"])
        self.promote(self.fixture.two)
        with self.assertRaisesRegex(ValueError,"raw output policy changed"):
            combine_batches([self.fixture.one,self.fixture.two])

    def test_declared_complete_policy_rejects_missing_output(self):
        rows = self.promote(self.fixture.one)
        (self.fixture.one/rows[-1]["raw_output"]["path"]).unlink()
        with self.assertRaises(FileNotFoundError): read_batch(self.fixture.one)


class RawOutputLiveHookTests(unittest.TestCase):
    def test_real_B_loop_archives_return_value_before_evaluator_without_network(self):
        import requests
        import train_live
        import runbook_matcher as matcher
        import runbook_system as system
        import evaluator
        output = {"matched_runbook":"synthetic", "api_call":[], "sql":"SELECT 1",
                  "result":{"columns":["v"],"row_count":5,"rows":[[i] for i in range(5)]},
                  "diagnostics":{"synthetic":True},"extra":"扩展值保留"}
        case = {"case_id":"SYNTH-HOOK","question":"合成问题"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); trace = root/"live.jsonl"
            def fake_query(question):
                requests.get('http://127.0.0.1:8080/rest/hackthon/db/instances/VM_NOVA?opaque=not_logged')
                return output
            query = Mock(side_effect=fake_query)
            fake_system = SimpleNamespace(initialization_metrics={}, query=query)
            fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock())),
                                          max_retries=0, close=Mock())
            def score(c, actual, elapsed):
                self.assertIs(actual,output)
                self.assertTrue((root/"live_outputs/live/000001.json.gz").is_file())
                return {"case_id":c["case_id"],"score":5,"elapsed":elapsed,"reason":"synthetic"}
            prior_logging = logging.root.manager.disable
            self.addCleanup(logging.disable,prior_logging)
            with patch.dict(os.environ), patch.object(train_live,"select_cases",return_value=([case],"train_only","full_training")), \
                    patch.object(system,"RunbookQuerySystem",return_value=fake_system), \
                    patch.object(requests.Session,'send',return_value=SimpleNamespace(status_code=200)), \
                    patch.object(matcher,"_llm_client",fake_client),patch.object(matcher,"_llm_events",[]), \
                    patch.object(matcher,"DEEPSEEK_API_KEY","synthetic-unused"),patch.object(evaluator,"evaluate_case",side_effect=score):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer): self.assertEqual(train_live.main([]),0)
                plan = json.loads(buffer.getvalue()); self.assertEqual(plan["raw_output_policy"],RAW_OUTPUT_POLICY)
                self.assertIn("scripts/training_raw_output.py",plan["source_sha256"])
                path = root/"plan.json"; path.write_text(json.dumps(plan))
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(train_live.main(["--run","--expected-plan",str(path),"--output",str(trace)]),0)
            records = [json.loads(line) for line in trace.read_text().splitlines()]
            row = next(r for r in records if r.get("type")=="case")
            self.assertEqual(verify_raw_output(root,row),output)
            self.assertEqual(records[-1]["generation_requests"],0)
            http=[r for r in records if r.get('type')=='data_http_request']
            self.assertEqual(len(http),1);self.assertEqual(http[0]['case_id'],'SYNTH-HOOK')
            self.assertEqual(http[0]['status'],200);self.assertNotIn('opaque',trace.read_text())
            self.assertEqual(records[-1]['case_data_HTTP_404'],0)
            query.assert_called_once_with(case["question"])
            fake_client.chat.completions.create.assert_not_called()


if __name__ == "__main__": unittest.main()
