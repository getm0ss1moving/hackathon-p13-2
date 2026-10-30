"""只校验官方文件字节；不导入/执行评测脚本，不读取用例语义，不调用模型。"""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OFFICIAL_COMMIT = "d79c316"
OFFICIAL_SHA256 = {
    "implementation/evaluator.py": "d2a93903f068d77d84470dcd1e3eef8671571136c1d7cfb7e4f9b3307d3516c1",
    "implementation/runbook_executor.py": "4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92",
    "implementation/quick_eval.py": "41c28aa77be441451c440e3ab8f7b4bfbb6172cb5d87dc016a68c0f23fca7324",
    "implementation/blackbox_eval.py": "4f20375597dad1927fa12a0c72d14c31021bbcd3bc4d059629804b9d9469198c",
}


ACCEPTED_REVISIONS = {'implementation/evaluator.py': {'revision_id': 'numeric_ratio_tolerance_20261030',
                                 'authority': '用户提供的评分器修订通知，2026-10-30',
                                 'base_commit': 'd79c316',
                                 'change': 'abs(ratio - 100.0) < 0.1 -> abs(ratio - 1.0) < 0.1'}}


def verify_official_files(root=HERE):
    root = Path(root)
    rows = []
    for relative, expected in OFFICIAL_SHA256.items():
        path = root / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        rows.append({"file": relative, "expected_sha256": expected,
                     "actual_sha256": actual, "unchanged": actual == expected})
    return {"official_commit": OFFICIAL_COMMIT, "unchanged": all(row["unchanged"] for row in rows),
            "files": rows, "accepted_revisions": {name: revision for name, revision in ACCEPTED_REVISIONS.items()
                                                  if name in OFFICIAL_SHA256},
            "scripts_executed": False, "model_requests": 0}


def require_official_files(root=HERE):
    result = verify_official_files(root)
    if not result["unchanged"]:
        failed = [row["file"] for row in result["files"] if not row["unchanged"]]
        raise ValueError("官方评测文件变化，停止测试：" + ", ".join(failed))
    return result


if __name__ == "__main__":
    report = verify_official_files()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["unchanged"] else 1)
