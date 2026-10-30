"""B对A bootable新合同的单族绑定；旧132数组/registry/模块字节不变。"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT/'experiments/b_bootable_native_overlay_20261031/REGISTRY.json'
_MODULE = None


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
                                    separators=(',',':')).encode()).hexdigest()


def enabled(item):
    return (os.environ.get('RUNBOOK_A132_NATIVE_BOOTABLE') == '1'
            and isinstance(item,dict) and item.get('id') == 'family_volume_rows')


def sources():
    pins = json.loads(REGISTRY.read_text())
    files = {str(REGISTRY.relative_to(ROOT)):_sha(REGISTRY)}
    expected = {'implementation/runbook_items.py':pins['base_runtime_array_sha256'],
                pins['base_registry_path']:pins['base_registry_sha256'],
                pins['new_module_path']:pins['new_module_sha256'],
                pins['A_manifest_path']:pins['A_manifest_sha256']}
    for relative,value in expected.items():
        if _sha(ROOT/relative) != value:
            raise ValueError('native_bootable_binding_drift:'+relative)
        files[relative] = value
    folder = (ROOT/pins['A_manifest_path']).parent
    manifest = json.loads((ROOT/pins['A_manifest_path']).read_text())
    for relative,value in manifest['files'].items():
        path = folder/relative
        if _sha(path) != value:
            raise ValueError('A_bootable_source_drift:'+relative)
        files[str(path.relative_to(ROOT))] = value
    return pins,files


def prompt_item(item):
    if not enabled(item):
        return item
    pins,_ = sources()
    if _digest(item) != pins['base_card_sha256']:
        raise ValueError('native_bootable_original_card_drift')
    shown = copy.deepcopy(item)
    contract = shown['parameter_contract']
    if contract.get('bootable') != pins['old_bootable_enum']:
        raise ValueError('native_bootable_old_enum_drift')
    contract['bootable'] = pins['new_bootable_enum'].copy()
    path = (ROOT/pins['new_module_path']).parent/'CONTRACT.json'
    contract['input_schema'] = json.loads(path.read_text())['parameter_schema']
    contract['bootable_normalization'] = 'JSON bool or case-insensitive true/false text -> native lowercase string; never numeric or truthiness conversion'
    return shown


def bind(base,item):
    """显式复制映射，完整原文prepare只派给已核SHA的新A模块；不修改A全局。"""
    if not enabled(item):
        return base
    global _MODULE
    pins,_ = sources()
    if _digest(item) != pins['base_card_sha256']:
        raise ValueError('native_bootable_original_item_drift')
    record = base._REGISTRY[item['id']]
    if record['module_sha256'] != pins['old_module_sha256']:
        raise ValueError('native_bootable_original_registry_drift')
    if _MODULE is None:
        path = ROOT/pins['new_module_path']
        spec = importlib.util.spec_from_file_location('_B_A_native_bootable',path)
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _MODULE = module
    registry = copy.deepcopy(base._REGISTRY)
    registry[item['id']].update(module=pins['new_module_path'],module_sha256=pins['new_module_sha256'])
    modules = dict(base._MODULES);modules[pins['new_module_sha256']] = _MODULE

    def prepare(question,selected,parsed,diagnostics=None):
        sources()  # 不以模块缓存掩盖冻结文件变化。
        if _digest(selected) != pins['base_card_sha256']:
            raise ValueError('native_bootable_selected_item_drift')
        result = _MODULE.prepare_candidate(question,selected,parsed,diagnostics)
        if diagnostics is not None:
            diagnostics['native_bootable_binding'] = {'family':item['id'],
                'module_sha256':pins['new_module_sha256'],'array_and_A_registry_unchanged':True,
                'full_original_question_prepare':True}
        return result
    return SimpleNamespace(handles_item=base.handles_item,prepare_candidate=prepare,
                           _REGISTRY=registry,_MODULES=modules)
