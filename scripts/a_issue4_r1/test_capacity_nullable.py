"""Only VOLUME.vdcName nullable-display increment; no VM/provider changes."""
from copy import deepcopy
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]/'experiments/a_issue4_r1_20261031/capacity'


def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 T=load('capacity_unchanged_control',Path(__file__).resolve().parent/'test_capacity.py');M=T.m
 old=load('capacity_v3_frozen',ROOT/'source/candidate.v3.py')
 checks=[]
 def check(name,passed):
  checks.append({'id':name,'passed':bool(passed)})
  if not passed:raise AssertionError(name)
 def blocked(name,p,d):
  out=M.execute(p,d);check(name,out.get('status')=='blocked' and 'rows' not in out);return out
 def sparse(v):
  v=dict(v);v.pop('vdcName');return v
 full=T.data([T.volume('a1',size='10',backend='p'),T.volume('a2',size='10',backend='q'),T.volume('b1','vdc-b','19'),T.volume('u1',None,'100')],[T.pool(),T.pool('q')])
 raw=deepcopy(full)
 for page in raw['VOLUME']['pages']:
  for row in page['objList']:row.pop('vdcName')
 before=deepcopy(raw);raw_hash=M.fingerprint(raw)
 strict=T.params();known=T.params(owner='known_only')
 check('v3.strict_original_sparse_block',old.execute(strict,deepcopy(raw))['reason']=='missing_row_schema')
 check('v3.known_only_original_sparse_block',old.execute(known,deepcopy(raw))['reason']=='missing_row_schema')
 out=blocked('v4.strict_unknown_owner_still_rejects',strict,raw)
 check('v4.strict_reaches_real_unknown_identity_gate',out['reason']=='unknown_vdc_identity' and out['unknown_owner_volume_count']==1)
 out=M.execute(known,raw)
 check('v4.known_only_real_ID_leader_and_two_pool_details',out['status']=='local_sql_ok_policy_conditional' and {x['vdc_id'] for x in out['rows']}=={'vdc-a'} and {x['pool_id'] for x in out['rows']}=={'p','q'})
 check('v4.source_units_capacity_not_doubled',all(x['known_volume_size_source_units']=='20' and x['total_volume_size_if_complete_source_units'] is None for x in out['rows']))
 check('v4.known_only_not_complete_winner',out['diagnostics']['scope_max_certified'] is False and out['diagnostics']['full_answer_certified'] is False and out['diagnostics']['winner_claim']=='known_lower_bound_leaders_only')
 check('v4.missing_display_remains_NULL',all(x['vdc_name'] is None for x in out['rows']))
 check('v4.raw_receipts_unchanged',M.fingerprint(raw)==raw_hash and raw==before and all('vdcName' not in r for pg in raw['VOLUME']['pages'] for r in pg['objList']))
 prepared=M.prepare(known,raw)
 check('v4.input_evidence_retains_original_missing_key',prepared['input_evidence']['snapshots']==before and all('vdcName' not in r for pg in prepared['input_evidence']['snapshots']['VOLUME']['pages'] for r in pg['objList']))
 check('v4.typed_projection_has_only_declared_NULL_display',all(r['vdcName'] is None for r in prepared['tables']['VOLUME']))
 check('v4.execute_prepared_rechecks_same_original_sparse_evidence',M.execute_prepared(known,prepared)['rows']==out['rows'])
 old_prepared=old.prepare(known,full)
 check('v4.explicit_new_projection_rejects_old_ready_version',M.execute_prepared(known,old_prepared)['reason']=='validated_projection_required')
 check('v4.projection_version_explicit',prepared['projection_contract']=='volume-capacity-vdc-pool-v4-nullable-vdc-name')
 for p in (strict,known):
  a,b=M.build(p),old.build(p)
  check('compat.ID_params_API_SQL_output_'+p['unknown_owner_policy'],all(a[k]==b[k] for k in ('id','profile','params','parameter_schema','resources','api_call','sql','output_columns','required_schema','prepared_schema','size_scale','size_unit')))
 known_display_missing=T.data([sparse(T.volume('known'))],[T.pool()])
 out=M.execute(strict,known_display_missing)
 check('display_missing_never_turns_known_ID_into_unknown_owner',out['status']=='local_sql_ok_policy_conditional' and out['diagnostics']['scope_max_certified'] is True and out['diagnostics']['full_answer_certified'] is False and out['rows'][0]['vdc_id']=='vdc-a')
 for value,label in [(None,'NULL'),('','empty'),(' ','blank')]:
  data=T.data([{**T.volume('known'),'vdcName':value}],[T.pool()])
  check('compat.existing_display_'+label,M.fingerprint(M.execute(strict,data)['rows'])==old.fingerprint(old.execute(strict,data)['rows']))
 # Exact seven rejection classes reported by B, using fresh synthetic receipts.
 base=T.data([sparse(T.volume('one')),sparse(T.volume('two'))],[T.pool()])
 variants=[
  ('missing_identity',lambda d:d['VOLUME']['pages'][0]['objList'][0].pop('id')),
  ('HTTP503',lambda d:d['VOLUME']['pages'][0].update(http_status=503)),
  ('schema_column_missing',lambda d:d['VOLUME']['columns'].remove('vdcName')),
  ('wrong_scope',lambda d:d['VOLUME']['pages'][0]['objList'][0].update(logicalRegionName='wrong')),
  ('nullable_wrong_type',lambda d:d['VOLUME']['pages'][0]['objList'][0].update(vdcName=False)),
  ('duplicate_identity',lambda d:d['VOLUME']['pages'][0]['objList'][1].update(id='one')),
  ('missing_page',lambda d:d['VOLUME']['pages'].pop()),
 ]
 for name,mutate in variants:
  bad=deepcopy(base);mutate(bad);bad_before=deepcopy(bad)
  blocked('B_negative_class.'+name,strict,bad);check('B_negative_immutable.'+name,bad==bad_before)
 # All other source fields remain mandatory, not just the seven representative failures.
 for ci in M.RESOURCES:
  for key in M.SCHEMA[ci]:
   if (ci,key)==('VOLUME','vdcName'):continue
   bad=deepcopy(base);bad[ci]['pages'][0]['objList'][0].pop(key)
   blocked('only_allow_target_missing.'+ci+'.'+key,known,bad)
 for ci in M.RESOURCES:
  for level in ('resource','page'):
   bad=deepcopy(base);target=bad[ci] if level=='resource' else bad[ci]['pages'][0];target['http_status']=503
   blocked('retained_HTTP503.'+ci+'.'+level,known,bad)
 for code in ('200',True,200.0,None):
  bad=deepcopy(base);bad['VOLUME']['pages'][0]['http_status']=code
  blocked('retained_HTTP_exact_type.'+repr(code),known,bad)
 bad=deepcopy(base);bad['VOLUME'].pop('schema_source');blocked('schema_source_required',known,bad)
 # Scope, numeric parsing, ranking, receipts and execution source checks unchanged by AST.
 def functions(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
 a,b=functions((ROOT/'candidate.py').read_text()),functions((ROOT/'source/candidate.v3.py').read_text())
 check('minimal.function_AST_only_build_preflight_changed',{k for k in a if a[k]!=b[k]}=={'build','preflight'})
 result={'status':'PASS','checks':checks,'source_original_sha256':hashlib.sha256((ROOT/'source/candidate.v3.py').read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256((ROOT/'candidate.py').read_bytes()).hexdigest(),'B_native_numbers':'reported only; not replayed','synthetic_only':True,'model_calls':0,'business_API_calls':0,'native_SQL_runs':0,'VM_or_provider_written':False,'full_original_question_certified':False}
 args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))


if __name__=='__main__':main()
