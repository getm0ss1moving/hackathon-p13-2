"""Rebuild the frozen, disabled A132 v2/r4 candidate from an exact local A160.

Run from the repository root. No model, SDK, service, evaluator or B code is used.
Expanded inherited examples remain in a new private directory outside Git.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "experiments/a_family_candidate_132_v2_r4_20261030"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base160", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((PACKAGE / "MANIFEST.json").read_text())
    for relative, expected in manifest["files"].items():
        assert sha((PACKAGE / relative).read_bytes()) == expected, relative
    assert sha(Path(__file__).read_bytes()) == manifest["builder_sha256"]
    recipe = json.loads((PACKAGE / "reconstruction.references.json").read_text())
    raw = args.base160.read_bytes()
    assert sha(raw) == recipe["base160_sha256"], "base160 drift"
    base = json.loads(raw)
    base_by_id = {item["id"]: item for item in base}
    assert len(base_by_id) == len(base) == 160

    def decode(value):
        if isinstance(value, dict):
            if set(value) == {"$base160"}:
                item_id, *keys = value["$base160"]
                result = base_by_id[item_id]
                for key in keys:
                    result = result[key]
                return copy.deepcopy(result)
            if set(value) == {"$concat"}:
                return "".join(decode(part) for part in value["$concat"])
            return {key: decode(part) for key, part in value.items()}
        if isinstance(value, list):
            return [decode(part) for part in value]
        return value

    out = args.output.resolve()
    assert out != ROOT and ROOT not in out.parents, "output must be outside repository"
    out.mkdir(parents=True, exist_ok=False)
    # Exact safe source files plus exact privately reconstructed source artifacts.
    for relative in manifest["files"]:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACKAGE / relative, target)
    for relative, spec in recipe["private_family_JSON_files"].items():
        fmt = spec["format"]
        kwargs = {"ensure_ascii": False, "indent": fmt["indent"]}
        if fmt["compact"]:
            kwargs["separators"] = (",", ":")
        data = (json.dumps(decode(spec["recipe"]), **kwargs)
                + ("\n" if fmt["newline"] else "")).encode()
        assert sha(data) == spec["sha256"], relative
        (out / relative).write_bytes(data)
    closure = json.loads((PACKAGE / "MINIMUM_RETRIEVAL_RUNTIME_CLOSURE.json").read_text())
    adapter = load_module("a132_public_metadata", out / "prompt_metadata.py")
    report = {"scope": "exact reconstruction and local index/metadata smoke only",
              "model_calls": 0, "service_calls": 0, "production_enabled": False,
              "full_private_1166_suite_rerun": False, "variants": {}}
    for variant, spec in recipe["variants"].items():
        items = decode(spec["array_recipe"])
        data = json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode()
        assert sha(data) == spec["array_sha256"], variant
        assert len(items) == len({item["id"] for item in items}) == 132
        array_name = f"templates132.{variant}.private.json"
        (out / array_name).write_bytes(data)
        module_data = (spec["python_prefix"] + repr(items)
                       + ("\n" if spec["python_newline"] else "")).encode()
        assert sha(module_data) == spec["python_items_sha256"]
        (out / f"runbook_items.{variant}.py").write_bytes(module_data)
        c = closure["variants"][variant]
        assert sha((out / c["module"]).read_bytes()) == c["module_sha256"]
        binding = {"module_sha256": c["module_sha256"],
                   "array_sha256": sha(data)}
        assert sha(canonical(binding)) == c["binding_sha256"]
        engine = load_module("a132_public_" + variant, out / c["module"])
        before = copy.deepcopy(items)
        index = engine.RunbookRetriever(items)
        assert items == before, "index mutated submitted array"
        assert index._doc_count == 400
        attribute_cards = len(index._attribute_records)
        assert attribute_cards == {"strict": 11, "enhanced": 22}[variant]
        f03 = next(item for item in items if item["id"] == "family_f03_spec")
        restored = adapter.prompt_item(f03)
        assert sha(canonical(restored)) == spec["restored_F03_sortedkeys_sha256"]
        assert len(restored["examples"]) == 7
        assert len(restored["parameter_contract"]["per_view_keys"]) == 6
        assert items == before, "adapter mutated submitted array"
        report["variants"][variant] = {
            "unique_ids": 132, "array_sha256": sha(data),
            "items_sha256": sha(module_data), "binding_sha256": c["binding_sha256"],
            "primary_documents": index._doc_count, "attribute_cards": attribute_cards,
            "F03_compact_UTF8_bytes": len(json.dumps(f03, ensure_ascii=False,
                                                       separators=(",", ":")).encode()),
            "F03_examples_restored": 7, "F03_view_key_contracts_restored": 6}
    registry = json.loads((out / "FAMILY_ROUTE_REGISTRY.json").read_text())
    assert len(registry) == 12
    for record in registry.values():
        assert sha((out / record["module"]).read_bytes()) == record["module_sha256"]
    # Every original source file, including generated private JSON/Python exports,
    # must be byte-identical to the reviewed owner closure.
    original = json.loads((PACKAGE / "SOURCE_CLOSURE.json").read_text())
    for relative, expected in original["files"].items():
        actual = original["source_archive_map"].get(relative, relative)
        assert sha((out / actual).read_bytes()) == expected, relative
    for path in out.rglob("*.py"):
        ast.parse(path.read_bytes(), filename=path.name)
    report["source_files_verified"] = len(original["files"])
    report["changed_family_modules_verified"] = len(registry)
    (out / "BUILD_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
