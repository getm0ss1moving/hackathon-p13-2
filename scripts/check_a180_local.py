"""180本地快照的来源/保护文件检查，可选只读原生CMDB执行；不调用模型。"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))
from check_official_integrity import require_official_files
from train_live import runtime_source_paths
import runbook_items as items
import runbook_matcher as matcher
import runbook_retriever as retriever
import runbook_system as system
import runbook_executor as executor
import evaluator


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-service", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖已有证据")
    require_official_files(ROOT)
    modules = {m.__name__: m for m in [items, matcher, retriever, system, executor, evaluator]}
    paths = runtime_source_paths(modules)
    candidate = json.loads((ROOT / "experiments/a_family_candidate_20261030/manifest.json").read_text())
    baseline = json.loads((ROOT / "baseline_manifest.json").read_text())
    readonly = dict(baseline["readonly_files"])
    readonly["implementation/runbook_items.py"] = candidate["materialized_candidate_Python_sha256"]
    assert all(digest(ROOT / p) == h for p, h in readonly.items()), "保护文件或候选模板漂移"
    families = {item["family_id"]: item for item in items.RUNBOOK_ITEMS if item.get("family_id")}
    assert len(items.RUNBOOK_ITEMS) == len({i["id"] for i in items.RUNBOOK_ITEMS}) == 180
    assert set(families) == set(matcher._FAMILY_SPECS)
    assert retriever.RunbookRetriever(items.RUNBOOK_ITEMS)._doc_count == 400
    assert system.RUNBOOK_ITEMS is items.RUNBOOK_ITEMS
    entrypoints = {"RunbookQuerySystem":{"template_count":len(system.RUNBOOK_ITEMS),"module_file":system.__file__}}
    # 官方入口在模块顶层打开200/黑盒；仅执行真实原件的导入前缀核查绑定，
    # 不执行N赋值及之后的任何评测/题集读取语句。
    for filename in ["quick_eval.py", "blackbox_eval.py"]:
        path = ROOT / "implementation" / filename
        prefix = []
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "N" for t in node.targets):
                break
            prefix.append(node)
        namespace = {"__file__":str(path)}
        exec(compile(ast.Module(body=prefix,type_ignores=[]),str(path),"exec"),namespace)
        assert namespace["RunbookQuerySystem"] is system.RunbookQuerySystem
        entrypoints[filename] = {"template_count":len(system.RUNBOOK_ITEMS),"system_module_file":system.__file__,
                                 "verification":"original import prefix only; evaluation not run"}
    original = subprocess.check_output(["git", "show", "7b7271e3:implementation/runbook_matcher.py"], cwd=ROOT, text=True)
    funcs = lambda s: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(s).body if isinstance(n, ast.FunctionDef)}
    before, after = funcs(original), funcs((ROOT / "implementation/runbook_matcher.py").read_text())
    allowed = {"get_llm_events", "llm_ask", "match_runbook", "_row_semantics_contract"}
    changed = [n for n in before if before[n] != after.get(n)]
    assert set(changed) <= allowed, changed
    result = {"status":"local_checks_passed", "branch":subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
              "head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
              "runtime_source_paths":paths, "runtime_sha256":{name:digest(Path(p)) for name,p in paths.items()},
              "template_count":180, "family_ids":sorted(families), "index_documents":400,
              "readonly_files_checked":len(readonly), "original_matcher_functions":len(before),
              "unchanged_original_matcher_functions":len(before)-len(changed), "changed_original_matcher_functions":changed,
              "model_requests":0, "sealed_or_full200_questions_loaded":False, "native_service":[],
              "official_files_unchanged":True, "native_service_requested":args.native_service}
    result["default_entrypoints"] = entrypoints
    if args.native_service:
        import requests
        assert executor.BASE_URL == "http://127.0.0.1:8080"
        matcher._warm_schema_cache()
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(executor.BASE_URL+"/rest/hackthon/db/schema/VM_NOVA",timeout=3)
            response.raise_for_status()
            region = response.json()["sample_data"][0]["logicalRegionName"]
        assert isinstance(region,str) and region
        base = {"scope":"filtered", "filters":{"logicalRegionName":region}, "required_filters":["logicalRegionName"]}
        cases = [("F01",dict(base,group="status",metrics="count")),
                 ("F08",dict(base,group="hypervisorType")),
                 ("F14",dict(base,metrics="count_sum")),
                 ("F18",dict(base,group="engineVersion",metrics="count")),
                 ("F20",dict(base,view="count",count_alias="total",filters={"logicalRegionName":region,"shared":False},required_filters=["logicalRegionName","shared"])),
                 ("F21",dict(base,group="tenantName_status"))]
        for family,parameters in cases:
            output = executor.execute(matcher._materialize_family(families[family],parameters))
            result["native_service"].append({"family_id":family,"error":output["error"],
                "columns":(output["result"] or {}).get("columns"),"row_count":(output["result"] or {}).get("row_count")})
        shared = matcher._materialize_family(families["F20"], {"scope":"filtered", "filters":{"shared":True},
            "required_filters":["shared"],"view":"rows"})
        shared_output = executor.execute(shared)
        result["native_shared_boolean_control"] = {
            "structural_value":True,"wire_value":shared["api_call"]["condition"]["constraint"][0]["simple"]["value"],
            "error":shared_output["error"],"row_count":(shared_output["result"] or {}).get("row_count")}
        assert not shared_output["error"] and shared_output["result"]["row_count"] > 0
        # 无数据与未支持必须分开记录；官方执行器行为只观察，不修改。
        empty = dict(base,group="status",metrics="count",filters={"logicalRegionName":"a180_missing_region_control_20261030"})
        output = executor.execute(matcher._materialize_family(families["F01"],empty))
        result["native_empty_control"] = {"error":output["error"],"result":output["result"]}
        result["native_model_extraction_tested"] = False
        if any(row["error"] for row in result["native_service"]):
            result["status"] = "native_execution_failure"
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(result["status"] != "local_checks_passed")


if __name__ == "__main__":
    raise SystemExit(main())
