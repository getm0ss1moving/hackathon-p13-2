"""A新网络政策的B端语义/原始人口/真实筛选/typed及完整明细保护，零网络。"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs

import runbook_issue3 as c
import runbook_issue4 as n
from test_training_issue3 import Session

GLOBAL='一共有多少VPC，VPC下有哪些子网，子网下有哪些虚拟机'
NAMED='VPCdemo下有多少个子网和弹性IP'


def fixture():
    def row(identity,**values):return dict(id=identity,logicalRegionName='region_demo',**values)
    rows={
        'ROUTER':[row('r1',name='demo',nativeId='nr1'),row('r2',name='demo',nativeId='nr2')],
        'PORT':[row('rp',devNativeId='nr1',devId=None),row('vp',devNativeId=None,devId='res1'),
                row('rp',devNativeId='nr1',devId=None,last_Modified='new')],
        'R_PORT_IN_SUBNET':[{'id':'rr','portId':'rp','subnetId':'s1'},{'id':'rv','portId':'vp','subnetId':'s1'}],
        'SUBNET':[row('s1',name='subnet',cidr='198.51.100.0/24')],
        'VM_NOVA':[row('vm1',resId='res1',name='synthetic_vm')],
        'FLOATING_IPS':[row('e1',routerId='r1')],
    }
    schemas={ci:sorted(set().union(*(r.keys() for r in values))) for ci,values in rows.items()}
    return schemas,rows


class Issue4NetworkTests(unittest.TestCase):
    def plan(self,question,schemas):
        item={'id':'synthetic','name':'synthetic','resources':['ROUTER','FLOATING_IPS']}
        plan=n.prepare(question,item,schemas)
        self.assertIsNotNone(plan)
        return plan

    def execute(self,question,*,rows=None,schemas=None,session_class=Session,**options):
        default_schemas,default_rows=fixture();rows=copy.deepcopy(default_rows if rows is None else rows)
        schemas=default_schemas if schemas is None else schemas
        before=copy.deepcopy(rows);diagnostics={};session=session_class(schemas,rows,**options)
        reader=c.NativeReader(diagnostics,session=session,raw_duplicate_resources={'PORT'})
        with patch.object(c,'_local_readonly_identity',return_value={'synthetic':True}):
            result=c.execute_plan(self.plan(question,schemas),[],diagnostics,reader=reader)
        self.assertEqual(rows,before)
        return result,diagnostics,session

    def test_hierarchy_keeps_total_and_all_parent_child_details(self):
        result,d,_=self.execute(GLOBAL);row=result['result']['rows'][0]
        self.assertEqual(row['total'],2)
        columns=json.loads(row['hierarchy_columns_json']);rows=[dict(zip(columns,v)) for v in json.loads(row['hierarchy_rows_json'])]
        self.assertEqual({r['vpc_id'] for r in rows},{'r1','r2'})
        self.assertIn('vm1',{r['vm_id'] for r in rows})
        self.assertTrue(d['all_A_details_retained']);self.assertFalse(d['business_complete'])

    def test_raw_duplicates_preserved_and_canonical_count_separate(self):
        _,d,_=self.execute(GLOBAL)
        receipt=d['canonical_receipts']['PORT']
        self.assertEqual((receipt['raw_total_num'],receipt['raw_observation_count'],receipt['canonical_object_count'],receipt['duplicate_observation_count']),(3,3,2,1))

    def test_named_selection_really_executes_name_and_keeps_all_matching_parents(self):
        result,d,session=self.execute(NAMED);row=result['result']['rows'][0]
        self.assertEqual((row['subnet_count'],row['known_eip_count']),(1,1))
        self.assertEqual(len(json.loads(row['parent_rows_json'])),2)
        selected=[url for url in session.calls if 'condition=' in url]
        self.assertTrue(any(json.loads(parse_qs(urlsplit(url).query)['condition'][0])['constraint'][0]['simple']=={'name':'name','operator':'equal','value':'demo'} for url in selected))

    def test_nonprojected_business_difference_and_json_type_conflict_still_refused(self):
        for first,second in [('old','new'),(1,True),(1,1.0)]:
            schemas,rows=fixture();rows['PORT'][0]['future_business']=first;rows['PORT'][2]['future_business']=second
            with self.subTest(first=first,second=second),self.assertRaisesRegex(ValueError,'duplicate identity'):
                self.execute(NAMED,rows=rows,schemas=schemas)

    def test_sparse_unknown_endpoint_keeps_parent_and_diagnostic(self):
        schemas,rows=fixture();rows['FLOATING_IPS'][0].pop('routerId')
        result,d,_=self.execute(NAMED,rows=rows,schemas=schemas)
        self.assertEqual(len(json.loads(result['result']['rows'][0]['parent_rows_json'])),2)
        self.assertEqual(d['A_diagnostics']['unknown_eip_parent_count'],1)

    def test_success_empty_returns_zero_summary_and_no_fabricated_parent(self):
        schemas,rows=fixture();rows={ci:[] for ci in rows}
        result,d,_=self.execute(NAMED,rows=rows,schemas=schemas)
        self.assertEqual(result['result']['rows'][0]['subnet_count'],0)
        self.assertEqual(json.loads(result['result']['rows'][0]['parent_rows_json']),[])
        result,_,_=self.execute(GLOBAL,rows=rows,schemas=schemas)
        self.assertEqual(result['result']['rows'][0]['total'],0)

    def test_HTTP_failure_bad_page_or_undeclared_schema_never_become_success_empty(self):
        for options in [{'status':503},{'corrupt':True}]:
            with self.subTest(options=options),self.assertRaises(c.Unsupported):self.execute(NAMED,**options)
        schemas,rows=fixture();schemas['SUBNET'].remove('id')
        self.assertIsNone(n.prepare(NAMED,{'id':'synthetic','resources':['ROUTER','FLOATING_IPS']},schemas))

    def test_name_selection_omission_cannot_be_filled_from_catalog(self):
        class MissingSelection(Session):
            def get(self,url,**kwargs):
                response=super().get(url,**kwargs)
                if '/instances/ROUTER?' in url and 'condition=' in url:
                    body=response.json();body['objList']=body['objList'][:1];body['totalNum']=1
                return response
        with self.assertRaisesRegex(ValueError,'selection and full parent catalog disagree'):
            self.execute(NAMED,session_class=MissingSelection)

    def test_old_reader_still_rejects_duplicate_PORT_and_other_CIs_remain_strict(self):
        schemas,rows=fixture();call={'method':'GET','url':'/rest/hackthon/db/instances/PORT?pageNo=1&pageSize=1000'}
        with self.assertRaisesRegex(c.Unsupported,'duplicate_or_missing_identity'):
            c.NativeReader({},session=Session(schemas,rows)).fetch(call)
        rows['ROUTER'].append(copy.deepcopy(rows['ROUTER'][0]))
        with self.assertRaisesRegex(c.Unsupported,'duplicate_or_missing_identity'):
            self.execute(NAMED,rows=rows,schemas=schemas)

    def test_extra_obligation_missing_entity_ambiguous_scope_and_long_wire_rejected(self):
        for question in [NAMED+'和管理员密码',GLOBAL+'以及磁盘容量','VPC下有多少个子网和弹性IP',NAMED+'或区域other']:
            self.assertIsNone(n.parameters(question))
        family,params=n.parameters('VPC'+('x'*5000)+'下有多少个子网和弹性IP')
        with self.assertRaisesRegex(ValueError,'exceeds4096'):n.layout(family,params)

    def test_prepared_plan_SQL_drift_fails_before_any_native_request(self):
        schemas,rows=fixture();plan=self.plan(NAMED,schemas);plan['sql']+=' LIMIT 1'
        session=Session(schemas,rows);reader=c.NativeReader({},session=session,raw_duplicate_resources={'PORT'})
        with self.assertRaisesRegex(ValueError,'plan_drift'):c.execute_plan(plan,[],{},reader=reader)
        self.assertEqual(session.calls,[])

    def test_packed_detail_loss_is_not_hidden_by_matching_summary_count(self):
        original=n.typed_sql
        def lost(sql,tables):
            result=original(sql,tables)
            if 'parent_rows_json' in result['columns']:result['rows'][0]['parent_rows_json']='[]'
            return result
        with patch.object(n,'typed_sql',side_effect=lost),self.assertRaisesRegex(ValueError,'detail_conservation_failed'):
            self.execute(NAMED)

    def test_source_lock_rejects_drift_even_after_module_cache_is_warm(self):
        n.module();read=Path.read_bytes
        def changed(path):
            if path.name=='adapters.py' and 'a_issue4_r1_20261031' in path.parts:return b'drift'
            return read(path)
        with patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'source_drift'):n.module()

    def test_family_whitelist_does_not_enable_named_candidate_implicitly(self):
        schemas,_=fixture();item={'id':'synthetic','resources':['ROUTER','FLOATING_IPS']}
        self.assertIsNotNone(n.prepare(GLOBAL,item,schemas,enabled_families=['hierarchy']))
        self.assertIsNone(n.prepare(NAMED,item,schemas,enabled_families=['hierarchy']))
        for bad in [['unknown'],['hierarchy','hierarchy'],'hierarchy',[{}],[None],[True]]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):n.prepare(GLOBAL,item,schemas,enabled_families=bad)


if __name__=='__main__':unittest.main()
