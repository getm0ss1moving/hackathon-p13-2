"""训练回放的小型兼容门禁；零I/O、零模型，不改变历史记录或生产检索器。"""

import copy
import hashlib
import math
from pathlib import PurePosixPath
import sys


class ReplayStop(BaseException):
    """回放不变量失败，必须穿过生产query的except Exception并中止整轮。"""


ITEMS = "implementation/runbook_items.py"
RETRIEVER = "implementation/runbook_retriever.py"
EVALUATOR = "implementation/evaluator.py"
LEGACY_ITEMS = "8f795734400eac0217ccde86c9bcd9bb38d9682b22fe833739d9695a54c32cd1"
INTEGRATED_ITEMS = "34ac7400c905c9da3657038f9f7bc40a80f07e6ba43ef70eca6e4ca3197d1a35"
CURRENT_ITEMS = "9799b9fd6007e80f08610aa3d62d8495b3e85efe4924328477343c967a158465"
LEGACY_RETRIEVER = "1f00b14b1c7c24104a2695f1f33e94d223f59d0cd0277b766c2bb6d8a3135705"
CURRENT_RETRIEVER = "affd82bde40d7e138ee1e0202beb826ff3b247c83c6f9ec1a951b26772d5df17"
LEGACY_EVALUATOR = "c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22"
CURRENT_EVALUATOR = "d2a93903f068d77d84470dcd1e3eef8671571136c1d7cfb7e4f9b3307d3516c1"
APPROVED_ALIASES = {"rb_054": "rb_052", "rb_087": "rb_086"}
SCRIPT_MOVES = {name: "scripts/" + name for name in
                ("train_live.py", "training_data.py", "run_whitebox.py")}
APPROVED_EDGES = {
    ITEMS: ((LEGACY_ITEMS, INTEGRATED_ITEMS, "ad45ecc root integration"),
            (INTEGRATED_ITEMS, CURRENT_ITEMS, "2707ff9 strict dedup: 200 to 198")),
    RETRIEVER: ((LEGACY_RETRIEVER, CURRENT_RETRIEVER, "2707ff9 retrieval aliases"),),
    EVALUATOR: ((LEGACY_EVALUATOR, CURRENT_EVALUATOR,
                 "numeric_ratio_tolerance_20261030: user authorized"),),
}
OFFICIAL_CURRENT = {
    EVALUATOR: CURRENT_EVALUATOR,
    "implementation/runbook_executor.py": "4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92",
    "implementation/quick_eval.py": "41c28aa77be441451c440e3ab8f7b4bfbb6172cb5d87dc016a68c0f23fca7324",
    "implementation/blackbox_eval.py": "4f20375597dad1927fa12a0c72d14c31021bbcd3bc4d059629804b9d9469198c",
}
AUTHORIZED_REVISION = {
    "revision_id": "numeric_ratio_tolerance_20261030", "file": EVALUATOR,
    "base_commit": "d79c316", "previous_sha256": LEGACY_EVALUATOR,
    "revised_sha256": CURRENT_EVALUATOR,
    "before": "if abs(ratio - 100.0) < 0.1:",
    "after": "if abs(ratio - 1.0) < 0.1:",
    "evaluator_exact_single_line_patch": True, "historical_results_rewritten": False,
}


def current_source_path(historical_key):
    """仅规范化已知脚本的当前路径；调用方保留历史plan的原始key及hash。"""
    if (not isinstance(historical_key, str) or not historical_key
            or str(PurePosixPath(historical_key)) != historical_key
            or PurePosixPath(historical_key).is_absolute()
            or ".." in PurePosixPath(historical_key).parts or "\\" in historical_key):
        raise ReplayStop("非法来源路径")
    return SCRIPT_MOVES.get(historical_key, historical_key)


def reconcile_sources(historical, current):
    """只接受固定三类hash链；其余源码、executor及数据必须逐字节不变。

    current用当前路径作为key。不要把这当成绕过现有官方文件、训练集合、
    运行中source freeze的入口；这只是对同一组保护文件的差异逐一解释。
    """
    evidence = {}
    for old_key, expected in historical.items():
        key = current_source_path(old_key)
        actual = current.get(key)
        if not all(isinstance(value, str) and len(value) == 64
                   and set(value) <= set("0123456789abcdef") for value in (expected, actual)):
            raise ReplayStop("缺失或非法来源hash：" + key)
        visited, path, value = set(), [], expected
        while value != actual:
            if value in visited:
                raise ReplayStop("来源链循环：" + key)
            visited.add(value)
            edge = next((edge for edge in APPROVED_EDGES.get(key, ()) if edge[0] == value), None)
            if edge is None:
                raise ReplayStop("未经交接的源码/数据变化：" + key)
            path.append({"before_sha256": edge[0], "after_sha256": edge[1], "evidence": edge[2]})
            value = edge[1]
        if path or old_key != key:
            evidence[old_key] = {"current_path": key, "historical_sha256": expected,
                                 "current_sha256": actual, "accepted_transitions": path}
    return evidence


