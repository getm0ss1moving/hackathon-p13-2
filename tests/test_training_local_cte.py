"""本地CTE不作为远端CI：合成HTTP、真实内存SQL及B query分派。"""
import copy
import os
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit
import unittest
from unittest.mock import patch

import runbook_matcher as m
import runbook_system as s


class LocalCTETests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.rows=[{'id':'id-a','name':'first'},{'id':'id-b','name':'second'}]
        self.item={'id':'synthetic','name':'synthetic','api_call':{'method':'GET','url':'/rest/hackthon/db/instances/VM_NOVA'},
            'sql':'WITH b_complete AS (SELECT id,name FROM CLOUD_VM_NOVA), orphan_vm AS (SELECT * FROM b_complete) SELECT name FROM orphan_vm ORDER BY name'}
        ctx=patch.object(m,'_schema_columns',{'VM_NOVA':['id','name']});ctx.start();self.addCleanup(ctx.stop)

    def get(self,url,**kwargs):
        ci=urlsplit(url).path.rsplit('/',1)[-1];self.calls.append(ci)
        if ci!='VM_NOVA':raise AssertionError('unexpected remote CI '+ci)
        size=int(parse_qs(urlsplit(url).query)['pageSize'][0])
        payload={'objList':copy.deepcopy(self.rows),'totalNum':len(self.rows),'totalPageNo':int(bool(self.rows)),
                 'currentPage':1,'pageSize':size}
        return SimpleNamespace(status_code=200,json=lambda:payload)

    def execute(self,item=None):
        diag={};fake=SimpleNamespace(get=self.get)
        result=s._execute_bounded_api(item or self.item,diag,session=fake)
        return result,diag

    def test_cte_references_are_local_and_strings_comments_are_not_tables(self):
        sql=self.item['sql']+" /* FROM invented */ -- JOIN bad\n"
        roles=m._sql_relation_roles(sql)
        self.assertEqual(roles['remote'],{'cloud_vm_nova':'CLOUD_VM_NOVA'})
        self.assertEqual(roles['local_ctes'],['b_complete','orphan_vm']);self.assertEqual(roles['unknown'],[])
        self.assertEqual(m._sql_relation_roles("SELECT 'FROM not_a_table' FROM CLOUD_VM_NOVA")['unknown'],[])

    def test_schema_lookup_uses_only_remote_registry_not_ctes_or_prepared_tables(self):
        sql='WITH b_anchor AS (SELECT * FROM CLOUD_VM_NOVA) SELECT * FROM b_anchor JOIN B_NATIVE_SUBNET_LABEL ON 1=1'
        with patch.object(m,'_schema_cache',{'CLOUD_VM_NOVA':'known schema'}),patch.object(m._schema_session,'get') as get:
            self.assertEqual(m._get_table_schemas(sql),'known schema')
        get.assert_not_called()

    def test_bounded_execution_fetches_only_real_ci_and_keeps_all_cte_rows(self):
        result,diag=self.execute()
        self.assertEqual(self.calls,['VM_NOVA']);self.assertEqual(result['result']['rows'],[{'name':'first'},{'name':'second'}])
        self.assertEqual(diag['local_sql_relations'],['b_complete','orphan_vm'])

    def test_empty_native_population_remains_zero_in_cte_count(self):
        self.rows=[];item=dict(self.item,sql='WITH b_anchor AS (SELECT * FROM CLOUD_VM_NOVA) SELECT COUNT(*) AS n FROM b_anchor')
        result,_=self.execute(item);self.assertEqual(result['result']['rows'],[{'n':0}])

    def test_unknown_remote_name_shadowing_and_write_are_rejected_before_http(self):
        for sql in ['WITH x AS (SELECT * FROM CLOUD_UNRECOGNIZED) SELECT * FROM x',
                    'WITH CLOUD_VM_NOVA AS (SELECT 1) SELECT * FROM CLOUD_VM_NOVA',
                    'WITH x AS (SELECT * FROM CLOUD_VM_NOVA) DELETE FROM CLOUD_VM_NOVA']:
            with self.subTest(sql=sql),self.assertRaises(s._APIPlanRefusal):self.execute(dict(self.item,sql=sql))
        self.assertEqual(self.calls,[])

    def test_query_routes_cte_plan_through_B_without_official_executor_mutation(self):
        instance=s.RunbookQuerySystem.__new__(s.RunbookQuerySystem);instance.items=[];instance.retriever=None
        fake=SimpleNamespace(get=self.get,close=lambda:None,mount=lambda *a:None)
        with patch.dict(os.environ,{'RUNBOOK_BOUNDED_API':'0','RUNBOOK_SG_RULE_SEMIJOIN':'0','RUNBOOK_TYPED_EMPTY_ROOT':'0','RUNBOOK_VERIFIED_EMPTY_ROOT':'0'}), \
             patch.object(s,'match_runbook',return_value=copy.deepcopy(self.item)),patch.object(s,'get_llm_events',return_value=[]), \
             patch.object(s.requests,'Session',return_value=fake),patch.object(s,'execute') as original:
            result=instance._query('合成明细')
        original.assert_not_called();self.assertEqual(result['result']['row_count'],2)
        self.assertTrue(result['diagnostics']['local_cte_execution']['sql_executed'])


if __name__=='__main__':unittest.main()
