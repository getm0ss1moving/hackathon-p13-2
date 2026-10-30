"""Build intermediate166 from frozen170. Does not publish or install B code."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import shutil
import sys

BASE_SHA='f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c'
ENGINE_SHA='befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24'
FAMILIES_SHA='c3044d34ca585caf4e7cdfe1c00a8bf084da7ad03938cc863944dfd0e6a21196'


def load_engine(path):
    spec=importlib.util.spec_from_file_location('_intermediate166_engine',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module.RunbookRetriever


def depth(value):
    if not isinstance(value,(dict,list)):return 0
    return 1+max((depth(v) for v in (value.values() if isinstance(value,dict) else value)),default=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base170',type=Path,required=True)
    parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--retriever',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Fresh private output required; preserve evidence')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(args.base170)==BASE_SHA and sha(args.retriever)==ENGINE_SHA
    original=json.loads(args.base170.read_text());by_id={i['id']:i for i in original}
    refs=json.loads(args.references.read_text());assert refs['source170_sha256']==BASE_SHA
    families=[];members={}
    for ref in refs['families']:
        examples=[example for old_id in ref['examples_from_source_ids'] for example in by_id[old_id].get('examples',[])]
        family={key:examples if key=='examples' else ref['template_fields_without_examples'][key] for key in ref['template_key_order']}
        families.append(family);members[family['id']]=ref['examples_from_source_ids']
    reconstructed=(json.dumps(families,ensure_ascii=False,indent=2)+'\n').encode()
    assert hashlib.sha256(reconstructed).hexdigest()==FAMILIES_SHA==refs['source_candidates_sha256']
    replacement={old_id:owner for owner,ids in members.items() for old_id in ids}
    assert len(original)==len(by_id)==170 and len(replacement)==7 and len(members)==3
    assert not set(members)&by_id.keys() and set(replacement)<=by_id.keys()
    cls=load_engine(args.retriever);before=cls(original)
    raw_order=list(dict.fromkeys(d.item_id for d in before._docs));assert len(raw_order)==200
    family_by={i['id']:i for i in families}
    for family in families:
        views=[]
        for old_id in members[family['id']]:
            old=by_id[old_id];assert not old.get('retrieval_views') and not old.get('retrieval_aliases')
            index=raw_order.index(old_id)
            view={'id':old_id,'after_id':raw_order[index-1] if index else None,'description':old.get('description',''),'examples':old.get('examples',[])}
            if view['description'] and view['examples']==[view['description']]:view.update(examples=[],description_repeat=2)
            views.append(view)
        family['retrieval_views']=views
    candidate=[];placed=set()
    for item in original:
        owner=replacement.get(item['id'])
        if owner:
            if owner not in placed:candidate.append(copy.deepcopy(family_by[owner]));placed.add(owner)
        else:candidate.append(copy.deepcopy(item))
    assert len(candidate)==len({i['id'] for i in candidate})==166
    assert [i for i in candidate if i['id'] not in members]==[i for i in original if i['id'] not in replacement]
    after=cls(candidate)
    assert [(d.item_id,d.tokens) for d in before._docs]==[(d.item_id,d.tokens) for d in after._docs]
    assert (before._df,before._idf,before._tau,before._avg_len,before._doc_tfs)==(after._df,after._idf,after._tau,after._avg_len,after._doc_tfs)
    assert before._attribute_records==after._attribute_records
    target=args.output.resolve();runtime=target/'candidate166/implementation';runtime.mkdir(parents=True)
    payload=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode()
    (target/'templates166.private.json').write_bytes(payload)
    (runtime/'runbook_items.py').write_text('# Intermediate166 only; no production or B adapter installed.\nRUNBOOK_ITEMS = '+pprint.pformat(candidate,width=120,sort_dicts=False)+'\n')
    shutil.copy2(args.retriever,runtime/'runbook_retriever.py')
    report={'status':'INTERMEDIATE166_NOT_FINAL160_NOT_FOR_SEPARATE_PUBLICATION','published170_base_source_commit':'6d3b47318ce767ef947c68019a2dce522de98c7a',
        'base170_sha256':BASE_SHA,'candidate166_sha256':hashlib.sha256(payload).hexdigest(),'retriever_sha256':ENGINE_SHA,
        'active_templates':166,'nonmember_items_unchanged':163,'replaced_old_IDs':replacement,
        'primary_documents':after._doc_count,'attribute_documents':after._attribute_index._doc_count,'original_text_profiles':200,
        'primary_statistics_and_attribute_index_unchanged':True,'max_compact_item_bytes':max(len(json.dumps(i,ensure_ascii=False,separators=(',',':')).encode()) for i in candidate),
        'max_item_container_depth':max(map(depth,candidate)),'outer_container_depth':depth(candidate),
        'B_copied_or_patched':False,'model_calls':0,'service_calls':0,'Git_publication':False,
        'not_included':['056/057','096/104','extended scalar count families with unresolved emptyCOUNT semantics'],
        'private_output_warning':'Inherited source entity examples stay private; use source-reference definitions for future delivery.'}
    (target/'BUILD_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
