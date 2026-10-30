"""仅补本地路径中断后尚无模型流量的验证后缀，不重跑已完成题或自动重试。"""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remaining_validation(root, parent, full_cases):
    root, parent = Path(root).resolve(), Path(parent).resolve()
    if not parent.is_relative_to(root):
        raise ValueError('续跑父记录必须位于本仓库')
    plan = json.loads((parent/'plan.json').read_text())
    budget = json.loads((parent/'budget.json').read_text())
    trace = [json.loads(line) for line in (parent/'live.jsonl').read_text().splitlines()]
    records = [row for row in trace if row.get('type') == 'case']
    requests = [row for row in trace if row.get('type') == 'request']
    summary = trace[-1]
    ids = [row['case_id'] for row in full_cases]
    if (plan.get('scope') != 'sealed50_validation' or plan.get('case_ids') != ids
            or len(ids) != 50 or summary.get('status') != 'incomplete'
            or not 0 < len(records) < 50 or summary.get('completed_cases') != len(records)
            or [row['case_id'] for row in records] != ids[:len(records)]
            or records != json.loads((parent/'case_results.json').read_text())):
        raise ValueError('父记录不是固定50的完整已记录前缀')
    errors = [row for row in trace if row.get('type') == 'run_error']
    completed = set(ids[:len(records)])
    if (len(errors) != 1 or errors[0].get('error_type') != 'FileNotFoundError'
            or any(row.get('status') != 'ok' or row.get('case_id') not in completed for row in requests)):
        raise ValueError('仅允许本地文件中断且未完成题无模型流量的后缀续跑')
    if (budget.get('status') != 'closed' or budget.get('used') != len(requests)
            or budget.get('plan_sha256') != sha(parent/'plan.json')
            or budget.get('trace_sha256') != sha(parent/'live.jsonl')):
        raise ValueError('父运行预算或日志来源不符')
    # 路径迁移可改变绝对位置；查询实现、候选包和数据必须原字节一致。
    runner_only = {'scripts/train_live.py', 'scripts/run_saved_training.py'}
    for name, expected in plan['source_sha256'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or name not in runner_only and sha(path) != expected:
            raise ValueError('父运行查询源码或数据变化：'+name)
    files = {str((parent/name).relative_to(root)): sha(parent/name)
             for name in ['plan.json','budget.json','live.jsonl','case_results.json','summary.json']}
    evidence = {'path': str(parent.relative_to(root)), 'completed_prefix': len(records),
                'parent_requests': len(requests), 'parent_budget_closed': True,
                'query_sources_unchanged': True, 'manual_retry': False,
                'old_runtime_root': str(Path(plan['runtime_source_paths']['runbook_matcher']).parent.parent),
                'current_runtime_root': str(root), 'files_sha256': files}
    return full_cases[len(records):], evidence
