"""从已发布的无实体合同构造合成测试fixture，默认198也能运行。"""
import copy
import json
from pathlib import Path

from runbook_items import RUNBOOK_ITEMS

ROOT = Path(__file__).resolve().parents[1]


def family_item(family):
    active = next((item for item in RUNBOOK_ITEMS if item.get("family_id") == family), None)
    if active is not None and len(RUNBOOK_ITEMS) != 132:
        return copy.deepcopy(active)
    if family in {"F02", "F19"}:
        items = json.loads((ROOT / "experiments/a_family_candidate_170_20261030/CANDIDATES.json").read_text())
    else:
        package = ROOT / "experiments/a_family_candidate_160_20261030/base160"
        if family in {"F11_CORE", "F16", "F26"}:
            references = json.loads((package / "stage166/FAMILY_DEFINITIONS.references.json").read_text())
            items = [entry["template_fields_without_examples"] for entry in references["families"]]
        elif family in {"F10", "F17_SAFE"}:
            items = json.loads((package / "sources/single/CANDIDATES.json").read_text())
        elif family == "NEXT_N28":
            items = [json.loads((package / "sources/count/FAMILY_CANDIDATE.json").read_text())]
        else:
            raise ValueError("No published synthetic family fixture: " + family)
    return copy.deepcopy(next(item for item in items if item.get("family_id") == family))
