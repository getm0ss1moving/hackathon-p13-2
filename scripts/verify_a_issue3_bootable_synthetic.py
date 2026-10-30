"""Public12 grouped bootable checks; native field evidence is a prior aggregate.

First11 pure/synthetic controls follow the independent receipt. The final control
checks exact patch/card/registry artifacts and aggregate consistency; it never
reads native records. Owner71 and B/official runtime are not run.
"""
import argparse,ast,collections,copy,hashlib,importlib.util,json,re,sqlite3,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'experiments/issue3_bootable_contract_20261030'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((SRC/'MANIFEST.json').read_text())
for rel,expected in manifest['files'].items():assert sha(SRC/rel)==expected,rel
for rel,expected in (manifest['tools']|manifest['external_files']).items():assert sha(ROOT/rel)==expected,rel
closure=json.loads((SRC/'SOURCE_CLOSURE.json').read_text())
for entry in closure['selected_exact_source_files']:
 assert sha(SRC/entry['path'])==entry['published_sha256']==entry['source_sha256']
paths=[SRC/'candidate.py',SRC/'source/family_volume_rows.original.py',SRC/'CHANGES.patch',SRC/'MANIFEST.json',SRC/'FAMILY_CARD_PATCH.json']
protected={str(p):sha(p) for p in paths}
out=args.output.resolve()
assert out!=ROOT and ROOT not in out.parents,'output must be outside repository'
out.mkdir(parents=True,exist_ok=False)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
new=load('public_bootable_new',paths[0]);old=load('public_bootable_old',paths[1])
item={"id":new.FAMILY_ID,"family_id":new.FAMILY_ID,"name":"independent_review","resources":["VOLUME"]}
region="Review-Region-X";az="Review-AZ-Y";vdc="Review-VDC"
def p(value=True):
 return {"view":"bootable_scoped_rows","filters":{"logicalRegionName":region,"azoneName":az,"bootable":value},
         "required_filters":["logicalRegionName","azoneName","bootable"]}
q='查询区域"'+region+'"可用区"'+az+'"中可启动云硬盘列表'
qfalse='查询区域"'+region+'"可用区"'+az+'"中bootable FALSE云硬盘列表'
checks=[]
def check(name,fn):
 try:
  detail=fn();ok=detail is True or isinstance(detail,dict) and detail.get("passed") is True
 except Exception as e:ok=False;detail={"error":type(e).__name__,"reason":str(e)}
 checks.append({"name":name,"passed":ok,"detail":detail})
def invalid(v):
 try:new.normalize_bootable(v)
 except ValueError:return True
 return False
check("01_normalization_bool_and_case_variants",lambda:all(
 new.normalize_bootable(v)==expected for v,expected in [(True,"true"),(False,"false"),("true","true"),("TRUE","true"),("tRuE","true"),("false","false"),("FALSE","false"),("fAlSe","false")]))
class Truthy:
 def __bool__(self):return True
check("02_no_numeric_null_container_truthiness_coercion",lambda:all(invalid(v) for v in [None,0,1,0.0,1.0,"0","1","yes","no","on","off",""," true","true ","false\n",[],{},Truthy()]))
def values(out):
 return {e["simple"]["name"]:e["simple"]["value"] for e in out["api_call"]["condition"]["constraint"]}
def true_api():
 before=copy.deepcopy(item);params=p(True);frozen=copy.deepcopy(params)
 outs=[new.prepare_candidate(q,item,p(v)) for v in [True,"TRUE","tRuE","true"]]
 return all(o and values(o)=={"logicalRegionName":region,"azoneName":az,"bootable":"true"}
  and type(values(o)["bootable"]) is str and o["api_call"]["method"]=="GET"
  and "/instances/VOLUME?" in o["api_call"]["url"] for o in outs) and item==before and params==frozen
