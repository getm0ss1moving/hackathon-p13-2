"""单GET空表数学语义；原执行器不修改，无模型或网络。"""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import runbook_matcher as m
import runbook_system as system


class DirectTypedEmptyTests(unittest.TestCase):
    def setUp(self):
        self.schema=patch.dict(m._schema_columns,{"NETWORK":["id","shared","providerNetworkType"]})
        self.schema.start();self.addCleanup(self.schema.stop)
        self.item={"sql":"SELECT COUNT(*) AS total FROM CLOUD_NETWORK",
                   "api_call":{"method":"GET","url":"/rest/hackthon/db/instances/NETWORK?pageNo=1&pageSize=10000",
                               "condition":{"constraint":[{"simple":{"name":"shared","operator":"equal","value":True}}]}}}

    def session(self,rows,error=None):
        payload={"objList":rows,"totalNum":len(rows),"totalPageNo":int(bool(rows)),
                 "currentPage":1,"pageSize":10000,"error":error,"success":error is None}
        calls=[]
        def get(*args,**kw):
            calls.append((args,kw));return SimpleNamespace(status_code=200,json=lambda:payload)
        return SimpleNamespace(get=get),calls

    def test_one_direct_table_has_a_finite_empty_domain_proof(self):
        self.assertTrue(system._single_ci_empty_eligibility(self.item)["eligible"])
        for sql in ["SELECT COUNT(*) FROM CLOUD_NETWORK n", "SELECT COUNT(*) FROM CLOUD_NETWORK,CLOUD_HOST",
                    "SELECT COUNT(*) FROM CLOUD_NETWORK UNION SELECT 1", "SELECT 1",
                    "WITH x AS (SELECT * FROM CLOUD_NETWORK) SELECT * FROM x"]:
            with self.subTest(sql=sql):
                item=dict(self.item,sql=sql);self.assertFalse(system._single_ci_empty_eligibility(item)["eligible"])
        item=dict(self.item,api_call=[self.item['api_call'],self.item['api_call']])
        self.assertFalse(system._single_ci_empty_eligibility(item)["eligible"])

    def test_real_empty_count_is_zero_and_keeps_columns(self):
        session,calls=self.session([]);diagnostic={}
        result=system._execute_bounded_api(self.item,diagnostic,session=session,empty_root_only=True)
        self.assertEqual(result['result'],{'columns':['total'],'rows':[{'total':0}],'row_count':1})
        self.assertTrue(system._execution_has_result_columns(result['result']))
        self.assertEqual(len(calls),1)

    def test_nonempty_root_defers_to_original_path(self):
        session,calls=self.session([{'id':'n1','shared':True,'providerNetworkType':'vlan'}]);d={}
        self.assertIsNone(system._execute_bounded_api(self.item,d,session=session,empty_root_only=True))
        self.assertFalse(d['sql_executed']);self.assertEqual(len(calls),1)

    def test_error_payload_is_never_converted_into_zero(self):
        session,calls=self.session([],error='backend failed')
        with self.assertRaises(RuntimeError):
            system._execute_bounded_api(self.item,{},session=session,empty_root_only=True)
        self.assertEqual(len(calls),1)

    def test_unknown_sql_field_still_refuses(self):
        session,_=self.session([]);item=dict(self.item,sql='SELECT missing_column FROM CLOUD_NETWORK')
        with self.assertRaises(system._APIPlanRefusal):
            system._execute_bounded_api(item,{},session=session,empty_root_only=True)


if __name__=='__main__':unittest.main()
