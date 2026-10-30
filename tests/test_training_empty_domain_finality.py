"""只用内存HTTP替身与原SQL；源表会被后步覆盖时不得伪造空答案。"""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as fixed
from test_bounded_api import MemorySession, call, book, JOIN_SQL


class EmptyDomainFinalityTests(unittest.TestCase):
    def setUp(self):
        schema=patch.object(matcher,'_schema_columns',{'HOST':['id','name'],'VM_NOVA':['id','name','hostId']})
        schema.start();self.addCleanup(schema.stop)
        guard=patch.object(matcher,'llm_ask',side_effect=AssertionError('no model'))
        guard.start();self.addCleanup(guard.stop)
        self.data={'HOST':[{'id':'h1','name':'first'},{'id':'h2','name':'second'}],
                   'VM_NOVA':[{'id':'v1','name':'vm1','hostId':'h1'},{'id':'v2','name':'vm2','hostId':'h2'}]}

    def overwritten(self):
        return book(call('HOST',('name','equal','absent')),call('VM_NOVA',('hostId','in','{{id from step 1}}')),
                    call('HOST'),sql=JOIN_SQL)

    def oracle(self,item):
        # 独立载入原字节的执行器，缓存自然冷启动；只替换requests传输，不改任何官方函数。
        spec=importlib.util.spec_from_file_location('untouched_oracle_executor',executor.__file__)
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        session=MemorySession(self.data)
        with patch.object(original.requests,'get',side_effect=session.get):
            output=original.execute(copy.deepcopy(item))
        self.assertIsNone(output['error'],output)
        return output,session

    def test_original_last_write_semantics_require_stopping_before_target(self):
        item=self.overwritten();native,transport=self.oracle(item)
        self.assertEqual(native['result']['rows'],[{'count':2}])
        self.assertEqual([x['ci'] for x in transport.requests],['HOST','VM_NOVA','HOST'])
        session=MemorySession(self.data);diagnostics={}
        with self.assertRaisesRegex(fixed._APIPlanRefusal,'empty_dependency_source_overwritten'):
            fixed._execute_bounded_api(item,diagnostics,session=session)
        self.assertEqual([x['ci'] for x in session.requests],['HOST'])
        self.assertFalse(diagnostics['sql_executed'])

    def test_same_ci_current_target_also_counts_as_source_overwrite(self):
        item=book(call('HOST',('name','equal','absent')),call('HOST',('id','in','{{id from step 1}}')),
                  sql='SELECT COUNT(*) AS count FROM CLOUD_HOST')
        native,_=self.oracle(item);self.assertEqual(native['result']['rows'],[{'count':2}])
        session=MemorySession(self.data);diagnostics={}
        with self.assertRaisesRegex(fixed._APIPlanRefusal,'empty_dependency_source_overwritten'):
            fixed._execute_bounded_api(item,diagnostics,session=session)
        self.assertEqual(len(session.requests),1)

    def test_true_empty_final_inner_join_has_typed_columns_and_zero_later_requests(self):
        empty={**self.data,'HOST':[]};session=MemorySession(empty);diagnostics={}
        sql='SELECT h.name AS host_name,v.name AS vm_name FROM CLOUD_HOST h JOIN CLOUD_VM_NOVA v ON v.hostId=h.id'
        item=book(call('HOST'),call('VM_NOVA',('hostId','in','{{id from step 1}}')),sql=sql)
        cache=copy.deepcopy(executor._cache)
        result=fixed._execute_bounded_api(item,diagnostics,session=session)
        self.assertEqual(result['result'],{'columns':['host_name','vm_name'],'rows':[],'row_count':0})
        self.assertTrue(diagnostics['sql_executed']);self.assertEqual(len(session.requests),1)
        self.assertEqual(executor._cache,cache)

    def test_nonempty_source_keeps_original_latest_table_and_dependent_result(self):
        item=book(call('HOST',('name','equal','first')),call('VM_NOVA',('hostId','in','{{id from step 1}}')),
                  call('HOST'),sql=JOIN_SQL)
        native,_=self.oracle(item);session=MemorySession(self.data)
        result=fixed._execute_bounded_api(item,{},session=session)
        self.assertEqual(result['result'],native['result']);self.assertEqual(result['result']['rows'],[{'count':1}])
        self.assertEqual(len(session.requests),3)

    def test_other_table_repeated_does_not_invalidate_final_empty_source(self):
        item=book(call('HOST'),call('VM_NOVA',('name','equal','absent')),
                  call('HOST',('id','in','{{hostId from step 2}}')),call('HOST'),sql=JOIN_SQL)
        session=MemorySession(self.data);diagnostics={}
        result=fixed._execute_bounded_api(item,diagnostics,session=session)
        self.assertEqual(result['result']['rows'],[{'count':0}])
        self.assertEqual([x['ci'] for x in session.requests],['HOST','VM_NOVA'])
        self.assertEqual(diagnostics['short_circuit'],'empty_inner_join_input')

    def test_failure_cannot_be_claimed_as_verified_empty(self):
        session=MemorySession(self.data,lambda *args:SimpleNamespace(status_code=503))
        diagnostics={}
        with self.assertRaisesRegex(RuntimeError,'HTTP 503'):
            fixed._execute_bounded_api(self.overwritten(),diagnostics,session=session)
        self.assertFalse(diagnostics['sql_executed']);self.assertEqual(len(session.requests),1)

    def test_outer_join_remains_unproven_and_input_not_mutated(self):
        item=book(call('HOST'),call('VM_NOVA',('hostId','in','{{id from step 1}}')),sql=JOIN_SQL.replace('JOIN','LEFT JOIN'))
        original=copy.deepcopy(item);session=MemorySession({**self.data,'HOST':[]})
        with self.assertRaisesRegex(fixed._APIPlanRefusal,'empty_dependency_source'):
            fixed._execute_bounded_api(item,{},session=session)
        self.assertEqual(item,original);self.assertEqual(len(session.requests),1)


if __name__=='__main__':unittest.main()
