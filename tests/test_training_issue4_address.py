"""地址成员独立管线的原生HTTP替身、LIKE候选、精确token及来源重验。"""
import copy
import json
import os
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit

import runbook_issue3 as c
import runbook_issue4_address as address
import runbook_matcher as matcher
from runbook_retriever import Candidate
from test_training_issue3 import Session

QUESTION='查询区域region_lab21下关联了弹性IP的ECS实例名和固定IP'


def role_item():
    return {'id':'synthetic','name':'synthetic','resources':['FLOATING_IPS','VM_NOVA'],
        'api_call':[{'method':'GET','url':'/rest/hackthon/db/instances/FLOATING_IPS',
                     'condition':{'constraint':[{'simple':{'name':'status','value':'{{status}}','operator':'equal'}}]}}],
        'sql':'SELECT CLOUD_VM_NOVA.name FROM CLOUD_FLOATING_IPS JOIN CLOUD_VM_NOVA '
              'ON CLOUD_FLOATING_IPS.fixedIpAddress=CLOUD_VM_NOVA.privateIps'}


def fixture():
    def row(identity,**kw):return dict(id=identity,logicalRegionName='region_lab21',**kw)
    rows={'FLOATING_IPS':[
        row('e1',status='ACTIVE',fixedIpAddress='node-A',floatingIpAddress='public-1'),
        row('e2',status='ACTIVE',fixedIpAddress='node-A',floatingIpAddress='public-2'),
        row('e3',status='ACTIVE',fixedIpAddress='node-Z',floatingIpAddress='public-3'),
        row('e4',status='ACTIVE',fixedIpAddress='@node-A@',floatingIpAddress='public-4')],
        'VM_NOVA':[row('v1',name='vm-1',privateIps='@node-A@other@'),
            row('v2',name='vm-prefix',privateIps='@node-AA@'),
            row('v3',name='vm-duplicate-token',privateIps='@node-A@node-A@'),
            row('v4',name='vm-unknown',privateIps=None),
            row('v5',name='vm-case',privateIps='@NODE-A@'),
            dict(id='cross-region',logicalRegionName='region_else',name='cross',privateIps='@node-A@')]}
    schemas={ci:list(fields) for ci,fields in address.module().SCHEMA.items()}
    return schemas,rows


