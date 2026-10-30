"""本地生成A/C交接包；显式文件清单，不打包密钥、封存数据或全200逐题日志。"""

import argparse
import json
from pathlib import Path
import zipfile

from training_data import sha

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE/"reports/b_to_a_c_train150_v2.zip")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖历史交接包")
    names = ["AGENTS.md", "TRAINING.md", "TRAINING_ISSUES.md", "A_REQUESTS_TRAINING.md", "C_REQUESTS_TRAINING.md",
             "TEAM_TRAINING_HANDOFF.md", "training_data.py", "train_live.py", "train_replay.py", "analyze_training.py",
             "audit_training_failures.py", "probe_training_field_contracts.py", "make_training_split.py",
             "resume_training_v2.py", "analyze_training_v2_coverage.py",
             "datasets/whitebox_150_50_v1/manifest.json", "datasets/whitebox_150_50_v1/train.json",
             "datasets/whitebox_150_50_v1/train_history.jsonl",
             "experiments/train150_v1_live.jsonl", "experiments/train150_v1_summary.md",
             "experiments/train150_v1_source.patch", "experiments/train150_v1_live_plan.json",
             "experiments/train150_v1_authorization.json", "experiments/train150_v1_live_analysis.json",
             "experiments/train150_v1_budget_usage.json", "experiments/train150_v1_baseline.json",
             "experiments/train150_v1_model_names.json", "experiments/train150_v1_entity_checks_v2.json",
             "experiments/train150_v1_validation.json", "experiments/train150_v2_summary.md",
             "experiments/train150_v2_source.patch", "experiments/train150_v2_live_plan.json",
             "experiments/train150_v2_failure_audit_final.json", "experiments/train150_v2_field_contracts.json",
             "experiments/train150_v2_issue_board.json", "experiments/train150_v2_controls_off.json",
             "experiments/train150_v2_grain_replay.json", "experiments/train150_v2_literals_replay.json",
             "experiments/train150_v2_prune_replay.json", "experiments/train150_v2_combined_replay.json",
             "experiments/train150_v2_offline_validation.json"]
    optional = ["experiments/train150_v2_authorization.json", "experiments/train150_v2_live.jsonl",
                "experiments/train150_v2_live_analysis.json", "experiments/train150_v2_budget_usage.json",
                "experiments/train150_v2_live_summary.md", "experiments/train150_v2_validation.json",
                "experiments/train150_v2_resume_plan.json", "experiments/train150_v2_resume_authorization.json",
                "experiments/train150_v2_resume_live.jsonl", "experiments/train150_v2_coverage_analysis.json"]
    for name in optional:
        if (HERE/name).exists():
            names.append(name)
    # 真实记录存在时必须完整且分析/结算已完成，不将运行中的半文件打包。
    if "experiments/train150_v2_live.jsonl" in names:
        records = [json.loads(line) for line in (HERE/"experiments/train150_v2_live.jsonl").read_text().splitlines()]
        if records[-1].get("type") != "summary":
            parser.error("真实运行仍在进行，暂不打包")
        if records[-1].get("status") == "incomplete":
            coverage = HERE/"experiments/train150_v2_coverage_analysis.json"
            if not coverage.exists():
                parser.error("中断记录尚无独立覆盖分析，暂不打包")
            checked = json.loads(coverage.read_text())
            if not checked.get("full_training_coverage") or checked.get("single_pass_complete"):
                parser.error("分段覆盖声明不匹配")
        elif not (HERE/"experiments/train150_v2_live_analysis.json").exists():
            parser.error("真实单轮分析未完成")
        if not (HERE/"experiments/train150_v2_budget_usage.json").exists():
            parser.error("预算结算未完成")
    names += [str(path.relative_to(HERE)) for path in sorted((HERE/"tests").glob("test_training_*.py"))]
    if any(not (HERE/name).is_file() for name in names):
        parser.error("交接材料未齐，不生成部分包")
    assert not any("sealed_test" in name or ".env" in name or "白盒200.json" in name for name in names)
    manifest = {"scope": "train150_only", "files": {"B/"+name: sha(HERE/name) for name in names},
                "sealed_dataset_file_included": False, "credential_file_included": False,
                "template_library": "existing public 200-template snapshot is in source patch; prior exposure disclosed",
                "source_base": "826525a", "apply_scope": "B only; review before integration; do not overwrite root A/C files",
                "v2_real_evaluation": "147 interrupted + separately authorized 3; full coverage, not complete single pass"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in names:
            archive.write(HERE/name, "B/"+name)
        archive.writestr("B/handoff_package_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest["files"]) | {"B/handoff_package_manifest.json"}
    print(json.dumps({"output": str(args.output), "files": len(names), "bytes": args.output.stat().st_size,
                      "sealed_dataset_file_included": False, "credential_file_included": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
