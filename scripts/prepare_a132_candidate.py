"""显式安装已重建的132配对，先备份当前库；不调用模型、服务或Git提交。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--variant', choices=['strict', 'enhanced'], default='strict')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    directory = args.build_dir.resolve()
    if directory == ROOT or ROOT in directory.parents:
        parser.error('使用仓库外的私有重建目录')
    source = json.loads((ROOT/'experiments/a132_runtime_port_20261030/SOURCE_MANIFEST.json').read_text())
    variant = source['variants'][args.variant]
    package = ROOT/source['package']
    if sha(package/'MANIFEST.json') != source['package_manifest_sha256']:
        parser.error('A132来源清单变化')
    manifest = json.loads((package/'MANIFEST.json').read_text())
    if any(sha(package/name) != h for name, h in manifest['files'].items()):
        parser.error('A132源码闭包变化')
    items_path = directory/f'runbook_items.{args.variant}.py'
    engine = directory/f'runbook_retriever.{args.variant}.py'
    array = directory/f'templates132.{args.variant}.private.json'
    if (sha(items_path) != variant['runtime_hashes']['implementation/runbook_items.py']
            or sha(engine) != variant['runtime_hashes']['implementation/runbook_retriever.py']
            or sha(array) != variant['array_sha256']):
        parser.error('数组/引擎必须匹配固定版本，不能混配')
    items = json.loads(array.read_text())
    if len(items) != 132 or len({item['id'] for item in items}) != 132:
        parser.error('不是132唯一模板')
    if len(items) != 132 or sum(bool(item.get('family_id')) for item in items) != 26:
        parser.error('模板或family数量不符')
    before = {}
    if args.activate:
        backup = directory/'before_B_activation'
        backup.mkdir(exist_ok=False)
        paths = {'implementation/runbook_items.py': items_path, 'implementation/runbook_retriever.py': engine}
        for name in paths:
            target = ROOT/name
            before[name] = sha(target)
            shutil.copy2(target, backup/target.name)
        try:
            for name, path in paths.items(): shutil.copyfile(path, ROOT/name)
            sys.path.insert(0, str(ROOT/'implementation'))
            from runbook_matcher import _verify_a132_sources
            _, _, active = _verify_a132_sources(ROOT)
            assert active == args.variant
        except Exception:
            for name in paths: shutil.copyfile(backup/Path(name).name, ROOT/name)
            raise
    result = {'status': 'A132_ACTIVATED' if args.activate else 'A132_VERIFIED_ONLY', 'variant': args.variant,
              'templates': 132, 'families': 26, 'previous_sha256': before,
              'installed_sha256': variant['runtime_hashes'] if args.activate else {},
              'A_ref': source['A_ref'], 'model_requests': 0, 'service_requests': 0}
    (directory/'B_ACTIVATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
