"""Provider increment: replay independent PORT counterexamples, no consumer claims."""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'provider'))
from copy import deepcopy
import argparse
import importlib.util
import json
from pathlib import Path
import traceback

import shared_policy as P
from validate_main import receipt

ROOT = PACKAGE / 'provider'
CHECKS = []


def same(name, actual, expected):
    CHECKS.append({'id': name, 'passed': actual == expected})
    if actual != expected:
        raise AssertionError(name + ': ' + repr(actual) + ' != ' + repr(expected))


def reject(name, call):
    try:
        call()
    except ValueError:
        same(name, True, True)
    else:
        same(name, False, True)


def batch(call, rows, schema=P.PORT_BATCH_COLUMNS):
    return {'request': deepcopy(call), 'receipt': receipt(call, schema, rows)}


def clause(call, key, op, value):
    call = deepcopy(call)
    cs = call.setdefault('condition', {}).setdefault('constraint', [])
    cs.append({'simple': {'name': key, 'operator': op, 'value': deepcopy(value)}, **({'logOp': 'and'} if cs else {})})
    return call


def run():
    counter = json.loads((ROOT/'review_inputs/port-interface-counterexample.json').read_text())
    raw = counter['minimal_raw_receipts']['PORT']
    call = raw['request']
    b = {'request': deepcopy(call), 'receipt': deepcopy(raw)}
    original = deepcopy(b)
    out = P.collect_port_batches([b])
    same('independent.raw2_canonical1', (out['canonical_receipt']['batch_raw_total_nums'], len(out['rows'])), ([2], 1))
    same('independent.raw_unchanged_no_recount', (b, out['raw_receipts']), (original, [original['receipt']]))
    same('independent.provider_output_not_HTTP_envelope', any(k in out for k in ('ok', 'http_status', 'pages')), False)
    same('provider.fixed_contract_output_keys', set(out), set(json.loads((ROOT/'PORT_PROVIDER_CONTRACT.json').read_text())['output_keys']))
    same('provider.source_schema_separate_from_typed_identity',
         (out['raw_receipts'][0]['schema_source'], out['typed_port_table']['table'], out['typed_port_table']['types']),
         ('independent-synthetic-schema-only', 'CLOUD_PORT', dict.fromkeys(P.PORT_BATCH_COLUMNS, 'TEXT')))
    same('provider.recheck_exact', P.recheck_port_batches(out), out)

    spec = importlib.util.spec_from_file_location('r1_policy_control', ROOT/'source/shared_policy.r1.py')
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    same('equal.old_output_byte_semantics_unchanged', P.collect('PORT', raw, call, P.PORT_BATCH_COLUMNS), old.collect('PORT', raw, call, P.PORT_BATCH_COLUMNS))
    scoped = clause(call, 'devId', 'in', ['res', 'other'])
    sb = batch(scoped, [raw['pages'][0]['objList'][0]])
    out = P.collect_port_batches([sb])
    same('independent.scoped_in_accepted_through_explicit_batch_entry', out['rows'][0]['devId'], 'res')
    same('strict_in.actual_request_operator_not_rewritten', out['raw_receipts'][0]['request'], scoped)
    same('strict_in.actual_page_request_retained', out['raw_receipts'][0]['pages'][0]['request'], P.page_request(scoped, 1))
    reject('equal.legacy_collect_still_equal_only', lambda: P.collect('PORT', sb['receipt'], scoped, P.PORT_BATCH_COLUMNS))
    reject('equal.equal_filters_still_equal_only', lambda: P.equal_filters(scoped))

    for label, values in [('scalar', 'res'), ('CSV', 'res,other'), ('JSON_string', '["res","other"]'),
                          ('empty', []), ('duplicate', ['res', 'res']), ('blank', [' ']),
                          ('NULL', [None]), ('bool', [False]), ('number', [1]), ('nested', [['res']])]:
        c = clause(call, 'devId', 'in', values)
        reject('strict_in.reject_'+label, lambda c=c: P.collect_port_batches([batch(c, [])]))
    for value in ('Res', 'prefix-res', 'other-region-res'):
        bad = batch(scoped, [{'id': 'p', 'devId': value, 'logicalRegionName': 'review-region'}])
        reject('strict_in.exact_no_case_or_substring_'+value, lambda bad=bad: P.collect_port_batches([bad]))
    literal = 'opaque,%_中文:2001:db8::01'
    c = clause(call, 'devId', 'in', [literal])
    out = P.collect_port_batches([batch(c, [{'id': 'literal', 'devId': literal, 'logicalRegionName': 'review-region'}])])
    same('strict_in.opaque_literal_unchanged', out['rows'][0]['devId'], literal)
    for label, mutate in [
        ('OR', lambda c: c['condition']['constraint'][-1].update(logOp='or')),
        ('unknown_clause_key', lambda c: c['condition']['constraint'][-1].update(nested=[])),
        ('unknown_simple_key', lambda c: c['condition']['constraint'][-1]['simple'].update(regex=False)),
        ('repeated_scope_field', lambda c: c['condition']['constraint'].append(deepcopy(c['condition']['constraint'][-1]))),
        ('unsupported_field', lambda c: c['condition']['constraint'][-1]['simple'].update(name='devNativeId')),
        ('unsupported_operator', lambda c: c['condition']['constraint'][-1]['simple'].update(operator='contain')),
        ('wrong_CI', lambda c: c.update(url=c['url'].replace('/PORT?', '/FLOATING_IPS?'))),
    ]:
        bad = deepcopy(scoped); mutate(bad)
        reject('scope.reject_'+label, lambda bad=bad: P.collect_port_batches([batch(bad, [])]))

    first = {'id': 'same-port-ID', 'devId': 'res', 'logicalRegionName': 'review-region'}
    eq1, eq2 = clause(call, 'devId', 'equal', 'res'), clause(call, 'devId', 'equal', 'conflicting-res')
    conflict_batches = [batch(eq1, [first]), batch(eq2, [{**first, 'devId': 'conflicting-res'}])]
    same('independent.equal_batches_individually_valid', [len(P.collect_port_batches([x])['rows']) for x in conflict_batches], [1, 1])
    reject('independent.cross_batch_same_ID_conflicting_devId_rejected', lambda: P.collect_port_batches(conflict_batches))
    equivalent = [batch(call, [first, {**first, 'last_Modified': 'later'}]), batch(scoped, [{**first, 'last_update_date': 'later-again'}])]
    out = P.collect_port_batches(equivalent)
    same('cross_batch.audit_only_equivalent_counts',
         tuple(out['canonical_receipt'][k] for k in ('raw_observation_count', 'sum_batch_canonical_object_counts', 'canonical_object_count', 'within_batch_duplicate_observation_count', 'cross_batch_duplicate_object_count')),
         (3, 2, 1, 1, 1))
    same('cross_batch.raw_totals_are_separate', out['canonical_receipt']['batch_raw_total_nums'], [2, 1])
    same('cross_batch.no_fabricated_union_raw_total', 'raw_total_num' in out['canonical_receipt'], False)
    same('cross_batch.no_global_scope_certificate', (out['canonical_receipt']['scope_coverage_complete'], out['full_answer']), (False, False))
    for label, changed in [('unprojected_field', {**first, 'futureBusiness': 'conflict'}),
                           ('missing_vs_NULL', {**first, 'futureBusiness': None}),
                           ('different_region', {**first, 'logicalRegionName': 'other-region'})]:
        global_call = deepcopy(call); global_call.pop('condition')
        reject('cross_batch.reject_'+label, lambda changed=changed: P.collect_port_batches([batch(global_call, [first]), batch(global_call, [changed])]))
    for left, right, label in [(1, True, 'int_bool'), (1, 1.0, 'int_float')]:
        reject('cross_batch.JSON_type_'+label,
               lambda left=left, right=right: P.collect_port_batches([batch(call, [{**first, 'extra': left}]), batch(call, [{**first, 'extra': right}])]))

    small = deepcopy(call); small['url'] = small['url'].replace('pageSize=1000', 'pageSize=1')
    paged = batch(small, [first, {**first, 'last_Modified': 'page2'}])
    before = deepcopy(paged)
    out = P.collect_port_batches([paged])
    same('pagination.actual_two_pages_retained', (len(out['raw_receipts'][0]['pages']), out['canonical_receipt']['batch_raw_total_nums'], len(out['rows'])), (2, [2], 1))
    same('pagination.input_immutable', paged, before)
    for label, mutate in [
        ('truncated_page', lambda x: x['receipt']['pages'][1]['objList'].clear()),
        ('missing_page', lambda x: x['receipt']['pages'].pop()),
        ('changing_total', lambda x: x['receipt']['pages'][1].update(totalNum=3)),
        ('wrong_page_request', lambda x: x['receipt']['pages'][1].update(request=deepcopy(call))),
        ('wrong_planned_request', lambda x: x['request'].update(condition={})),
        ('resource_HTTP_absent', lambda x: x['receipt'].pop('http_status')),
        ('page_HTTP_absent', lambda x: x['receipt']['pages'][1].pop('http_status')),
        ('contradictory_HTTP', lambda x: x['receipt']['pages'][1].update(status_code=503)),
    ]:
        bad = deepcopy(paged); mutate(bad)
        reject('pagination.reject_'+label, lambda bad=bad: P.collect_port_batches([bad]))

    p = P.collect('PORT', raw, call, P.PORT_BATCH_COLUMNS)
    derived = {'ok': True, 'http_status': 200, 'request': deepcopy(call), 'schema_verified': True,
               'schema_source': raw['schema_source'], 'schema': list(P.PORT_BATCH_COLUMNS),
               'pages': P.projected_pages(p, bound_request=call), 'receipt_kind': 'derived_validated_projection_not_HTTP'}
    for page in derived['pages']:
        page['http_status'] = 200
    reject('independent.derived_wrapper_plus200_is_not_raw', lambda: P.collect_port_batches([{'request': call, 'receipt': derived}]))
    derived.pop('receipt_kind')
    reject('independent.derived_page_plus200_is_not_raw', lambda: P.collect_port_batches([{'request': call, 'receipt': derived}]))
    reject('independent.provider_output_is_not_raw', lambda: P.collect_port_batches([{'request': call, 'receipt': out}]))

    for label, dev in [('omitted', 'OMIT'), ('NULL', None), ('blank', ' ')]:
        r = {'id': 'unknown-'+label, 'logicalRegionName': 'review-region'}
        if dev != 'OMIT': r['devId'] = dev
        out = P.collect_port_batches([batch(call, [r])])
        same('nullable.devId_'+label+'_only_with_source_schema', out['rows'][0]['devId'], None)
    for key in ('id', 'logicalRegionName'):
        r = deepcopy(first); r.pop(key)
        reject('identity.never_fill_'+key, lambda r=r: P.collect_port_batches([batch(call, [r])]))
    reject('schema.missing_devId_column_not_filled', lambda: P.collect_port_batches([batch(call, [first], ('id', 'logicalRegionName'))]))
    reject('typed.PORT_bool_not_text_or_unknown', lambda: P.collect_port_batches([batch(call, [{**first, 'devId': False}])]))
    eip = counter['minimal_raw_receipts']['FLOATING_IPS']; eip_before = deepcopy(eip)
    reject('independent.EIP_bool_not_decoded_by_PORT_provider', lambda: P.collect_port_batches([{'request': eip['request'], 'receipt': eip}]))
    reject('legacy.EIP_bool_text_projection_behavior_not_relaxed', lambda: P.collect('FLOATING_IPS', eip, eip['request'], eip['schema']))
    same('EIP.raw_bool_and_role_left_unchanged', (eip, type(eip['pages'][0]['objList'][0]['isInternal']).__name__), (eip_before, 'bool'))

    prepared = P.collect_port_batches(equivalent)
    for label, mutate in [
        ('rows', lambda x: x['rows'][0].update(devId='tamper')),
        ('typed_rows', lambda x: x['typed_port_table']['rows'][0].update(devId='tamper')),
        ('canonical_total', lambda x: x['canonical_receipt'].update(canonical_object_count=999)),
        ('raw_copy', lambda x: x['raw_receipts'][0]['pages'][0].update(totalNum=999)),
        ('flag', lambda x: x.update(full_answer=True)),
        ('evidence_request', lambda x: x['input_evidence']['batches'][0]['request'].update(url='changed')),
    ]:
        bad = deepcopy(prepared); mutate(bad)
        bad['canonical_projection_sha256'] = P.digest(bad['rows'])
        bad['input_evidence_sha256'] = P.digest(bad['input_evidence'])
        reject('recheck.reject_rehashed_'+label, lambda bad=bad: P.recheck_port_batches(bad))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    error = None
    try: run()
    except Exception: error = traceback.format_exc()
    result = {'status': 'PASS' if error is None else 'FAIL', 'counterexample_checks': CHECKS,
              'error': error, 'provider_only': True, 'consumer_pairing': 'pending consumer owner',
              'synthetic_only': True, 'model_calls': 0, 'API_calls': 0, 'native_SQL_runs': 0,
              'score_or_business_coverage_claim': False}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='counterexample_checks'}, ensure_ascii=False))
    if error: raise SystemExit(1)


if __name__ == '__main__': main()
