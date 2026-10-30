"""Independent frozen explicit/implicit170 integration controls; no services/models."""
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
FROZEN=ROOT/'frozen_candidate'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module


def main():
    proof=json.loads((FROZEN/'INPUT_FINGERPRINTS.json').read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(ROOT/'PROTOCOL.json')==proof['test_protocol_sha256']
    assert sha(ROOT/'CASES70.private.json')==proof['cases_sha256']
    assert sha(FROZEN/'natural_view_candidate.py')==proof['prototype_sha256']
    assert sha(FROZEN/'family_batch3_additions.py')==proof['closed_helper_sha256']
    template_path=ROOT.parent/'private_170/templates170.attributes.private.json'
    assert sha(template_path)=='f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c'
    items={i['family_id']:i for i in json.loads(template_path.read_text()) if i.get('family_id')}
    prototype=load('_independent170_natural',FROZEN/'natural_view_candidate.py')
    frozen=load('_independent170_closed',FROZEN/'family_batch3_additions.py')
    views_by_shape={(v[0],tuple(v[1]),v[2]):name for name,v in prototype.VIEWS.items()}
    results=[];attempts=0
    for case in json.loads((ROOT/'CASES70.private.json').read_text()):
        family=case['family_id'];item=items[family]
        if case['expected']=='ordinary':
            expected=case['contract'];parameters=expected['parameters']
            view=views_by_shape[(family,tuple(parameters['projection']),parameters['order'])]
            parsed={'view':view,'filters':copy.deepcopy(parameters['filters']),
                    'required_filters':copy.deepcopy(parameters['required_filters'])}
            diagnostics={};attempts+=1
            actual=prototype.prepare_natural_candidate(case['question'],item,parsed,frozen._prepare_batch3_candidate,diagnostics)
            passed=actual is not None and actual['api_call']==expected['api_call'] and actual['sql']==expected['sql']
            results.append({'id':case['id'],'kind':case['kind'],'expected':'ordinary','actual':'ordinary' if actual is not None else 'empty',
                            'passed':passed,'diagnostics':diagnostics,
                            'sql':actual.get('sql') if actual else None,
                            'api_contract_equal':actual is not None and actual.get('api_call')==expected['api_call'],
                            'sql_equal':actual is not None and actual.get('sql')==expected['sql']})
        else:
            # Probe every eligible view and both complete and omitted-filter
            # model hypotheses. None may erase an original unsupported clause.
            name='VM-Q' if family=='F02' else 'DB-Q'
            hypotheses=[{}, {'name':name}, {'logicalRegionName':'Region-Q'},
                        {'name':name,'status':'active'}, {'name':name,'azoneName':'AZ-Q'}]
            if family=='F02':
                hypotheses += [{'tenantName':'Tenant-Q','logicalRegionName':'Region-Q'},
                               {'logicalRegionName':'Region-Q','azoneName':'AZ-Q'},
                               {'azoneName':'AZ-Q','status':'active'}, {'name':'VM-R'}]
            else:hypotheses += [{'name':'DB-R'}]
            accepted=[];last_diagnostic={};case_attempts=0
            for view,spec in prototype.VIEWS.items():
                if spec[0]!=family:continue
                for filters in hypotheses:
                    parsed={'view':view,'filters':copy.deepcopy(filters),'required_filters':list(filters)}
                    diagnostics={};attempts+=1;case_attempts+=1
                    actual=prototype.prepare_natural_candidate(case['question'],item,parsed,frozen._prepare_batch3_candidate,diagnostics)
                    if actual is not None:
                        accepted.append({'parsed':parsed,'sql':actual.get('sql'),'diagnostics':diagnostics})
                    last_diagnostic=diagnostics
            results.append({'id':case['id'],'kind':case['kind'],'expected':'empty','actual':'ordinary' if accepted else 'empty',
                            'passed':not accepted,'attempts':case_attempts,'accepted':accepted,'last_diagnostic':last_diagnostic})
    false_empty=sum(r['expected']=='ordinary' and r['actual']=='empty' for r in results)
    false_nonempty=sum(r['expected']=='empty' and r['actual']=='ordinary' for r in results)
    wrong_contract=sum(r['expected']=='ordinary' and r['actual']=='ordinary' and not r['passed'] for r in results)
    kinds={kind:{'total':sum(r['kind']==kind for r in results),'passed':sum(r['kind']==kind and r['passed'] for r in results)} for kind in sorted({r['kind'] for r in results})}
    summary={'status':'PASS' if all(r['passed'] for r in results) else 'FAIL_PUBLICATION_PAUSED',
             'cases':len(results),'passed':sum(r['passed'] for r in results),'false_empty':false_empty,
             'false_nonempty':false_nonempty,'wrong_ordinary_contract':wrong_contract,'pure_prepare_attempts':attempts,
             'by_kind':kinds,'frozen_input_fingerprints':proof,
             'runtime_template_sha256_unchanged':sha(template_path),
             'retrieval_evidence':'Semantic70 only; the attribute retriever and its eight expected2148 differences are validated separately in COMBINED_VALIDATION.json.',
             'model_calls':0,'service_calls':0,'B_production_modified':False,'fixed_modules_modified':False,
             'Git_publication':False,'not_full_B_selector_family_fill_refine_or_composition':True,
             'design_scope':'Post-development independent controls, not preregistration or true hidden blackbox.'}
    (ROOT/'RESULTS70.private.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'SUMMARY70.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
