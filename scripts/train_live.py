"""固定训练诊断；仅显式解封冻结参数允许单次50题验证，默认只预检。"""

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from training_data import load_training, sha, SPLIT
from run_whitebox import now, result_preview, peak_memory_mib, percentile

HERE = Path(__file__).resolve().parents[1]
V2_HISTORY_FILES = ("train150_v2_live.jsonl", "train150_v2_resume_live.jsonl")


def runtime_source_paths(modules):
    """拒绝被旧目录/PYTHONPATH/sys.modules污染的运行时。"""
    result = {}
    for name, module in modules.items():
        actual = Path(getattr(module, "__file__", "")).resolve()
        expected = (HERE / "implementation" / (name + ".py")).resolve()
        if actual != expected:
            raise ValueError("运行时源码不来自本clone：" + name)
        result[name] = str(actual)
    return result


def a170_source_contract(root):
    """只接受已复建并审查的170库与全部来源；不放宽原保护文件。"""
    name = "experiments/a170_runtime_port_20261030/SOURCE_MANIFEST.json"
    candidate = json.loads((root / name).read_text())
    expected = {
        "implementation/runbook_items.py": "040040177f8db8bcfa62252567ffbc41199dd0ae8bfd8d2a34aa68364680b28c",
        "implementation/runbook_retriever.py": "befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24",
        "implementation/runbook_family_views.py": "7915b297783e71fc6ac405c5d0f01184ae49299e6775b7446b7a62131c7dbba7",
    }
    if (candidate.get("A_ref") != "6d3b47318ce767ef947c68019a2dce522de98c7a"
            or candidate.get("template_json_sha256") != "f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c"
            or candidate.get("runtime_hashes") != expected
            or any(sha(root / path) != digest for path, digest in expected.items())
            or any(sha(root / path) != digest for path, digest in candidate["source_files"].items())):
        raise ValueError("A170库、检索、视图或来源指纹变化，停止")
    return candidate, [name, *sorted(candidate["source_files"]), "implementation/runbook_family_views.py"]


def select_cases(cases, requested_ids, phase):
    """只缩小load_training给出的固定成员；题号只用于冻结实验范围。"""
    if len(cases) != 150 or len({case["case_id"] for case in cases}) != 150:
        raise ValueError("必须由load_training读取完整固定150训练题")
    if requested_ids is None:
        if phase is not None:
            raise ValueError("--phase必须与明确的--case-id子集一起使用")
        return cases, "train_only", "full_training"
    if (not requested_ids or len(requested_ids) > 150
            or any(not isinstance(value, str) or not value.strip() for value in requested_ids)):
        raise ValueError("子集题号不能为空且不能超过150个")
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("子集题号不能重复")
    if phase not in {"failure_probe", "passed_regression"}:
        raise ValueError("子集必须显式指定--phase failure_probe或passed_regression")
    known = {case["case_id"] for case in cases}
    if not set(requested_ids) <= known:
        raise ValueError("子集包含固定训练150之外的题号")
    return [case for case in cases if case["case_id"] in requested_ids], "train_subset", phase


def a160_source_contract(root):
    """固定A160数据与纯函数来源；官方保护清单保持原判定。"""
    name = "experiments/a160_runtime_port_20261030/SOURCE_MANIFEST.json"
    candidate = json.loads((root / name).read_text())
    expected = {
        "implementation/runbook_items.py": "8df154209342b3b983cb2f73015cd00ce8603ffc7e480397ae32f8030e3007a6",
        "implementation/runbook_retriever.py": "befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24",
        "implementation/runbook_family_views.py": "7915b297783e71fc6ac405c5d0f01184ae49299e6775b7446b7a62131c7dbba7",
        "implementation/runbook_family_batch4.py": "cbbf06aed3a921ccf1940c23568666f14b7838b945c46439682f15b985e3d781",
        "implementation/runbook_family_single.py": "04098b713541a87681e0e916f84ccb4d82644ee218a68e424587c1cd3ced6576",
        "implementation/runbook_family_count.py": "ebd8200c53d358a98ef2e8720cff87393300bb89e036d31d590dfb4c56120c87",
    }
    if (candidate.get("A_ref") != "e0f34ed42937203631eef0309964431c376cd179"
            or candidate.get("template_json_sha256") != "477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182"
            or candidate.get("runtime_hashes") != expected
            or any(sha(root / path) != digest for path, digest in expected.items())
            or any(sha(root / path) != digest for path, digest in candidate["source_files"].items())):
        raise ValueError("A160库、检索、helper或来源指纹变化，停止")
    return candidate, [name, *sorted(candidate["source_files"]), *sorted(expected)]


