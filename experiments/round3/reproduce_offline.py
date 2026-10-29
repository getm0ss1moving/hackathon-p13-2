"""先验证冻结输入，再复现；共享代码变化时保护本轮结果，零模型调用。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

out = Path(__file__).resolve().parent
root = out.parents[1]
manifest = json.loads((out / 'manifest.json').read_text())
expected = {root / p: value for p, value in manifest['sha256'].items()}
expected.update({root / p: value for p, value in manifest['data_sha256'].items()})
expected.update({(root / p if p == 'CMDB用例集-白盒200.json' else out / p): value
                 for p, value in manifest['input_sha256'].items()})
changed = [str(p.relative_to(root)) for p, value in expected.items()
           if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != value]
if changed:
    print('冻结输入已变化；保留本轮结果，未执行实验：' + ', '.join(changed), file=sys.stderr)
    sys.exit(2)
sys.exit(subprocess.run([sys.executable, str(out / 'run_offline.py')], cwd=root).returncode)
