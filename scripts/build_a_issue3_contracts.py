"""Reconstruct the exact rb196 input for disabled Issue3 source-contract review.

No B registration, model, HTTP, official executor, scorer or production changes.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "experiments/issue3_contracts_20261030"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_public():
    manifest = json.loads((PACKAGE / "MANIFEST.json").read_text())
    for relative, expected in manifest["files"].items():
        assert sha(PACKAGE / relative) == expected, relative
    for relative, expected in manifest["tools"].items():
        assert sha(ROOT / relative) == expected, relative
    minimal = json.loads((PACKAGE / "MINIMAL_B_HANDOFF.json").read_text())
    assert minimal["file_count"] == len(minimal["files"]) == 13
    for entry in minimal["files"]:
        if entry["delivery"] == "exact_source_bytes":
            assert sha(PACKAGE / entry["path"]) == entry["sha256"]
    return minimal


def fresh_output(path):
    out = path.resolve()
    assert out != ROOT and ROOT not in out.parents, "output must be outside repository"
    out.mkdir(parents=True, exist_ok=False)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base160", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    minimal = verify_public()
    recipe = json.loads((PACKAGE / "rb196.references.json").read_text())
    assert sha(args.base160) == recipe["base160_sha256"], "base160 drift"
    base = json.loads(args.base160.read_text())
    by_id = {item["id"]: item for item in base}
    assert len(by_id) == len(base) == 160

    def decode(value):
        if isinstance(value, dict):
            if set(value) == {"$base160"}:
                item_id, *keys = value["$base160"]
                result = by_id[item_id]
                for key in keys:
                    result = result[key]
                return copy.deepcopy(result)
            if set(value) == {"$concat"}:
                return "".join(decode(part) for part in value["$concat"])
            return {key: decode(part) for key, part in value.items()}
        if isinstance(value, list):
            return [decode(part) for part in value]
        return value

    result = decode(recipe["recipe"])
    assert recipe["format"] == {"indent": 2, "compact": False, "newline": True}
    data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    expected = recipe["expected_source_JSON_sha256"]
    assert hashlib.sha256(data).hexdigest() == expected
    out = fresh_output(args.output)
    (out / "rb_196.after.json").write_bytes(data)
    assert sha(out / "rb_196.after.json") == next(
        entry["sha256"] for entry in minimal["files"]
        if entry["role"] == "exact_single_template_input")
    report = {"exact_source_contract_files_verified": 12,
              "exact_private_template_reconstructed": True,
              "logical_closure_files_verified": 13,
              "rb196_sha256": expected, "production_enabled": False,
              "runtime_N_delta": 0, "model_or_service_calls": 0}
    (out / "BUILD_REPORT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
