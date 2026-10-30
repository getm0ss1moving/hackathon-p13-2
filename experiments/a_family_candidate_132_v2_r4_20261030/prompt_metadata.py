"""Self-contained F03 text/schema deduplication; no execution templates or I/O.

Use prompt_item(item) at B's selection and parameter-prompt presentation boundary.
Keep the compact item in the submitted array and ordinary prepare/execute path.
"""
import copy


def prompt_item(item):
    """Restore only metadata derived from the same submitted item.

    Existing items pass through unchanged. Malformed references fail closed.
    No question, old ID, model, service, external catalog, API or SQL is used.
    """
    if 'examples_from' not in item:
        return item
    if (item.get('id') != 'family_f03_spec'
            or item.get('family_id', 'family_f03_spec') != 'family_f03_spec'
            or 'examples' in item):
        raise ValueError('invalid_compact_prompt_metadata')
    views = item.get('retrieval_views')
    if (not isinstance(views, list) or not views
            or any(not isinstance(v, dict) or not isinstance(v.get('description'), str)
                   for v in views)):
        raise ValueError('invalid_compact_example_source')
    indexes = item['examples_from']
    if (not isinstance(indexes, list) or not indexes
            or any(type(i) is not int or not 0 <= i < len(views) for i in indexes)):
        raise ValueError('invalid_compact_example_indexes')
    result = copy.deepcopy(item)
    result['examples'] = [views[i]['description'] for i in indexes]
    del result['examples_from']
    # The ordinary materialized item no longer has a parameter contract.
    if 'parameter_contract' in result:
        contract = result['parameter_contract']
        if ('per_view_keys' in contract or not isinstance(contract.get('keys'), list)
                or not isinstance(contract.get('views'), dict)):
            raise ValueError('invalid_compact_parameter_contract')
        contract['per_view_keys'] = {
            view: copy.deepcopy(spec.get('keys', contract['keys']))
            for view, spec in contract['views'].items()
        }
    return result
