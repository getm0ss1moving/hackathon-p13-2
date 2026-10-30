"""仅测试补测预检与来源门禁，不读取留出、不调用模型。"""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resume_training_v2


class ResumeTests(unittest.TestCase):
    def setUp(self):
        # 旧补测已经结束；只在单测中模拟它的冻结来源，独立检查范围/预算。
        # 新候选源码本来就不能通过旧补测门禁，另有原生哈希测试验证拒绝。
        self.native_sha = resume_training_v2.sha
        frozen_plan = json.loads((resume_training_v2.HERE/"experiments/train150_v2_live_plan.json").read_text())
        self.frozen_sources = frozen_plan["source_sha256"]
        import runbook_matcher
        for name,key in [("DEEPSEEK_MODEL", "model"), ("DEEPSEEK_BASE_URL", "base_url")]:
            context = patch.object(runbook_matcher, name, frozen_plan[key])
            context.start()
            self.addCleanup(context.stop)

        def frozen_sha(path):
            try:
                name = str(Path(path).relative_to(resume_training_v2.HERE))
            except ValueError:
                return self.native_sha(path)
            logical = name.removeprefix("scripts/") if name.startswith("scripts/") else name
            return self.frozen_sources.get(logical, self.native_sha(path))

        context = patch.object(resume_training_v2, "sha", side_effect=frozen_sha)
        context.start()
        self.addCleanup(context.stop)
        for owner, name in [(requests.Session, "request"), (httpx.Client, "send")]:
            context = patch.object(owner, name, side_effect=AssertionError("预检禁止网络"))
            context.start()
            self.addCleanup(context.stop)

    def preflight(self):
        out = io.StringIO()
        with patch.object(sys, "argv", ["resume_training_v2.py"]), redirect_stdout(out):
            self.assertEqual(resume_training_v2.main(), 0)
        return json.loads(out.getvalue())

    def test_only_uncompleted_training_tail_and_budget(self):
        plan = self.preflight()
        self.assertEqual(plan["case_count"], 3)
        self.assertEqual(plan["max_requests"], 9)
        self.assertLessEqual(plan["previous_used_requests"]+plan["max_requests"], 450)
        self.assertTrue(plan["new_process_and_executor_cache"])

    def test_missing_resume_plan_stops_before_network(self):
        with patch.object(sys, "argv", ["resume_training_v2.py", "--run"]), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
            resume_training_v2.main()
        self.assertEqual(result.exception.code, 2)

    def test_changed_resume_budget_is_rejected(self):
        plan = self.preflight()
        plan["max_requests"] = 10
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"plan.json"
            path.write_text(json.dumps(plan))
            with patch.object(sys, "argv", ["resume_training_v2.py", "--expected-plan", str(path)]), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
                resume_training_v2.main()
            self.assertEqual(result.exception.code, 2)

    def test_changed_candidate_cannot_reuse_old_resume(self):
        if all(self.native_sha(resume_training_v2.HERE/("scripts/"+name if "/" not in name else name)) == value for name,value in self.frozen_sources.items()):
            self.skipTest("当前恰为v2冻结来源；漂移候选适用")
        errors = io.StringIO()
        with patch.object(resume_training_v2, "sha", side_effect=self.native_sha), \
                patch.object(sys, "argv", ["resume_training_v2.py"]), redirect_stdout(io.StringIO()), \
                patch("sys.stderr", errors), self.assertRaises(SystemExit) as result:
            resume_training_v2.main()
        self.assertEqual(result.exception.code, 2)
        self.assertIn("源代码已偏离父运行", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