def require_official_hashes(current):
    if any(current.get(name) != expected for name, expected in OFFICIAL_CURRENT.items()):
        raise ReplayStop("官方文件hash不符合原件/唯一授权修订")


def verified_library_aliases(items, current_source_hashes):
    """只有审核过的A198两文件可提供alias；任意新alias或执行payload均拒绝。"""
    if current_source_hashes.get(ITEMS) != CURRENT_ITEMS or current_source_hashes.get(RETRIEVER) != CURRENT_RETRIEVER:
        raise ReplayStop("alias的A源码不是已核验版本")
    ids = [item.get("id") for item in items]
    if len(ids) != 198 or len(set(ids)) != 198 or any(not isinstance(value, str) or not value for value in ids):
        raise ReplayStop("A198活动ID不完整/不唯一")
    aliases = {}
    for item in items:
        for alias in item.get("retrieval_aliases", []):
            if (not isinstance(alias, dict) or set(alias) != {"id", "after_id", "examples", "description"}
                    or alias["id"] in ids or alias["id"] in aliases or alias["after_id"] not in ids):
                raise ReplayStop("alias冲突/含未知执行字段")
            aliases[alias["id"]] = item["id"]
    if aliases != APPROVED_ALIASES:
        raise ReplayStop("alias映射不是已交接的两项")
    return aliases


class SelectionReplay:
    """单题门禁：真实候选先核对，才允许该题任何GET或模拟模型阶段。"""

    def __init__(self, historical_ids, selected_id, active_ids, aliases, recorded_index=None):
        self.historical_ids, self.active_ids, self.aliases = tuple(historical_ids), frozenset(active_ids), dict(aliases)
        self.checked, self.failed, self.proof = False, False, None
        if (len(set(self.historical_ids)) != len(self.historical_ids)
                or any(not isinstance(value, str) or not value for value in self.historical_ids)):
            self.stop("历史候选ID为空/重复")
        self.expected_ids = tuple(dict.fromkeys(self.canonical(value) for value in self.historical_ids))
        if selected_id is not None and selected_id not in self.historical_ids:
            self.stop("历史选中ID不在历史候选中")
        self.selected_id = selected_id
        self.selected_canonical_id = self.canonical(selected_id) if selected_id is not None else None
        self.old_index = self.historical_ids.index(selected_id) + 1 if selected_id is not None else 0
        if recorded_index is not None and (type(recorded_index) is not int or recorded_index != self.old_index):
            self.stop("历史选中ID与记录序号不符")

    def stop(self, reason):
        self.failed, self.checked = True, False
        raise ReplayStop(reason)

    def canonical(self, value):
        target = self.aliases.get(value, value)
        if target not in self.active_ids:
            self.stop("未知或已删除且无已证alias的模板ID")
        return target

    def observe(self, current_ids):
        current_ids = tuple(current_ids)
        if (self.failed or len(set(current_ids)) != len(current_ids)
                or any(value not in self.active_ids for value in current_ids)
                or current_ids != self.expected_ids):
            self.stop("当前实际候选顺序不等于历史alias稳定去重结果")
        new_index = current_ids.index(self.selected_canonical_id) + 1 if self.selected_canonical_id is not None else 0
        self.checked = True
        self.proof = {"historical_candidate_ids": list(self.historical_ids),
                      "canonical_candidate_ids": list(self.expected_ids), "actual_candidate_ids": list(current_ids),
                      "historical_selected_id": self.selected_id, "canonical_selected_id": self.selected_canonical_id,
                      "historical_model_index": self.old_index, "replayed_model_index": new_index,
                      "alias_mappings_used": {value: self.aliases[value] for value in self.historical_ids if value in self.aliases}}
        return copy.deepcopy(self.proof)

    def require_ready(self):
        if not self.checked or self.failed:
            self.stop("该题实际候选尚未核验，禁止API/模拟模型")

    def model_index(self):
        self.require_ready()
        return self.proof["replayed_model_index"]

    def selected_item(self, items_by_id):
        self.require_ready()
        if self.selected_canonical_id is None or self.selected_canonical_id not in items_by_id:
            self.stop("该历史选择没有可执行canonical模板")
        return items_by_id[self.selected_canonical_id]


