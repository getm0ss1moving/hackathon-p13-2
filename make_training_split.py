"""一次性随机分组划分：仅输出训练统计；不按历史得分选择或重抽样。"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def partition(cases, frozen_groups, seed):
    """用既有查询族及完全相同题文的并集，随机选恰好50题整组留出。"""
    ids = [case["case_id"] for case in cases]
    if len(ids) != 200 or len(set(ids)) != 200:
        raise ValueError("要求原200题且case_id唯一")
    parent = {case_id: case_id for case_id in ids}

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left, right):
        parent[find(right)] = find(left)

    grouped_ids = [case_id for group in frozen_groups for case_id in group["case_ids"]]
    if Counter(grouped_ids) != Counter(ids):
        raise ValueError("既有分组未完整覆盖同一200题")
    for group in frozen_groups:
        for value in group["case_ids"][1:]:
            union(group["case_ids"][0], value)
    questions = {}
    for case in cases:
        question = " ".join(case["question"].split())
        if question in questions:
            union(questions[question], case["case_id"])
        questions[question] = case["case_id"]
    groups = {}
    for value in ids:
        groups.setdefault(find(value), []).append(value)
    shuffled = sorted((sorted(values) for values in groups.values()), key=lambda values: tuple(values))
    random.Random(seed).shuffle(shuffled)
    # 在随机组顺序上做只依赖组大小的subset sum，保持整族不跨边且恰好50。
    reachable = {0: []}
    for index, values in enumerate(shuffled):
        for count, selected in list(reachable.items())[::-1]:
            total = count + len(values)
            if total <= 50 and total not in reachable:
                reachable[total] = selected + [index]
        if 50 in reachable:
            break
    if 50 not in reachable:
        raise ValueError("整组约束下无法恰好留出50题；不自动改种子")
    selected = set(reachable[50])
    held_ids = {value for index, values in enumerate(shuffled) if index in selected for value in values}
    train = [case for case in cases if case["case_id"] not in held_ids]
    holdout = [case for case in cases if case["case_id"] in held_ids]
    if len(train) != 150 or len(holdout) != 50:
        raise AssertionError("划分大小错误")
    if any(bool(set(values) & held_ids) and not set(values) <= held_ids for values in shuffled):
        raise AssertionError("同族跨集合")
    if {" ".join(case["question"].split()) for case in train} & {" ".join(case["question"].split()) for case in holdout}:
        raise AssertionError("相同题文跨集合")
    return train, holdout, len(shuffled), len(shuffled) - len(selected), len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261030)
    parser.add_argument("--output", type=Path, default=HERE/"datasets/whitebox_150_50_v1")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("划分已存在；禁止覆盖或按结果重新抽样")
    source, group_source = HERE/"CMDB用例集-白盒200.json", HERE/"experiments/round3/groups.json"
    history = HERE/"experiments/iteration3_20261030_live.jsonl"
    cases = json.loads(source.read_text())["cases"]
    grouping = json.loads(group_source.read_text())
    train, holdout, group_count, train_groups, holdout_groups = partition(cases, grouping["groups"], args.seed)
    # 先冻结划分，随后才过滤历史记录；选择过程不接触任何得分。
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output/"train.json", {"partition": "train", "cases": train})
    write_json(args.output/"sealed_test.json", {"partition": "sealed_test", "cases": holdout})
    train_ids = {case["case_id"] for case in train}
    historical = []
    source_plan = None
    with history.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["type"] == "plan":
                source_plan = row
            elif row["type"] == "case" and row["case_id"] in train_ids:
                historical.append(row)
    assert [row["case_id"] for row in historical] == [case["case_id"] for case in train]
    training_summary = {
        "case_count": 150,
        "untimed_score": round(sum(row["score_without_time_penalty"] for row in historical), 1),
        "full_quality_answers": sum(row["score_without_time_penalty"] == 5 for row in historical),
        "partial_answers": sum(0 < row["score_without_time_penalty"] < 5 for row in historical),
        "wrong_answers": sum(row["score_without_time_penalty"] < 0 for row in historical),
        "refusals": sum(row["score_without_time_penalty"] == 0 for row in historical),
        "measurement": "historical iteration3 training subset; not a new model run",
    }
    with (args.output/"train_history.jsonl").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "training_history", "source_sha256": sha(history),
                                 "training_file_sha256": sha(args.output/"train.json"),
                                 "runtime_sources": source_plan["source_sha256"]}, ensure_ascii=False)+"\n")
        for row in historical:
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
        stream.write(json.dumps({"type": "training_summary", **training_summary}, ensure_ascii=False)+"\n")
    runtime = {"implementation/"+name: value for name, value in source_plan["source_sha256"].items()}
    manifest = {
        "split_id": "whitebox_150_50_v1", "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "seed": args.seed, "python_random_algorithm": "Random(seed).shuffle; first reachable group subset of size 50",
        "selection_uses_scores": False, "resampling_allowed": False,
        "source_dataset_sha256": sha(source), "group_source_sha256": sha(group_source),
        "grouping_method": grouping["method"], "group_count": group_count,
        "train_count": 150, "holdout_count": 50, "train_group_count": train_groups, "holdout_group_count": holdout_groups,
        "case_order_within_partitions": "original file order",
        "train_file": "train.json", "train_sha256": sha(args.output/"train.json"),
        "train_history_file": "train_history.jsonl", "train_history_sha256": sha(args.output/"train_history.jsonl"),
        "sealed_test_file": "sealed_test.json", "sealed_test_sha256": sha(args.output/"sealed_test.json"),
        "initial_template_count": 200, "initial_runtime_sha256": runtime,
        "splitter_sha256": sha(Path(__file__)),
        "previous_exposure": "All 200 questions and outcomes were inspected before this split; existing 200-template library contains public examples/descriptions. This is prospective tuning exclusion only, not a pristine unseen benchmark.",
        "policy": "After creation, development reads train.json/train_history.jsonl only; do not inspect sealed_test, full historical case logs or all-200 replays. Freeze candidate before a separately authorized one-time final evaluation; do not tune on its per-case feedback.",
        "training_summary": training_summary,
    }
    write_json(args.output/"manifest.json", manifest)
    (args.output/"sealed_test.json").chmod(0o444)
    print(json.dumps({"split_id": manifest["split_id"], "seed": args.seed, "train_count": 150,
                      "sealed_test_count": 50, "groups": group_count, "same_family_overlap": 0,
                      "identical_question_overlap": 0, "training_summary": training_summary,
                      "holdout_metrics": "not computed or displayed"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
