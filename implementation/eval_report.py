"""原评估入口的可选 JSONL 记录；不参与查询或评分。"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


class EvaluationReport:
    def __init__(self, path, test_file, planned):
        self.path = Path(path) if path else None
        self.test_file = Path(test_file)
        self.planned = planned
        self.handle = None
        self.count = 0
        self.score = 0
        self.finished = False
        self.stop_reason = '评估提前结束'

    def _write(self, record):
        if self.handle is None:
            return
        text = json.dumps(record, ensure_ascii=False)
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if key:
            text = text.replace(key, '[REDACTED]')
        self.handle.write(text + '\n')
        self.handle.flush()

    def __enter__(self):
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open('x', encoding='utf-8', newline='\n')
            try:
                implementation = Path(__file__).resolve().parent
                self._write({'type': 'run', 'planned_cases': self.planned,
                             'started_at': datetime.now(timezone.utc).isoformat(),
                             'case_file': self.test_file.name,
                             'case_file_sha256': hashlib.sha256(self.test_file.read_bytes()).hexdigest(),
                             'implementation_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                       for p in sorted(implementation.glob('*.py'))}})
            except BaseException:
                self.handle.close()
                raise
        return self

    def record(self, case, output, evaluation, elapsed):
        # 在原 query 计时和原评分完成后写盘，不改变评分输入。
        self._write({'type': 'case', 'case_id': case['case_id'], 'question': case['question'],
                     'elapsed_seconds': elapsed, 'evaluation': evaluation,
                     'output': {k: (output or {}).get(k) for k in
                                ('matched_runbook', 'api_call', 'sql', 'result', 'error')}})
        self.count += 1
        self.score += evaluation['score']

    def complete(self):
        self._write({'type': 'summary', 'status': 'complete', 'completed_cases': self.count,
                     'total_score': self.score, 'max_score': self.count * 5})
        self.finished = True

    def __exit__(self, error_type, error, traceback):
        if self.handle is not None:
            try:
                if not self.finished:
                    self._write({'type': 'summary', 'status': 'incomplete',
                                 'completed_cases': self.count, 'total_score': self.score,
                                 'max_score': self.count * 5,
                                 'stop_reason': error_type.__name__ if error_type else self.stop_reason})
            finally:
                self.handle.close()
