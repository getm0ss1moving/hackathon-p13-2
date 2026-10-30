"""Pure synthetic semantics/contract checks, not official evaluation."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
import sys
R=Path(__file__).resolve().parents[2]/'experiments/a_issue4_r1_20261031/capacity'
s=importlib.util.spec_from_file_location('ranked_vdc_pool',R/'candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def params(region='region-example',owner='reject',size='reject'):
 return {'logicalRegionName':region,'tie_policy':'all_ties','unknown_owner_policy':owner,'unknown_size_policy':size}
def volume(i,owner='vdc-a',size='10',backend='p',region='region-example'):
 return {'id':i,'logicalRegionName':region,'vdcId':owner,'vdcName':'same-display','size':size,'attachBackendId':backend}
def pool(i='p',region='region-example'):
 return {'id':i,'logicalRegionName':region,'poolName':'pool-'+i,'totalCapacityGB':'1000','freeCapacityGB':'300','allocatedCapacityGB':'700','provisionedCapacityGB':'900'}
def snapshot(ci,rows,region='region-example',ps=2,empty_total=0):
 n=max(1,(len(rows)+ps-1)//ps)
 return {'ok':True,'schema_source':'synthetic-schema-v1','columns':list(m.SCHEMA[ci]),'pages':[
  {'ok':True,'currentPage':i+1,'pageSize':ps,'totalNum':len(rows),'totalPageNo':n if rows else empty_total,
   'request':m.request(ci,region,i+1,ps),'objList':rows[i*ps:(i+1)*ps]} for i in range(n)]}
def data(vols=None,pools=None,region='region-example',empty_total=0):
 return {'VOLUME':snapshot('VOLUME',vols or [],region,empty_total=empty_total),'STORAGE_POOL':snapshot('STORAGE_POOL',pools or [],region,empty_total=empty_total)}
def winners(result):return {r['vdc_id'] for r in result['rows']}

class Tests(unittest.TestCase):
 def test_rank_numeric_before_pool_details(self):
  r=m.execute(params(),data([volume('a',size='9'),volume('b','vdc-b','100','q')],[pool(),pool('q')]))
  self.assertEqual(winners(r),{'vdc-b'});self.assertEqual(r['rows'][0]['known_volume_size_source_units'],'100');self.assertEqual(r['rows'][0]['pool_id'],'q')
 def test_repeated_equal_sizes_count_distinct_volume_ids_not_values(self):
  r=m.execute(params(),data([volume('1',size='10'),volume('2',size='10'),volume('3','vdc-b','19')],[pool()]))
  self.assertEqual(winners(r),{'vdc-a'});self.assertEqual(r['rows'][0]['volume_count'],2);self.assertEqual(r['rows'][0]['known_volume_size_source_units'],'20')
 def test_exact_decimal_addition_preserves_tied_maxima(self):
  r=m.execute(params(),data([volume('1',size='0.1'),volume('2',size='0.2'),volume('3','vdc-b','0.3')],[pool()]))
  self.assertEqual(winners(r),{'vdc-a','vdc-b'});self.assertEqual({x['known_volume_size_source_units'] for x in r['rows']},{'0.3'})
 def test_pool_references_deduplicate_after_sum_and_shared_pool_is_whole(self):
  r=m.execute(params(),data([volume('1',size='10'),volume('2',size='10'),volume('3','vdc-b','20')],[pool()]))
  self.assertEqual(len(r['rows']),2);self.assertEqual({x['pool_id'] for x in r['rows']},{'p'})
  self.assertEqual({x['pool_total_capacity_raw'] for x in r['rows']},{'1000'});self.assertIn('not exclusive',r['diagnostics']['pool_capacity_meaning'])
 def test_winner_without_pool_reference_is_preserved(self):
  r=m.execute(params(),data([volume('1',backend=None)]))
  self.assertEqual(winners(r),{'vdc-a'});self.assertEqual(r['rows'][0]['pool_state'],'no_pool_reference');self.assertEqual(r['diagnostics']['winner_unknown_backend_volume_count'],1);self.assertFalse(r['diagnostics']['complete_winner_pool_details'])
 def test_dangling_reference_kept_separate_from_no_pool_reference(self):
  r=m.execute(params(),data([volume('1',backend='missing'),volume('2',backend='missing')]))
  self.assertEqual(len(r['rows']),1);self.assertEqual(r['rows'][0]['referenced_pool_id'],'missing');self.assertEqual(r['rows'][0]['pool_state'],'unresolved_pool');self.assertEqual(r['diagnostics']['winner_unresolved_backend_volume_count'],2)
 def test_unknown_size_can_change_winner_and_never_certifies_max(self):
  d=data([volume('1',size='10'),volume('2','vdc-b','1'),volume('3','vdc-b','unknown')],[pool()])
  self.assertEqual(m.execute(params(),d)['reason'],'unknown_volume_size')
  r=m.execute(params(size='known_only'),d);self.assertEqual(winners(r),{'vdc-a'});self.assertFalse(r['diagnostics']['scope_max_certified']);self.assertEqual(r['diagnostics']['winner_claim'],'known_lower_bound_leaders_only')
 def test_unknown_size_on_winner_preserves_null_complete_total(self):
  r=m.execute(params(size='known_only'),data([volume('1'),volume('2',size='garbage')],[pool()]))
  self.assertEqual(r['rows'][0]['known_volume_size_source_units'],'10');self.assertEqual(r['rows'][0]['unknown_size_volume_count'],1);self.assertIsNone(r['rows'][0]['total_volume_size_if_complete_source_units'])
 def test_unknown_owner_can_change_winner_and_complete_total_is_null(self):
  d=data([volume('1'),volume('2',None,'100')],[pool()]);self.assertEqual(m.execute(params(),d)['reason'],'unknown_vdc_identity')
  r=m.execute(params(owner='known_only'),d);self.assertEqual(winners(r),{'vdc-a'});self.assertFalse(r['diagnostics']['scope_max_certified']);self.assertEqual(r['diagnostics']['unknown_owner_volume_count'],1);self.assertIsNone(r['rows'][0]['total_volume_size_if_complete_source_units'])
 def test_null_empty_unicode_owner_identity_projected_without_name_buckets(self):
  for ident in [None,'',' ','\t','\r\n','\u3000','\u00a0']:
   with self.subTest(identity=repr(ident)):
    raw=data([volume('1'),volume('2',ident)],[pool()]);before=copy.deepcopy(raw);p=params(owner='known_only')
    checked=m.prepare(p,raw);self.assertIsNone(checked['tables']['VOLUME'][1]['vdcId']);self.assertEqual(raw,before)
    r=m.execute_prepared(p,checked);self.assertEqual(winners(r),{'vdc-a'});self.assertEqual(r['diagnostics']['unknown_owner_volume_count'],1)
 def test_nonblank_identity_not_trimmed_or_merged(self):
  r=m.execute(params(),data([volume('1',' A'),volume('2','A '),volume('3','A')],[pool()]))
  self.assertEqual(winners(r),{' A','A ','A'})
 def test_dirty_numeric_is_unknown_never_cast_zero_or_round(self):
  for value in [None,'','\t','notnum','12GB','1,024','-1','1e3','NaN','0.0000001',True]:
   with self.subTest(value=repr(value)):
    raw=data([volume('1',size=value)],[pool()]);r=m.execute(params(size='known_only'),raw)
    self.assertEqual(r['rows'][0]['unknown_size_volume_count'],1);self.assertEqual(r['rows'][0]['known_volume_size_source_units'],'0');self.assertIsNone(r['rows'][0]['total_volume_size_if_complete_source_units']);self.assertFalse(r['diagnostics']['scope_max_certified'])
 def test_numeric_range_and_sum_overflow_block(self):
  big=str(2**63);self.assertEqual(m.execute(params(),data([volume('1',size=big)],[pool()]))['reason'],'numeric_range_exceeded')
  each='6000000000000';self.assertEqual(m.execute(params(),data([volume('1',size=each),volume('2',size=each)],[pool()]))['reason'],'numeric_aggregate_range_exceeded')
 def test_exact_six_decimal_and_numeric_scalar_inputs(self):
  r=m.execute(params(),data([volume('1',size=' 1.000001\t'),volume('2',size=2)],[pool()]))
  self.assertEqual(r['rows'][0]['known_volume_size_source_units'],'3.000001');self.assertEqual(r['rows'][0]['total_volume_size_if_complete_source_units'],'3.000001')
 def test_true_empty_zero_or_one_page_count_and_no_volumes_not_all_vdc_catalog(self):
  for n in [0,1]:
   r=m.execute(params(),data(empty_total=n));self.assertEqual(r['rows'],[]);self.assertTrue(r['diagnostics']['no_volume_population'])
 def test_schema_and_missing_key_are_not_true_empty(self):
  variants=[];x=data();del x['VOLUME']['schema_source'];variants.append(x)
  x=data([volume('1')]);del x['VOLUME']['pages'][0]['objList'][0]['vdcId'];variants.append(x)
  x=data();x['STORAGE_POOL']['columns']=['_empty'];variants.append(x)
  for x in variants:self.assertEqual(m.execute(params(),x)['status'],'blocked')
 def test_failure_or_missing_success_receipt_blocks(self):
  for ci in m.RESOURCES:
   for mutate in [lambda x:x.pop('ok'),lambda x:x.update(ok=False),lambda x:x.update(error='failed')]:
    x=data();mutate(x[ci]);self.assertEqual(m.execute(params(),x)['status'],'blocked')
    x=data();mutate(x[ci]['pages'][0]);self.assertEqual(m.execute(params(),x)['status'],'blocked')
 def test_full_pagination_duplicate_overlap_and_unstable_metadata(self):
  original=data([volume(str(i)) for i in range(3)],[pool()]);self.assertEqual(m.execute(params(),original)['status'],'local_sql_ok_policy_conditional')
  changes=[lambda x:x['VOLUME']['pages'].pop(),lambda x:x['VOLUME']['pages'].reverse(),lambda x:x['VOLUME']['pages'][1].update(totalNum=4),lambda x:x['VOLUME']['pages'][1]['objList'][0].update(id='0')]
  for change in changes:
   x=copy.deepcopy(original);change(x);self.assertEqual(m.execute(params(),x)['status'],'blocked')
 def test_request_binding_exact_method_scope_operator_and_page(self):
  for mutate in [lambda q:q.update(method='POST'),lambda q:q['condition']['constraint'][0]['simple'].update(operator='contain'),lambda q:q['condition']['constraint'][0]['simple'].update(value='other'),lambda q:q.update(url=q['url'].replace('pageNo=1','pageNo=2'))]:
   x=data();mutate(x['VOLUME']['pages'][0]['request']);self.assertEqual(m.execute(params(),x)['reason'],'request_binding_mismatch')
 def test_wrong_region_rows_and_pool_duplicate_are_blocked(self):
  for d in [data([volume('1',region='other')]),data([], [pool(region='other')]),data([], [pool(),pool()])]:self.assertEqual(m.execute(params(),d)['status'],'blocked')
 def test_closed_parameters_policies_and_region_no_default(self):
  for k in params():
   x=params();del x[k]
   with self.assertRaises(ValueError):m.build(x)
  for extra in [{'scope':'global'},{'metric':'count'},{'azoneName':'az'},{'question':'text'},{'source_id':'anything'}]:
   x=params();x.update(extra)
   with self.assertRaises(ValueError):m.build(x)
  x=params();x['tie_policy']='first'
  with self.assertRaises(ValueError):m.build(x)
 def test_entity_replacements_quotes_and_scope_propagated(self):
  for region in ['new-region','区域',"r' OR 1=1 --",'r_%']:
   p=params(region);r=m.execute(p,data([volume('1',region=region)],[pool(region=region)],region))
   self.assertEqual(winners(r),{'vdc-a'});self.assertEqual(r['rows'][0]['logical_region_name'],region)
 def test_projection_drift_raw_execution_and_diagnostic_mismatch_blocked(self):
  p=params();checked=m.prepare(p,data([volume('1')],[pool()]));self.assertEqual(m.execute_prepared(p,{})['reason'],'validated_projection_required')
  checked['tables']['VOLUME'][0]['size_scaled']=0;self.assertEqual(m.execute_prepared(p,checked)['reason'],'projection_changed')
  checked['projection_sha256']=m.fingerprint(checked['tables']);self.assertEqual(m.execute_prepared(p,checked)['reason'],'size_projection_changed')
  checked=m.prepare(p,data([volume('1')],[pool()]));checked['diagnostics']['unknown_size_volume_count']=2;self.assertEqual(m.execute_prepared(p,checked)['reason'],'diagnostic_projection_mismatch')
 def test_unknown_max_certification_diagnostic_drift_is_rejected(self):
  p=params(size='known_only');checked=m.prepare(p,data([volume('1',size='dirty')],[pool()]))
  checked['diagnostics']['scope_max_certified']=True
  self.assertEqual(m.execute_prepared(p,checked)['reason'],'diagnostic_projection_mismatch')
 def test_length_boundaries_static_wire_fullplan_outer_separate(self):
  small=m.build(params());self.assertEqual(small['byte_boundaries']['full_plan_bytes'],m.compact(small))
  self.assertEqual(small['byte_boundaries']['expanded_wire_bytes'],m.compact({k:small[k] for k in ['api_call','sql']}))
  long=m.build(params('区'*2000));self.assertEqual(long['status'],'blocked_transport_budget');self.assertEqual(m.preflight(params('区'*2000),{})['reason'],'transport_budget')
  self.assertGreater(long['blocked_reason']['measured_bytes'],4096)
  self.assertEqual(m.build(params('r'*100))['status'],'isolated_candidate_policy_conditional')
  self.assertEqual(m.envelope_budget({'outer':small,'extra':'x'*4096})['status'],'blocked')

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);r=unittest.TextTestRunner(verbosity=1).run(suite)
 out={'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'successful':r.wasSuccessful(),'scope':'pure synthetic Python + in-memory SQLite','not_run':['native SQL','business service','model','official evaluation','B runtime','sealed answers/references','full200']}
 (Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/a-capacity-validation.json')).write_text(json.dumps(out,indent=2)+'\n');raise SystemExit(0 if r.wasSuccessful() else 1)
