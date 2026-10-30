"""Minimal release checks, without arrays, model calls or B initialization.

Replays each exact r5 delta in a fresh external copy and checks six synthetic
segmentation cases. An optional isolated B boundary helper can be supplied.
This does not rerun the independent50/12 or any complete regression suite.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "experiments/a_retriever_r6_increment_20261031"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def query_case(name, parts, connectors, prefix="", suffix=""):
    query = prefix
    expected = []
    for i, part in enumerate(parts):
        if i:
            query += connectors[i - 1]
        start = len(query)
        query += part
        expected.append((start, len(query), part))
    return name, query + suffix, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r5-source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--b-span-helper", type=Path)
    args = parser.parse_args()
    manifest = json.loads((PACKAGE / "MANIFEST.json").read_text())
    for relative, expected in manifest["files"].items():
        assert sha(PACKAGE / relative) == expected, relative
    for relative, expected in (manifest["tools"] | manifest["external_files"]).items():
        assert sha(ROOT / relative) == expected, relative
    out = args.output.resolve()
    assert not out.exists() and ROOT != out and ROOT not in out.parents
    out.mkdir(parents=True)
    b_helper = None
    if args.b_span_helper:
        tree = ast.parse(args.b_span_helper.read_text())
        assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
        assert tree.body[0].name == "_original_obligation_span"
        namespace = {}
        exec(compile(tree, "isolated_published_B_helper", "exec"), namespace)
        b_helper = namespace["_original_obligation_span"]
    a = "查询ECS实例alpha的创建时间"
    b = "查询ECS实例beta的创建时间"
    repeated = '查询ECS实例“alpha😀é”的创建时间'
    cases = [
        query_case("reported_AND", [a, b], [" AND "]),
        query_case("repeated_Unicode", [repeated, b, repeated],
                   ["\u2003AND\t", "\r\n以及\u3000"], "\t\u00a0", "\n\u3000"),
        query_case("one_aggregate", ["查询物理服务器CPU架构类型并统计各类数量"], [], "\u3000", "\t"),
        query_case("quoted_AND", ['查询ECS实例“alpha AND 查询ECSbeta”的创建时间'], []),
        ("only_whitespace", "\t\u3000", None),
        ("five_clauses", " AND ".join([a] * 5), None),
    ]
    interface = json.loads((PACKAGE / "R6_INTERFACE.json").read_text())
    report = {"scope": "exact patch replay, AST and six segmentation cases per variant",
              "B_actual_runtime_or_model_execution": False, "template_arrays_read": False,
              "independent50_and12_not_rerun": True, "root_runtime_changed": False,
              "variants": {}}
    for variant, record in interface["variants"].items():
        base = args.r5_source_root / ("runbook_retriever." + variant + ".py")
        assert sha(base) == record["r5_base_sha256"]
        patch = PACKAGE / record["patch"]
        assert sha(patch) == record["patch_sha256"]
        work = out / variant
        target = work / ("runbook_retriever." + variant + ".py")
        target.parent.mkdir(parents=True)
        shutil.copyfile(base, target)
        for args_git in [["git", "apply", "-p0", "--check", str(patch)],
                         ["git", "apply", "-p0", str(patch)]]:
            subprocess.run(args_git, cwd=work, check=True, capture_output=True, text=True)
        assert sha(target) == record["module_sha256"]
        def functions(path):
            return {node.name: ast.dump(node, include_attributes=False)
                    for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef)}
        old_ast, new_ast = functions(base), functions(target)
        assert set(new_ast) - set(old_ast) == {"_trimmed_query_part"}
        assert {name for name in old_ast if old_ast[name] != new_ast.get(name)} == {"_compound_parts"}
        module = load("r6_release_" + variant, target)
        passed = []
        for name, query, expected in cases:
            actual = module._compound_parts(query)
            assert actual == expected, (variant, name, actual, expected)
            for start, end, text in actual or []:
                assert type(start) is int and type(end) is int and 0 <= start < end <= len(query)
                assert query[start:end] == text == text.strip()
                if b_helper:
                    assert b_helper(query, {"start": start, "end": end, "text": text}) == (start, end, text)
            passed.append(name)
        assert sha(base) == record["r5_base_sha256"]
        report["variants"][variant] = {"patch_sha256": sha(patch), "r6_sha256": sha(target),
            "exact_replay": True, "AST_only_span_boundary_delta": True,
            "minimal_smoke_cases_passed": len(passed), "case_names": passed,
            "isolated_B_helper_accepts_unchanged_exact_spans": b_helper is not None}
    (out / "SMOKE_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