def guard_retrieve(retrieve, active_gate):
    """包装原instance.retrieve；不改检索算法。active_gate返回当前单题门禁。"""
    def checked(*args, **kwargs):
        candidates = retrieve(*args, **kwargs)
        gate = active_gate()
        if gate is None:
            raise ReplayStop("逐题检索缺少回放门禁")
        gate.observe([candidate.id for candidate in candidates])
        return candidates
    return checked


def load_verified_scorers(revised_bytes, revision, filename):
    """仅从精确授权源码逆向重建旧函数；两个独立namespace，均不运行main。"""
    if (any(revision.get(key) != value for key, value in AUTHORIZED_REVISION.items())
            or hashlib.sha256(revised_bytes).hexdigest() != CURRENT_EVALUATOR):
        raise ReplayStop("评分器源码/授权记录不符")
    before, after = AUTHORIZED_REVISION["before"].encode(), AUTHORIZED_REVISION["after"].encode()
    if revised_bytes.count(after) != 1 or revised_bytes.count(before) != 0:
        raise ReplayStop("授权修订不是唯一一行")
    legacy_bytes = revised_bytes.replace(after, before, 1)
    if hashlib.sha256(legacy_bytes).hexdigest() != LEGACY_EVALUATOR:
        raise ReplayStop("逆变换没有恢复精确旧评分器")
    functions = []
    for label, source in (("legacy", legacy_bytes), ("authorized", revised_bytes)):
        namespace = {"__name__": "_verified_evaluator_" + label, "__file__": str(filename)}
        path_before = list(sys.path)
        try:
            # 文件hash已锁定；__name__不是__main__，不会读批量用例或调用系统。
            exec(compile(source, str(filename) + ":" + label, "exec"), namespace)
        finally:
            sys.path[:] = path_before
        functions.append(namespace["evaluate_case"])
    return functions[0], functions[1], copy.deepcopy(AUTHORIZED_REVISION)


def require_full_result(output):
    if output is None or output.get("matched_runbook") is None or output.get("error"):
        return
    results = output.get("result")
    for result in results if isinstance(results, list) else [results]:
        if (not isinstance(result, dict) or not isinstance(result.get("columns"), list)
                or not isinstance(result.get("rows"), list) or type(result.get("row_count")) is not int
                or result["row_count"] != len(result["rows"]) or any(not isinstance(row, dict) for row in result["rows"])):
            raise ReplayStop("必须使用完整原执行结果，不能用预览或截断行评分")


def verify_legacy_then_rescore(case, baseline_output, historical, legacy, revised, candidate_query):
    """先用旧函数复现历史无时延分；之后才用修订函数打基线并运行候选query。"""
    expected = historical.get("score_without_time_penalty")
    if (not isinstance(case.get("case_id"), str) or not case["case_id"]
            or historical.get("case_id") != case["case_id"]
            or historical.get("question") not in (case.get("question"), str(case.get("question", ""))[:60])
            or type(expected) not in (int, float) or not math.isfinite(expected) or not -1 <= expected <= 5):
        raise ReplayStop("历史题目身份/原无时延分缺失或不匹配")
    require_full_result(baseline_output)
    original = legacy(copy.deepcopy(case), copy.deepcopy(baseline_output), 0)
    if original["score"] != expected:
        raise ReplayStop("原评分器不能复现历史，禁止用新评分器掩盖差异")
    new_baseline = revised(copy.deepcopy(case), copy.deepcopy(baseline_output), 0)
    candidate = candidate_query()  # 不提前运行候选，尤其不能在legacy核验失败后做GET。
    require_full_result(candidate)
    new_candidate = revised(copy.deepcopy(case), copy.deepcopy(candidate), 0)
    return {"legacy_historical_expected": expected, "legacy_replay_actual": original, "legacy_verified": True,
            "revised_baseline": new_baseline, "revised_candidate": new_candidate,
            "revised_delta": new_candidate["score"] - new_baseline["score"],
            "evaluator_revision": AUTHORIZED_REVISION["revision_id"],
            "legacy_evaluator_sha256": LEGACY_EVALUATOR, "revised_evaluator_sha256": CURRENT_EVALUATOR,
            "elapsed_policy": "both evaluators use 0: untimed diagnosis; no fresh model or latency claim"}
