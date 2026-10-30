"""Build170 attribute-index overlay privately; no B/executor/model/service changes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import pprint
import shutil
import subprocess

PINS={
    'templates':'804a1626669ae24bab860b282e465113241dceee09d567f6d12866bb37a09de0',
    'metadata':'ebcb5200636ae189455336199957a432ae6ffef39781b485ff17d3397be96ec5',
    'retriever':'8fd12b7556bdcf89a10f9d408d9c8473e04a48bcd4bd3bd89bc06c8aaec856cc',
    'patch':'7d52e65f9ae4d4e115aea6b229c46a938246d9787afc711486e5e0621ffe9ecf',
}
NEW_ITEMS='f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c'
NEW_ENGINE='befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--templates',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True)
    parser.add_argument('--retriever',type=Path,required=True)
    parser.add_argument('--patch',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Fresh private directory required; never overwrite evidence')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,digest in PINS.items():
        if sha(getattr(args,name))!=digest:parser.error('Frozen input changed: '+name)
    original=json.loads(args.templates.read_text());overlay=json.loads(args.metadata.read_text())
    assert len(original)==len({item['id'] for item in original})==170
    assert set(overlay)=={'family_f02','family_f19'}
    candidate=copy.deepcopy(original);contracts=[]
    for item in candidate:
        if item['id'] not in overlay:continue
        metadata=overlay[item['id']]
        assert set(metadata)=={'resource_terms','views'}
        assert isinstance(metadata['resource_terms'],str) and all(isinstance(v,dict) and set(v)=={'output','filters'} for v in metadata['views'])
        extracted=[]
        for view in metadata['views']:
            for fields in view['filters'].split('|'):
                extracted.append((tuple(view['output'].split()),frozenset(fields.split())))
        expected=[(tuple(profile['projection']),frozenset(profile['filters'])) for profile in item['parameter_contract']['profiles']]
        assert sorted(extracted,key=str)==sorted(expected,key=str)
        contracts+=extracted
        assert 'retrieval_attributes' not in item
        item['retrieval_attributes']=copy.deepcopy(metadata)
    assert len(contracts)==11
    assert [{k:v for k,v in item.items() if k!='retrieval_attributes'} for item in candidate]==original
    payload=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode()
    assert hashlib.sha256(payload).hexdigest()==NEW_ITEMS
    target=args.output.resolve();runtime=target/'candidate170/implementation';runtime.mkdir(parents=True)
    shutil.copy2(args.retriever,runtime/'runbook_retriever.py')
    patch_targets=[line for line in args.patch.read_text().splitlines() if line.startswith(('--- ','+++ '))]
    assert patch_targets==['--- a/implementation/runbook_retriever.py','+++ b/implementation/runbook_retriever.py']
    actions=[]
    for command in [['apply','--check',str(args.patch.resolve())],['apply',str(args.patch.resolve())]]:
        result=subprocess.run(['git',*command],cwd=target/'candidate170',capture_output=True,text=True)
        actions.append({'operation':'check' if '--check' in command else 'apply','exit_code':result.returncode,'error':result.stderr})
        if result.returncode:raise RuntimeError(result.stderr)
    assert sha(runtime/'runbook_retriever.py')==NEW_ENGINE
    compile((runtime/'runbook_retriever.py').read_bytes(),'runbook_retriever.py','exec')
    (target/'templates170.attributes.private.json').write_bytes(payload)
    (runtime/'runbook_items.py').write_text('# Isolated170 with text-only attribute index; B adaptation is separate.\nRUNBOOK_ITEMS = '+pprint.pformat(candidate,width=120,sort_dicts=False)+'\n')
    def depth(value):
        if not isinstance(value,(dict,list)):return 0
        return 1+max((depth(v) for v in (value.values() if isinstance(value,dict) else value)),default=0)
    report={'status':'BUILT_PRIVATE170_ATTRIBUTE_CANDIDATE_NOT_PRODUCTION','active_templates':170,
        'source_templates_sha256':PINS['templates'],'candidate_templates_sha256':NEW_ITEMS,
        'source_retriever_sha256':PINS['retriever'],'candidate_retriever_sha256':NEW_ENGINE,
        'attribute_metadata_sha256':PINS['metadata'],'attribute_text_profiles':11,
        'existing_fields_API_SQL_unchanged':True,'patch_replay':actions,
        'max_compact_template_bytes':max(len(json.dumps(item,ensure_ascii=False,separators=(',',':')).encode()) for item in candidate),
        'max_template_container_depth':max(map(depth,candidate)),'outer_container_depth':depth(candidate),
        'model_calls':0,'service_calls':0,'B_copied_or_patched':False,'Git_index_or_commits_modified':False,
        'private_expansion_warning':'Contains inherited source entities; publish source references and overlay only.'}
    (target/'BUILD_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
