#!/usr/bin/env python3
"""Offline overlay integration controls; no model/network/executor/evaluator calls."""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'experiments/a_issue4_r1_20261031'
sys.path.insert(0, str(PACKAGE / 'main'))
sys.path.insert(0, str(PACKAGE / 'management'))
import argparse,copy,hashlib,json,shutil,sqlite3,tempfile,types
from pathlib import Path
ROOT=PACKAGE / 'management'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(name,path):
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--legacy-source-root',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args()
 args.output_dir.mkdir(parents=True,exist_ok=True)
 adapter=load('management_overlay',ROOT/'adapter.py');core=load('management_core_oracle',ROOT/'core/candidate.py');pin=sha(ROOT/'BINDING.json')
 p={'view':core.VIEW,'logicalRegionName':'geo-sable','ip_role':'both_raw','capacity_mode':'per_volume_raw_and_numeric_summary'}
 q='查询区域“geo-sable”下各VDC的管理虚拟机名称、IP、所属云服务、规格和挂载云硬盘容量'
 item=json.loads((ROOT/'SELECTION_CARD.json').read_text());checks=[]
 def check(name,value):checks.append({'id':name,'passed':bool(value)})
 def rejected(name,call):
  try:call()
  except (ValueError,LookupError,OSError):check(name,True)
  else:check(name,False)
 def router(*,enabled=True,prepared=True,root=ROOT,legacy=args.legacy_source_root,expected=pin):return adapter.bind(legacy,expected,enable_experimental=enabled,prepared_pipeline=prepared,package_root=root)
 off=router(enabled=False,prepared=False)
 check('default_module_not_enabled',adapter.handles_item(item) is False)
 check('default_bound_no_selection_card',off.selection_cards()==[] and not off.handles_item(item))
 rejected('explicit_new_route_disabled',lambda:off.prepare_candidate(q,item,p))
 rejected('enable_without_typed_pipeline',lambda:router(prepared=False))
 rejected('config_flags_not_model_truthiness',lambda:router(enabled=1))
 r=router();cards=r.selection_cards();check('one_independent_card',len(cards)==1 and cards[0]['id']==core.FAMILY_ID and r.handles_item(item))
 cards[0]['name']='tampered';check('selection_copy_does_not_mutate_binding',r.selection_cards()[0]['name']==item['name'])
 check('exact_four_parameter_schema',set(item['parameter_schema']['required'])=={'view','logicalRegionName','ip_role','capacity_mode'} and item['parameter_schema']==json.loads((ROOT/'PARAMETER_SCHEMA.json').read_text()))
 d={};ordinary=r.prepare_candidate(q,item,p,d);bare=core.prepare_candidate(q,item,p)
 check('core_missing_name_reproduced','name'not in bare)
 check('adapter_adds_only_name',{k:v for k,v in ordinary.items() if k!='name'}==bare and ordinary['name']==item['name'])
 check('ordinary_metadata_compatible',{'id','name','resources','api_call','sql'}<=set(ordinary))
 check('build_metadata_name',r.build(p)['name']==item['name'])
 check('typed_contract_preserved',ordinary['requires_prepared_inputs']is True and ordinary['source_schema']==bare['source_schema'] and ordinary['prepared_schema']==bare['prepared_schema'])
 check('SQL_is_prepared_table_not_raw_CI',core.TABLE in ordinary['sql'] and 'CLOUD_VM_NOVA'not in ordinary['sql'])
 check('native_bool_preserved',ordinary['api_call'][0]['condition']['constraint'][1]['simple']['value'] is True)
 check('full_original_question_evidence',d['contract_evidence']['scope']=={'logicalRegionName':'geo-sable','management':True})
 for label,question in [('wrong_region',q.replace('geo-sable','geo-other')),('wrong_case',q.replace('geo-sable','Geo-sable')),('wrong_role',q.replace('区域','可用区')),('extra_VM_count',q+'并统计ECS数量'),('extra_delete',q+'并删除虚拟机'),('missing_service',q.replace('、所属云服务',''))]:
  check(label,r.prepare_candidate(question,item,p) is None)
 extra={**p,'enable_experimental':True};check('model_cannot_enable_route',r.prepare_candidate(q,item,extra) is None)
 mismatch={**item,'name':'different'};rejected('card_name_drift',lambda:r.prepare_candidate(q,mismatch,p))
 mismatch=copy.deepcopy(item);mismatch['parameter_schema']['properties']['ip_role']['enum']=['both_raw'];rejected('card_schema_drift',lambda:r.prepare_candidate(q,mismatch,p))
 rejected('unbound_SQL_in_selected_card',lambda:r.prepare_candidate(q,{**item,'sql':'SELECT 0'},p))
 # Nonmatching items pass byte-for-byte object identities to legacy B, even with
 # a drifted optional new source pin; the overlay never owns those routes.
 for legacy_item in [{'id':'rb_synthetic_fixed'},{'id':'family_volume_rows'},None]:
  original_params={'unchanged':object()};diagnostics={};calls=[];sentinel=object()
  def old_route(question,selected,parsed,diag):calls.append((question,selected,parsed,diag));return sentinel
  result=r.prepare_or_delegate(q,legacy_item,original_params,old_route,diagnostics)
  check('legacy_args_unchanged_'+str(legacy_item),result is sentinel and calls[0][0]is q and calls[0][1]is legacy_item and calls[0][2]is original_params and calls[0][3]is diagnostics and diagnostics=={})
 badpin=router(expected='0'*64)
 check('unmatched_old_route_not_blocked_by_new_pin',badpin.prepare_or_delegate(q,{'id':'rb_other'},p,lambda *a:'legacy')=='legacy')
 rejected('binding_outer_pin_drift',lambda:badpin.prepare_candidate(q,item,p))
 # Exercise the actual old unified prepare on an existing family, with synthetic
 # entity parameters only. Nothing is written to its source tree.
 legacy=load('legacy_prepare_source',args.legacy_source_root/'unified_prepare.py')
 li={'id':'family_volume_rows','family_id':'family_volume_rows','name':'synthetic old family'}
 lp={'view':'vdc_scoped_rows','filters':{'vdcName':'vdc-cedar','logicalRegionName':'geo-sable'},'required_filters':['vdcName','logicalRegionName']}
 lq='查询VDC“vdc-cedar”在区域“geo-sable”中的云硬盘列表及容量';diag_a={};diag_b={}
 direct=legacy.prepare_candidate(lq,li,lp,diag_a);forwarded=r.prepare_or_delegate(lq,li,lp,legacy.prepare_candidate,diag_b)
 check('real_old_unified_route_unchanged',direct is not None and direct==forwarded and diag_a==diag_b)
 check('new_family_not_registered_in_old_registry',not legacy.handles_item(item))
 # The old shape gate is reproduced on a temporary copy of the old dispatcher.
 with tempfile.TemporaryDirectory(prefix='management-overlay-gate-') as td:
  t=Path(td);shutil.copyfile(args.legacy_source_root/'unified_prepare.py',t/'unified_prepare.py');shutil.copyfile(ROOT/'core/candidate.py',t/'candidate.py')
  reg={core.FAMILY_ID:{'family_id':core.FAMILY_ID,'module':'candidate.py','module_sha256':sha(t/'candidate.py')}}
  (t/'FAMILY_ROUTE_REGISTRY.json').write_text(json.dumps(reg));oldgate=load('copied_old_shape_gate',t/'unified_prepare.py')
  rejected('actual_old_gate_rejects_core_no_name',lambda:oldgate.prepare_candidate(q,item,p))
  key=sha(t/'candidate.py');oldgate._MODULES[key]=types.SimpleNamespace(prepare_candidate=lambda *a:ordinary)
  check('actual_old_shape_gate_accepts_overlay_metadata',oldgate.prepare_candidate(q,item,p)==ordinary)
 # Local receipts and typed prepared-table path retain unknown VDC/owner flags.
 data={ci:[] for ci in core.SCHEMA}
 data['VM_NOVA']=[dict(id='vm-synthetic',name='VM Cedar',logicalRegionName='geo-sable',management=True,vdcId=None,vdcName=None,privateIps='10.24.8.1',ipAddress='10.24.8.1',flavorId=None)]
 data['S_DeployNode']=[dict(id='unknown-owner',vmId=None,hostClass='VM')]
 def receipts():
  return {ci:{'ok':True,'schema_verified':True,'schema':list(core.SCHEMA[ci]),'request':copy.deepcopy(call),'pages':[{'ok':True,'pageNo':1,'pageSize':1000,'totalNum':len(data[ci]),'totalPageNo':int(bool(data[ci])),'objList':copy.deepcopy(data[ci])}]} for ci,call in zip(core.SCHEMA,ordinary['api_call'])}
 rec=receipts();original=copy.deepcopy((p,item,rec));prepared=r.prepare_inputs(q,item,p,rec)
 expected_tables,expected_diag=core.prepare(p,rec)
 check('preflight_semantics_byte_equivalent',prepared['tables']==expected_tables and prepared['diagnostics']==expected_diag and (p,item,rec)==original)
 check('unknown_owner_VDC_not_loosened',prepared['diagnostics']['unknown_VDC_count']==1 and prepared['diagnostics']['unknown_global_service_owner_nodes']==1 and prepared['diagnostics']['full_answer_certified']is False and not prepared['diagnostics']['requested_values_complete_in_declared_snapshot'])
 check('rejected_question_cannot_prepare_receipts',r.prepare_inputs(q+'并删除虚拟机',item,p,rec) is None)
 conn=sqlite3.connect(':memory:');cols=ordinary['prepared_schema'][core.TABLE]
 conn.execute('CREATE TABLE '+core.TABLE+' ('+','.join('"'+c+'" '+('INTEGER' if c in {'management','declared_values_complete','unknown_service_link_count','unknown_size_reference_count'} else 'TEXT') for c in cols)+')')
 conn.executemany('INSERT INTO '+core.TABLE+' VALUES ('+','.join('?' for c in cols)+')',[[row[c] for c in cols] for row in prepared['tables'][core.TABLE]])
 cur=conn.execute(ordinary['sql']);rows=cur.fetchall();check('typed_SQL_end_to_end_unknown_parent_retained',len(rows)==1 and rows[0][0]=='vm-synthetic' and rows[0][-1]==0);conn.close()
 rejects=receipts();rejects['VM_NOVA']['request']['condition']['constraint'][1]['simple']['value']='true'
 rejected('no_string_true_API_substitution',lambda:r.prepare_inputs(q,item,p,rejects))
 # Source/card/schema/adapter and old132 drift are each a separate failure.
 with tempfile.TemporaryDirectory(prefix='management-overlay-drift-') as td:
  tmp=Path(td)
  for role,record in json.loads((ROOT/'BINDING.json').read_text())['assets'].items():
   copyroot=tmp/role;shutil.copytree(ROOT,copyroot);target=copyroot/record['path'];target.write_bytes(target.read_bytes()+b'\n')
   rejected('asset_drift_'+role,lambda copyroot=copyroot:router(root=copyroot).prepare_candidate(q,item,p))
  legacycopy=tmp/'legacy';legacycopy.mkdir()
  binding=json.loads((ROOT/'BINDING.json').read_text())
  for record in binding['legacy132_source']['files']:shutil.copyfile(args.legacy_source_root/record['path'],legacycopy/record['path'])
  for record in binding['legacy132_source']['files']:
   target=legacycopy/record['path'];content=target.read_bytes();target.write_bytes(content+b'\n')
   rejected('legacy_source_drift_'+record['role'],lambda:router(legacy=legacycopy).prepare_candidate(q,item,p));target.write_bytes(content)
 report={'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL','checks':len(checks),'passed':sum(c['passed'] for c in checks),'failed':[c for c in checks if not c['passed']],'checks_detail':checks,'model_calls':0,'business_API_calls':0,'repository_downloads':0,'full_suite_runs':0,'old_registry_or_arrays_written':False,'core_semantics_changed':False,'independent_review_pending':True}
 (args.output_dir/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 (args.output_dir/'MATERIALIZED_SYNTHETIC.json').write_text(json.dumps({'params':p,'ordinary_plan':ordinary,'prepared_diagnostics':prepared['diagnostics'],'prepared_table_row_count':len(rows)},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='checks_detail'},ensure_ascii=False))
 if report['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
