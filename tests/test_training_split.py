"""仅合成数据检验分组划分和训练加载，不读取真实留出集。"""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_training_split import partition
import training_data


class TrainingSplitTests(unittest.TestCase):
    def test_exact_reproducible_group_split_on_synthetic_cases(self):
        cases = [{"case_id": f"synthetic-{i:03}", "question": f"合成输入{i}"} for i in range(200)]
        cases[1]["question"] = cases[0]["question"]
        groups = [{"case_ids": [case["case_id"]]} for case in cases]
        groups[2]["case_ids"].append(groups[3]["case_ids"][0])
        del groups[3]
        first = partition(cases, groups, 20261030)
        self.assertEqual(first, partition(cases, groups, 20261030))
        train, held, *_ = first
        self.assertEqual((len(train), len(held)), (150, 50))
        train_ids = {case["case_id"] for case in train}
        self.assertFalse(train_ids & {case["case_id"] for case in held})
        self.assertEqual("synthetic-000" in train_ids, "synthetic-001" in train_ids)
        self.assertEqual("synthetic-002" in train_ids, "synthetic-003" in train_ids)

    def fixture(self, root):
        train = {"partition": "train", "cases": [{"case_id": f"fixture-{i}", "question": f"仅训练{i}"} for i in range(150)]}
        path = root/"train.json"
        path.write_text(json.dumps(train))
        history = root/"train_history.jsonl"
        history.write_text("\n".join(json.dumps({"type": "case", **case}) for case in train["cases"]))
        manifest = {"split_id": "whitebox_150_50_v1", "train_count": 150, "train_file": "train.json",
                    "train_history_file": "train_history.jsonl", "train_sha256": training_data.sha(path),
                    "train_history_sha256": training_data.sha(history)}
        (root/"manifest.json").write_text(json.dumps(manifest))
        return manifest

    def test_loader_never_opens_holdout_or_original(self):
        native = Path.open
        opened = []

        def guarded(path, *args, **kwargs):
            if path.name in {"sealed_test.json", "CMDB用例集-白盒200.json"}:
                raise AssertionError("训练不能打开留出或原200题")
            opened.append(path.name)
            return native(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with patch.object(training_data, "SPLIT", root), patch.object(Path, "open", guarded):
                _, cases, records = training_data.load_training()
            self.assertEqual((len(cases), len(records)), (150, 150))
            self.assertTrue(set(opened) <= {"manifest.json", "train.json", "train_history.jsonl"})

    def test_modified_training_data_fails_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root/"train.json").write_text('{"partition":"train","cases":[]}')
            with patch.object(training_data, "SPLIT", root), self.assertRaisesRegex(ValueError, "哈希错误"):
                training_data.load_training()

    def test_manifest_cannot_redirect_training_to_holdout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            manifest["train_file"] = "sealed_test.json"
            (root/"manifest.json").write_text(json.dumps(manifest))
            with patch.object(training_data, "SPLIT", root), self.assertRaisesRegex(ValueError, "合同错误"):
                training_data.load_training()


if __name__ == "__main__":
    unittest.main()
