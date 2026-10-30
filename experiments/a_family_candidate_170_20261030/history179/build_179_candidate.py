"""Offline A-only 180 -> 179 data/index assembly; no matcher, service or Git writes."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import shutil
import sys


def load_engine(path):
    spec = importlib.util.spec_from_file_location('_offline179_retriever', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RunbookRetriever


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base180', type=Path, required=True)
    parser.add_argument('--f27', type=Path, required=True)
    parser.add_argument('--retriever', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a fresh private output directory; do not overwrite evidence')
    source_bytes = args.base180.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != '5c987e77da5b52883a5a6047faf6c7710a9fa41621c4080a53231cc2916bd1e3':
        parser.error('Not the frozen published180 stage1 input; freeze a new protocol first')
    if hashlib.sha256(args.retriever.read_bytes()).hexdigest() != '8fd12b7556bdcf89a10f9d408d9c8473e04a48bcd4bd3bd89bc06c8aaec856cc':
        parser.error('Retriever version differs from the published stage1 engine')
    original = json.loads(source_bytes)
    assert len(original) == len({i['id'] for i in original}) == 180
    family = json.loads(args.f27.read_text())
    assert family['id'] == 'family_f27' and family['family_id'] == 'F27'
    assert 'default_params' not in family
    removed = {'rb_099', 'rb_101'}
    old_by = {item['id']: item for item in original}
    assert removed <= old_by.keys()
    engine = load_engine(args.retriever)
    before = engine(original)
    profile_order = list(dict.fromkeys(d.item_id for d in before._docs))
    assert len(profile_order) == 200 and before._doc_count == 400
    family['retrieval_views'] = []
    for item_id in ['rb_099', 'rb_101']:
        old = old_by[item_id]
        assert not old.get('retrieval_aliases') and not old.get('retrieval_views')
        position = profile_order.index(item_id)
        view = {'id': item_id, 'after_id': profile_order[position - 1] if position else None,
                'description': old.get('description', ''), 'examples': old.get('examples', [])}
        if view['description'] and view['examples'] == [view['description']]:
            view.update(examples=[], description_repeat=2)
        family['retrieval_views'].append(view)
    candidate, inserted = [], False
    for item in original:
        if item['id'] in removed:
            if not inserted:
                candidate.append(copy.deepcopy(family)); inserted = True
        else:
            candidate.append(copy.deepcopy(item))
    assert len(candidate) == len({i['id'] for i in candidate}) == 179
    retained = [i for i in original if i['id'] not in removed]
    assert [i for i in candidate if i['id'] != family['id']] == retained
    after = engine(candidate)
    assert [(d.item_id, d.tokens) for d in before._docs] == [(d.item_id, d.tokens) for d in after._docs]
    assert (before._df, before._idf, before._avg_len, before._tau, before._doc_tfs) == (
        after._df, after._idf, after._avg_len, after._tau, after._doc_tfs)
    target = args.output.resolve(); target.mkdir(parents=True)
    runtime = target / 'candidate179/implementation'; runtime.mkdir(parents=True)
    payload = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode()
    (target / 'templates179.private.json').write_bytes(payload)
    (runtime / 'runbook_items.py').write_text('# Isolated A179 data/index only; B port required.\nRUNBOOK_ITEMS = ' +
        pprint.pformat(candidate, width=120, sort_dicts=False) + '\n')
    shutil.copy2(args.retriever, runtime / 'runbook_retriever.py')
    def depth(value):
        if not isinstance(value, (list, dict)):
            return 0
        return 1 + max((depth(v) for v in (value.values() if isinstance(value, dict) else value)), default=0)
    summary = {'status': 'A179_DATA_INDEX_ONLY_NOT_PRODUCTION', 'source180_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'candidate179_sha256': hashlib.sha256(payload).hexdigest(), 'source_N': 180, 'candidate_N': 179,
        'retired_to_family': {k: 'family_f27' for k in sorted(removed)}, 'retained_items_exactly_unchanged': 178,
        'active_families': sorted(i['family_id'] for i in candidate if i.get('family_id')),
        'index_documents': after._doc_count, 'text_profiles': len(profile_order),
        'identical_raw_profile_order_tokens_and_BM25_statistics': True,
        'max_compact_template_bytes': max(len(json.dumps(i, ensure_ascii=False, separators=(',', ':')).encode()) for i in candidate),
        'max_template_dict_list_depth': max(map(depth, candidate)), 'outer_array_depth': depth(candidate),
        'matcher_or_system_copied': False, 'model_calls': 0, 'service_calls': 0,
        'native_pagination_or_bucket_uniqueness_proved': False,
        'warning': 'Private output inherits baseline entities; publish source references instead. B must port family semantics before query use.'}
    (target / 'BUILD_MANIFEST.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
