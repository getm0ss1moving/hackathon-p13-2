"""Public offline replay of fixed170 attribute invariants; not the private70 suite."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module.RunbookRetriever


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base170',type=Path,required=True)
    parser.add_argument('--attributes170',type=Path,required=True)
    parser.add_argument('--base-retriever',type=Path,required=True)
    parser.add_argument('--attribute-retriever',type=Path,required=True)
    args=parser.parse_args()
    for path,digest in [(args.base170,'804a1626669ae24bab860b282e465113241dceee09d567f6d12866bb37a09de0'),
        (args.attributes170,'f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c'),
        (args.base_retriever,'8fd12b7556bdcf89a10f9d408d9c8473e04a48bcd4bd3bd89bc06c8aaec856cc'),
        (args.attribute_retriever,'befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24')]:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,path.name
    original=json.loads(args.base170.read_text());candidate=json.loads(args.attributes170.read_text())
    assert len(candidate)==len({i['id'] for i in candidate})==170
    assert [{k:v for k,v in i.items() if k!='retrieval_attributes'} for i in candidate]==original
    before=load('_public170_base',args.base_retriever)(original)
    after=load('_public170_attribute',args.attribute_retriever)(candidate)
    assert [(d.item_id,d.tokens) for d in before._docs]==[(d.item_id,d.tokens) for d in after._docs]
    assert (before._df,before._idf,before._tau,before._avg_len,before._doc_tfs)==(after._df,after._idf,after._tau,after._avg_len,after._doc_tfs)
    assert after._doc_count==400 and after._attribute_index._doc_count==11
    positive,negative=0,0
    for record in after._attribute_records.values():
        output=list(record['projection'])
        prefix='查询'+record['resource_terms'][0]+'，'+','.join(field+'="Synthetic-'+field+'"' for field in sorted(record['filters']))
        question=prefix+'，输出'+','.join(output)
        assert record['owner'] in {c.id for c in after.retrieve(question)}
        assert record['owner'] in {c.id for c in after._attribute_candidates(question)}
        positive+=1
        for columns in [output[1:],list(reversed(output)),output+['unknownColumn']]:
            assert not after._attribute_candidates(prefix+'，输出'+','.join(columns))
            negative+=1
    assert positive==11 and negative==33
    print(json.dumps({'status':'PASS_PUBLIC_ATTRIBUTE_INVARIANTS','active_templates':170,
        'primary_documents':400,'attribute_documents':11,'profile_controls':positive,'invalid_projection_controls':negative,
        'API_SQL_and_other_existing_fields_unchanged':True,'primary_BM25_statistics_unchanged':True,
        'private70_replayed_here':False,'model_calls':0,'service_calls':0,'production_modified':False},ensure_ascii=False))


if __name__=='__main__':main()
