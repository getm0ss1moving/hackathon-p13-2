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


def load_sealed_validation(root, freeze_path, manifest, training, *, allow_subset_freeze=False):
    root = Path(root).resolve()
    freeze = verify_validation_freeze(root, freeze_path)  # 在打开任何验证题内容前检查候选。
    if freeze.get('subset_case_ids') and not allow_subset_freeze:
        raise ValueError('子集冻结不能扩展为完整50运行')
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


def load_validation_subset(root, freeze_path, manifest, training, requested):
    """已曝光验证题的显式失败子集；绑定用户本轮范围，不能扩展为全部50。"""
    freeze = verify_validation_freeze(root, freeze_path)
    ids = freeze.get('subset_case_ids')
    if (freeze.get('subset_authorization') not in {
            'user_B_only_and_delivered_contracts_20261031',
            'user_exposed_log_failures_20261031'}
            or not isinstance(ids, list) or not 1 <= len(ids) < 50
            or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids)
            or not isinstance(requested, list) or len(set(requested)) != len(requested)
            or set(ids) != set(requested)):
        raise ValueError('验证子集未绑定本轮明确范围')
    cases = load_sealed_validation(root, freeze_path, manifest, training, allow_subset_freeze=True)
    if set(ids) - {c['case_id'] for c in cases}:
        raise ValueError('验证子集含非固定50成员')
    return [c for c in cases if c['case_id'] in ids]


def load_explicit_whitebox200(root, manifest, training):
    """仅显式全200入口使用原数据；固定划分/题序不变，不作为封存泛化。"""
    path = Path(root).resolve()/'CMDB用例集-白盒200.json'
    if sha(path) != manifest.get('source_dataset_sha256'):
        raise ValueError('原白盒200来源哈希不符')
    cases = json.loads(path.read_text()).get('cases')
    if (not isinstance(cases, list) or len(cases) != 200
            or len({row['case_id'] for row in cases}) != 200
            or manifest.get('train_count') != 150 or manifest.get('holdout_count') != 50
            or len(training) != 150 or len({row['case_id'] for row in training}) != 150):
        raise ValueError('完整白盒或固定150/50数量不符')
    train_ids = {row['case_id'] for row in training}
    observed = [(row['case_id'], row['question']) for row in cases if row['case_id'] in train_ids]
    if observed != [(row['case_id'], row['question']) for row in training]:
        raise ValueError('原白盒与固定训练成员/题序不符')
    return cases
