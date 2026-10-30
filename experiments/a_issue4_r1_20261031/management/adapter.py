"""Opt-in management-VM prepare overlay; never replace legacy B routes/executor.

The bound object's prepare_candidate has the legacy four-argument signature.
Only trusted host config may enable the candidate or declare the typed pipeline.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import types

FAMILY_ID='family_management_vm_details'
_REQUIRED={'id','name','resources','api_call','sql','requires_prepared_inputs','source_schema','prepared_schema'}
_CACHE={}
class BindingError(ValueError):pass
class RouteNotHandled(LookupError):pass

def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def _path(root,relative):
 p=(root/relative).resolve()
 if not p.is_relative_to(root.resolve()):raise BindingError('binding path escapes source root')
 return p

def handles_item(item):
 """Unbound module is disabled. Use bind(...) for isolated opt-in."""
 return False

def prepare_candidate(question,item,parsed,diagnostics=None):
 raise RouteNotHandled('EXPERIMENTAL_ROUTE_DISABLED_BIND_EXPLICITLY' if isinstance(item,dict) and item.get('id')==FAMILY_ID else 'UNCHANGED_B_ROUTE_REQUIRED')

class BoundRouter:
 def __init__(self,legacy_source_root,expected_binding_sha256,*,enable_experimental=False,prepared_pipeline=False,package_root=None):
  if type(enable_experimental)is not bool or type(prepared_pipeline)is not bool:raise BindingError('trusted config flags must be booleans')
  if enable_experimental and not prepared_pipeline:raise BindingError('typed prepared-input pipeline must be explicitly available')
  self.root=Path(package_root) if package_root is not None else Path(__file__).resolve().parent
  self.legacy_root=Path(legacy_source_root)
  self.pin=expected_binding_sha256
  self.enabled=enable_experimental
  self.prepared_pipeline=prepared_pipeline

 def _verified(self):
  raw=(self.root/'BINDING.json').read_bytes()
  if type(self.pin)is not str or len(self.pin)!=64 or _sha(raw)!=self.pin:raise BindingError('binding manifest drift or missing trusted outer pin')
  binding=json.loads(raw)
  if binding.get('family_id')!=FAMILY_ID or binding.get('default_enabled')is not False:raise BindingError('binding family/default drift')
  assets={}
  for role,record in binding['assets'].items():
   path=_path(self.root,record['path']);content=path.read_bytes()
   if _sha(content)!=record['sha256']:raise BindingError(role+': asset drift')
   assets[role]=(path,content)
  for record in binding['legacy132_source']['files']:
   if _sha(_path(self.legacy_root,record['path']).read_bytes())!=record['sha256']:raise BindingError('legacy132 source drift: '+record['role'])
  overlay=json.loads(assets['registry_overlay'][1])
  if set(overlay)!={FAMILY_ID}:raise BindingError('overlay registry must own only the new family')
  record=overlay[FAMILY_ID]
  for field,role in [('module_sha256','adapter'),('core_module_sha256','management_core'),('selection_card_sha256','selection_card'),('parameter_schema_sha256','parameter_schema')]:
   if record.get(field)!=binding['assets'][role]['sha256']:raise BindingError('overlay asset binding disagreement: '+field)
  if record.get('default_enabled')is not False or record.get('requires_prepared_inputs')is not True:raise BindingError('overlay activation/pipeline contract drift')
  card=json.loads(assets['selection_card'][1]);schema=json.loads(assets['parameter_schema'][1]);contract=json.loads(assets['core_contract'][1])
  if _canonical(card.get('parameter_schema'))!=_canonical(schema) or _canonical(schema)!=_canonical(contract['parameter_schema']):raise BindingError('card/schema/core contract disagree')
  if card.get('id')!=FAMILY_ID or card.get('family_id')!=FAMILY_ID or not card.get('name'):raise BindingError('bound card identity/name missing')
  digest=binding['assets']['management_core']['sha256']
  if digest not in _CACHE:
   path,content=assets['management_core'];module=types.ModuleType('management_core_'+digest);module.__file__=str(path)
   exec(compile(content,str(path),'exec'),module.__dict__);_CACHE[digest]=module
  core=_CACHE[digest]
  if core.FAMILY_ID!=FAMILY_ID or core.VIEW!=card['view']:raise BindingError('core/card view mismatch')
  return card,core

 def selection_cards(self):
  if not self.enabled:return []
  card,_=self._verified();return [deepcopy(card)]

 def handles_item(self,item):
  if not isinstance(item,dict) or item.get('id')!=FAMILY_ID:return False
  if not self.enabled:return False
  self._verified();return True

 def _bound_card(self,item,card):
  if not isinstance(item,dict) or any(k not in item for k in card):raise BindingError('complete bound selection card required')
  if _canonical({k:item[k] for k in card})!=_canonical(card):raise BindingError('selected card differs from pinned card')
  if any(k in item and k not in card for k in ('api_call','sql','requires_prepared_inputs','source_schema','prepared_schema')):raise BindingError('selected card includes unbound execution override')

 def _ordinary(self,plan,card,core):
  if plan is None:return None
  result=deepcopy(plan);result['name']=card['name']
  if not _REQUIRED<=set(result) or result['id']!=FAMILY_ID or result.get('family_id')!=FAMILY_ID:raise BindingError('incomplete ordinary metadata')
  expected_schema={ci:list(cols) for ci,cols in core.SCHEMA.items()}
  expected_prepared={core.TABLE:list(core.OUTPUT)+['management']}
  if result['requires_prepared_inputs']is not True or result['source_schema']!=expected_schema or result['prepared_schema']!=expected_prepared:raise BindingError('typed pipeline contract lost')
  return result

 def _active(self):
  if not self.enabled or not self.prepared_pipeline:raise RouteNotHandled('EXPERIMENTAL_ROUTE_DISABLED')
  return self._verified()

 def build(self,parsed):
  """Structural only; full-question prepare remains mandatory."""
  card,core=self._active();return self._ordinary(core.build(parsed),card,core)

 def prepare_candidate(self,question,item,parsed,diagnostics=None):
  if not isinstance(item,dict) or item.get('id')!=FAMILY_ID:raise RouteNotHandled('UNCHANGED_B_ROUTE_REQUIRED')
  card,core=self._active();self._bound_card(item,card)
  # Forward the entire original string and original four-key params unchanged.
  result=core.prepare_candidate(question,deepcopy(card),parsed,diagnostics)
  return self._ordinary(result,card,core)

 def prepare_or_delegate(self,question,item,parsed,legacy_prepare,diagnostics=None):
  """Unmatched IDs reach the caller's existing B route with identical args."""
  if not isinstance(item,dict) or item.get('id')!=FAMILY_ID:
   return legacy_prepare(question,item,parsed,diagnostics)
  return self.prepare_candidate(question,item,parsed,diagnostics)

 def preflight(self,parsed,receipts):
  _,core=self._active();return core.prepare(parsed,receipts)

 def prepare_inputs(self,question,item,parsed,receipts,diagnostics=None):
  """No fetching/execution. B loads these typed tables before contract SQL."""
  plan=self.prepare_candidate(question,item,parsed,diagnostics)
  if plan is None:return None
  tables,source_diagnostics=self.preflight(parsed,receipts)
  return {'plan':plan,'tables':tables,'diagnostics':source_diagnostics}

def bind(legacy_source_root,expected_binding_sha256,*,enable_experimental=False,prepared_pipeline=False,package_root=None):
 return BoundRouter(legacy_source_root,expected_binding_sha256,enable_experimental=enable_experimental,prepared_pipeline=prepared_pipeline,package_root=package_root)
