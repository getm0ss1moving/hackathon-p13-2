"""仅用户明确解封并冻结候选后读取固定50验证题；默认训练入口不用此模块。"""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_validation_freeze(root, freeze_path):
    root = Path(root).resolve()
    freeze_path = Path(freeze_path).resolve()
    if not freeze_path.is_relative_to(root):
        raise ValueError('验证冻结记录必须位于当前仓库')
    freeze = json.loads(freeze_path.read_text())
    if freeze.get('authorization') != 'user_explicit_validation50_20261030' or freeze.get('scope') != 'sealed50_once':
        raise ValueError('没有本轮用户解封授权/固定50验证范围')
    paths = {str(path.relative_to(root)): sha(path) for path in (root/'implementation').glob('*.py')}
    if paths != freeze.get('runtime_sha256'):
        raise ValueError('候选未冻结或冻结后运行时已变化')
    split = root/'datasets/whitebox_150_50_v1'
    if sha(split/'manifest.json') != freeze.get('split_manifest_sha256'):
        raise ValueError('原始划分已变化')
    config = root/freeze['configuration_path']
    if not config.resolve().is_relative_to(root) or sha(config) != freeze.get('configuration_sha256'):
        raise ValueError('冻结验证配置已变化')
    return freeze


def load_sealed_validation(root, freeze_path, manifest, training):
    root = Path(root).resolve()
    verify_validation_freeze(root, freeze_path)  # 在打开任何验证题内容前检查候选。
    if manifest.get('holdout_count') != 50 or manifest.get('sealed_test_file') != 'sealed_test.json':
        raise ValueError('只允许原划分固定50验证题')
    path = root/'datasets/whitebox_150_50_v1/sealed_test.json'
    if sha(path) != manifest['sealed_test_sha256']:
        raise ValueError('验证题哈希不符；不重抽划分或回落到原200')
    dataset = json.loads(path.read_text())
    cases = dataset.get('cases')
    if (dataset.get('partition') != 'sealed_test' or not isinstance(cases, list) or len(cases) != 50
            or len({row['case_id'] for row in cases}) != 50
            or {row['case_id'] for row in cases} & {row['case_id'] for row in training}):
        raise ValueError('验证题数量、身份或训练隔离不符')
    return cases
