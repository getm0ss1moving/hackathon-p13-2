"""Build private A180 data/index artifacts; never activates production or patches B.

The reviewed R5 patch predates B v18 and needs B's port. This builder deliberately
does not copy/overwrite matcher/system or start a query/model/data service.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import subprocess
import sys


def load_items(source):
    tree = ast.parse(source)
    return ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'RUNBOOK_ITEMS' for t in n.targets)))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--base-ref', help='Exact compatible baseline; defaults to manifest pin')
    parser.add_argument('--output', type=Path, required=True, help='New private directory outside repository')
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error('Generated template text contains inherited local entities; keep it outside the Git checkout')
    if output.exists():
        parser.error('Output already exists; choose a fresh directory, never overwrite evidence')
    package = repo / 'experiments/a_family_candidate_20261030'
    manifest = json.loads((package / 'manifest.json').read_text())
    for name, sha in manifest['files'].items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != sha:
            parser.error('Candidate source changed: ' + name)
    git = lambda *a: subprocess.check_output(['git', *a], cwd=repo)
    base = git('rev-parse', (args.base_ref or manifest['base_ref']) + '^{commit}').decode().strip()
    source = git('show', base + ':implementation/runbook_items.py')
    retriever_source = git('show', base + ':implementation/runbook_retriever.py')
    matcher_source = git('show', base + ':implementation/runbook_matcher.py')
    checks = [('items', source, manifest['baseline_items_sha256']),
              ('retriever', retriever_source, manifest['retriever_sha256']),
              ('B matcher', matcher_source, manifest['baseline_matcher_sha256'])]
    for label, payload, expected in checks:
        if hashlib.sha256(payload).hexdigest() != expected:
            parser.error(label + ' differs from pinned reviewed input; freeze/review the new baseline first')
    baseline = load_items(source)
    assert len(baseline) == len({i['id'] for i in baseline}) == 198
    replacement = json.loads((package / 'canonical_to_family.json').read_text())
    families = json.loads((package / 'family_candidates.json').read_text())
    family_by = {i['id']: i for i in families}
    assert len(replacement) == 24 and len(family_by) == 6
    assert set(replacement) <= {i['id'] for i in baseline}
    candidate, placed = [], set()
    for item in baseline:
        target = replacement.get(item['id'])
        if target:
            if target not in placed:
                candidate.append(copy.deepcopy(family_by[target])); placed.add(target)
        else:
            candidate.append(copy.deepcopy(item))
    helper = load_module('_a180_offline_alias_builder', package / 'alias_migration.py')
    candidate, alias_changes = helper.migrate_existing_aliases(baseline, candidate, replacement)
    # Preserve every old short text profile independently. No API/SQL/defaults enter
    # these profiles; old IDs are only offline identity labels, never query routing.
    expanded = helper._expanded_entries(baseline)
    source_owner = {item['id']: item['id'] for item in baseline}
    for item in baseline:
        source_owner.update({a['id']: item['id'] for a in item.get('retrieval_aliases', [])})
    groups, prior_id = {}, None
    for item in expanded:
        owner = replacement.get(source_owner[item['id']], source_owner[item['id']])
        description, examples = item.get('description', ''), list(item.get('examples', []))
        view = {'id': item['id'], 'after_id': prior_id,
                'description': description, 'examples': examples}
        if description and examples == [description]:
            view.update(examples=[], description_repeat=2)
        groups.setdefault(owner, []).append(view)
        prior_id = item['id']
    before_views = copy.deepcopy(candidate)
    for item in candidate:
        if len(groups[item['id']]) > 1 or item['id'] in family_by:
            item['retrieval_views'] = groups[item['id']]
    assert len(candidate) == len({i['id'] for i in candidate}) == 180
    for a, b in zip(before_views, candidate):
        assert a == {k: v for k, v in b.items() if k != 'retrieval_views'}
    output.mkdir(parents=True)
    runtime = output / 'candidate180/implementation'; runtime.mkdir(parents=True)
    (runtime / 'runbook_retriever.py').write_bytes(retriever_source)
    library_source = ('# Private A180 candidate; B v18 adaptation is NOT applied.\n'
                      'RUNBOOK_ITEMS = ' + pprint.pformat(candidate, width=120, sort_dicts=False) + '\n')
    (runtime / 'runbook_items.py').write_text(library_source)
    (output / 'templates180.private.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n')
    engine = load_module('_a180_frozen_index', runtime / 'runbook_retriever.py')
    original, index = engine.RunbookRetriever(baseline), engine.RunbookRetriever(candidate)
    assert [(d.item_id, d.tokens) for d in original._docs] == [(d.item_id, d.tokens) for d in index._docs]
    assert (original._df, original._idf, original._avg_len, original._tau) == (index._df, index._idf, index._avg_len, index._tau)
    def expected(results):
        seen, answer = set(), []
        for c in results:
            item_id = replacement.get(c.id, c.id)
            if item_id not in seen:
                answer.append((item_id, c.tier, c.score, c.coverage)); seen.add(item_id)
        return answer
    texts = [s for i in expanded for s in [*i.get('examples', []), i.get('description', '')] if s]
    for text in texts:
        for k in [None, 1, 5, 10]:
            assert expected(original.retrieve(text, k)) == [
                (c.id, c.tier, c.score, c.coverage) for c in index.retrieve(text, k)]
    def depth(value):
        if not isinstance(value, (dict, list)):
            return 0
        return 1 + max((depth(x) for x in (value.values() if isinstance(value, dict) else value)), default=0)
    result = {'status': 'A180_DATA_INDEX_READY_B_V18_PORT_REQUIRED', 'base_commit': base,
        'production_N': 198, 'candidate_N': 180, 'replaced_active_templates': 24,
        'new_families': 6, 'text_profiles': len(expanded), 'index_documents': index._doc_count,
        'source_text_proxy_inputs': len(texts), 'paired_topk_checks': len(texts) * 4,
        'family_normalized_differences': 0, 'alias_changes': alias_changes,
        'max_compact_template_bytes': max(len(json.dumps(i, ensure_ascii=False, separators=(',', ':')).encode()) for i in candidate),
        'max_template_dict_list_depth': max(map(depth, candidate)),
        'B_matcher_system_copied_or_patched': False, 'R5_semantics_applied_to_v18': False,
        'model_calls': 0, 'service_calls': 0, 'training_or_sealed_inputs_read': False,
        'output_files': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [runtime / 'runbook_items.py', runtime / 'runbook_retriever.py', output / 'templates180.private.json']},
        'limits': ['Data/index only; do not call an unadapted B query with these families.',
                   'No real model score or native SDK/service validation of B v18 integration.',
                   'Generated text inherits baseline entities: private local output, not an upload payload.',
                   'Official depth algorithm unresolved; dictionary/list depth is only a risk measurement.']}
    (output / 'BUILD_MANIFEST.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