check("03_true_input_API_string_and_scope_preserved",true_api)
check("04_false_input_requires_explicit_false_and_is_string",lambda:all(
 (lambda o:o is not None and values(o)["bootable"]=="false" and type(values(o)["bootable"]) is str)
 (new.prepare_candidate(qfalse,item,p(v))) for v in [False,"fAlSe"]))
check("05_opposite_predicate_never_rebound",lambda:
 new.prepare_candidate(q,item,p(False)) is None and new.prepare_candidate(qfalse,item,p(True)) is None)
def wrong_scopes():
 variants=[]
 for field,value in [("logicalRegionName",region.lower()),("azoneName",az.lower()),("azoneName","Other-AZ")]:
  x=p();x["filters"][field]=value;variants.append(x)
 x=p();x["filters"]["logicalRegionName"],x["filters"]["azoneName"]=az,region;variants.append(x)
 return all(new.prepare_candidate(q,item,x) is None for x in variants)
check("06_region_AZ_case_and_role_mismatch_rejected",wrong_scopes)
def bad_schema():
 variants=[]
 x=p();x["filters"]["logicalRegionName"]=True;variants.append(x)
 x=p();x["required_filters"]=["logicalRegionName","bootable"];variants.append(x)
 x=p();x["filters"]["management"]=True;variants.append(x)
 x=p();x["filters"].pop("azoneName");variants.append(x)
 wrong=dict(item,family_id="different_family")
 return all(new.prepare_candidate(q,item,x) is None for x in variants) and new.prepare_candidate(q,wrong,p()) is None and new.prepare_candidate(q+"并统计数量",item,p()) is None
check("07_exact_schema_roles_and_extra_obligation_rejected",bad_schema)
def other_view():
 params={"view":"vdc_scoped_rows","filters":{"vdcName":vdc,"logicalRegionName":region},
         "required_filters":["vdcName","logicalRegionName"]}
 text='查询VDC"'+vdc+'"区域"'+region+'"云硬盘名称和容量列表'
 a=old.prepare_candidate(text,item,params);b=new.prepare_candidate(text,item,params)
 return a is not None and a==b and old.prepare_candidate(text+"并统计虚拟机数量",item,params)==new.prepare_candidate(text+"并统计虚拟机数量",item,params)
check("08_other_view_old_new_equivalence",other_view)
def sole_delta():
 a=old.prepare_candidate(q,item,p("True"));b=new.prepare_candidate(q,item,p(True))
 if a is None or b is None:return False
 changed=copy.deepcopy(a)
 for e in changed["api_call"]["condition"]["constraint"]:
  if e["simple"]["name"]=="bootable":e["simple"]["value"]="true"
 return changed==b and a["sql"]==b["sql"] and values(a)["logicalRegionName"]==values(b)["logicalRegionName"] and values(a)["azoneName"]==values(b)["azoneName"]
check("09_only_canonical_bootable_value_changes_in_materialized_item",sole_delta)
def ast_delta():
 def funcs(pth):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(pth.read_text()).body if isinstance(n,ast.FunctionDef)}
 a=funcs(paths[1]);b=funcs(paths[0]);changed={k for k in a if a[k]!=b.get(k)};added=set(b)-set(a)
 return {"passed":new.VIEWS==old.VIEWS and changed=={"_materialize","_literal","_bind","_ground"} and added=={"normalize_bootable","_normalize_bootable_parameters"},
         "changed":sorted(changed),"added":sorted(added),"VIEWS_identical":new.VIEWS==old.VIEWS}
check("10_AST_diff_limited_and_all_view_API_SQL_unchanged",ast_delta)
def sql_controls():
 with sqlite3.connect(":memory:") as db:
  db.execute("CREATE TABLE CLOUD_VOLUME(name TEXT,size INTEGER,status TEXT,bootable TEXT)")
  db.executemany("INSERT INTO CLOUD_VOLUME VALUES(?,?,?,?)",[("dup",None,None,"true"),("dup",None,None,"true")])
  sql=new.VIEWS["bootable_scoped_rows"]["sql"];a=db.execute(sql).fetchall()
  db.execute("DELETE FROM CLOUD_VOLUME");b=db.execute(sql).fetchall()
  return a==[("dup",None,None,"true")]*2 and b==[]
