"""Stage166->164->160 privately. Equivalence is separate from business correctness."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import shutil
import sys

PINS={'base166':'8c89e4fe8b8ed7ffecd8292120f7fdc46ea24e74a5efea43cdf729ada4f936f7',
      'single':'af55eb71053b1d4498bea4d727a2457a8d47a6a96cb7ad62b582e23ed12ff3a0',
      'count':'4ef8394caa370df046a7a18e890ca72f67c1c9aaf14449f78eda6f74779162d0',
      'retriever':'befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24'}
MEMBERS_SINGLE={'family_f10':['rb_056','rb_057'],'family_f17_safe':['rb_096','rb_104']}
MEMBERS_COUNT={'family_next_n28':['rb_046','rb_047','rb_070','rb_109','rb_120']}


def load_engine(path):
    spec=importlib.util.spec_from_file_location('_staged160_engine',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module.RunbookRetriever


def make_stage(original,families,members,cls):
    by_id={i['id']:i for i in original};replacements={old:new for new,ids in members.items() for old in ids}
    assert set(replacements)<=by_id.keys() and not set(members)&by_id.keys()
    family_by={i['id']:copy.deepcopy(i) for i in families};assert set(family_by)==set(members)
    before=cls(original);raw_order=list(dict.fromkeys(d.item_id for d in before._docs))
    assert len(raw_order)==200
    for owner,ids in members.items():
        views=[]
        for old_id in ids:
            old=by_id[old_id];assert not old.get('retrieval_views') and not old.get('retrieval_aliases')
            pos=raw_order.index(old_id)
            view={'id':old_id,'after_id':raw_order[pos-1] if pos else None,'description':old.get('description',''),'examples':old.get('examples',[])}
            if view['description'] and view['examples']==[view['description']]:view.update(examples=[],description_repeat=2)
            views.append(view)
        family_by[owner]['retrieval_views']=views
    candidate=[];placed=set()
    for item in original:
        owner=replacements.get(item['id'])
        if owner:
            if owner not in placed:candidate.append(family_by[owner]);placed.add(owner)
        else:candidate.append(copy.deepcopy(item))
    assert [i for i in candidate if i['id'] not in members]==[i for i in original if i['id'] not in replacements]
    after=cls(candidate)
    assert [(d.item_id,d.tokens) for d in before._docs]==[(d.item_id,d.tokens) for d in after._docs]
    assert (before._df,before._idf,before._tau,before._avg_len,before._doc_tfs,before._attribute_records)==(after._df,after._idf,after._tau,after._avg_len,after._doc_tfs,after._attribute_records)
    return candidate,replacements


def depth(value):
    if not isinstance(value,(dict,list)):return 0
    return 1+max((depth(v) for v in (value.values() if isinstance(value,dict) else value)),default=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in PINS:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if args.output.exists():parser.error('Fresh private output only; do not overwrite170 or earlier evidence')
    for name,digest in PINS.items():assert sha(getattr(args,name))==digest,name
    original=json.loads(args.base166.read_text());single=json.loads(args.single.read_text());count=[json.loads(args.count.read_text())]
    assert len(original)==len({i['id'] for i in original})==166
    assert not set(sum(MEMBERS_SINGLE.values(),[]))&set(sum(MEMBERS_COUNT.values(),[]))
    cls=load_engine(args.retriever)
    candidate164,map164=make_stage(original,single,MEMBERS_SINGLE,cls)
    candidate160,map160=make_stage(candidate164,count,MEMBERS_COUNT,cls)
    target=args.output.resolve();target.mkdir()
    reports={}
    for n,items,replacements in [(164,candidate164,map164),(160,candidate160,map160)]:
        assert len(items)==len({i['id'] for i in items})==n
        payload=(json.dumps(items,ensure_ascii=False,indent=2)+'\n').encode();path=target/('templates'+str(n)+'.private.json');path.write_bytes(payload)
        runtime=target/('candidate'+str(n))/'implementation';runtime.mkdir(parents=True)
        (runtime/'runbook_items.py').write_text('# Private staged candidate; count business gate is not passed.\nRUNBOOK_ITEMS = '+pprint.pformat(items,width=120,sort_dicts=False)+'\n')
        shutil.copy2(args.retriever,runtime/'runbook_retriever.py')
        reports[str(n)]={'active_templates':n,'sha256':hashlib.sha256(payload).hexdigest(),'replaced_IDs':replacements,'nonmembers_unchanged_from_previous_stage':166-4 if n==164 else 164-5,
            'max_compact_item_bytes':max(len(json.dumps(i,ensure_ascii=False,separators=(',',':')).encode()) for i in items),'max_container_depth':max(map(depth,items)),'outer_container_depth':depth(items),
            'primary_documents':400,'attribute_documents':11,'original_profiles':200}
    report={'status':'STAGED164_160_EQUIVALENCE_CANDIDATES_BUSINESS_NOT_PASSED','source166_sha256':PINS['base166'],'retriever_sha256':PINS['retriever'],'stages':reports,
        'business_correctness_passed':False,'known_count_blockers':['fixed SDK empty COUNT may return1','missing-column branch can clear UNION result','success-empty and failed/missing objList not reliably distinguishable'],
        'B_adapter_installed':False,'production_modified':False,'Git_publication':False,'model_calls':0,'service_calls':0}
    (target/'BUILD_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
