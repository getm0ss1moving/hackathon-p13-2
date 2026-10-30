"""真实system.query接线，纯模型/执行器替身；无题库或网络。"""
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_system as fixed
import runbook_executor as executor


class ResultSchemaTests(unittest.TestCase):
    def test_legitimate_empty_select_and_zero_count_keep_columns(self):
        for result in [{'columns':['name'], 'rows':[], 'row_count':0},
                       {'columns':['count'], 'rows':[{'count':0}], 'row_count':1},
                       [{'columns':['name'], 'rows':[], 'row_count':0},
                        {'columns':['count'], 'rows':[{'count':0}], 'row_count':1}]]:
            with self.subTest(result=result):
                self.assertTrue(fixed._execution_has_result_columns(result))

    def test_empty_or_missing_column_schema_cannot_prove_success(self):
        for result in [None, [], {}, {'columns':[],'rows':[],'row_count':0},
                       {'columns':None}, {'columns':['']}, {'columns':['  ']}, {'columns':[1]},
                       [{'columns':['name']}, {'columns':[],'rows':[]}]]:
            with self.subTest(result=result):
                self.assertFalse(fixed._execution_has_result_columns(result))

    def query(self, result, error=None, bounded=False):
        system = fixed.RunbookQuerySystem.__new__(fixed.RunbookQuerySystem)
        system.items=[]; system.retriever=object()
        item={'name':'合成例','api_call':{'method':'GET','url':'/unused'},'sql':'SELECT name FROM CLOUD_HOST'}
        execution={'sql':item['sql'],'result':copy.deepcopy(result),'error':error}
        original=copy.deepcopy(execution)
        with patch.dict(os.environ,{'RUNBOOK_BOUNDED_API':'1' if bounded else '0', 'RUNBOOK_EMPTY_ANSWER_FALLBACK':'0'}), \
                patch.object(fixed,'match_runbook',return_value=item), \
                patch.object(fixed,'get_llm_events',return_value=[]), \
                patch.object(fixed,'execute',return_value=execution) as native, \
                patch.object(fixed,'_execute_bounded_api',return_value=execution) as bound:
            output=system.query('合成问题')
        self.assertEqual(execution,original)
        self.assertEqual(native.call_count,0 if bounded else 1)
        self.assertEqual(bound.call_count,1 if bounded else 0)
        return output

    def test_query_refuses_silent_missing_column_style_output(self):
        output=self.query({'columns':[],'rows':[],'row_count':0})
        self.assertIsNone(output['matched_runbook']);self.assertIsNone(output['result'])
        self.assertEqual(output['diagnostics']['rejection'],{'stage':'execution','reason':'unverified_result_schema'})
        self.assertEqual(output['diagnostics']['execution']['status'],'rejected')

    def test_query_accepts_legitimate_empty_rows_without_renaming_columns(self):
        result={'columns':['name'],'rows':[],'row_count':0}
        output=self.query(result)
        self.assertEqual(output['result'],result);self.assertEqual(output['matched_runbook'],'合成例')
        self.assertNotIn('rejection',output['diagnostics'])

    def test_bounded_typed_empty_is_valid_but_schema_less_output_is_not(self):
        good={'columns':['host_name','vm_name'],'rows':[],'row_count':0}
        self.assertEqual(self.query(good,bounded=True)['result'],good)
        self.assertIsNone(self.query({'columns':[],'rows':[],'row_count':0},bounded=True)['matched_runbook'])

    def test_explicit_engine_error_preserves_original_failure(self):
        output=self.query(None,error='explicit synthetic SQL error')
        self.assertEqual(output['error'],'explicit synthetic SQL error')
        self.assertEqual(output['matched_runbook'],'合成例')
        self.assertNotIn('rejection',output['diagnostics'])

    def test_multi_statement_with_one_invalid_schema_is_not_a_complete_answer(self):
        output=self.query([{'columns':['count'],'rows':[{'count':2}],'row_count':1},
                           {'columns':[],'rows':[],'row_count':0}])
        self.assertIsNone(output['matched_runbook'])

    def test_native_memory_select_empty_rows_still_has_schema(self):
        db=executor.load_into_sqlite({'CLOUD_HOST':[{'id':'h1','name':'demo'}]})
        try:
            cursor=db.execute("SELECT name FROM CLOUD_HOST WHERE id='absent'")
            result={'columns':[d[0] for d in cursor.description],'rows':cursor.fetchall(),'row_count':0}
            self.assertTrue(fixed._execution_has_result_columns(result))
        finally:
            db.close()

    def test_native_swallowed_column_failure_is_rejected_at_query_boundary(self):
        spec=importlib.util.spec_from_file_location('unmodified_original_executor',executor.__file__)
        native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
        with patch.object(native,'_execute_api_call',return_value={'CLOUD_HOST':[]}):
            actual=native.execute({'api_call':{},'sql':'SELECT name FROM CLOUD_HOST'})
        self.assertIsNone(actual['error']);self.assertEqual(actual['result']['columns'],[])
        output=self.query(actual['result'])
        self.assertIsNone(output['matched_runbook'])


if __name__=='__main__':
    unittest.main()
