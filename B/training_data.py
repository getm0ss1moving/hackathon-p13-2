"""固定训练集读取；没有留出入口，不回落到原200题。"""

import hashlib
import json
from pathlib import Path

SPLIT = Path(__file__).resolve().parent/"datasets/whitebox_150_50_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_training():
    manifest = json.loads((SPLIT/"manifest.json").read_text())
    if (manifest.get("split_id") != "whitebox_150_50_v1" or manifest.get("train_count") != 150
            or manifest.get("train_file") != "train.json" or manifest.get("train_history_file") != "train_history.jsonl"):
        raise ValueError("训练划分合同错误；不读取其他集合")
    train, history = SPLIT/"train.json", SPLIT/"train_history.jsonl"
    if sha(train) != manifest["train_sha256"] or sha(history) != manifest["train_history_sha256"]:
        raise ValueError("训练文件哈希错误；不回落到原200题")
    dataset = json.loads(train.read_text())
    if dataset.get("partition") != "train":
        raise ValueError("只允许训练集合")
    cases = dataset["cases"]
    rows = [json.loads(line) for line in history.read_text().splitlines()]
    records = [row for row in rows if row["type"] == "case"]
    if (len(cases) != 150 or len({case["case_id"] for case in cases}) != 150
            or [(row["case_id"], row["question"]) for row in records]
            != [(case["case_id"], case["question"]) for case in cases]):
        raise ValueError("训练范围/顺序不匹配")
    return manifest, cases, records
