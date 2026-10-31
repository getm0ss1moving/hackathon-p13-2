"""JSON收据的深复制快路径；保留别名/环语义，其他Python对象交回标准库。"""
from copy import deepcopy as _standard_deepcopy
import hashlib
import json
import os
from pathlib import Path

_ATOMS=frozenset((str,int,float,bool,type(None)))


class _NeedsStandardCopy(Exception):pass


def _json_clone(value,memo):
    kind=type(value)
    if kind in _ATOMS:return value
    if kind not in (dict,list) or kind is dict and any(type(k) is not str for k in value):
        raise _NeedsStandardCopy()
    identity=id(value)
    if identity in memo:return memo[identity]
    if kind is list:
        result=[];memo[identity]=result
        result.extend(_json_clone(item,memo) for item in value)
    else:
        result={};memo[identity]=result
        for key,item in value.items():result[key]=_json_clone(item,memo)
    return result


def deepcopy(value,memo=None):
    # 外部memo可能预置原子替换；此时必须完整沿用标准库行为。
    if memo is not None:return _standard_deepcopy(value,memo)
    if type(value) in _ATOMS:return value
    try:return _json_clone(value,{})
    except _NeedsStandardCopy:return _standard_deepcopy(value)


def mode():
    value=os.environ.get('RUNBOOK_JSON_COPY_MODE','standard')
    if value not in {'standard','fast'}:raise ValueError('unsupported_JSON_copy_mode')
    return value


def copy_value(value):
    return deepcopy(value) if mode()=='fast' else _standard_deepcopy(value)


def sources():
    root=Path(__file__).resolve().parents[1]
    relative='experiments/b_issue4_copy_runtime_20261031/SOURCE_MANIFEST.json'
    path=root/relative;binding=json.loads(path.read_text())
    if binding['policy_change'] is not False or binding['variant']!='B_JSON_container_deepcopy_v1':
        raise ValueError('copy_variant_binding_changed')
    files={relative:hashlib.sha256(path.read_bytes()).hexdigest()}
    for name,expected in binding['files'].items():
        actual=root/name
        if not actual.resolve().is_relative_to(root) or actual.is_symlink() or hashlib.sha256(actual.read_bytes()).hexdigest()!=expected:
            raise ValueError('copy_variant_source_drift')
        files[name]=expected
    return files


def bind(module):
    """显式B执行变体：仅替换A模块的复制原语，A导入和全部校验照常运行。"""
    selected=mode();sources()
    if not hasattr(module,'_B_standard_deepcopy'):
        original=getattr(module,'deepcopy',None)
        if original is not None and original is not _standard_deepcopy:
            raise ValueError('unexpected_A_copy_implementation')
        module._B_standard_deepcopy=original
        module._B_standard_module_loader=getattr(module,'_module',None)
    if module._B_standard_deepcopy is not None:
        module.deepcopy=deepcopy if selected=='fast' else module._B_standard_deepcopy
    loader=module._B_standard_module_loader
    if loader is not None:
        # A的原loader仍逐次核源码pin；只在核验完成后绑定同一复制变体。
        def verified_loader(*args,**kwargs):return bind(loader(*args,**kwargs))
        module._module=verified_loader if selected=='fast' else loader
    module._B_copy_variant='B_JSON_container_deepcopy_v1' if selected=='fast' else 'standard_library'
    return module
