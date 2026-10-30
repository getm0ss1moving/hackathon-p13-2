"""Read-only A170 offline acceptance; synthetic API/SQLite and real BM25 only."""
import argparse
import ast
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

MEMBERS = {'family_f02': ['rb_006','rb_009','rb_029','rb_037','rb_038','rb_039','rb_042'],
           'family_f19': ['rb_142','rb_145','rb_146','rb_148']}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base179', type=Path, required=True)
    parser.add_argument('--candidate170', type=Path, required=True)
    parser.add_argument('--retriever', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--known-queries', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Use a fresh result directory')
    assert hashlib.sha256(args.base179.read_bytes()).hexdigest() == '1743b73df31b420a5d9f3a0f775d5c93e0277ce9c5e2d85585adef79b4f3d026'
    assert hashlib.sha256(args.candidate170.read_bytes()).hexdigest() == '804a1626669ae24bab860b282e465113241dceee09d567f6d12866bb37a09de0'
    assert hashlib.sha256(args.retriever.read_bytes()).hexdigest() == '8fd12b7556bdcf89a10f9d408d9c8473e04a48bcd4bd3bd89bc06c8aaec856cc'
    assert hashlib.sha256(args.helper.read_bytes()).hexdigest() == '79815020db5c0f82ff3e5f0fb20c5b6f5d0ed69d43a363a6fe67b17228372ba7'
    old, new = json.loads(args.base179.read_text()), json.loads(args.candidate170.read_text())
    before_by, after_by = ({i['id']:i for i in library} for library in [old,new])
    replacement = {old_id:family for family, members in MEMBERS.items() for old_id in members}
    assert len(old) == len(before_by) == 179 and len(new) == len(after_by) == 170
    assert [i for i in old if i['id'] not in replacement] == [i for i in new if i['id'] not in MEMBERS]
    cls = load_module('_170_bm25', args.retriever).RunbookRetriever
    before, after = cls(old), cls(new)
    assert [(d.item_id,d.tokens) for d in before._docs] == [(d.item_id,d.tokens) for d in after._docs]
    assert (before._df,before._idf,before._tau,before._avg_len,before._doc_tfs) == (after._df,after._idf,after._tau,after._avg_len,after._doc_tfs)
    controls = [
        '查询ECS名称为 Instance-A 的实例，输出name、createdAt',
        '查询ECS名称为 Instance-A 的实例，输出name、clusterName、azoneName',
        '查询ECS租户 Tenant-A 区域 Region-A，输出name、privateIps、status',
        '查询ECS可用区 AZ-A 状态 active，输出name、privateIps、tenantName',
        '查询GaussDB名称 DB-A，输出engineVersion、haMode、flavorCode',
        '查询GaussDB区域 Region-A，输出name、engineName、engineVersion、haMode、flavorCode',
        '查询GaussDB区域 Region-A，输出name、engineVersion、dataVip',
        '查询GaussDB名称 DB-A，输出haMode、dataVip',
        '查询ECS创建时间以及GaussDB实例版本和规格',
        '查询ECS创建时间，以及这个实例的集群和可用区',
        '列出区域 Region-A GaussDB实例清单并统计各版本实例数',
        '查询ECS实例名称和IP，以及区域 Region-A 的OBS桶列表',
    ]
    queries = json.loads(args.known_queries.read_text()) if args.known_queries else []
    known_count = len(queries)
    queries += [{'id':'synthetic170-'+str(i),'question':q} for i,q in enumerate(controls)]
    def normalized(results):
        seen, result = set(), []
        for c in results:
            owner = replacement.get(c.id,c.id)
            if owner not in seen:
                seen.add(owner); result.append((owner,c.tier,c.score,c.coverage))
        return result
    timing={'179':[],'170':[]}; differences=[]; details=[]
    for query in queries:
        for k in [None,1,5,10]:
            start=time.perf_counter(); a=before.retrieve(query['question'],k)
            if k is None: timing['179'].append((time.perf_counter()-start)*1000)
            start=time.perf_counter(); b=after.retrieve(query['question'],k)
            if k is None: timing['170'].append((time.perf_counter()-start)*1000)
            assert all(c.id in after_by for c in b)
            if normalized(a) != [(c.id,c.tier,c.score,c.coverage) for c in b]: differences.append({'id':query['id'],'k':k})
        details.append({'id':query['id'],'before_ids':[c[0] for c in normalized(before.retrieve(query['question']))],
                        'after_ids':[c.id for c in after.retrieve(query['question'])]})
    assert not differences, differences
    # Exact reviewed helper imports only copy/re and calls no SDK/model/service.
    tree=ast.parse(args.helper.read_text())
    imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    assert all(isinstance(n,ast.Import) and all(a.name in {'copy','re'} for a in n.names) for n in imports)
    helper=load_module('_170_closed_helper',args.helper)
    rows=json.loads(args.mapping.read_text())['mappings']
    assert len(rows)==11 and {r['old_id'] for r in rows}==set(replacement)
    checks=[]; implicit=[]; positive=0
    all_fields=['name','privateIps','tenantName','status','createdAt','clusterName','azoneName','vdcName','logicalRegionName','engineName','engineVersion','haMode','flavorCode','dataVip']
    sql_count=0
    for row in rows:
        source=before_by[row['old_id']];family=after_by[row['candidate_id']]
        assert source['api_call']==row['api_contract'] and source['sql']==row['sql_contract']
        parameters=copy.deepcopy(row['parameters'])
        parameters['filters']={key:'Synthetic-'+key for key in parameters['filters']}
        native=helper._materialize_batch3(family,parameters)
        def fill(x):
            if isinstance(x,dict):return {k:fill(v) for k,v in x.items()}
            if isinstance(x,list):return [fill(v) for v in x]
            if isinstance(x,str):
                for key,value in parameters['filters'].items():x=x.replace('{{'+key+'}}',value)
            return x
        assert native['api_call']==fill(row['api_contract']) and native['sql']==row['sql_contract']
        resource='ECS' if row['family_id']=='F02' else 'GaussDB'
        question='查询'+resource+'，'+ '，'.join(key+'="'+value+'"' for key,value in parameters['filters'].items())
        if parameters['order']!='none':question+='，按租户名称排序'
        question+='，输出'+ '、'.join(parameters['projection'])
        assert helper._prepare_batch3_candidate(question,family,parameters) == native
        positive+=1
        diagnostics={}
        original_params=copy.deepcopy(row['parameters'])
        defaults=source.get('default_params',{})
        original_params['filters']={key:defaults.get(key,'Synthetic-'+key) for key in original_params['filters']}
        native_original=helper._prepare_batch3_candidate(source.get('description',''),family,original_params,diagnostics)
        implicit.append({'old_id':row['old_id'],'ordinary_returned':native_original is not None,
                         'diagnostic':diagnostics.get('family_error')})
        table=helper._B3_SPECS[row['family_id']]['table']
        normal={field:'Data-'+field for field in all_fields};normal.update(parameters['filters'])
        nullable=copy.deepcopy(normal)
        for field in parameters['projection']:
            if field not in parameters['filters']:nullable[field]=None
        mismatch=copy.deepcopy(normal);mismatch[next(iter(parameters['filters']))]='Different'
        for dataset in [[],[normal],[normal,copy.deepcopy(normal),nullable,mismatch]]:
            filtered=[r for r in dataset if all(r[k]==v for k,v in parameters['filters'].items())]
            with sqlite3.connect(':memory:') as connection:
                connection.execute('CREATE TABLE '+table+'('+','.join(field+' TEXT' for field in all_fields)+')')
                connection.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in all_fields)+')',[[r[f] for f in all_fields] for r in filtered])
                a=connection.execute(row['sql_contract']);old_columns=[d[0] for d in a.description];old_rows=a.fetchall()
                b=connection.execute(native['sql']);columns=[d[0] for d in b.description];actual=b.fetchall()
                assert old_columns==columns==row['output_columns'] and actual==old_rows
                assert len(actual)==len(filtered)
                if parameters['order']=='none':assert actual==[tuple(r[f] for f in parameters['projection']) for r in filtered]
                sql_count+=1
            checks.append({'old_id':row['old_id'],'input_rows':len(dataset),'synthetic_filter_matched_rows':len(filtered),'output_rows':len(actual),'SQL_API_equal':True})
    negative={}
    row=rows[1];family=after_by[row['candidate_id']];params=copy.deepcopy(row['parameters']);params['filters']={'name':'Instance-A'}
    good='查询ECS名称为 "Instance-A"，输出name、createdAt'
    cases={'missing_terminal_projection':('查询ECS名称为 "Instance-A" 的创建时间',params),
        'contains_name':('查询ECS名称包含 "Instance-A"，输出name、createdAt',params),
        'OR_extra_name':('查询ECS名称为 "Instance-A" 或名称为 "Instance-B"，输出name、createdAt',params),
        'cross_resource':(good+' 和GaussDB实例清单',params),
        'unknown_projection':(good,{**params,'projection':['name','unknown']}),
        'global_scope':(good,{**params,'scope':'global','filters':{},'required_filters':[]}),
        'null_name':(good,{**params,'filters':{'name':None}}),
        'extra_metric':(good,{**params,'metrics':'count'})}
    for label,(question,parameters) in cases.items():
        assert helper._prepare_batch3_candidate(question,family,parameters) is None,label
        negative[label]='unsupported_empty_candidate'
    percentile=lambda xs,p:sorted(xs)[int((len(xs)-1)*p)]
    summary={'status':'PASS170_OFFLINE_DATA_INDEX_CLOSED_CONTRACT_ONLY','baseline_N':179,'candidate_N':170,
        'production_activated':False,'nonmembers_exactly_unchanged':168,'raw_profile_order_and_BM25_statistics_identical':True,
        'known_exposed_query_count':known_count,'additional_synthetic_queries':len(controls),'paired_top_k_checks':len(queries)*4,
        'normalized_ID_order_tier_score_coverage_differences':len(differences),'template_IDs_unique':True,
        'text_profiles':200,'index_documents':400,'old_contracts_equal':len(rows),'explicit_prepare_positives':positive,
        'synthetic_SQL_API_comparisons':sql_count,'negative_controls':negative,
        'original_surface_prepare_ordinary_count':sum(x['ordinary_returned'] for x in implicit),
        'original_surface_prepare_total':len(implicit),'original_surface_diagnostic_counts':dict(Counter(x['diagnostic'] for x in implicit)),
        'measurements_ms':{name:{'samples':len(v),'p95':percentile(v,.95),'p99':percentile(v,.99),'max':max(v)} for name,v in timing.items()},
        'model_calls':0,'service_calls':0,'shared_data_or_sealed_or_200_eval_accessed':False,
        'B_adapter_installed':False,'native_empty_schema_or_pagination_tested':False,
        'limits':['Explicit terminal ordered projection and explicit equality roles only; original implicit wording is not equivalent yet.',
        'Compound retrieval equality does not prove obligation execution; repeated family views need B composition.',
        'rb038 defaults-versus-question conflict remains unresolved; placeholders do not fix it.',
        'SQLite tables have predefined columns and synthetic filtered records; native empty-table behavior, pagination and unique-resource semantics are not proven.',
        'No new model score, official total or black-box improvement is established.']}
    args.output.mkdir(parents=True)
    for name,data in [('VALIDATION.json',summary),('SQL_FIXTURE_DETAILS.json',checks),('ORIGINAL_SURFACE_DIAGNOSTICS.json',implicit),('RETRIEVAL_DETAILS.private.json',details)]:
        (args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
