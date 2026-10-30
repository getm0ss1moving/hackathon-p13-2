"""Public160 build/parser controls; no private51/70/537 fixture or SDK/model."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--templates160',type=Path,required=True)
    parser.add_argument('--retriever',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();package=Path(__file__).resolve().parent
    repo=package.parents[1];target=args.output.resolve()
    if target.exists() or target==repo or repo in target.parents:
        parser.error('Use a fresh private output outside the Git checkout')
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(args.templates160)=='477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182'
    assert sha(args.retriever)=='befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24'
    for label in ['base160','parser_r2']:
        manifest=json.loads((package/label/'MANIFEST.json').read_text())
        for name,digest in manifest['files'].items():
            assert sha(package/label/name)==digest,(label,name)
    candidate=json.loads(args.templates160.read_text())
    assert len(candidate)==len({item['id'] for item in candidate})==160
    mapping=json.loads((package/'base160/ID_MAP160.json').read_text())['original200_to160']
    assert len(mapping)==200 and set(mapping.values())=={item['id'] for item in candidate}
    index=load('_public160_engine',args.retriever).RunbookRetriever(candidate)
    assert index._doc_count==400 and index._attribute_index._doc_count==11
    assert len({document.item_id for document in index._docs})==200
    assert {'rb_054','rb_087'}<={document.item_id for document in index._docs}
    source=package/'base160/sources/single/single_table_families.py'
    patch=package/'parser_r2/ascii_atom_only.patch'
    fixed=package/'parser_r2/single_table_families.py'
    assert sha(source)=='fc71c51f346c3ebf0b09911bc030bb40c1ba0547f25cdf6bf8d75b3b8a6bb506'
    assert sha(fixed)=='04098b713541a87681e0e916f84ccb4d82644ee218a68e424587c1cd3ced6576'
    targets=[line for line in patch.read_text().splitlines() if line.startswith(('--- ','+++ '))]
    assert targets==['--- a/single_table_families.py','+++ b/single_table_families.py']
    target.mkdir(parents=True);shutil.copyfile(source,target/'single_table_families.py')
    for operation in [['apply','--check',str(patch.resolve())],['apply',str(patch.resolve())]]:
        result=subprocess.run(['git',*operation],cwd=target,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    assert sha(target/'single_table_families.py')==sha(fixed)
    old=load('_public160_old_single',source);new=load('_public160_R2_single',fixed)
    by_id={item['id']:item for item in candidate}
    rows=json.loads((package/'parser_r2/ORIGINAL4_TRANSITIONS.json').read_text())['cases']
    assert len(rows)==4
    for row in rows:
        owner=new.F10 if 'metric' in row['parsed'] else new.F17
        item=by_id[owner]
        assert old.prepare_single_table_candidate(row['question'],item,row['parsed']) is None
        ordinary=new.prepare_single_table_candidate(row['question'],item,row['parsed'])
        assert ordinary is not None
        assert ordinary['api_call']==row['api_call'] and ordinary['sql']==row['sql']
        assert new.infer_parameters(row['question'],owner)==row['parsed']
    row=rows[0];item=by_id[new.F10]
    wrong=copy.deepcopy(row['parsed']);wrong['filters']['logicalRegionName']='Different'
    boolean_k=copy.deepcopy(row['parsed']);boolean_k['top_k']=True
    negatives=[(row['question']+'，状态active',row['parsed']),
        (row['question']+' 或者区域Other',row['parsed']),
        (row['question'],wrong),(row['question'],boolean_k)]
    for question,parsed in negatives:
        assert new.prepare_single_table_candidate(question,item,parsed) is None
    fixtures=json.loads((package/'base160/evidence/SQL_COMPARISONS.json').read_text())
    assert len(fixtures)==27 and sum(bool(row.get('error')) for row in fixtures)==2
    result={'status':'PASS_PUBLIC160_BUILD_AND_R2_PARSER_CONTROLS_BUSINESS_BLOCKED',
        'active_templates_unique':160,'families':sum(bool(item.get('family_id')) for item in candidate),
        'original_profiles_and_aliases':200,'primary_documents':400,'attribute_documents':11,
        'template160_sha256':sha(args.templates160),'retriever_sha256':sha(args.retriever),
        'parser_sha256':sha(fixed),'exact_patch_replay':True,
        'public_bare_atom_controls':4,'old_None_to_new_ordinary':4,'public_negative_controls':4,
        'recorded_SQL_fixtures':27,'recorded_SQL_errors_preserved_not_success':2,
        'private51_70_41_or_full_retrieval_rerun_here':False,'COUNT_business_gate':'BLOCKED',
        'new_B_full160_integration_tested':False,'model_calls':0,'service_calls':0,
        'native_SDK_or_score_tested':False,'production_modified':False}
    (target/'PUBLIC_REPLAY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
