"""170隔离候选免费门禁：受控模型文本、真实BM25及可选原生CMDB；不发模型请求。"""
import argparse
import ast
from contextlib import nullcontext
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))
from train_live import a170_source_contract, runtime_source_paths
from check_official_integrity import require_official_files
import runbook_matcher as m
import runbook_items as items
import runbook_retriever as retrieval
import runbook_family_views as views
import runbook_system as system
import runbook_executor as executor
import evaluator


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contracts():
    base = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"}, "required_filters": ["logicalRegionName"]}
    result = [
        ("F01", "查询区域region_demo下ECS按状态统计数量", dict(base, group="status", metrics="count")),
        ("F08", "查询区域region_demo下宿主机按虚拟化类型统计数量", dict(base, group="hypervisorType")),
        ("F14", "查询区域region_demo下各VDC云硬盘数量和总容量", dict(base, metrics="count_sum")),
        ("F18", "查询区域region_demo下各引擎版本的GaussDB实例数量", dict(base, group="engineVersion", metrics="count")),
        ("F20", "查询区域region_demo下非共享网络的数量", dict(base, view="count", count_alias="total", filters={"logicalRegionName": "region_demo", "shared": False}, required_filters=["logicalRegionName", "shared"])),
        ("F21", "查询区域region_demo下各VDC的弹性IP数量", dict(base, group="vdcName")),
        ("F27", "查询区域region_demo下OBS桶列表", dict(base, view="rows")),
        ("F27", "统计区域region_demo下各租户的OBS桶数量", dict(base, view="tenant_count")),
    ]
    for view, (family, columns, order, _) in views.VIEWS.items():
        for fields in views._B3_SPECS[family]["shapes"][tuple(columns)][order]:
            filters = {field: ("active" if field == "status" else "Demo_" + field) for field in fields}
            resource = "ECS" if family == "F02" else "GaussDB"
            question = "查询" + resource + "，" + "，".join(field + "=" + json.dumps(value) for field, value in filters.items())
            if order != "none":
                question += "，按tenantName排序"
            question += "，输出" + "、".join(columns)
            result.append((family, question, {"view": view, "filters": filters, "required_filters": list(fields)}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-service", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("不覆盖既有证据")
    require_official_files(ROOT)
    source, _ = a170_source_contract(ROOT)
    readonly = json.loads((ROOT / "baseline_manifest.json").read_text())["readonly_files"]
    readonly.update({p: source["runtime_hashes"][p] for p in ["implementation/runbook_items.py", "implementation/runbook_retriever.py"]})
    assert all(digest(ROOT / p) == h for p, h in readonly.items())
    modules = [m, items, retrieval, views, system, executor, evaluator]
    paths = runtime_source_paths({module.__name__: module for module in modules})
    library = items.RUNBOOK_ITEMS
    families = {item["family_id"]: item for item in library if item.get("family_id")}
    assert len(library) == len({item["id"] for item in library}) == 170
    assert sorted(families) == source["families"]
    retriever = retrieval.RunbookRetriever(library)
    assert retriever._doc_count == 400 and retriever._attribute_index._doc_count == 11
    assert system.RUNBOOK_ITEMS is items.RUNBOOK_ITEMS
    entrypoints = {"RunbookQuerySystem": {"template_count": len(system.RUNBOOK_ITEMS), "module_file": system.__file__}}
    for filename in ["quick_eval.py", "blackbox_eval.py"]:
        path = ROOT / "implementation" / filename
        prefix = []
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "N" for target in node.targets):
                break
            prefix.append(node)
        namespace = {"__file__": str(path)}
        exec(compile(ast.Module(body=prefix, type_ignores=[]), str(path), "exec"), namespace)
        assert namespace["RunbookQuerySystem"] is system.RunbookQuerySystem
        entrypoints[filename] = {"template_count": 170, "verification": "original import prefix only; N/evaluation/data loading not run"}
    functions = lambda text: {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}
    before = functions(subprocess.check_output(["git", "show", "fa9fe40:implementation/runbook_matcher.py"], cwd=ROOT, text=True))
    after = functions((ROOT / "implementation/runbook_matcher.py").read_text())
    changed = [name for name in before if before[name] != after.get(name)]
    assert set(changed) == {"_materialize_family", "_match_family_candidate", "match_runbook"}
    result = {"status": "free_checks_in_progress", "templates": 170, "families": sorted(families), "primary_documents": 400,
              "attribute_documents": 11, "readonly_files_checked": len(readonly), "runtime_source_paths": paths,
              "default_entrypoints": entrypoints,
              "runtime_sha256": {name: digest(Path(path)) for name, path in paths.items()}, "B_changed_functions": changed,
              "B_unchanged_functions": len(before) - len(changed), "model_requests": 0, "controlled_pipeline": [],
              "native_results": [], "negative_controls": [], "known_official_SDK_limits": [], "private70_or537_replayed": False,
              "sealed_or_full200_loaded": False, "provider_model_quality_tested": False}
    if args.native_service:
        m._warm_schema_cache()
    for family, question, parameters in contracts():
        candidates = retriever.retrieve(question)
        target = families[family]
        offered = [c.id for c in candidates]
        assert target["id"] in offered, (family, question, offered)
        stages = []
        def ask(prompt, stage="unknown"):
            stages.append(stage)
            if stage == "select":
                return str(offered.index(target["id"]) + 1)
            if stage == "family_fill":
                return json.dumps(parameters, ensure_ascii=False)
            if stage == "refine":
                return prompt.rsplit("当前SQL：", 1)[1].split("\n\n只输出", 1)[0].strip()
            raise AssertionError(stage)
        diagnostic = {}
        schema_context = nullcontext() if args.native_service else patch.object(m, "_get_table_schemas", return_value="")
        with patch.object(m, "llm_ask", side_effect=ask), schema_context:
            ordinary = m.match_runbook(question, library, retriever, diagnostic)
        assert ordinary is not None, (family, diagnostic)
        assert "family_id" not in ordinary and isinstance(ordinary["api_call"], (dict, list)) and "{{" not in json.dumps(ordinary["api_call"])
        assert all(key not in ordinary for key in ["projection", "view"])
        result["controlled_pipeline"].append({"family": family, "view": parameters.get("view"), "stages": stages,
                                                "default_candidate_count": len(candidates), "ordinary": True})
    negative = [
        ("F02", "查询ECS名称包含Demo_name的创建时间", {"view": "ecs_creation_time", "filters": {"name": "Demo_name"}, "required_filters": ["name"]}),
        ("F02", "查询ECS名称为Demo_name或名称为Other的创建时间", {"view": "ecs_creation_time", "filters": {"name": "Demo_name"}, "required_filters": ["name"]}),
        ("F02", "查询ECS名称不是Demo_name的创建时间", {"view": "ecs_creation_time", "filters": {"name": "Demo_name"}, "required_filters": ["name"]}),
        ("F02", "查询ECS实例Demo_name的创建时间及GaussDB实例清单", {"view": "ecs_creation_time", "filters": {"name": "Demo_name"}, "required_filters": ["name"]}),
        ("F19", "查询GaussDB实例Demo_name的业务IP", {"view": "db_named_ha_vip", "filters": {"name": "Demo_name"}, "required_filters": ["name"]}),
        ("F19", "查询GaussDB实例Demo_name的高可用模式和数据VIP", {"view": "db_named_ha_vip", "filters": {"name": None}, "required_filters": ["name"]}),
    ]
    for family, question, parsed in negative:
        diagnostic = {}
        assert views.prepare_natural_candidate(question, families[family], parsed, views._prepare_batch3_candidate, diagnostic) is None
        result["negative_controls"].append({"family": family, "rejected": True, "reason": diagnostic.get("natural_view_error") or diagnostic.get("family_error")})
    obs = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"}, "required_filters": ["logicalRegionName"], "view": "rows"}
    for question in ["查询区域region_demo下OBS桶容量", "查询区域region_demo下OBS桶列表和数量", "查询区域不是region_demo下OBS桶列表", "查询区域region_demo或区域region_other下OBS桶列表"]:
        try:
            m._ground_obs_parameters(question, obs)
        except ValueError as exc:
            result["negative_controls"].append({"family": "F27", "rejected": True, "reason": str(exc)})
        else:
            raise AssertionError(question)
    if args.native_service:
        # 同一原生CI读取少量schema样例，只用于构造正常范围；不是标准答案。
        samples = {}
        for ci in ["VM_NOVA", "HOST", "VOLUME", "GAUSSDB_INSTANCE", "NETWORK", "FLOATING_IPS", "OBS_BUCKET"]:
            response = m._schema_session.get(m.SCHEMA_BASE_URL + "/rest/hackthon/db/schema/" + ci, timeout=5)
            response.raise_for_status()
            samples[ci] = response.json()["sample_data"]
        for family, question, parameters in contracts():
            target = families[family]
            ci = views._B3_SPECS[family]["ci"] if family in views._B3_SPECS else m._FAMILY_SPECS[family]["ci"]
            native = copy.deepcopy(parameters)
            fields = list(native["filters"])
            sample = next((row for row in samples[ci] if all(row.get(field) is not None and str(row[field]).strip() for field in fields if field not in {"shared", "management"})), None)
            if sample is None:
                # schema只返回两条样例；首次native页仅作正常范围取值，不作为完整性证明。
                response = m._schema_session.get(m.SCHEMA_BASE_URL + "/rest/hackthon/db/instances/" + ci + "?pageNo=1&pageSize=10000", timeout=10)
                response.raise_for_status()
                samples[ci] = response.json()["objList"]
                sample = next((row for row in samples[ci] if all(row.get(field) is not None and str(row[field]).strip() for field in fields if field not in {"shared", "management"})), None)
            assert sample is not None, (family, fields)
            native["filters"] = {field: native["filters"][field] if field in {"shared", "management"} else str(sample[field]) for field in fields}
            make = (lambda params: views._materialize_batch3(target, views.view_parameters(target, params))) if family in views._B3_SPECS else (lambda params: m._materialize_family(target, params))
            ordinary = make(native)
            source_rows, _ = executor._execute_single_api_call(ordinary["api_call"])
            assert source_rows, (family, "native normal scope has no source records")
            normal = executor.execute(ordinary)
            assert not normal["error"], (family, normal["error"])
            empty = copy.deepcopy(native)
            field = next(field for field in fields if field not in {"shared", "management"})
            empty["filters"][field] = "a170_missing_entity_control_20261030"
            empty_ordinary = make(empty)
            empty_source, _ = executor._execute_single_api_call(empty_ordinary["api_call"])
            assert not empty_source
            empty_output = executor.execute(empty_ordinary)
            assert not empty_output["error"], (family, empty_output["error"])
            if family == "F20" and parameters.get("view") == "count":
                # 原SDK为空表插入_empty占位行；只记录，不能称语义正确或改官方文件。
                assert empty_output["result"]["rows"] == [{"total": 1}]
                result["known_official_SDK_limits"].append({"case": "empty_scalar_count", "logical_expected_count": 0,
                    "SDK_actual_count": 1, "official_source": "load_into_sqlite inserts one _empty placeholder row", "fixed": False})
            else:
                assert empty_output["result"]["row_count"] == 0, (family, empty_output)
            result["native_results"].append({"family": family, "view": parameters.get("view"), "normal_error": normal["error"],
                "normal_rows": normal["result"]["row_count"], "empty_error": empty_output["error"], "empty_rows": empty_output["result"]["row_count"],
                "normal_source_records": len(source_rows), "empty_source_records": 0, "empty_columns": empty_output["result"]["columns"]})
        missing = views._materialize_batch3(families["F02"], views.view_parameters(families["F02"],
            {"view": "ecs_creation_time", "filters": {"name": "Demo_name"}, "required_filters": ["name"]}))
        with patch.object(executor, "_query_server", return_value=[{"id": "fixture_without_required_columns"}]):
            missing_output = executor.execute(missing)
        assert missing_output["error"] is None and missing_output["result"] == {"columns": [], "rows": [], "row_count": 0}
        result["known_official_SDK_limits"].append({"case": "synthetic_missing_columns", "SDK_actual": missing_output,
            "official_source": "execute catches no such column and emits empty rows", "not_native_service_mutation": True, "fixed": False})
    result["status"] = "free_contract_checks_passed_native_empty_semantic_gate_blocked"
    result["native_empty_semantic_gate_passed"] = False
    result["model_execution_allowed_by_this_report"] = False
    assert not m.get_llm_events()
    result["controlled_pipeline_count"] = len(result["controlled_pipeline"])
    result["native_cases"] = len(result["native_results"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ["status", "templates", "families", "primary_documents", "attribute_documents", "controlled_pipeline_count", "native_cases", "model_requests"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
