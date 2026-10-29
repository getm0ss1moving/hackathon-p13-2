"""Rebuild the historical 199-item candidate from an explicit Git object.

No model, network, business-module import or production-file mutation.
The generated template JSON contains local data: keep it outside the repository.
"""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare-existing', type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if repo == output or repo in output.parents:
        parser.error('Keep generated template data outside the repository')
    ref = subprocess.check_output(['git', 'rev-parse', args.base_commit + '^{commit}'], cwd=repo, text=True).strip()
    source = subprocess.check_output(['git', 'show', ref + ':implementation/runbook_items.py'], cwd=repo)
    node = next(n.value for n in ast.parse(source.decode('utf-8')).body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'RUNBOOK_ITEMS' for t in n.targets))
    items = ast.literal_eval(node)
    by_id = {item['id']: item for item in items}
    assert len(items) == len(by_id) == 200
    assert all(by_id['rb_086'].get(k) == by_id['rb_087'].get(k)
               for k in ('api_call', 'sql', 'default_params'))
    candidate = [item for item in items if item['id'] != 'rb_087']
    assert len(candidate) == 199 and 'rb_086' in {item['id'] for item in candidate}
    assert all(item == by_id[item['id']] for item in candidate)
    assert [item['id'] for item in candidate] == [item['id'] for item in items if item['id'] != 'rb_087']
    payload = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    comparison = None
    if args.compare_existing:
        old = args.compare_existing.read_bytes()
        comparison = {'sha256': sha(old), 'bytes_equal': old == payload,
                      'structures_equal': json.loads(old) == candidate}
        assert comparison['bytes_equal'] and comparison['structures_equal']
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as f:
        f.write(payload)
    working = repo / 'implementation/runbook_items.py'
    print(json.dumps({'base_commit': ref, 'input_kind': 'explicit Git object, never working-tree fallback',
          'source_sha256': sha(source), 'working_tree_matches_base': working.read_bytes() == source,
          'candidate_sha256': sha(payload), 'counts': [200, 199], 'removed_ids': ['rb_087'],
          'kept_id': 'rb_086', 'changed_surviving_entries': [], 'unchanged_surviving_entries': 199,
          'id_order_preserved': True, 'index_text_documents': sum(len(i.get('examples', [])) + bool(i.get('description')) for i in candidate),
          'existing_comparison': comparison, 'model_calls': 0, 'network_calls': 0,
          'production_changed': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
