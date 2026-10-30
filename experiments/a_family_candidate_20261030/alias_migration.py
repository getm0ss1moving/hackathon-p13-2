"""Offline assembly helper for existing retrieval aliases only.

No retriever, BM25 formula, family text, executable API/SQL or runtime routing is
changed here. The integration builder supplies its explicit replacement map.
"""
import copy


def _expanded_entries(items):
    """Validate and reproduce the unchanged retriever's legacy insertion order."""
    entries = list(items)
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
            raise ValueError('invalid active item ID')
        if item['id'] in seen:
            raise ValueError('duplicate active item ID: ' + item['id'])
        seen.add(item['id'])
    for owner in items:
        aliases = owner.get('retrieval_aliases', [])
        if not isinstance(aliases, list):
            raise ValueError('retrieval_aliases must be a list')
        for alias in aliases:
            if (not isinstance(alias, dict) or not isinstance(alias.get('id'), str)
                    or not alias['id'] or not isinstance(alias.get('after_id'), str)):
                raise ValueError('invalid retrieval alias')
            if alias['id'] in seen:
                raise ValueError('duplicate index ID: ' + alias['id'])
            if alias.get('retrieval_aliases'):
                raise ValueError('nested retrieval aliases are unsupported')
            anchors = [i for i, item in enumerate(entries) if item['id'] == alias['after_id']]
            if len(anchors) != 1:
                raise ValueError('missing or forward retrieval anchor: ' + alias['id'] + ' -> ' + alias['after_id'])
            entries.insert(anchors[0] + 1, alias)
            seen.add(alias['id'])
    return entries


def migrate_existing_aliases(baseline, preview, replacements):
    """Copy old aliases to live owners and explicitly repair vanished anchors.

    The candidate's normal text and old-member consolidation are untouched.
    Existing anchors that are active remain identical. If an alias was anchored
    to its own replaced owner, use the owner's replacement. Otherwise use the
    nearest preceding still-active original entry in the frozen logical order.
    Any missing/conflicting evidence raises instead of deleting text or guessing.
    """
    source_entries = _expanded_entries(baseline)
    source_position = {entry['id']: i for i, entry in enumerate(source_entries)}
    baseline_ids = {item['id'] for item in baseline}
    if not isinstance(replacements, dict) or set(replacements) - baseline_ids:
        raise ValueError('replacement map contains unknown baseline IDs')
    result = copy.deepcopy(preview)
    active = {item['id']: item for item in result}
    if len(active) != len(result):
        raise ValueError('duplicate preview item IDs')
    if any(target not in active for target in replacements.values()):
        raise ValueError('replacement owner absent from preview')
    if any(source in active and source != target for source, target in replacements.items()):
        raise ValueError('replaced old item still active in preview')
    existing = {}
    for owner in result:
        aliases = owner.get('retrieval_aliases', [])
        if not isinstance(aliases, list):
            raise ValueError('preview aliases must be a list')
        for alias in aliases:
            if not isinstance(alias, dict) or not isinstance(alias.get('id'), str):
                raise ValueError('invalid preview alias')
            if alias['id'] in existing or alias['id'] in active:
                raise ValueError('duplicate preview index ID: ' + alias['id'])
            existing[alias['id']] = (owner, alias)
    changes = []
    for old_owner in baseline:
        for source_alias in old_owner.get('retrieval_aliases', []):
            alias_id = source_alias['id']
            owner_id = replacements.get(old_owner['id'], old_owner['id'])
            if owner_id not in active:
                raise ValueError('unmapped removed alias owner: ' + old_owner['id'])
            found = existing.get(alias_id)
            if found:
                prior_owner, prior_alias = found
                # Only anchor changes may have been staged by another assembler.
                source_payload = {k: v for k, v in source_alias.items() if k != 'after_id'}
                prior_payload = {k: v for k, v in prior_alias.items() if k != 'after_id'}
                if source_payload != prior_payload:
                    raise ValueError('alias text/metadata conflict: ' + alias_id)
                prior_owner['retrieval_aliases'].remove(prior_alias)
            target_owner = active[owner_id]
            alias = copy.deepcopy(source_alias)
            old_anchor = source_alias['after_id']
            if old_anchor in active:
                new_anchor = old_anchor
                method = 'existing active anchor unchanged'
            elif old_anchor == old_owner['id'] and owner_id != old_owner['id']:
                new_anchor = owner_id
                method = 'same-owner replacement at the canonical family position'
            else:
                preceding = source_entries[:source_position[alias_id]]
                new_anchor = next((entry['id'] for entry in reversed(preceding) if entry['id'] in active), None)
                if new_anchor is None:
                    raise ValueError('no surviving original predecessor: ' + alias_id)
                method = 'nearest preceding surviving original entry'
            alias['after_id'] = new_anchor
            target_owner.setdefault('retrieval_aliases', []).append(alias)
            if owner_id != old_owner['id'] or new_anchor != old_anchor or not found:
                changes.append({'alias_id': alias_id, 'old_owner': old_owner['id'], 'new_owner': owner_id,
                                'old_anchor': old_anchor, 'new_anchor': new_anchor,
                                'method': method, 'payload_preserved_except_after_id': True})
    # Check the exact constructor order, not merely membership in a set of IDs.
    _expanded_entries(result)
    return result, changes
