"""Pure changed-family dispatch, NOT an executor or replacement B matcher.
Call handles_item first. The14 unchanged families and106 fixed items stay on B's
existing routes. This entry owns only the12 changed/new family implementations.
"""
import hashlib,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
_REGISTRY=json.loads((ROOT/'FAMILY_ROUTE_REGISTRY.json').read_text())
_MODULES={}
def handles_item(item):
    return isinstance(item,dict) and item.get('id') in _REGISTRY
def prepare_candidate(question,item,parsed,diagnostics=None):
    if not handles_item(item):
        raise LookupError('UNCHANGED_B_ROUTE_REQUIRED; do not serialize as unsupported empty')
    record=_REGISTRY[item['id']]
    if item.get('family_id')!=record['family_id']:
        if diagnostics is not None:diagnostics['unified_status']='family_identity_mismatch'
        return None
    path=ROOT/record['module'];raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record['module_sha256']:
        raise ValueError('frozen_module_drift')
    key=record['module_sha256']
    if key not in _MODULES:
        name='a132_'+key;module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
        exec(compile(raw,str(path),'exec'),module.__dict__);_MODULES[key]=module
    result=_MODULES[key].prepare_candidate(question,item,parsed,diagnostics)
    if result is not None and (not isinstance(result,dict) or not {'id','name','resources','api_call','sql'}<=set(result)):
        raise ValueError('not_an_ordinary_materialized_item')
    return result