def phase_metadata(selected, history, phase):
    """回归严格限v2已过题；失败小测是显式标签，可包含之后新发现的失败。"""
    if phase not in {"failure_probe", "passed_regression"}:
        raise ValueError("未知子集阶段")
    if len(history) != 150 or len({row["case_id"] for row in history}) != 150:
        raise ValueError("子集阶段必须引用完整150训练历史")
    by_id = {row["case_id"]: row for row in history}
    qualities = []
    for case in selected:
        prior = by_id.get(case["case_id"], {})
        quality = prior.get("score_without_time_penalty")
        if prior.get("question") != case["question"] or type(quality) not in {int, float}:
            raise ValueError("阶段历史缺题、题文或无时延质量")
        if phase == "passed_regression" and quality != 5:
            raise ValueError("passed_regression只能选固定v2历史已满5质量的训练题")
        qualities.append({"case_id": case["case_id"], "v2_quality": quality})
    return {"reference": "fixed v2 parent147 plus resume3; not one continuous pass",
            "membership_policy": ("v2 untimed quality must equal 5" if phase == "passed_regression" else
                                  "explicit failure-probe label; v2 quality may be 5 for later-discovered failures"),
            "case_quality": qualities,
            "v2_full_quality_members": [item["case_id"] for item in qualities if item["v2_quality"] == 5]}


