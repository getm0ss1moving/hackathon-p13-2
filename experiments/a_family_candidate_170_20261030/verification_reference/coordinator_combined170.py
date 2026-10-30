"""Independent fixed170 attribute gate; no new model/service/full200 cases."""
import ast
import dataclasses
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import tracemalloc
import sys

ROOT=Path(__file__).resolve().parent
F=ROOT/'frozen'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def owner_map(items):
    result={item['id']:item['id'] for item in items}
    for item in items:
        for view in item.get('retrieval_views',[])+item.get('retrieval_aliases',[]):
            assert view['id'] not in result or result[view['id']]==item['id']
            result[view['id']]=item['id']
    return {k:v for k,v in result.items() if k.startswith('rb_')}


def main():
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    old_items=json.loads((F/'base170.private.json').read_text())
    new_items=json.loads((ROOT/'private_170/templates170.attributes.private.json').read_text())
    assert sha(ROOT/'private_170/templates170.attributes.private.json')=='f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c'
    assert [{k:v for k,v in item.items() if k!='retrieval_attributes'} for item in new_items]==old_items
    assert len(new_items)==len({x['id'] for x in new_items})==170
    old_engine=load('_combined170_original_engine',F/'base_runbook_retriever.py')
    new_engine=load('_combined170_attribute_engine',ROOT/'private_170/candidate170/implementation/runbook_retriever.py')
    a=old_engine.RunbookRetriever(json.loads((F/'base179.private.json').read_text()))
    b=old_engine.RunbookRetriever(old_items);c=new_engine.RunbookRetriever(new_items)
    base198=old_engine.RunbookRetriever(json.loads((F/'base198.private.json').read_text()))
    assert [(d.item_id,d.tokens) for d in b._docs]==[(d.item_id,d.tokens) for d in c._docs]
    assert (b._df,b._idf,b._tau,b._avg_len,b._doc_tfs)==(c._df,c._idf,c._tau,c._avg_len,c._doc_tfs)
    assert c._doc_count==400 and c._attribute_index._doc_count==11
    assert [(f.name,str(f.type)) for f in dataclasses.fields(old_engine.Candidate)]==[(f.name,str(f.type)) for f in dataclasses.fields(new_engine.Candidate)]
    original_owners=owner_map(old_items);new_owners=owner_map(new_items)
    assert original_owners==new_owners and len(new_owners)==200
    assert new_owners['rb_054']=='rb_052' and new_owners['rb_087']=='family_f14'
    # Prove the old BM25 query path is unchanged, rather than trusting examples.
    def methods(path):
        tree=ast.parse(path.read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RunbookRetriever')
        return {n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)},tree
    old_methods,old_tree=methods(F/'base_runbook_retriever.py')
    new_methods,new_tree=methods(ROOT/'private_170/candidate170/implementation/runbook_retriever.py')
    stable_methods=[]
    for name,node in old_methods.items():
        if name in {'__init__','retrieve'}:continue
        assert ast.dump(node)==ast.dump(new_methods[name]),name;stable_methods.append(name)
    assert ast.dump(ast.Module(body=old_methods['retrieve'].body,type_ignores=[]))==ast.dump(ast.Module(body=new_methods['_retrieve_primary'].body,type_ignores=[]))
    patch=(F/'attribute_retriever.patch').read_text()
    assert 'rb_' not in patch and 'family_f02' not in patch and 'family_f19' not in patch
    cases=json.loads((ROOT/'natural_language_acceptance_r4/CASES70.private.json').read_text())
    values={str(v) for case in cases if case.get('contract') for v in case['contract']['parameters']['filters'].values() if len(str(v))>3 and v!='active'}
    assert not any(value in patch for value in values)
    assert all(c._attribute_records[k]['owner'] in {'family_f02','family_f19'} for k in c._attribute_records)
    def vector(results):return [(x.id,x.tier,x.score,x.coverage) for x in results]
    members={'family_f02':['rb_006','rb_009','rb_029','rb_037','rb_038','rb_039','rb_042'],'family_f19':['rb_142','rb_145','rb_146','rb_148']}
    replacement={old:owner for owner,ids in members.items() for old in ids}
    def normalized(results):
        seen,result=set(),[]
        for x in results:
            owner=replacement.get(x.id,x.id)
            if owner not in seen:seen.add(owner);result.append((owner,x.tier,x.score,x.coverage))
        return result
    queries=json.loads((F/'inputs537.private.json').read_text());changes=[];timings={'base170':[],'attribute170':[]}
    for query in queries:
        for k in [None,1,5,10]:
            original179=a.retrieve(query['question'],k)
            start=time.perf_counter();baseline=b.retrieve(query['question'],k)
            if k is None:timings['base170'].append((time.perf_counter()-start)*1000)
            start=time.perf_counter();patched=c.retrieve(query['question'],k)
            if k is None:timings['attribute170'].append((time.perf_counter()-start)*1000)
            assert normalized(original179)==vector(baseline)
            assert all(x.id in {item['id'] for item in new_items} for x in patched)
            if vector(baseline)!=vector(patched):
                changes.append({'id':query['id'],'k':k,'attribute_owners':[x.id for x in c._attribute_candidates(query['question'])],
                                'before_ids':[x.id for x in baseline],'after_ids':[x.id for x in patched]})
    assert len(changes)==8 and {x['id'] for x in changes}=={'synthetic170-0','synthetic170-1'},changes
    assert all(x['attribute_owners']==['family_f02'] for x in changes)
    # Full46 positives: verify old198 inheritance and new default/top-k coverage.
    rows=json.loads((ROOT.parent/'combined170-batch3-offline-20261030/frozen/OLD_TO_NEW.json').read_text())['mappings']
    positive=[];negative=[]
    for case in cases:
        target='family_'+case['family_id'].lower()
        if case['expected']=='ordinary':
            p=case['contract']['parameters']
            matches=[row for row in rows if row['family_id']==case['family_id'] and row['parameters']['projection']==p['projection'] and row['parameters']['order']==p['order'] and set(row['parameters']['filters'])==set(p['filters'])]
            assert len(matches)==1
            old_id=matches[0]['old_id'];report={'id':case['id'],'kind':case['kind'],'target':target,'old198_contract':old_id,'before':{},'after':{}}
            original_ids={x.id for x in base198.retrieve(case['question'])}
            report['old198_contract_present']=old_id in original_ids
            report['old198_family_present']=bool(original_ids & set(members[target]))
            for k in [None,1,5,10]:
                report['before'][str(k)]=target in {x.id for x in b.retrieve(case['question'],k)}
                report['after'][str(k)]=target in {x.id for x in c.retrieve(case['question'],k)}
            positive.append(report)
        else:
            before={x.id for x in b.retrieve(case['question'])};after={x.id for x in c.retrieve(case['question'])}
            negative.append({'id':case['id'],'before_nonempty':bool(before),'after_nonempty':bool(after),'new_IDs':sorted(after-before),'attribute_owners':[x.id for x in c._attribute_candidates(case['question'])]})
    assert len(positive)==46 and len(negative)==24
    inherited=[x['id'] for x in positive if not x['old198_family_present']]
    exact_old_missing=[x['id'] for x in positive if not x['old198_contract_present']]
    baseline_missing=[x['id'] for x in positive if not x['before']['None']]
    assert inherited==baseline_missing==['explicit-'+str(i) for i in range(8)]
    coverage={str(k):sum(x['after'][str(k)] for x in positive) for k in [None,1,5,10]}
    assert coverage=={'None':46,'1':40,'5':44,'10':45},coverage
    assert not any(x['new_IDs'] for x in negative)
    semantic=json.loads((ROOT/'natural_language_acceptance_r4/SUMMARY70.json').read_text())
    assert semantic['status']=='PASS' and semantic['passed']==70
    # Deterministic invalid projections from every approved attribute card.
    attribute_negative=[]
    for record in c._attribute_records.values():
        output=list(record['projection']);resource=record['resource_terms'][0]
        prefix='查询'+resource+'，'+','.join(field+'="Synthetic-'+field+'"' for field in sorted(record['filters']))
        for kind,cols in [('missing_column',output[1:]),('reversed',list(reversed(output))),('unknown_column',output+['unknownColumn'])]:
            question=prefix+'，输出'+','.join(cols)
            result=c._attribute_candidates(question)
            assert not result,(kind,record)
            attribute_negative.append({'kind':kind,'attribute_owners':[]})
    assert len(attribute_negative)==33
    def traced_build(cls,items):
        gc.collect();tracemalloc.start();start=time.perf_counter();instance=cls(items)
        elapsed=(time.perf_counter()-start)*1000;current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        return {'build_ms_under_tracemalloc':elapsed,'live_python_allocated_bytes':current,'peak_python_allocated_bytes':peak}
    memory={'base170':traced_build(old_engine.RunbookRetriever,old_items),'attribute170':traced_build(new_engine.RunbookRetriever,new_items)}
    memory['live_delta_bytes']=memory['attribute170']['live_python_allocated_bytes']-memory['base170']['live_python_allocated_bytes']
    pct=lambda values,p:sorted(values)[int((len(values)-1)*p)]
    summary={'status':'PASS_FIXED170_COMBINED_LOCAL_GATE_NOT_REAL_MODEL_OR_PRODUCTION','active_templates':170,
        'source170_sha256':sha(F/'base170.private.json'),'candidate170_sha256':sha(ROOT/'private_170/templates170.attributes.private.json'),
        'base_retriever_sha256':sha(F/'base_runbook_retriever.py'),'candidate_retriever_sha256':sha(ROOT/'private_170/candidate170/implementation/runbook_retriever.py'),
        'semantic_prototype_sha256':semantic['frozen_input_fingerprints']['prototype_sha256'],
        'semantic70':{'passed':70,'false_empty':0,'false_nonempty':0,'wrong_contract':0},
        'real_positive_cases':46,'coverage_after_by_k':coverage,'original198_family_coverage':38,'original170_family_coverage':38,
        'original198_exact_contract_coverage':sum(x['old198_contract_present'] for x in positive),
        'original198_exact_contract_missing':exact_old_missing,
        'upstream_baseline_correction':'On these coordinator-frozen46, original198 family coverage is38 but exact old-contract coverage is37. paraphrase-0 has another family member only; do not conflate these metrics.',
        'inherited_explicit_gaps':inherited,'new_merge_regressions':0,'new_attribute_improvements':8,
        'original179_to_base170_exact_comparisons':2148,'attribute_full_field_exact_comparisons':2140,
        'intentional_attribute_differences':changes,'original525_all_four_k_exact':True,
        'fixed24_semantic_negatives_pass':True,'raw_negative_nonempty_before':sum(x['before_nonempty'] for x in negative),
        'raw_negative_nonempty_after':sum(x['after_nonempty'] for x in negative),'negative_new_candidate_ID_exposures':0,
        'deterministic_attribute_projection_negatives':33,'projection_negative_attribute_exposures':0,
        'primary_index_documents':400,'attribute_index_documents':11,'original200_profile_owners_and_aliases_unchanged':True,
        'primary_BM25_statistics_unchanged':True,'primary_query_body_AST_unchanged':True,'unchanged_primary_methods':stable_methods,
        'general_attribute_matching_no_old_ID_or_test_entity_dispatch_in_patch':True,
        'query_timings_ms':{name:{'samples':len(v),'p95':pct(v,.95),'p99':pct(v,.99),'max':max(v)} for name,v in timings.items()},
        'index_build_python_memory':memory,'B_full_model_selection_or_native_executor_tested':False,
        'model_calls':0,'service_calls':0,'stage2_enabled':False,'production_modified':False,'Git_publication':False,
        'limits':['The70 are exposed regression controls, not a new hidden blackbox.',
        'Default46/46 is not top5 or top10 full coverage; B must respect candidate list semantics.',
        'New attribute candidate scores come from a separate normalized text query and are not original full-question score probabilities.',
        'No native SDK, actual model, official200, sealed50 or official score measured.',
        'Container depth7/outer8 unresolved; known relation, default-value, pagination and empty-table limitations remain.']}
    out=ROOT/'acceptance';out.mkdir(exist_ok=False)
    for name,data in [('COMBINED_VALIDATION.json',summary),('DIFF2148.json',changes),('REAL46_DETAILS.json',positive),('NEGATIVE24_DETAILS.json',negative)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'intentional_attribute_differences','unchanged_primary_methods'}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
