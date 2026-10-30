"""按已保存参数运行原train_live；每轮保留命令、计划、控制台、结果及费用计数。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    flags = config["arguments"]
    if (not isinstance(flags, list) or not all(isinstance(x, str) for x in flags)
            or any(x.split("=", 1)[0] in {"--run", "--output", "--expected-plan"} for x in flags)):
        parser.error("config只接受原训练参数，不允许覆盖运行开关和输出路径")
    out = (ROOT / config["output_dir"]).resolve()
    base = [sys.executable, "-B", str(ROOT / "scripts/train_live.py"), *flags]
    if not args.run:
        out.mkdir(parents=True, exist_ok=False)
        process = subprocess.run(base, cwd=ROOT, text=True, capture_output=True)
        (out / "preflight.stdout").write_text(process.stdout)
        (out / "preflight.stderr").write_text(process.stderr)
        if process.returncode:
            return process.returncode
        plan = json.loads(process.stdout)
        validation = plan['scope'] == 'sealed50_validation' and '--sealed-validation-freeze' in flags
        if (plan["scope"] not in {"train_subset", "train_only", "sealed50_validation"}
                or plan["model"] != "deepseek-flash" or plan["thinking"] != "disabled"
                or not 1 <= plan["case_count"] <= 150 or not 1 <= plan["max_requests"] <= 450
                or (plan["holdout_evaluated"] is not validation)
                or validation and (plan['case_count'] != 50 or plan['max_requests'] > 150)):
            parser.error("仅允许Flash关闭思考的固定150训练集或其子集，每轮最多450请求")
        (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        (out / "config.freeze.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        commands = {"preflight": base, "run": [*base, "--run", "--expected-plan", str(out / "plan.json"), "--output", str(out / "live.jsonl")]}
        (out / "commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n")
        with zipfile.ZipFile(out / "source.zip", "x", zipfile.ZIP_DEFLATED) as archive:
            for relative, expected in plan["source_sha256"].items():
                if digest(ROOT / relative) != expected:
                    parser.error("预检源码已漂移，未调用模型")
                archive.write(ROOT / relative, "runtime/" + relative)
            archive.write(Path(__file__), "launcher/run_saved_training.py")
            archive.write(out / "commands.json", "commands.json")
            archive.write(out / "config.freeze.json", "config.freeze.json")
        print(json.dumps({"status": "preflight", "cases": plan["case_ids"], "maximum": plan["max_requests"], "output_dir": str(out), "model_requests": 0}))
        return 0
    if json.loads((out / "config.freeze.json").read_text()) != config:
        parser.error("参数与已保存配置不同")
    if (out / "live.jsonl").exists() or (out / "stdout.log").exists():
        parser.error("不覆盖已有结果；需要新的独立轮次")
    commands = json.loads((out / "commands.json").read_text())
    plan = json.loads((out / "plan.json").read_text())
    command = [*base, "--run", "--expected-plan", str(out / "plan.json"), "--output", str(out / "live.jsonl")]
    if command != commands["run"]:
        parser.error("命令与预检记录不同")
    with (out / "stdout.log").open("x") as log:
        child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        print(json.dumps({"pid": child.pid, "status": "running", "output_dir": str(out)}), flush=True)
        code = child.wait()
    trace = out / "live.jsonl"
    rows = [json.loads(x) for x in trace.read_text().splitlines()] if trace.exists() else []
    requests = [row for row in rows if row.get("type") == "request"]
    cases = [row for row in rows if row.get("type") == "case"]
    summary = next((row for row in reversed(rows) if row.get("type") == "summary"), None)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    budget = {"status": "closed", "maximum": plan["max_requests"], "used": len(requests),
              "failed": sum(row.get("status") != "ok" for row in requests),
              "unused_closed": plan["max_requests"] - len(requests), "SDK_retries": 0,
              "plan_sha256": digest(out / "plan.json"), "trace_sha256": digest(trace) if trace.exists() else None,
              "child_exit_code": code, "prior_balance_reused": False}
    (out / "budget.json").write_text(json.dumps(budget, ensure_ascii=False, indent=2) + "\n")
    (out / "case_results.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": summary, "budget": budget}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