class LikeSession(Session):
    """与只读服务一致的SQLite LIKE行为；保留真实分页与原请求文本。"""
    def get(self,url,**kwargs):
        parsed=urlsplit(url);ci=parsed.path.rsplit('/',1)[-1]
        if '/schema/' in parsed.path:return super().get(url,**kwargs)
        self.calls.append(url);query=parse_qs(parsed.query)
        rows=copy.deepcopy(self.rows.get(ci,[]));page=int(query['pageNo'][0]);size=int(query['pageSize'][0])
        constraints=json.loads(query.get('condition',['{}'])[0]).get('constraint',[])
        with sqlite3.connect(':memory:') as sql:
            for entry in constraints:
                s=entry['simple']
                if s.get('operator','equal')=='contain':
                    rows=[r for r in rows if sql.execute('SELECT ? LIKE ?',
                        (r.get(s['name']),'%'+s['value']+'%')).fetchone()[0]]
                else:rows=[r for r in rows if r.get(s['name'])==s['value']]
        total=len(rows);body={'currentPage':page,'pageSize':size,'totalNum':total,
            'totalPageNo':(total+size-1)//size,'objList':rows[(page-1)*size:page*size]}
        if self.corrupt:body['currentPage']+=1
        return SimpleNamespace(status_code=self.status,json=lambda:body)


class AddressTests(unittest.TestCase):
    def setUp(self):
        schemas,_=fixture()
        for context in [patch.dict(matcher._schema_columns,schemas),
                        patch.dict(matcher._schema_values,{'FLOATING_IPS':{'status':['ACTIVE','DOWN']}})]:
            context.start();self.addCleanup(context.stop)

    def execute(self,*,rows=None,session_class=LikeSession,max_http=1024,**options):
        schemas,default=fixture();rows=copy.deepcopy(default if rows is None else rows);before=copy.deepcopy(rows)
        session=session_class(schemas,rows,**options);diag={}
        reader=c.NativeReader(diag,session=session,max_http=max_http,contain_fields={('VM_NOVA','privateIps')})
        plan=address.prepare(QUESTION,role_item(),schemas)
        self.assertIsNotNone(plan)
        try:
            with patch.object(c,'_local_readonly_identity',return_value={'synthetic':True}):
                result=c.execute_plan(plan,[],diag,reader=reader)
        finally:reader.close()
        self.assertEqual(rows,before)
        return result,diag,session

    def test_full_token_case_and_region_match_without_prefix_or_duplicate_token_fanout(self):
        result,d,session=self.execute();rows=result['result']['rows']
        self.assertEqual(len(rows),6)
        for eip in ['e1','e2']:
            selected=[r for r in rows if r['eip_id']==eip]
            self.assertEqual({r['vm_id'] for r in selected},{'v1','v3'})
            self.assertEqual({r['known_matching_vm_count'] for r in selected},{2})
        self.assertEqual(next(r for r in rows if r['vm_id']=='v1')['private_ips_raw'],'@node-A@other@')
        self.assertEqual(d['actual_contain_requests'],2)
        self.assertEqual(d['A_diagnostics']['duplicate_member_tokens_removed'],1)
        self.assertFalse(d['business_complete']);self.assertFalse(d['full_eip_objects_binding_complete'])
        self.assertFalse(any('/A_' in url for url in session.calls))

    def test_unknown_fixed_and_unknown_population_do_not_certify_no_binding(self):
        result,d,_=self.execute();rows=result['result']['rows']
        self.assertEqual(d['A_diagnostics']['unknown_VM_address_rows'],1)
        self.assertEqual(next(r for r in rows if r['eip_id']=='e3')['membership_status'],'known_candidates_population_incomplete')
        self.assertEqual(next(r for r in rows if r['eip_id']=='e4')['membership_status'],'unknown_fixed_address')

    def test_wildcard_like_candidates_are_not_exact_members(self):
        _,rows=fixture();rows['FLOATING_IPS']=rows['FLOATING_IPS'][:1];rows['FLOATING_IPS'][0]['fixedIpAddress']='a_b'
        rows['VM_NOVA']=[dict(id='exact',logicalRegionName='region_lab21',name='exact',privateIps='@a_b@'),
            dict(id='wildcard',logicalRegionName='region_lab21',name='wildcard',privateIps='@axb@')]
        result,_,_=self.execute(rows=rows)
        self.assertEqual([r['vm_id'] for r in result['result']['rows']],['exact'])

    def test_success_empty_stops_followups_and_keeps_real_output_schema(self):
        _,rows=fixture();rows['FLOATING_IPS']=[]
        result,d,session=self.execute(rows=rows)
        self.assertEqual(result['result']['rows'],[]);self.assertEqual(result['result']['columns'],list(address.module().OUTPUT))
        self.assertEqual(d['actual_contain_requests'],0)
        self.assertFalse(any('/VM_NOVA?' in u for u in session.calls))

    def test_native_reader_contain_requires_explicit_field_opt_in(self):
        schemas,rows=fixture();session=LikeSession(schemas,rows);reader=c.NativeReader({},session=session)
        request=address.module().request('VM_NOVA',[address.module().predicate('privateIps','node-A','contain')])
        try:
            with self.assertRaisesRegex(c.Unsupported,'unverified_native_contain'):reader.fetch(request)
        finally:reader.close()

    def test_candidate_recall_gap_and_budget_failure_are_not_empty_success(self):
        class MissingCandidates(LikeSession):
            def get(self,url,**kw):
                out=super().get(url,**kw)
                if 'contain' in url:
                    body=out.json();body['objList']=[];body['totalNum']=body['totalPageNo']=0
                return out
        with self.assertRaisesRegex(ValueError,'omitted an exact'):self.execute(session_class=MissingCandidates)
        with self.assertRaisesRegex(c.Unsupported,'remaining_HTTP_budget'):self.execute(max_http=2)

    def test_HTTP_page_metadata_or_prepared_drift_still_fail(self):
        for options in [{'status':503},{'corrupt':True}]:
            with self.subTest(options=options),self.assertRaises(c.Unsupported):self.execute(**options)
        original=address.module().prepare
        def changed(*args):
            p=original(*args);p['tables']['CLOUD_VM_NOVA'][0]['name']='tampered';return p
        with patch.object(address.module(),'prepare',side_effect=changed),self.assertRaisesRegex(ValueError,'prepared tables'):
            self.execute()

    def test_complete_question_and_matcher_flag_preserve_scope(self):
        schemas,_=fixture();item=role_item()
        for q in [QUESTION+'和管理员密码',QUESTION.replace('region_lab21','region_lab21或region_other'),
                  QUESTION.replace('区域region_lab21','整个Region')]:
            self.assertIsNone(address.prepare(q,item,schemas))
        retriever=SimpleNamespace(retrieve=lambda *a,**k:[Candidate(item['id'],'strong',2,1)])
        with patch.dict(os.environ,{'RUNBOOK_A132_CANDIDATE':'1','RUNBOOK_ISSUE4_ADDRESS':'1'}), \
                patch.object(matcher,'llm_ask',return_value='1'), \
                patch.object(matcher,'_get_table_schemas',return_value='synthetic'), \
                patch.object(matcher,'_refine_sql',side_effect=lambda q,s,*a,**k:s):
            result=matcher.match_runbook(QUESTION,[item],retriever,{})
        self.assertEqual(result['_issue3']['kind'],'issue4_address')


if __name__=='__main__':unittest.main()
