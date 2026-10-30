"""Replay the frozen53 R3 synthetic checks with the exact privately rebuilt template.

The provider in this verifier is test-only. It does not authenticate a production
capture reader or resolve B typed COUNT, native response or official policy gates.
"""
import ast,copy,hashlib,importlib.util,json,argparse
from pathlib import Path
from build_a_issue3_contracts import PACKAGE, verify_public, fresh_output
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--private-template',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
minimal=verify_public()
out=fresh_output(args.output)
P=PACKAGE/'modules/291_R3/materialize.py'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(P)=='70f255816ba7e83678002cba06e0761612bcf3dbf03508d4209209c9d2ffcae7'
assert sha(args.private_template)=='f2c25f8f5b7902b47eeedde370cfdd8ee91c059bd471f7d13f4dd0fe953e48b7'
paths=[P,PACKAGE/'modules/291_R3/CONTRACT.json',args.private_template]
before={str(p):sha(p) for p in paths}
spec=importlib.util.spec_from_file_location('public_R3',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
T=json.loads(args.private_template.read_text())
checks=[];positive=[]
def check(name,ok,detail=None):checks.append({"name":name,"passed":bool(ok),"detail":detail})
def fixture():
 return {"AZONE":[{"id":"fresh_az_A","logicalRegionId":"fresh_logical_A","logicalRegionName":"fresh_region_A"},
                  {"id":"fresh_az_B","logicalRegionId":"fresh_logical_B","logicalRegionName":"fresh_region_B"}],
         "MIDDLEWARE":[{"id":"fresh_mw_A","logicalRegionId":"fresh_logical_A"},
                       {"id":"fresh_mw_B","logicalRegionId":"fresh_logical_B"}]}
def capture(e,execution_id="independent_execution",snapshot_id="test_fixture_source_revision",size=2):
 c={"execution_id":execution_id,"snapshot_id":snapshot_id,"reads":{}}
 for ci,fields in m.FIELDS.items():
  records=copy.deepcopy(e[ci]);n=len(records);count=(n+size-1)//size
  request={"method":"GET","ci":ci,"endpoint":"instances","constraints":[]}
  pages=[]
  for pn in range(1,max(1,count)+1):
   pages.append({"http_status":200,"snapshot_id":snapshot_id,"request_page":pn,
    "request":dict(request,pageNo=pn,pageSize=size),
    "body":{"objList":records[(pn-1)*size:pn*size],"totalNum":n,
            "totalPageNo":count,"pageSize":size,"currentPage":pn}})
  c["reads"][ci]={"request":request,"schema":list(fields),"pages":pages}
 return c
def invoke(c,region="fresh_region_A",template=None,execution_id="independent_execution"):
 diag={}
 bound=m.make_region_count_binder(lambda eid:copy.deepcopy(c))(template or T,{"logicalRegionName":region},execution_id,diag)
 return bound,diag
def actual(e,region):
 return {"AZONE":[r for r in e["AZONE"] if r["logicalRegionName"]==region],"MIDDLEWARE":e["MIDDLEWARE"]}
scenarios=[("new_complete_consistent_namespace",fixture(),"fresh_region_A")]
e=fixture();e["MIDDLEWARE"].append({"id":"fresh_added_mw","logicalRegionId":"fresh_logical_A"})
scenarios.append(("new_middleware_entity_in_existing_logical_region",e,"fresh_region_A"))
e=fixture();e["AZONE"].append({"id":"fresh_added_az","logicalRegionId":"fresh_logical_A","logicalRegionName":"fresh_region_A"})
scenarios.append(("new_AZ_entity_same_valid_mapping",e,"fresh_region_A"))
e=fixture();e["AZONE"].append({"id":"fresh_az_C","logicalRegionId":"fresh_logical_C","logicalRegionName":"fresh_region_C"})
e["MIDDLEWARE"].append({"id":"fresh_mw_C","logicalRegionId":"fresh_logical_C"})
scenarios.append(("new_legal_region_with_matching_entity",e,"fresh_region_C"))
e=fixture();e["MIDDLEWARE"]=[]
scenarios.append(("complete_true_empty_middleware_known_directory",e,"fresh_region_A"))
e=fixture()
for ci in e:
 for row in e[ci]:row["logicalRegionId"]="renamed_"+row["logicalRegionId"]
scenarios.append(("consistent_logical_ID_entity_replacement",e,"fresh_region_A"))
proofs=[]
for i,(name,e,region) in enumerate(scenarios):
 sid="fixture_revision_"+str(i);c=capture(e,snapshot_id=sid);bound,diag=invoke(c,region)
 accepted=bound is not None;proof=bound["_namespace_execution_requirement"] if accepted else {}
 checked=m.check_execution_namespace(bound,"independent_execution",sid,actual(e,region)) if accepted else None
 positive.append({"name":name,"accepted":accepted,"actual_current_namespace_inputs_checked":checked is True,
                  "count_validated":proof.get("count_data_validated"),"reason":diag.get("reason")})
 check(name,accepted and checked is True and proof.get("count_data_validated") is False,diag)
 if accepted:
  proofs.append(proof["global_projection_sha256"])
  check(name+"_all_three_API_scope_values",[x["condition"]["constraint"][0]["simple"]["value"] for x in bound["api_call"] if "condition" in x]==[region]*3)
  check(name+"_no_automatic_COUNT_marker",bound.get("_closed_independent_count") is not True)
check("fresh_accepted_inputs_produce_different_dynamic_digests",len({json.dumps(p,sort_keys=True) for p in proofs})==6)
check("exact_source_template_positive",m._exact_template_contract(T))
for i in range(4):
 t=copy.deepcopy(T);t["api_call"][i]["method"]="POST"
 b,d=invoke(capture(fixture()),template=t)
 check("POST_drift_"+str(i)+"_rejected",b is None and d.get("reason")=="template_contract_or_fingerprint_mismatch")
t=copy.deepcopy(T);t["sql"]="SELECT 1,2,3"
b,d=invoke(capture(fixture()),template=t)
check("SQL_drift_rejected",b is None and d.get("reason")=="template_contract_or_fingerprint_mismatch")
for label,mut,wanted in [
 ("same_ID_two_names",lambda e:e["AZONE"][1].update(logicalRegionId="fresh_logical_A"),"global_id_has_multiple_names"),
 ("same_name_two_IDs",lambda e:e["AZONE"][1].update(logicalRegionName="fresh_region_A"),"global_name_has_multiple_ids"),
 ("orphan_MW",lambda e:e["MIDDLEWARE"][0].update(logicalRegionId="missing"),"unresolved_global_middleware_region_id")]:
 e=fixture();mut(e);b,d=invoke(capture(e))
 check(label,b is None and d.get("reason")==wanted,d)
b,d=invoke(capture(fixture()),"unseen_requested_region")
check("unknown_requested_region_rejected",b is None and d.get("reason")=="requested_region_not_in_current_namespace")
for val in [None,{},[],{"complete":True,"verified":True}]:
 try:m.make_region_count_binder(val)
 except ValueError:check("noncallable_source_rejected_"+str(len(checks)),True)
 else:check("noncallable_source_rejected_"+str(len(checks)),False)
for supplied in [{},{"complete":True,"verified":True},
 {"execution_id":"independent_execution","snapshot_id":"invented","complete":True,"verified":True}]:
 b,d=invoke(supplied);check("bare_flags_not_a_capture_"+str(len(checks)),b is None,d)
def unavailable(_):raise RuntimeError("synthetic capture unavailable")
d={};b=m.make_region_count_binder(unavailable)(T,{"logicalRegionName":"fresh_region_A"},"independent_execution",d)
check("trusted_reader_failure_is_unavailable",b is None and d.get("reason")=="trusted_B_capture_unavailable")
mods=[
 ("partial_MW_last_page",lambda c:c["reads"]["MIDDLEWARE"]["pages"].pop(),"incomplete_namespace_pages"),
 ("missing_objList",lambda c:c["reads"]["MIDDLEWARE"]["pages"][0]["body"].pop("objList"),"namespace_objList_missing"),
 ("HTTP_failure",lambda c:c["reads"]["AZONE"]["pages"][0].update(http_status=503),"namespace_HTTP_failure"),
 ("filtered_global_directory",lambda c:c["reads"]["AZONE"]["request"].update(constraints=[{"field":"logicalRegionName","value":"fresh_region_A"}]),"global_unfiltered_CI_request_required"),
 ("schema_missing_region",lambda c:c["reads"]["MIDDLEWARE"].update(schema=["id"]),"required_namespace_schema_unavailable"),
 ("source_snapshot_drift",lambda c:c["reads"]["MIDDLEWARE"]["pages"][0].update(snapshot_id="different_revision"),"source_snapshot_drift"),
 ("source_version_absent",lambda c:c.pop("snapshot_id"),"trusted_source_snapshot_required"),
 ("request_scope_drift",lambda c:c["reads"]["MIDDLEWARE"]["pages"][0]["request"].update(constraints=[{"unexpected":"filter"}]),"namespace_page_request_scope_drift"),
 ("page_number_replay",lambda c:c["reads"]["MIDDLEWARE"]["pages"][1].update(request_page=1),"duplicate_missing_or_out_of_order_page"),
 ("total_drift",lambda c:c["reads"]["MIDDLEWARE"]["pages"][1]["body"].update(totalNum=5,totalPageNo=3),"namespace_page_total_drift"),
]
e=fixture();e["MIDDLEWARE"] += [{"id":"extra_"+str(i),"logicalRegionId":"fresh_logical_A"} for i in range(2)]
for name,mut,wanted in mods:
 c=capture(e);mut(c);b,d=invoke(c)
 check(name,b is None and d.get("reason")==wanted,d)
c=capture(fixture());bound,_=invoke(c);tables=actual(fixture(),"fresh_region_A")
for name,eid,sid,mut in [
 ("wrong_execution","old_execution",c["snapshot_id"],lambda t:None),
 ("wrong_source_revision","independent_execution","old_source",lambda t:None),
 ("MW_input_added","independent_execution",c["snapshot_id"],lambda t:t["MIDDLEWARE"].append({"id":"new_exec_mw","logicalRegionId":"fresh_logical_A"})),
 ("AZ_input_other_scope","independent_execution",c["snapshot_id"],lambda t:t["AZONE"].append({"id":"wrong_scope","logicalRegionId":"fresh_logical_B","logicalRegionName":"fresh_region_B"})),
]:
 t=copy.deepcopy(tables);mut(t);d={}
 result=m.check_execution_namespace(bound,eid,sid,t,d)
 check("execution_binding_"+name,result is None,d)
source=P.read_text()
tree=ast.parse(source)
imported=[n.module for n in tree.body if isinstance(n,ast.ImportFrom)]
assigned={t.id for n in tree.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}
check("no_fixed_namespace_hash_or_R2_pin_dependency","GLOBAL_NAMESPACE_SHA256" not in assigned and "NAMESPACE_PIN" not in source and not imported)
after={str(p):sha(p) for p in paths}
check("candidate_sources_unchanged",before==after)
summary={"status":"INDEPENDENT_R3_A_BOUNDARY_PASS_B_TRUSTED_CAPTURE_AND_TYPED_COUNT_PENDING",
 "module_sha256":sha(P),"checks":checks,"passed":sum(x["passed"] for x in checks),"failed":sum(not x["passed"] for x in checks),
 "R2_six_valid_inputs":positive,"valid_new_inputs_accepted":sum(x["accepted"] for x in positive),
 "source_hashes":before,"sources_unchanged":before==after,
 "trust_boundary":"Only B trusted host configures capture reader from controlled actual requests/pages/source isolation; callable/JSON/snapshot label alone cannot authenticate provenance.",
 "remaining":["B actual trusted capture and source isolation provider absent","B must call current execution input check before typed SQL","GaussDB/OBS actual data and typed COUNT empty/failure gates remain unvalidated","139 dedicated-volume evidence remains missing"],
 "boundaries":{"synthetic_only":True,"owner_93_suite_run":False,"native_records_read":False,"model_requests":0,"business_service_requests":0,"B_runtime_calls":0,"official_executor_calls":0,"scorer_calls":0,"sealed_or_full200_feedback_read":False,"candidate_modified":False}}
(out/"R3_RESULTS.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:summary[k] for k in ["status","module_sha256","passed","failed","valid_new_inputs_accepted","sources_unchanged"]},ensure_ascii=False,indent=2))


assert summary["passed"]==53 and summary["failed"]==0, "R3 synthetic replay failed"
