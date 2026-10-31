"""直接导入评测入口时也采用已验收的132配置；显式环境变量优先。"""
import os
from pathlib import Path
import shlex


def apply_defaults():
    config=Path(__file__).resolve().parents[1]/'configs/whitebox200_a132.env'
    for line in config.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        name,separator,value=line.partition('=')
        if not separator:raise ValueError('invalid_public_runtime_config')
        if name=='RUNBOOK_MAX_LLM_CALLS':continue  # 开发450上限不能截断评测机的完整任务。
        parts=shlex.split(value,comments=True)
        if len(parts)!=1:raise ValueError('invalid_public_runtime_config_value')
        os.environ.setdefault(name,parts[0])
