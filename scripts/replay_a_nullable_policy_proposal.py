"""仅反事实：显式声明的可空字段补NULL，验证A后续逻辑；不是原生验收或生产执行。"""
import argparse
import copy
import difflib
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['vm','capacity'],required=True)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--source-patch',action='store_true',help='执行隔离源码提案，使用未改原始收据；A源文件仍不修改')
    args=parser.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=False)
    package=ROOT/'experiments/issue3_next_capabilities_20261030';manifest=json.loads((package/'MANIFEST.json').read_text())
    for name,h in manifest['files'].items():assert hashlib.sha256((package/name).read_bytes()).hexdigest()==h,name
    capacity=args.profile=='capacity';kind='ranked_vdc_pool_http_r2' if capacity else 'vm_eip_host'
    path=package/'modules'/kind/'candidate.py';spec=importlib.util.spec_from_file_location('_B_nullable_policy_replay',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    summary=json.loads((args.input_dir/'summary.json').read_text());params=summary['parameters']
    src=args.input_dir/('raw_snapshots.json.gz' if capacity else 'raw_receipts.json.gz');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original_sha=sha(src);original=json.load(gzip.open(src,'rt'));modified=copy.deepcopy(original)
    ci,field=('VOLUME','vdcName') if capacity else ('VM_NOVA','floatingIp')
    schema=modified[ci]['columns' if capacity else 'schema'];assert field in schema,'cannot invent an undeclared field'
    changes=0
    for page in modified[ci]['pages']:
        for row in page['objList']:
            if field not in row:row[field]=None;changes+=1
    proposal_hash=None
    if args.source_patch:
        source=path.read_text();proposal=source
        if capacity:
            old="any(k not in raw for k in SCHEMA[ci])"
            new="any(k not in raw for k in set(SCHEMA[ci])-({'vdcName'} if ci=='VOLUME' else set()))"
            assert proposal.count(old)==1;proposal=proposal.replace(old,new)
            proposal=proposal.replace("raw[k] is not None and not isinstance(raw[k],str)","raw.get(k) is not None and not isinstance(raw.get(k),str)")
            proposal=proposal.replace("row={k:deepcopy(raw[k]) for k in SCHEMA[ci]}","row={k:deepcopy(raw.get(k)) for k in SCHEMA[ci]}")
            proposal=proposal.replace('volume-capacity-vdc-pool-v3-source-rechecked','volume-capacity-vdc-pool-v4-nullable-display-proposal')
        else:
            old="any(k not in raw for k in columns)"
            new="any(k not in raw for k in set(columns)-({'floatingIp'} if resource=='VM_NOVA' else set()))"
            assert proposal.count(old)==1;proposal=proposal.replace(old,new)
            proposal=proposal.replace("row={k:raw[k] for k in columns}","row={k:raw.get(k) for k in columns}")
        assert proposal!=source
        (out/'PROPOSED_SOURCE.patch').write_text(''.join(difflib.unified_diff(source.splitlines(keepends=True),proposal.splitlines(keepends=True),fromfile='a/'+str(path.relative_to(ROOT)),tofile='b/'+str(path.relative_to(ROOT)))))
        proposal_hash=hashlib.sha256(proposal.encode()).hexdigest()
        exec(compile(proposal,'<isolated_unpublished_nullable_policy_proposal>','exec'),mod.__dict__)
        modified=copy.deepcopy(original)
    report={'mode':'COUNTERFACTUAL_INPUT_TRANSFORM_NOT_NATIVE_ACCEPTANCE','model_requests':0,'production_enabled':False,
        'A_source_file_changed':False,'source_sha256':sha(path),'original_receipts_sha256':original_sha,
        'only_added_declared_nullable_field':ci+'.'+field,'changed_rows':changes,'raw_input_unchanged':True,'results':{}}
    if args.source_patch:
        report.update(mode='UNPUBLISHED_ISOLATED_SOURCE_PROPOSAL_NOT_A_RELEASE',proposal_sha256=proposal_hash,
            input_rows_modified=0,changed_rows=0,omitted_nullable_rows_handled=changes)
    def execute(data,p):
        if not capacity:
            try:
                result=mod.execute_local(p,data)
                return {'status':'counterfactual_sql_passed','row_count':len(result['rows']),'diagnostics':result['diagnostics']}
            except mod.Unsupported as error:return {'status':'blocked','reason':str(error)}
        prepared=mod.preflight(p,data)
        if prepared['status']!='ready_for_typed_sql':return prepared
        result=mod.execute_prepared(p,prepared)
        return {k:v for k,v in result.items() if k not in {'rows','columns','byte_boundaries'}}|{'row_count':len(result.get('rows',[])),
            'leaders':[{k:r[k] for k in ['vdc_id','vdc_name','known_volume_size_source_units','total_volume_size_if_complete_source_units']} for r in result.get('rows',[])]}
    policies=['reject','known_only'] if capacity else ['declared_native_view']
    for policy in policies:
        p=dict(params,unknown_owner_policy=policy,unknown_size_policy=policy) if capacity else params
        report['results'][policy]=execute(modified,p)
    if args.source_patch:
        if capacity:assert report['results']['known_only']['status']=='local_sql_ok_policy_conditional'
        else:
            result=report['results']['declared_native_view']
            assert result['status']=='counterfactual_sql_passed'
            assert result['row_count']==sum(len(p['objList']) for p in original[ci]['pages'])
    p=dict(params,unknown_owner_policy='known_only',unknown_size_policy='known_only') if capacity else params
    controls={}
    for name in ['missing_identity','HTTP503','missing_declared_schema','wrong_scope','invalid_nullable_type','duplicate_identity','missing_page']:
        data=copy.deepcopy(modified)
        if name=='missing_identity':del data[ci]['pages'][0]['objList'][0]['id']
        elif name=='HTTP503':data[ci]['http_status']=503
        elif name=='missing_declared_schema':data[ci]['columns' if capacity else 'schema'].remove(field)
        elif name=='wrong_scope':data[ci]['pages'][0]['objList'][0]['logicalRegionName' if capacity else 'tenantName']='synthetic_other_scope'
        elif name=='invalid_nullable_type':data[ci]['pages'][0]['objList'][0][field]=[]
        elif name=='duplicate_identity':data[ci]['pages'][0]['objList'][-1]=copy.deepcopy(data[ci]['pages'][0]['objList'][0])
        else:data[ci]['pages']=data[ci]['pages'][:-1]
        result=execute(data,p);controls[name]=result
        assert result['status']=='blocked',name
    report['negative_controls']=controls
    assert original==json.load(gzip.open(src,'rt')) and sha(src)==original_sha,'original input changed'
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
