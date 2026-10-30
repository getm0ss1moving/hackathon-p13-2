"""训练真实入口的免费预检/漂移门禁；不调用模型或读取留出题。"""

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
import train_live
from runbook_items import RUNBOOK_ITEMS

A180_FLAGS = (["--a170-candidate"] if len(RUNBOOK_ITEMS) == 170 else ["--a180-candidate"]) if any(item.get("family_id") for item in RUNBOOK_ITEMS) else []


class TrainingLiveTests(unittest.TestCase):
    def setUp(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("预检不允许网络")
        for target, name in [(requests.Session, "request"), (httpx.Client, "send")]:
            context = patch.object(target, name, side_effect=forbidden)
            context.start()
            self.addCleanup(context.stop)

    def preflight(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(train_live.main(A180_FLAGS), 0)
        return json.loads(out.getvalue())

    def test_preflight_is_training_only_without_network(self):
        native = Path.open

        def guarded(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if path.name == "sealed_test.json" or path.name == "CMDB用例集-白盒200.json" and "b" not in mode:
                raise AssertionError("不能读取留出题或解释原200题")
            return native(path, *args, **kwargs)

        with patch.object(Path, "open", guarded):
            plan = self.preflight()
        self.assertEqual((plan["case_count"], plan["max_requests"]), (150, 450))
        self.assertEqual(plan["scope"], "train_only")
        self.assertFalse(plan["holdout_evaluated"])
        self.assertNotIn("DEEPSEEK_API_KEY", json.dumps(plan))

    def test_wrong_plan_stops_before_any_network(self):
        plan = self.preflight()
        plan["case_count"] = 151
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"wrong-plan.json"
            path.write_text(json.dumps(plan))
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
                train_live.main([*A180_FLAGS, "--expected-plan", str(path)])
            self.assertEqual(result.exception.code, 2)

    def test_run_requires_frozen_plan_before_network(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
            train_live.main(["--run"])
        self.assertEqual(result.exception.code, 2)

    def test_request_limit_can_only_tighten_the_frozen_budget(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(train_live.main([*A180_FLAGS, "--request-limit", "400"]), 0)
        self.assertEqual(json.loads(out.getvalue())["max_requests"], 400)
        for limit in ["0", "451"]:
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                train_live.main([*A180_FLAGS, "--request-limit", limit])


if __name__ == "__main__":
    unittest.main()