def subset_history(manifest, all_cases, selected, phase):
    # 复用既有严格parent+resume来源、顺序、请求账目核验；没有任意历史文件入口。
    from train_prompt_probe import validate_history
    paths = [HERE/"experiments"/name for name in V2_HISTORY_FILES]
    rows = [[json.loads(line) for line in path.read_text().splitlines()] for path in paths]
    parent, history = validate_history(manifest, all_cases, rows[0], rows[1], sha(paths[0]), sha(SPLIT/"manifest.json"))
    metadata = phase_metadata(selected, history, phase)
    metadata.update(file_sha256={path.name: sha(path) for path in paths},
                    source_sha256=parent["source_sha256"], training_sha256=parent["training_sha256"])
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expected-plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--request-limit", type=int, help="本次最多请求数；仅可收紧默认3倍题数及450上限")
    parser.add_argument("--a180-candidate", action="store_true", help="显式采用已审查A180构建指纹；不改变原198基线清单")
    parser.add_argument("--a170-candidate", action="store_true", help="采用已审查A170完整来源清单；仅隔离候选")
    parser.add_argument("--a160-candidate", action="store_true", help="采用固定A160完整来源与R2解析；仅训练候选")
    parser.add_argument("--a132-candidate", action="store_true", help="显式采用固定A132v2/r4数组引擎配对及12变更族入口")
    parser.add_argument("--candidate-flags", action="store_true", help="启用已通过训练回放的本轮通用保护")
    parser.add_argument("--refine-contract-prompt", action="store_true", help="独立SQL输出合同提示词候选，默认关闭")
    parser.add_argument("--independent-aggregates", action="store_true", help="独立资源完整聚合候选，默认关闭")
    parser.add_argument("--grouped-aggregates", action="store_true", help="同范围各VDC网络资源完整计数，默认关闭")
    parser.add_argument("--network-details", action="store_true", help="具名VM网卡计数与CIDR对应明细，默认关闭")
    parser.add_argument("--identity-projection", action="store_true", help="固定SQL角色证明的实例标识补列，默认关闭")
    parser.add_argument("--vpc-subnets", action="store_true", help="逐VPC透明子网统计，默认关闭")
    parser.add_argument("--tenant-resources", action="store_true", help="同区域各租户完整资源及规格统计，默认关闭")
    parser.add_argument("--vm-volume-details", action="store_true", help="同租户区域VM及卷完整明细，默认关闭")
    parser.add_argument("--tenant-vdc-binding", action="store_true", help="同CI原生查询证明租户对应VDC条件，默认关闭")
    parser.add_argument("--parallel-resource-lists", action="store_true", help="同范围VM/卷/VPC三份独立列表，默认关闭")
    parser.add_argument("--sg-rule-semijoin", action="store_true", help="规则按真实安全组父ID分批读取，默认关闭")
    parser.add_argument("--verified-empty-root", action="store_true", help="已证空根保留SQL列并停止后续依赖，默认关闭")
    parser.add_argument("--typed-empty-root", action="store_true", help="单CI真实空集按正确空表执行，COUNT为0，默认关闭")
    parser.add_argument("--no-empty-answer-fallback", action="store_true", help="关闭用户默认启用的拒答/错误猜空策略，用于原行为对照")
    parser.add_argument("--detail-count", action="store_true", help="同范围原明细与对象总数完整输出，默认关闭")
    parser.add_argument("--ground-sql-measures", action="store_true", help="拒绝SQL时钟/随机伪造业务测量，默认关闭")
    parser.add_argument("--partial-storage-pools", action="store_true", help="存储池明细/容量与明确磁盘类型缺项，默认关闭")
    parser.add_argument("--preserve-sparse-nulls", action="store_true", help="保留已审稀疏NULL投影候选；参考范围冲突未解决，默认关闭")
    parser.add_argument("--bind-deploy-node-region", action="store_true", help="部署节点规范区域ID绑定候选；默认关闭")
    parser.add_argument("--issue3-contracts", action="store_true", help="接入A已交付组合合同；完整原文与原生preflight门禁，默认关闭")
    parser.add_argument('--issue3-profile',action='append',choices=('namespace_counts','tenant_lists','vdc_network',
        'vdc_counts','network','capacity','tenant_vm_rank','tenant_volume_rank'),help='只开启指定A合同，可重复；须同时指定--issue3-contracts')
    parser.add_argument("--thinking-mode", choices=("provider_default", "disabled"), default="disabled",
                        help="固定思考模式；默认disabled显式关闭thinking，provider_default不传额外参数")
    parser.add_argument("--case-id", action="append", help="可重复指定固定训练成员；最终按原train顺序运行")
    parser.add_argument("--phase", choices=("failure_probe", "passed_regression"), help="子集实验阶段，必须显式指定")
    parser.add_argument("--sealed-validation-freeze", type=Path, help="用户本轮明确解封的固定50验证；必须先冻结运行时")
    parser.add_argument("--validation-resume", type=Path, help="只补固定50因本地文件中断、且尚无模型流量的后缀")
    parser.add_argument("--validation-case-id", action="append", help="已曝光验证题失败子集；必须有绑定相同成员的新冻结")
    parser.add_argument("--whitebox200", action="store_true", help="用户明确要求后显式全200诊断；默认入口仍只训练150，请求上限450")
    args = parser.parse_args(argv)
    from check_official_integrity import require_official_files
    try:
        if args.issue3_profile and (not args.issue3_contracts or len(set(args.issue3_profile))!=len(args.issue3_profile)):
            raise ValueError('A合同profile要求显式启用且不能重复')
        official_integrity = require_official_files(HERE)
    except ValueError as exc:
        parser.error(str(exc))
    manifest, all_cases, _ = load_training()  # 失败即停；不打开原200题或封存文件。
    sealed_validation = args.sealed_validation_freeze is not None
    validation = sealed_validation or args.whitebox200
    resume_evidence = None
    try:
        if args.validation_case_id is not None and (not sealed_validation or args.validation_resume is not None
                or args.whitebox200 or args.case_id is not None or args.phase is not None):
            raise ValueError('验证失败子集不能混用训练/全量/续跑范围')
        if args.validation_resume is not None and (not sealed_validation or args.whitebox200):
            raise ValueError('验证续跑必须使用新的50验证冻结，不能混用其他范围')
        if args.whitebox200:
            if sealed_validation or args.case_id is not None or args.phase is not None:
                raise ValueError('全200不允许混用50冻结或训练子集参数')
            from validation_data import load_explicit_whitebox200
            cases = load_explicit_whitebox200(HERE, manifest, all_cases)
            scope, phase = 'whitebox200_explicit', 'user_authorized_full_whitebox_once'
        elif sealed_validation:
            if args.case_id is not None or args.phase is not None:
                raise ValueError('50验证不允许子集、挑题或重抽')
            if args.validation_case_id is not None:
                from validation_data import load_validation_subset
                cases = load_validation_subset(HERE, args.sealed_validation_freeze, manifest, all_cases, args.validation_case_id)
                scope, phase = 'validation_subset', 'user_authorized_validation_failure_subset'
            else:
                from validation_data import load_sealed_validation
                cases = load_sealed_validation(HERE, args.sealed_validation_freeze, manifest, all_cases)
                scope, phase = 'sealed50_validation', 'user_authorized_validation_once'
            if args.validation_resume is not None:
                from validation_resume import remaining_validation
                cases, resume_evidence = remaining_validation(HERE, args.validation_resume, cases)
                scope, phase = 'sealed50_resume', 'unrun_validation_suffix_after_local_file_interruption'
        else:
            cases, scope, phase = select_cases(all_cases, args.case_id, args.phase)
        phase_reference = subset_history(manifest, all_cases, cases, phase) if scope == "train_subset" else None
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    case_count, max_requests = len(cases), min(3 * len(cases), 450)
    if args.request_limit is not None:
        if not 1 <= args.request_limit <= min(max_requests, 450):
            parser.error("--request-limit只能在1与默认预算之间收紧")
        max_requests = args.request_limit
    training_indices = {case["case_id"]: index+1 for index, case in enumerate(all_cases)}
    local = HERE/".env.local"
    if local.exists():
        for line in local.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}:
                os.environ[name] = value
    flags = {"RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1", "RUNBOOK_RULE_ONLY_FILL": "1",
             "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1", "RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": "1",
             "RUNBOOK_VALIDATE_API_DEPENDENCIES": "0", "RUNBOOK_BOUNDED_API": "0"}
    flags.update({name: "1" if args.candidate_flags else "0" for name in [
        "RUNBOOK_PRESERVE_AGGREGATE_GRAIN", "RUNBOOK_PRESERVE_LITERAL_LABELS",
        "RUNBOOK_PRUNE_UNUSED_LOOKUPS", "RUNBOOK_GROUND_ENUM_LABELS"]})
    flags["RUNBOOK_REFINE_CONTRACT_PROMPT"] = "1" if args.refine_contract_prompt else "0"
    flags["RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES"] = "1" if args.independent_aggregates else "0"
    flags["RUNBOOK_COMPLETE_GROUPED_AGGREGATES"] = "1" if args.grouped_aggregates else "0"
    flags["RUNBOOK_COMPLETE_NETWORK_DETAILS"] = "1" if args.network_details else "0"
    flags["RUNBOOK_COMPLETE_IDENTITY_PROJECTION"] = "1" if args.identity_projection else "0"
    flags["RUNBOOK_COMPLETE_VPC_SUBNETS"] = "1" if args.vpc_subnets else "0"
    flags["RUNBOOK_COMPLETE_TENANT_RESOURCES"] = "1" if args.tenant_resources else "0"
    flags["RUNBOOK_COMPLETE_VM_VOLUME_DETAILS"] = "1" if args.vm_volume_details else "0"
    flags["RUNBOOK_BIND_TENANT_VDC"] = "1" if args.tenant_vdc_binding else "0"
    flags["RUNBOOK_COMPLETE_PARALLEL_LISTS"] = "1" if args.parallel_resource_lists else "0"
    flags["RUNBOOK_SG_RULE_SEMIJOIN"] = "1" if args.sg_rule_semijoin else "0"
    flags["RUNBOOK_VERIFIED_EMPTY_ROOT"] = "1" if args.verified_empty_root else "0"
    flags["RUNBOOK_TYPED_EMPTY_ROOT"] = "1" if args.typed_empty_root else "0"
    flags["RUNBOOK_EMPTY_ANSWER_FALLBACK"] = "0" if args.no_empty_answer_fallback else "1"
    flags["RUNBOOK_COMPLETE_DETAIL_COUNT"] = "1" if args.detail_count else "0"
    flags["RUNBOOK_GROUND_SQL_MEASURES"] = "1" if args.ground_sql_measures else "0"
    flags["RUNBOOK_PARTIAL_STORAGE_POOLS"] = "1" if args.partial_storage_pools else "0"
    flags["RUNBOOK_PRESERVE_SPARSE_NULLS"] = '1' if args.preserve_sparse_nulls else '0'
    flags["RUNBOOK_BIND_DEPLOY_NODE_REGION"] = '1' if args.bind_deploy_node_region else '0'
    flags['RUNBOOK_ISSUE3_CONTRACTS']='1' if args.issue3_contracts else '0'
    flags['RUNBOOK_ISSUE3_PROFILES']=json.dumps(sorted(args.issue3_profile) if args.issue3_profile else None,separators=(',',':'))
    flags["RUNBOOK_THINKING_MODE"] = args.thinking_mode
    thinking_extra_body = {"thinking": {"type": "disabled"}} if args.thinking_mode == "disabled" else None
    os.environ.update(flags)
    os.environ["RUNBOOK_MAX_LLM_CALLS"] = str(max_requests)
    os.environ["RUNBOOK_MAX_OUTPUT_TOKENS"] = "1024"
    sys.path.insert(0, str(HERE/"implementation"))
    import runbook_matcher as matcher
    import runbook_system as system_module
    import runbook_items
    from evaluator import evaluate_case
    is170 = args.a170_candidate or len(runbook_items.RUNBOOK_ITEMS) == 170
    is160 = args.a160_candidate or len(runbook_items.RUNBOOK_ITEMS) == 160
    is132 = args.a132_candidate or len(runbook_items.RUNBOOK_ITEMS) == 132
    flags['RUNBOOK_A132_CANDIDATE'] = '1' if is132 else '0'
    os.environ['RUNBOOK_A132_CANDIDATE'] = flags['RUNBOOK_A132_CANDIDATE']
    if sum([bool(args.a180_candidate), bool(is170), bool(is160), bool(is132)]) > 1:
        parser.error("不能同时选择不同条数的候选")
    module_names = ["runbook_matcher", "runbook_system", "runbook_items", "runbook_retriever", "runbook_executor", "evaluator"]
    if is170 or is160 or is132:
        import runbook_family_views
        module_names.append("runbook_family_views")
    if is160 or is132:
        import runbook_family_batch4, runbook_family_single, runbook_family_count
        module_names += ["runbook_family_batch4", "runbook_family_single", "runbook_family_count"]
    try:
        runtime_paths = runtime_source_paths({name: sys.modules[name] for name in module_names})
    except ValueError as exc:
        parser.error(str(exc))
    runtime_manifest = json.loads((HERE/"baseline_manifest.json").read_text())
    readonly = dict(runtime_manifest["readonly_files"])
    template_revision = {"mode": "baseline", "expected_items_sha256": readonly["implementation/runbook_items.py"]}
    candidate_sources = []
    if is132:
        try:
            candidate, source_files, variant = matcher._verify_a132_sources(HERE)
        except (ValueError, KeyError, OSError) as exc:
            parser.error(str(exc))
        if (len(runbook_items.RUNBOOK_ITEMS) != 132
                or len({item['id'] for item in runbook_items.RUNBOOK_ITEMS}) != 132
                or sum(bool(item.get('family_id')) for item in runbook_items.RUNBOOK_ITEMS) != 26):
            parser.error('A132模板及family结构不符')
        candidate_sources = list(source_files)
        readonly.update(candidate['variants'][variant]['runtime_hashes'])
        template_revision = {'mode': 'a132_reviewed_private_build', 'A_ref': candidate['A_ref'],
                             'variant': variant, 'package_manifest_sha256': candidate['package_manifest_sha256'],
                             'runtime_hashes': candidate['variants'][variant]['runtime_hashes']}
    elif is160:
        try:
            candidate, candidate_sources = a160_source_contract(HERE)
        except (ValueError, KeyError, OSError) as exc:
            parser.error(str(exc))
        if (len(runbook_items.RUNBOOK_ITEMS) != 160
                or len({item["id"] for item in runbook_items.RUNBOOK_ITEMS}) != 160
                or sorted(item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id")) != candidate["families"]):
            parser.error("A160活动库结构不符，停止")
        for path in ("implementation/runbook_items.py", "implementation/runbook_retriever.py"):
            readonly[path] = candidate["runtime_hashes"][path]
        template_revision = {"mode": "a160_reviewed_private_build", "A_ref": candidate["A_ref"],
                             "manifest_sha256": sha(HERE / "experiments/a160_runtime_port_20261030/SOURCE_MANIFEST.json"),
                             "runtime_hashes": candidate["runtime_hashes"]}
    elif is170:
        try:
            candidate, candidate_sources = a170_source_contract(HERE)
        except (ValueError, KeyError, OSError) as exc:
            parser.error(str(exc))
        if (len(runbook_items.RUNBOOK_ITEMS) != 170
                or len({item["id"] for item in runbook_items.RUNBOOK_ITEMS}) != 170
                or sorted(item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id")) != candidate["families"]):
            parser.error("A170活动库结构不符，停止")
        for path in ("implementation/runbook_items.py", "implementation/runbook_retriever.py"):
            readonly[path] = candidate["runtime_hashes"][path]
        template_revision = {"mode": "a170_reviewed_private_build", "A_ref": candidate["A_ref"],
                             "manifest_sha256": sha(HERE / "experiments/a170_runtime_port_20261030/SOURCE_MANIFEST.json"),
                             "runtime_hashes": candidate["runtime_hashes"]}
    elif args.a180_candidate or any(item.get("family_id") for item in runbook_items.RUNBOOK_ITEMS):
        package = HERE / "experiments/a_family_candidate_20261030"
        candidate = json.loads((package / "manifest.json").read_text())
        if any(sha(package / name) != digest for name, digest in candidate["files"].items()):
            parser.error("A180候选来源指纹变化，停止")
        if (len(runbook_items.RUNBOOK_ITEMS) != 180
                or len({item["id"] for item in runbook_items.RUNBOOK_ITEMS}) != 180
                or sorted(item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id"))
                != ["F01", "F08", "F14", "F18", "F20", "F21"]):
            parser.error("A180活动库结构不符，停止")
        readonly["implementation/runbook_items.py"] = candidate["materialized_candidate_Python_sha256"]
        template_revision = {"mode": "a180_reviewed_build", "base_ref": candidate["base_ref"],
                             "previous_items_sha256": runtime_manifest["readonly_files"]["implementation/runbook_items.py"],
                             "expected_items_sha256": readonly["implementation/runbook_items.py"],
                             "manifest_sha256": sha(package / "manifest.json")}
        candidate_sources = ["scripts/build_a180_candidate.py", "experiments/a_family_candidate_20261030/manifest.json"]
        candidate_sources += ["experiments/a_family_candidate_20261030/" + name for name in sorted(candidate["files"])]
    if not all(sha(HERE/name) == digest for name, digest in readonly.items()):
        parser.error("只读文件变化，停止")
    sources = ["scripts/train_live.py", "scripts/training_data.py", "scripts/run_whitebox.py", "scripts/check_official_integrity.py", "baseline_manifest.json"] + ["implementation/"+name for name in
               ["runbook_matcher.py", "runbook_system.py", "runbook_items.py", "runbook_retriever.py", "evaluator.py", "runbook_executor.py"]]
    sources.append("implementation/runbook_aggregates.py")
    sources += ["implementation/runbook_network_details.py", "implementation/runbook_projection_roles.py"]
    sources.append("implementation/runbook_vpc_subnets.py")
    sources.append("implementation/runbook_tenant_resources.py")
    sources.append("implementation/runbook_vm_volume_details.py")
    sources += ["implementation/runbook_scope_bindings.py", "implementation/runbook_identity_guard.py"]
    sources.append("implementation/runbook_parallel_resource_lists.py")
    sources.append("implementation/runbook_sg_rule_semijoin.py")
    sources.append("implementation/runbook_empty_root.py")
    sources.append("implementation/runbook_detail_count.py")
    sources.append("implementation/runbook_measurement_guard.py")
    sources.append("implementation/runbook_storage_pool_partial.py")
    sources += ["implementation/quick_eval.py", "implementation/blackbox_eval.py"]
    sources += candidate_sources
    if args.issue3_contracts:
        import runbook_issue3
        sources += ['implementation/runbook_issue3.py',*runbook_issue3.source_files()]
    handoff_evidence = {}
    for record in runtime_manifest.get("integration", {}).get("reconciled_files", {}).values():
        path, expected = record.get("handoff_evidence"), record.get("handoff_evidence_sha256")
        if path and expected:
            if sha(HERE/path) != expected:
                parser.error("来源交接证据哈希不符，未调用模型")
            handoff_evidence[path] = expected
    sources += sorted(handoff_evidence)
    if scope == "train_subset":
        sources.append("scripts/train_prompt_probe.py")
    if sealed_validation:
        sources += ['scripts/validation_data.py', str(args.sealed_validation_freeze.resolve().relative_to(HERE))]
        if resume_evidence:
            sources += ['scripts/validation_resume.py', *resume_evidence['files_sha256']]
    elif args.whitebox200:
        sources += ['scripts/validation_data.py', 'CMDB用例集-白盒200.json']
    plan = {"type": "validation_plan" if validation else "training_plan", "created_at": now(), "split_id": manifest["split_id"],
            "record_format": 2,
            "case_count": case_count, "case_ids": [case["case_id"] for case in cases], "phase": phase,
            "phase_reference": phase_reference,
            "repeats": 1, "case_order": ("original whitebox file order" if args.whitebox200 else
                                         "fixed sealed file order" if sealed_validation else "fixed train file order"), "scope": scope,
            "training_sha256": manifest["train_sha256"], "split_manifest_sha256": sha(SPLIT/"manifest.json"),
            "training_history_sha256": manifest["train_history_sha256"],
            "source_sha256": {name: sha(HERE/name) for name in sources},
            "runtime_source_paths": runtime_paths,
            "template_revision": template_revision,
            "family_ids": sorted({item["family_id"] for item in runbook_items.RUNBOOK_ITEMS if item.get("family_id")}),
            "scoring_revision": official_integrity.get("accepted_revisions", {}),
            "source_handoff_sha256": handoff_evidence,
            "code_base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
            "model": matcher.DEEPSEEK_MODEL, "base_url": matcher.DEEPSEEK_BASE_URL,
            "max_requests": max_requests, "max_output_tokens": 1024, "sdk_max_retries": 0,
            "thinking": "provider default" if args.thinking_mode == "provider_default" else "disabled",
            "thinking_mode": args.thinking_mode, "thinking_extra_body": thinking_extra_body,
            "temperature": "provider default", "feature_flags": flags,
            "template_count": len(runbook_items.RUNBOOK_ITEMS), "holdout_evaluated": validation,
            "score_policy": "original query and evaluate_case; no weighting or template-count score",
            "cache_policy": "fresh process; schema warmup excluded; executor cache shared across training cases",
            "authorization": "preflight only; bounded training runs may be decided under the user's standing autonomy authorization; freeze and record each actual scope before --run"}
    if sealed_validation:
        plan.update(evaluation_sha256=manifest['sealed_test_sha256'],
                    partition_status='validation_after_explicit_user_exposure',
                    authorization='user explicitly requested testing the remaining fixed50 on 2026-10-30; one bounded pass')
        if scope == 'validation_subset':
            plan['authorization'] = 'user explicitly requested fixing B_ONLY and B_INTEGRATE on 2026-10-31; bounded exposed validation failure subset'
    elif args.whitebox200:
        plan.update(evaluation_sha256=manifest['source_dataset_sha256'],
                    partition_status='development_whitebox_after_holdout_exposure',
                    authorization='user explicitly requested a complete run on 2026-10-30; original200 once, up to450 calls')
    if resume_evidence:
        plan['resume_parent'] = resume_evidence
    if args.expected_plan:
        expected = json.loads(args.expected_plan.read_text())
        if any(expected.get(key) != value for key, value in plan.items() if key not in {"created_at", "authorization"}):
            parser.error("候选/范围/配置与冻结计划不同，未调用模型")
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.run:
        return 0
    if not args.expected_plan or not args.output:
        parser.error("真实运行必须指定冻结计划和新的输出路径")
    if not matcher.DEEPSEEK_API_KEY or matcher.get_llm_events():
        parser.error("需要已配置密钥及新进程")
    if args.output.exists():
        parser.error("不覆盖已有训练记录")
    original_ask, original_create = matcher.llm_ask, None
    records, identities, mismatch = [], {}, []
    fatal_request_errors = []
    started, exit_code = time.perf_counter(), 1

    def frozen():
        if fatal_request_errors:
            raise RuntimeError("本轮已有模型请求或来源异常，禁止发起后续请求")
        if (runtime_source_paths({name: sys.modules[name] for name in runtime_paths}) != runtime_paths
                or any(sha(HERE/name) != digest for name, digest in plan["source_sha256"].items())
                or sha(SPLIT/"train.json") != plan["training_sha256"]
                or sha(SPLIT/"train_history.jsonl") != plan["training_history_sha256"]
                or sha(SPLIT/"manifest.json") != plan["split_manifest_sha256"]
                or sealed_validation and sha(SPLIT/'sealed_test.json') != plan['evaluation_sha256']
                or phase_reference is not None and any(sha(HERE/"experiments"/name) != digest
                                                       for name, digest in phase_reference["file_sha256"].items())
                or any(os.environ.get(key) != value for key, value in flags.items())
                or os.environ.get("RUNBOOK_MAX_LLM_CALLS") != str(max_requests)
                or os.environ.get("RUNBOOK_MAX_OUTPUT_TOKENS") != "1024" or mismatch):
            raise RuntimeError("训练源码、集合、配置或型号漂移，停止请求")

    logging.disable(logging.CRITICAL)
    with args.output.open("x", encoding="utf-8") as stream:
        def write(row):
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
            stream.flush()

        write(plan)
        try:
            frozen()
            system = system_module.RunbookQuerySystem()
            write({"type": "initialization", **system.initialization_metrics})
            original_create = matcher._llm_client.chat.completions.create

            def create(*values, **options):
                frozen()
                if matcher._llm_client.max_retries != 0:
                    raise RuntimeError("SDK重试必须为0")
                if (options.get("max_tokens") != 1024 or options.get("model") != plan["model"]
                        or len(matcher.get_llm_events()) > max_requests):
                    raise RuntimeError("模型输出/请求数超出冻结上限")
                if options.get("extra_body") != plan["thinking_extra_body"]:
                    raise RuntimeError("实际thinking请求参数与冻结模式不同，未发送请求")
                index = len(matcher.get_llm_events())-1
                response = original_create(*values, **options)
                identity = {"requested_model": options.get("model"), "response_model": getattr(response, "model", None)}
                identities[index] = identity
                if identity["requested_model"] != plan["model"] or identity["response_model"] != plan["model"]:
                    mismatch.append(identity)
                frozen()
                return response

            matcher._llm_client.chat.completions.create = create

            def ask(prompt, stage="unknown"):
                frozen()
                before = len(matcher.get_llm_events())
                error = {}
                try:
                    value = original_ask(prompt, stage)
                    frozen()
                    return value
                except Exception as exc:
                    error = {"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}
                    fatal_request_errors.append(error)
                    raise
                finally:
                    for index, event in enumerate(matcher.get_llm_events()[before:], before):
                        write({"type": "request", "case_id": cases[len(records)]["case_id"], **event,
                               "requested_model": plan["model"], "response_model": None, **identities.get(index, {}), **error})

            matcher.llm_ask = ask
            for index, case in enumerate(cases):
                frozen()
                t0 = time.perf_counter()
                output = system.query(case["question"])
                elapsed = time.perf_counter()-t0
                frozen()
                scored, untimed = evaluate_case(case, output, elapsed), evaluate_case(case, output, 0)
                row = {"type": "case", "case_index": index+1, **scored, "question": case["question"],
                       "training_case_index": training_indices.get(case["case_id"]),
                       "score_without_time_penalty": untimed["score"], "matched_runbook": output.get("matched_runbook"),
                       "api_call": output.get("api_call"), "sql": output.get("sql"), "result": result_preview(output.get("result")),
                       "diagnostics": output.get("diagnostics")}
                records.append(row)
                write(row)
                print(json.dumps({"completed": len(records), "of": case_count, "score": scored["score"]}), flush=True)
            exit_code = 0
        except Exception as exc:
            write({"type": "run_error", "error_type": type(exc).__name__,
                   "missing_file": str(exc.filename) if isinstance(exc, FileNotFoundError) else None,
                   "frames": [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                              for frame in traceback.extract_tb(exc.__traceback__)]})
        finally:
            events = matcher.get_llm_events()
            summary = {"type": "summary", "scope": scope, "phase": phase,
                       "thinking_mode": plan["thinking_mode"],
                       "case_ids": plan["case_ids"], "status": "complete" if exit_code == 0 and len(records) == case_count else "incomplete",
                       "completed_cases": len(records), "planned_cases": case_count, "max_score": 5 * case_count,
                       "total_score": round(sum(row["score"] for row in records), 1),
                       "untimed_score": round(sum(row["score_without_time_penalty"] for row in records), 1),
                       "full_quality_answers": sum(row["score_without_time_penalty"] == 5 for row in records),
                       "runtime_abstentions": sum(row["matched_runbook"] is None for row in records),
                       "empty_answer_guesses": sum(bool((row.get("diagnostics") or {}).get("empty_answer_fallback")) for row in records),
                       "scorer_abstentions": sum(row["score_without_time_penalty"] == 0 for row in records),
                       "generation_requests": len(events), "failed_requests": sum(row["status"] != "ok" for row in events),
                       "max_requests": max_requests,
                       "model_identity_mismatches": mismatch, "holdout_evaluated": validation,
                       "wall_seconds": round(time.perf_counter()-started, 3), "peak_evaluation_process_mib": peak_memory_mib(),
                       "latency_p50": percentile([row["elapsed"] for row in records], .5),
                       "latency_p95": percentile([row["elapsed"] for row in records], .95)}
            write(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            matcher.llm_ask = original_ask
            if matcher._llm_client is not None:
                if original_create is not None:
                    matcher._llm_client.chat.completions.create = original_create
                matcher._llm_client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
