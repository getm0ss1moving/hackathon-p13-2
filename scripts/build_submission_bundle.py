"""打包当前运行时及固定来源依赖；不带密钥、题集、参考答案、数据或本地环境。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'implementation'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    from runbook_matcher import _verify_a132_sources
    from runbook_issue3 import source_files
    from runbook_issue4 import sources
    from runbook_bootable_native import sources as bootable_sources
    from runbook_cluster_rank_details import sources as cluster_sources
    paths={str(p.relative_to(ROOT)) for p in (ROOT/'implementation').glob('*.py')}
    paths.update(_verify_a132_sources()[1]);paths.update(source_files());paths.update(sources()[1])
    paths.update(bootable_sources()[1]);paths.update(cluster_sources()[1])
    paths.update(['configs/whitebox200_a132.env','requirements.txt','requirements.in','背景知识.md',
                  'scripts/check_submission.py','docs/SUBMISSION_README.md'])
    # 官方评估入口由评测机提供用例后直接运行；包内不带任何题目或参考答案。
    stage=out/'submission';stage.mkdir();files={}
    for name in sorted(paths):
        src=ROOT/name
        if (src.is_symlink() or not src.resolve().is_relative_to(ROOT) or not src.is_file()
                or name.startswith(('datasets/','reports/','output-server/')) or src.name.startswith('.env')):
            raise ValueError('not_a_runtime_asset:'+name)
        raw=src.read_bytes()
        if re.search(rb'sk-[a-zA-Z0-9]{20,}',raw):raise ValueError('possible_credential_in_asset:'+name)
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        files[name]=hashlib.sha256(raw).hexdigest()
    (stage/'README.md').write_bytes((stage/'docs/SUBMISSION_README.md').read_bytes())
    files['README.md']=hashlib.sha256((stage/'README.md').read_bytes()).hexdigest()
    manifest={'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'variant':'132-strict-r5-B-submission-v2-console-recovery-address-isolated','files':files,'contains_credentials':False,
        'source_identity':'base_commit plus exact archived file hashes; working-tree bytes are authoritative',
        'git_worktree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        'address_membership_default_enabled':False,
        'contains_reference_cases':False,'new_full200_score':None,'status':'candidate_for_evaluation_machine_smoke'}
    (stage/'SUBMISSION_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=out/'submission.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(stage.rglob('*')):
            if path.is_file():z.write(path,'submission/'+str(path.relative_to(stage)))
    result={'zip':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'bytes':archive.stat().st_size,'runtime_files':len(files),'model_requests':0}
    (out/'BUILD_RECEIPT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':raise SystemExit(main())
