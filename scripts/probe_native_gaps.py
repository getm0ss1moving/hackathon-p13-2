"""保存实际schema及完整原生收据，诊断合同缺口；不调用模型或评分。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'implementation'), str(ROOT/'scripts')]
import runbook_executor as executor
from runbook_issue3 import NativeReader, _local_readonly_identity
from check_official_integrity import require_official_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ci', action='append', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if len(set(args.ci)) != len(args.ci) or any(ci not in executor.CI_NAME_MAP for ci in args.ci):
        parser.error('CI须唯一且属于原执行器映射')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    execution = {}; reader = NativeReader(execution); snapshots = {}; resources = {}
    summary = {'model_requests':0, 'scoring_executed':False, 'query_result_claimed':False,
               'official_integrity':require_official_files(ROOT),
               'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        before = _local_readonly_identity(reader.base)
        for ci in args.ci:
            kind = 'relations' if ci.startswith(('R_','M_')) else 'instances'
            snap = reader.fetch({'method':'GET','url':f'/rest/hackthon/db/{kind}/{ci}?pageNo=1&pageSize=10000'})
            snapshots[ci] = snap
            rows = snap['rows']
            ids = [r.get('id') for r in rows]
            resources[ci] = {'row_count':len(rows),'schema':snap['columns'],
                             'missing_or_duplicate_id_count':len(ids)-len(set(ids)),
                             'present_fields':sorted({k for r in rows for k in r})}
        assert _local_readonly_identity(reader.base) == before, 'native service changed'
        summary.update(status='complete',resources=resources,source_snapshot=before)
    except Exception as error:
        summary.update(status='blocked',error_type=type(error).__name__,reason=str(error),resources=resources)
    finally:
        reader.close();summary['execution']=execution
        with gzip.open(args.output_dir/'actual_receipts.json.gz','wt',encoding='utf-8') as stream:
            json.dump(snapshots,stream,ensure_ascii=False)
    (args.output_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'official_integrity','execution','source_snapshot'}},ensure_ascii=False))
    return 0 if summary['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
