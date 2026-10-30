#!/usr/bin/env python3
"""Reproduce delta only in a NEW private output tree, never patch B in place."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'experiments/a_retriever_r5_increment_20261030'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=['strict','enhanced'],default='strict')
    p.add_argument('--base-module',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    manifest=json.loads((ROOT/'MANIFEST.json').read_text())
    for relative,expected in manifest['files'].items():
        if sha(ROOT/relative)!=expected:raise ValueError('delivery fingerprint changed: '+relative)
    for relative,expected in (manifest['tools']|manifest['external_files']).items():
        if sha(REPO/relative)!=expected:raise ValueError('tool/document fingerprint changed: '+relative)
    record=json.loads((ROOT/'INCREMENT_INTERFACE.json').read_text())['variants'][a.variant]
    source=a.base_module.resolve();out=a.output.resolve()
    if out.exists() or source.is_relative_to(out) or REPO.is_relative_to(out) or out.is_relative_to(REPO):
        raise ValueError('output must be a fresh private directory outside this package; no overwrite')
    if sha(source)!=record['r4_module_sha256']:raise ValueError('wrong r4 base; stop rather than force')
    patch=ROOT/record['patch']
    if sha(patch)!=record['patch_sha256']:raise ValueError('patch fingerprint changed')
    target=out/'implementation/runbook_retriever.py';target.parent.mkdir(parents=True);shutil.copyfile(source,target)
    # git apply works on files without a Git repo; no stage/commit/ref/push is used.
    for command in [['git','apply','--check',str(patch)],['git','apply',str(patch)]]:
        subprocess.run(command,cwd=out,check=True,capture_output=True,text=True)
    if sha(target)!=record['r5_module_sha256']:raise ValueError('result differs from accepted module')
    if sha(source)!=record['r4_module_sha256']:raise ValueError('source unexpectedly changed')
    receipt={'variant':a.variant,'r4_sha256':sha(source),'r5_sha256':sha(target),'patch_sha256':sha(patch),'source_unchanged':True,
             'scope':'patch reproducibility only; no retrieval/model/API/SQL test or B activation'}
    (out/'REPRODUCTION_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
if __name__=='__main__':main()
