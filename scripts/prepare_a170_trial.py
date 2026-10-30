"""冻结本次170诊断试用；只准备4×3与438请求计划，不调用模型。"""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/a170_local_port"
CONTROL = ROOT.parent / "hackathon-p13-2-180-20261030"
PYTHON = str(ROOT.parent / "hackathon-p13-2/.venv/bin/python")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    assert not list(REPORT.glob("*live.jsonl"))
    assert not list(REPORT.glob("*budget.json"))
    assert sha(ROOT / "implementation/runbook_matcher.py") == "aa272bee2c483351701c6bc01ce575dec41993a30d81803f241edef6d1487c1f"
    assert sha(CONTROL / "implementation/runbook_matcher.py") == "dced03e08a68670a7c4899060b6c2ac1fee57c680bf91de53322928f7a7b96d9"
    base = [PYTHON, "-B", "scripts/train_live.py", "--a170-candidate", "--candidate-flags",
            "--refine-contract-prompt", "--independent-aggregates", "--grouped-aggregates",
            "--network-details", "--identity-projection", "--vpc-subnets", "--tenant-resources",
            "--vm-volume-details", "--tenant-vdc-binding", "--parallel-resource-lists",
            "--thinking-mode", "disabled"]
    scopes = []
    for number in ["019", "148", "214", "217"]:
        scopes.append(("a170_v1_probe" + number,
                       ["--request-limit", "3", "--phase", "failure_probe", "--case-id", "CMDB-" + number]))
    scopes.append(("a170_v1_full150", ["--request-limit", "438"]))
    allocations = []
    shared = None
    for label, args in scopes:
        proc = subprocess.run(base + args, cwd=ROOT, text=True, capture_output=True)
        assert proc.returncode == 0, proc.stderr
        plan = json.loads(proc.stdout)
        assert plan["model"] == "deepseek-flash" and plan["base_url"] == "https://api.deepseek.com"
        assert plan["template_count"] == 170 and len(plan["family_ids"]) == 9
        assert len(plan["runtime_source_paths"]) == 7 and plan["sdk_max_retries"] == 0
        assert plan["max_output_tokens"] == 1024
        assert all(sha(ROOT / path) == digest for path, digest in plan["source_sha256"].items())
        if shared is None:
            shared = plan["source_sha256"]
        else:
            assert all(shared[path] == digest for path, digest in plan["source_sha256"].items() if path in shared)
        plan_path = REPORT / (label + "_plan.json")
        write_new(plan_path, plan)
        supervisor = (CONTROL / "reports/a180_local_port/a180_v11_supervisor.txt").read_text()
        supervisor = supervisor.replace("hackathon-p13-2-180-20261030", "hackathon-p13-2-170-20261030")
        supervisor = supervisor.replace("a180_local_port", "a170_local_port")
        supervisor = supervisor.replace("a180_v11_full", label).replace("a180_v11_process", label + "_process")
        extra = ["--a170-candidate", *args]
        supervisor = supervisor.replace("'--expected-plan'", ",".join(repr(x) for x in extra) + ",'--expected-plan'", 1)
        supervisor = supervisor.replace("'cases':150,'max_requests':450", "'cases':plan['case_count'],'max_requests':plan['max_requests']")
        assert "hackathon-p13-2-180-20261030" not in supervisor
        ast.parse(supervisor)
        supervisor_path = REPORT / (label + "_supervisor.txt")
        with supervisor_path.open("x") as stream:
            stream.write(supervisor)
        archive_path = REPORT / (label + "_source.zip")
        with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED) as archive:
            for path in plan["source_sha256"]:
                archive.write(ROOT / path, path)
            for path in ["scripts/check_a170_local.py", "scripts/prepare_a170_trial.py", "tests/test_training_a170.py"]:
                archive.write(ROOT / path, path)
            archive.write(supervisor_path, "external_supervisor.txt")
        frozen = {
            "plan_sha256": sha(plan_path), "source_zip_sha256": sha(archive_path),
            "source_sha256": plan["source_sha256"], "case_ids": plan["case_ids"],
            "max_requests": plan["max_requests"], "source_frozen_before_first_request": True,
            "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "known_common_SDK_empty_semantics_open": True,
            "formal_adoption_gate_passed": False, "isolated_diagnostic_trial_authorized": True,
        }
        write_new(REPORT / (label + "_freeze.json"), frozen)
        allocations.append({"label": label, "case_count": plan["case_count"],
                            "maximum": plan["max_requests"], "status": "planned",
                            "plan_sha256": sha(plan_path), "source_zip_sha256": sha(archive_path)})
    budget = {
        "round": "a170_independent_trial1", "status": "open", "maximum_all_requests": 450,
        "small_allocated_maximum": 12, "full_allocated_maximum": 438,
        "actual_requests": 0, "failed_requests": 0, "allocations": allocations, "unallocated": 0,
        "closed_old_balances_reused": False,
        "actual_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "matcher_sha256": sha(ROOT / "implementation/runbook_matcher.py"),
        "probe_policy": "four sequential single-case plans; stop on first nonfull quality/error; no paid retry",
        "full_policy": "only after all probes pass unchanged; one continuous150 <=438; no recovery/fallback",
        "small_unused_closed_not_reallocated": True,
        "known_common_SDK_empty_semantic_gate_passed": False,
        "diagnostic_trial_override_from_latest_user_scope": True, "formal_default_switch": False,
        "latest_180_training_aggregate_reference": {"timed": 637.1, "quality": 638.1,
            "source": "supervisor aggregate from independent interleaved200; no case-level logs read"},
        "holdout_evaluated_by_this_executor": False,
        "model": "deepseek-flash", "base_url": "https://api.deepseek.com", "thinking": "disabled",
        "output_limit": 1024, "SDK_retries": 0,
        "prior_orchestration_compile_failure": "no statements/model calls executed; preserved in tool transcript",
    }
    write_new(REPORT / "a170_trial1_budget.json", budget)
    print(json.dumps({"round": budget["round"], "maximum": 450, "small": 12, "full": 438,
                      "allocations": [{"label": row["label"], "max": row["maximum"]} for row in allocations],
                      "head": budget["actual_head"], "model_requests": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
