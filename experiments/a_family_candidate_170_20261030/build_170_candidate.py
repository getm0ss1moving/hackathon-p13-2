"""Offline A179 -> A170 data/index assembly. Does not install a B adapter."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import shutil
import sys

BASE_SHA = '1743b73df31b420a5d9f3a0f775d5c93e0277ce9c5e2d85585adef79b4f3d026'
ENGINE_SHA = '8fd12b7556bdcf89a10f9d408d9c8473e04a48bcd4bd3bd89bc06c8aaec856cc'
FAMILY_SHA = '7ffe9e3c4f5880c96e1e2bcb9c4ef866fe16dfa7b39f5d89165be0da64f9c6e2'
MEMBERS = {
    'family_f02': ['rb_006', 'rb_009', 'rb_029', 'rb_037', 'rb_038', 'rb_039', 'rb_042'],
    'family_f19': ['rb_142', 'rb_145', 'rb_146', 'rb_148'],
}


def load_engine(path):
    spec = importlib.util.spec_from_file_location('_offline170_engine', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RunbookRetriever


def depth(value):
    if not isinstance(value, (dict, list)):
        return 0
    return 1 + max((depth(v) for v in (value.values() if isinstance(value, dict) else value)), default=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base179', type=Path, required=True)
    parser.add_argument('--families', type=Path, required=True)
    parser.add_argument('--retriever', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a fresh private output directory; preserve existing evidence')
    for path, expected in [(args.base179, BASE_SHA), (args.families, FAMILY_SHA), (args.retriever, ENGINE_SHA)]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            parser.error('Input differs from frozen candidate: ' + path.name)
    original = json.loads(args.base179.read_text())
    families = json.loads(args.families.read_text())
    by_id = {item['id']: item for item in original}
    family_by = {item['id']: copy.deepcopy(item) for item in families}
    replacement = {old: owner for owner, members in MEMBERS.items() for old in members}
    assert len(original) == len(by_id) == 179
    assert len(replacement) == 11 and set(replacement) <= by_id.keys()
    assert set(family_by) == set(MEMBERS) and not set(family_by) & by_id.keys()
    cls = load_engine(args.retriever)
    before = cls(original)
    raw_order = list(dict.fromkeys(d.item_id for d in before._docs))
    assert len(raw_order) == 200 and before._doc_count == 400
    for owner, members in MEMBERS.items():
        views = []
        for old_id in members:
            old = by_id[old_id]
            assert not old.get('retrieval_views') and not old.get('retrieval_aliases')
            position = raw_order.index(old_id)
            view = {'id': old_id, 'after_id': raw_order[position - 1] if position else None,
                    'description': old.get('description', ''), 'examples': old.get('examples', [])}
            if view['description'] and view['examples'] == [view['description']]:
                view.update(examples=[], description_repeat=2)
            views.append(view)
        family_by[owner]['retrieval_views'] = views
    candidate, placed = [], set()
    for item in original:
        owner = replacement.get(item['id'])
        if owner:
            if owner not in placed:
                candidate.append(family_by[owner]); placed.add(owner)
        else:
            candidate.append(copy.deepcopy(item))
    assert len(candidate) == len({item['id'] for item in candidate}) == 170
    assert [item for item in candidate if item['id'] not in MEMBERS] == [
        item for item in original if item['id'] not in replacement]
    after = cls(candidate)
    assert [(d.item_id, d.tokens) for d in before._docs] == [(d.item_id, d.tokens) for d in after._docs]
    assert (before._df, before._idf, before._tau, before._avg_len, before._doc_tfs) == (
        after._df, after._idf, after._tau, after._avg_len, after._doc_tfs)
    target = args.output.resolve(); runtime = target / 'candidate170/implementation'
    runtime.mkdir(parents=True)
    payload = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode()
    (target / 'templates170.private.json').write_bytes(payload)
    (runtime / 'runbook_items.py').write_text('# Isolated A170 data/index only; B adapter is not installed.\nRUNBOOK_ITEMS = ' +
        pprint.pformat(candidate, width=120, sort_dicts=False) + '\n')
    shutil.copy2(args.retriever, runtime / 'runbook_retriever.py')
    report = {'status': 'A170_DATA_INDEX_ONLY_NOT_PRODUCTION', 'source_N': 179, 'candidate_N': 170,
        'source179_sha256': BASE_SHA, 'candidate170_sha256': hashlib.sha256(payload).hexdigest(),
        'retired_to_family': replacement, 'nonmember_items_exactly_unchanged': 168,
        'active_families': sorted(item['family_id'] for item in candidate if item.get('family_id')),
        'text_profiles': 200, 'index_documents': 400,
        'raw_profile_order_tokens_DF_IDF_TF_tau_identical': True,
        'max_compact_template_bytes': max(len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()) for item in candidate),
        'max_template_dict_list_depth': max(map(depth, candidate)), 'outer_array_depth': depth(candidate),
        'matcher_or_system_copied': False, 'model_calls': 0, 'service_calls': 0,
        'warning': 'Private expansion inherits original entities; publish source references, not this raw JSON. B adapter and implicit-language coverage are not established.'}
    (target / 'BUILD_MANIFEST.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
