"""按A固定资料离线复建160，可显式启用本地候选；不调用模型或服务。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="新的仓库外私有输出目录")
    parser.add_argument("--activate", action="store_true", help="复核通过后替换本地items/retriever；不提交Git")
    args = parser.parse_args()
    out = args.output.resolve()
    if out == ROOT or ROOT in out.parents or out.exists():
        parser.error("请使用新的仓库外输出目录，不覆盖历史证据")
    out.mkdir(parents=True)
    (out / "logs").mkdir()
    package = "experiments/a_family_candidate_160_20261030"
    a170 = "experiments/a_family_candidate_170_20261030"
    source = json.loads((ROOT / "experiments/a160_runtime_port_20261030/SOURCE_MANIFEST.json").read_text())
    for name, expected in source["source_files"].items():
        if sha(ROOT / name) != expected:
            parser.error("A固定来源变化：" + name)
    steps = [
        ("build180", ["scripts/build_a180_candidate.py", "--repo", ".", "--output", out / "base180"]),
        ("build179", [a170 + "/history179/build_179_candidate.py", "--base180", out / "base180/templates180.private.json",
                       "--f27", a170 + "/history179/F27_CANDIDATE.json", "--retriever", out / "base180/candidate180/implementation/runbook_retriever.py", "--output", out / "base179"]),
        ("build170", [a170 + "/build_170_candidate.py", "--base179", out / "base179/templates179.private.json",
                       "--families", a170 + "/CANDIDATES.json", "--retriever", out / "base179/candidate179/implementation/runbook_retriever.py", "--output", out / "semantic170"]),
        ("attributes170", [a170 + "/build_170_attributes.py", "--templates", out / "semantic170/templates170.private.json",
                            "--metadata", a170 + "/attribute_index/ATTRIBUTE_METADATA.json", "--retriever", out / "semantic170/candidate170/implementation/runbook_retriever.py",
                            "--patch", a170 + "/attribute_index/attribute_retriever.patch", "--output", out / "final170"]),
        ("verify170", [a170 + "/verify_170_attributes_public.py", "--base170", out / "semantic170/templates170.private.json",
                        "--attributes170", out / "final170/templates170.attributes.private.json", "--base-retriever", out / "semantic170/candidate170/implementation/runbook_retriever.py",
                        "--attribute-retriever", out / "final170/candidate170/implementation/runbook_retriever.py"]),
        ("build166", [package + "/base160/stage166/build_166_candidate.py", "--base170", out / "final170/templates170.attributes.private.json",
                       "--references", package + "/base160/stage166/FAMILY_DEFINITIONS.references.json", "--retriever", out / "final170/candidate170/implementation/runbook_retriever.py", "--output", out / "chain166"]),
        ("build160", [package + "/base160/build_164_160.py", "--base166", out / "chain166/templates166.private.json",
                       "--single", package + "/base160/sources/single/CANDIDATES.json", "--count", package + "/base160/sources/count/FAMILY_CANDIDATE.json",
                       "--retriever", out / "final170/candidate170/implementation/runbook_retriever.py", "--output", out / "stages160"]),
        ("verify160", [package + "/verify_public160.py", "--templates160", out / "stages160/templates160.private.json",
                        "--retriever", out / "stages160/candidate160/implementation/runbook_retriever.py", "--output", out / "public160"]),
    ]
    commands = [[sys.executable, "-B", *map(str, command)] for _, command in steps]
    (out / "commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n")
    for (label, _), command in zip(steps, commands):
        process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        (out / "logs" / (label + ".stdout")).write_text(process.stdout)
        (out / "logs" / (label + ".stderr")).write_text(process.stderr)
        print(json.dumps({"step": label, "exit_code": process.returncode}), flush=True)
        if process.returncode:
            return process.returncode
    runtime = out / "stages160/candidate160/implementation"
    installed = []
    if args.activate:
        baseline = json.loads((ROOT / "baseline_manifest.json").read_text())["readonly_files"]
        names = ["implementation/runbook_items.py", "implementation/runbook_retriever.py"]
        for name, expected in source["runtime_hashes"].items():
            path = runtime / Path(name).name if name in names else ROOT / name
            if sha(path) != expected:
                parser.error("候选/helper指纹不符，未启用：" + name)
        for name in names:
            current = sha(ROOT / name)
            if current not in {baseline[name], source["runtime_hashes"][name]}:
                parser.error("发现未知本地items/retriever改动，未覆盖：" + name)
        backups = out / "before_activation"
        backups.mkdir()
        try:
            for name in names:
                target = ROOT / name
                shutil.copy2(target, backups / target.name)
                installed.append({"path": name, "previous_sha256": sha(target)})
                shutil.copyfile(runtime / target.name, target)
                installed[-1]["installed_sha256"] = sha(target)
        except Exception:
            for item in installed:
                shutil.copyfile(backups / Path(item["path"]).name, ROOT / item["path"])
            raise
    receipt = {"status": "A160_LOCAL_CANDIDATE_ACTIVATED" if args.activate else "A160_PRIVATE_BUILD_READY",
               "A_ref": source["A_ref"], "template_json_sha256": source["template_json_sha256"],
               "active_templates": 160, "families": 15, "installed": installed,
               "model_requests": 0, "service_requests": 0, "official_files_modified": False,
               "business_gate_passed": False, "git_commit_or_push": False}
    (out / "RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
