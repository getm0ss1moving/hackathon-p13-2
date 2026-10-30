"""empty-only根探测协议，全部内存响应；题意资格由独立planner证明。"""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system
from test_bounded_api import MemorySession, call, book, JOIN_SQL

DETAIL = 'SELECT h.name AS host_name,v.name AS vm_name FROM CLOUD_HOST h JOIN CLOUD_VM_NOVA v ON v.hostId=h.id'


class EmptyRootProtocolTests(unittest.TestCase):
    def setUp(self):
        context=patch.object(matcher,'_schema_columns',{'HOST':['id','name'],'VM_NOVA':['id','hostId','name']})
        context.start();self.addCleanup(context.stop)

    def run_empty(self, sql=DETAIL, responder=None, schema=None):
        item=book(call('HOST',('name','equal','absent')),sql=sql)
        before=copy.deepcopy(item);cache=copy.deepcopy(executor._cache)
        session=MemorySession({'HOST':[], 'VM_NOVA':[{'id':'v1','hostId':'h1','name':'vm'}]},responder)
        diagnostics={}
        output=system._execute_bounded_api(item,diagnostics,session=session,empty_root_only=True)
        self.assertEqual(item,before);self.assertEqual(executor._cache,cache)
        self.assertEqual([r['ci'] for r in session.requests],['HOST'])
        return output,diagnostics

    def test_verified_empty_root_executes_original_detail_and_count_without_loading_children(self):
        for sql, rows, columns in [(DETAIL,[],['host_name','vm_name']),(JOIN_SQL,[{'count':0}],['count'])]:
            with self.subTest(sql=sql):
                output,diagnostics=self.run_empty(sql)
                self.assertEqual(output['sql'],sql)
                self.assertEqual(output['result']['columns'],columns)
                self.assertEqual(output['result']['rows'],rows)
                self.assertEqual(diagnostics['short_circuit'],'verified_empty_root')
                self.assertTrue(diagnostics['sql_executed'])

    def test_nonempty_root_defers_without_SQL_or_child_reads_and_does_not_write_native_cache(self):
        session=MemorySession({'HOST':[{'id':'h1','name':'found'}]})
        cache=copy.deepcopy(executor._cache);diagnostics={}
        output=system._execute_bounded_api(book(call('HOST'),sql=DETAIL),diagnostics,
                                          session=session,empty_root_only=True)
        self.assertIsNone(output);self.assertEqual(len(session.requests),1)
        self.assertFalse(diagnostics['sql_executed'])
        self.assertEqual(diagnostics['empty_root_outcome'],'nonempty_defer_to_original_executor')
        self.assertEqual(executor._cache,cache)

    def test_HTTP_or_incomplete_empty_response_never_becomes_empty_success(self):
        for response in [SimpleNamespace(status_code=503),
                         SimpleNamespace(status_code=200,json=lambda:{'objList':[],'totalNum':2,'totalPageNo':1,
                                                                     'currentPage':1,'pageSize':10000}),
                         SimpleNamespace(status_code=200,json=lambda:{'objList':[],'totalNum':0,'totalPageNo':0,
                                                                     'currentPage':1,'pageSize':10000,'error':'incomplete'}),
                         SimpleNamespace(status_code=200,json=lambda:{'objList':[],'totalNum':0,'totalPageNo':0,
                                                                     'currentPage':1,'pageSize':10000,'success':False})]:
            with self.subTest(response=response),self.assertRaises(RuntimeError):
                self.run_empty(responder=lambda *args:response)

    def test_outer_union_multiple_calls_and_unused_root_refuse_before_HTTP(self):
        items=[book(call('HOST'),sql=DETAIL.replace('JOIN','LEFT JOIN')),
               book(call('HOST'),sql=DETAIL+' UNION ALL '+DETAIL),
               book(call('HOST'),call('HOST'),sql=DETAIL),
               book(call('HOST'),sql='SELECT name FROM CLOUD_VM_NOVA')]
        for item in items:
            session=MemorySession({'HOST':[]});diagnostics={}
            with self.subTest(item=item),self.assertRaisesRegex(system._APIPlanRefusal,'single_mandatory_root'):
                system._execute_bounded_api(item,diagnostics,session=session,empty_root_only=True)
            self.assertEqual(session.requests,[])

    def test_unknown_empty_table_schema_and_unknown_SQL_field_fail_closed(self):
        with patch.object(matcher,'_schema_columns',{'HOST':['id','name']}), \
                self.assertRaisesRegex(system._APIPlanRefusal,'unknown_empty_table_schema'):
            self.run_empty()
        with self.assertRaisesRegex(system._APIPlanRefusal,'required_sql_field_unavailable'):
            self.run_empty(DETAIL.replace('v.name','v.missing'))

    def test_incomplete_pagination_does_not_prove_empty_even_when_page_is_blank(self):
        bad=SimpleNamespace(status_code=200,json=lambda:{'objList':[],'totalNum':10001,'totalPageNo':2,
                                                        'currentPage':1,'pageSize':10000})
        with self.assertRaisesRegex(RuntimeError,'提前结束分页'):
            self.run_empty(responder=lambda *args:bad)
        for page,size in [(True,10000),(1.0,10000),(1,10000.0),(1,True)]:
            with self.subTest(page=page,size=size),self.assertRaisesRegex(RuntimeError,'分页格式异常'):
                self.run_empty(responder=lambda *args:SimpleNamespace(status_code=200,json=lambda:{
                    'objList':[],'totalNum':0,'totalPageNo':0,'currentPage':page,'pageSize':size}))


if __name__=='__main__':unittest.main()
