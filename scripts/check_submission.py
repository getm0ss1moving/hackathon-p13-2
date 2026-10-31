"""提交包解压后检查：默认完全离线，--server只读本地服务，不调用模型。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'implementation'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--server',action='store_true')
    args=parser.parse_args();report={'model_requests':0,'server_checked':args.server,'errors':[]}
    try:
        if sys.version_info<(3,10):raise ValueError('Python >=3.10 required; recommend3.11')
        manifest=json.loads((ROOT/'SUBMISSION_MANIFEST.json').read_text())
        for name,digest in manifest['files'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('package_file_drift:'+name)
        import runbook_system
        import runbook_matcher as matcher
        from runbook_items import RUNBOOK_ITEMS
        from runbook_retriever import RunbookRetriever
        _,_,variant=matcher._verify_a132_sources()
        from runbook_issue3 import source_files
        source_files()
        from runbook_issue4 import sources
        sources()
        from runbook_bootable_native import sources as bootable_sources
        bootable_sources()
        from runbook_cluster_rank_details import sources as cluster_sources
        cluster_sources()
        with sqlite3.connect(':memory:') as conn:conn.execute('SELECT json_array(1)').fetchone()
        retriever=RunbookRetriever(RUNBOOK_ITEMS)
        report.update(python=sys.version.split()[0],template_count=len(RUNBOOK_ITEMS),retriever=variant,
            indexed=True,package_files=len(manifest['files']),API_key_configured=bool(os.environ.get('DEEPSEEK_API_KEY')),
            model=os.environ.get('DEEPSEEK_MODEL'),thinking=os.environ.get('RUNBOOK_THINKING_MODE'),
            json_copy_mode=os.environ.get('RUNBOOK_JSON_COPY_MODE','standard'),
            address_membership_enabled=os.environ.get('RUNBOOK_ISSUE4_ADDRESS','0')=='1')
        if args.server:
            from runbook_issue3 import NativeReader,_local_readonly_identity
            diagnostics={};reader=NativeReader(diagnostics,max_http=2)
            try:reader.schema('VM_NOVA');report['native_source_identity']=_local_readonly_identity(reader.base)
            finally:reader.close()
    except Exception as error:report['errors'].append({'type':type(error).__name__,'message':str(error)})
    report['status']='passed' if not report['errors'] else 'failed'
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