check("11_SQL_preserves_NULL_duplicate_and_typed_empty",sql_controls)
def public_artifacts():
 # Exact unified patch replay in memory; no shell patch or source mutation.
 original=paths[1].read_text().splitlines(keepends=True)
 patch=paths[2].read_text().splitlines(keepends=True)
 output=[];position=0;i=0;exact=True
 while i<len(patch):
  if not patch[i].startswith('@@ '):i+=1;continue
  match=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',patch[i]);start=int(match[1])-1
  output.extend(original[position:start]);position=start;i+=1
  while i<len(patch) and not patch[i].startswith('@@ '):
   line=patch[i]
   if line.startswith(' '):exact &= original[position]==line[1:];output.append(line[1:]);position+=1
   elif line.startswith('-'):exact &= original[position]==line[1:];position+=1
   elif line.startswith('+'):output.append(line[1:])
   i+=1
 output.extend(original[position:])
 patch_ok=exact and ''.join(output)==paths[0].read_text()
 registry=json.loads((SRC/'REGISTRY_PATCH.json').read_text())
 card=json.loads((SRC/'FAMILY_CARD_PATCH.json').read_text())
 contract=json.loads((SRC/'CONTRACT.json').read_text())
 proposals_ok=(registry['selector']=={'family_id':new.FAMILY_ID}
  and registry['field']=='module_sha256' and registry['test']==sha(paths[1])
  and registry['replace']==sha(paths[0]) and registry['default_enablement'] is False
  and card['target_family_id']==new.FAMILY_ID
  and card['source_card_sha256']=='2e7436eede49378d098cc8cc80f86b50dec3ab614015e16669cf297b70f57061'
  and card['json_patch']==[{'op':'test','path':'/parameter_contract/bootable','value':['True','False']},
                         {'op':'replace','path':'/parameter_contract/bootable','value':['true','false']}]
  and contract['enabled'] is False and contract['normalization']['canonical_API_type']=='string'
  and contract['normalization']['canonical_API_enum']==['true','false'])
 # These are published historical field aggregates, not a new native scan.
 ev=json.loads((SRC/'NATIVE_BOOTABLE_EVIDENCE.json').read_text())
 aggregate_ok=(sum(f['records'] for f in ev['files'])==6190 and ev['missing']==0
  and {(x['type'],x['representation']) for x in ev['type_value_counts']}=={('str',"'true'"),('str',"'false'")}
  and sum(x['count'] for x in ev['type_value_counts'])==6190)
 return {'passed':patch_ok and proposals_ok and aggregate_ok,
         'patch_replays_exactly':patch_ok,'four_part_integration_proposals_consistent':proposals_ok,
         'historical_field_aggregate_artifact_consistent':aggregate_ok,'native_records_reread':False}
check('12_public_patch_card_registry_and_historical_aggregate_artifacts',public_artifacts)
unchanged=protected=={str(p):sha(p) for p in paths}
summary={'scope':'public12 grouped controls; final artifact check differs from original native reread control',
 'checks':len(checks),'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),
 'source_files_unchanged':unchanged,'owner71_suite_run':False,'native_records_read':False,
 'prior_native_field_evidence_referenced_only':True,'model_calls':0,'service_calls':0,'B_runtime_calls':0,
 'official_executor_or_scorer_calls':0,'management_VM_implemented_or_bool_changed':False,
 'production_enabled':False,'actual_runtime_N_delta':0}
(out/'RESULTS.json').write_text(json.dumps({'summary':summary,'checks':checks},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert summary['checks']==summary['passed']==12 and summary['failed']==0 and unchanged,'public bootable replay failed'
