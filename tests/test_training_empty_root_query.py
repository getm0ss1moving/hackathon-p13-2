"""窄空根资格→严格HTTP替身→原SQL；非空与不合资格保持原执行路径。"""
import ast
import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system
from runbook_retriever import RunbookRetriever
from test_bounded_api import MemorySession, call

QUESTION='查询CCE集群demo_cluster下的容器节点列表及节点IP'
SQL=('SELECT n.name AS node_name,n.privateIP AS node_ip,n.status AS status FROM CLOUD_CCE_CLUSTER c '
     'INNER JOIN CLOUD_CCE_NODE n ON c.id=n.ref_clusterId')
SCHEMA={'CCE_CLUSTER':['id','name'],'CCE_NODE':['id','name','privateIP','status','ref_clusterId']}

def selected():
    return {'id':'synthetic_cce_nodes','name':'合成节点清单','description':'CCE集群的容器节点列表及节点IP',
            'examples':[],'resources':['CCE_CLUSTER','CCE_NODE'],
            'api_call':call('CCE_CLUSTER',('name','equal','demo_cluster')),'sql':SQL}


class EmptyRootQueryTests(unittest.TestCase):
    def make_system(self):
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        instance.items=[];instance.retriever=object();return instance

    def query(self,item=None,question=QUESTION,database=None,enabled=True,response=None):
        item=selected() if item is None else item
        session=MemorySession({'CCE_CLUSTER':[]} if database is None else database,
                              responder=(lambda *args:response) if response is not None else None)
        native_result={'sql':item['sql'],'error':None,
                       'result':{'columns':[],'rows':[],'row_count':0}}
        original=system._execute_bounded_api
        def probe(value,diagnostics,**kwargs):return original(value,diagnostics,session=session,**kwargs)
        before=copy.deepcopy(item);cache=copy.deepcopy(executor._cache)
        with patch.dict(os.environ,{'RUNBOOK_BOUNDED_API':'0','RUNBOOK_VERIFIED_EMPTY_ROOT':'1' if enabled else '0'}), \
                patch.object(matcher,'_schema_columns',SCHEMA),patch.object(system,'get_llm_events',return_value=[]), \
                patch.object(system,'match_runbook',return_value=item), \
                patch.object(system,'_execute_bounded_api',side_effect=probe) as bounded, \
                patch.object(system,'execute',return_value=native_result) as native:
            output=self.make_system().query(question)
        self.assertEqual(item,before);self.assertEqual(executor._cache,cache)
        return output,session,bounded,native

    def test_empty_eligible_root_returns_real_columns_without_original_or_child_query(self):
        output,session,bounded,native=self.query()
        self.assertEqual(output['result'],{'columns':['node_name','node_ip','status'],'rows':[],'row_count':0})
        self.assertEqual(output['sql'],SQL);self.assertEqual(output['matched_runbook'],'合成节点清单')
        self.assertEqual([r['ci'] for r in session.requests],['CCE_CLUSTER'])
        native.assert_not_called();bounded.assert_called_once()
        self.assertEqual(output['diagnostics']['verified_empty_root']['short_circuit'],'verified_empty_root')

    def test_positive_root_defers_to_original_executor_instead_of_claiming_join_coverage(self):
        output,session,bounded,native=self.query(database={'CCE_CLUSTER':[{'id':'c1','name':'demo_cluster'}]})
        self.assertEqual(len(session.requests),1);native.assert_called_once();bounded.assert_called_once()
        self.assertFalse(output['diagnostics']['verified_empty_root']['sql_executed'])
        self.assertEqual(output['diagnostics']['verified_empty_root']['empty_root_outcome'],
                         'nonempty_defer_to_original_executor')
        # The synthetic original result lacks schema, so the existing outer result guard still rejects it.
        self.assertIsNone(output['matched_runbook'])
        self.assertEqual(output['diagnostics']['rejection']['reason'],'unverified_result_schema')

    def test_extra_scope_or_wrong_literal_is_not_probed(self):
        wrong=selected();wrong['api_call']['condition']['constraint'][0]['simple']['value']='other_cluster'
        for item,question in [(selected(),QUESTION+'，只看region_extra区域'),(wrong,QUESTION)]:
            with self.subTest(question=question):
                output,session,bounded,native=self.query(item,question)
                self.assertFalse(output['diagnostics']['verified_empty_root_eligibility']['eligible'])
                bounded.assert_not_called();native.assert_called_once();self.assertEqual(session.requests,[])

    def test_probe_protocol_failure_never_falls_back_to_original_empty_error(self):
        with self.assertRaisesRegex(RuntimeError,'HTTP 503'):
            self.query(response=SimpleNamespace(status_code=503))

    def test_default_off_keeps_original_execution_and_cli_freezes_new_helper(self):
        output,session,bounded,native=self.query(enabled=False)
        bounded.assert_not_called();native.assert_called_once();self.assertEqual(session.requests,[])
        self.assertNotIn('verified_empty_root_eligibility',output['diagnostics'])
        source=(Path(__file__).resolve().parents[1]/'scripts/train_live.py').read_text()
        options=[node for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Call)
                 and isinstance(node.func,ast.Attribute) and node.func.attr=='add_argument' and node.args
                 and isinstance(node.args[0],ast.Constant) and node.args[0].value=='--verified-empty-root']
        self.assertEqual(len(options),1)
        self.assertEqual(next(k.value.value for k in options[0].keywords if k.arg=='action'),'store_true')
        self.assertIn('sources.append("implementation/runbook_empty_root.py")',source)

    def test_missing_root_filter_schema_is_ineligible_before_any_probe(self):
        broken={**SCHEMA,'CCE_CLUSTER':['id']}
        with patch.dict(os.environ,{'RUNBOOK_BOUNDED_API':'0','RUNBOOK_VERIFIED_EMPTY_ROOT':'1'}), \
                patch.object(matcher,'_schema_columns',broken),patch.object(system,'get_llm_events',return_value=[]), \
                patch.object(system,'match_runbook',return_value=selected()), \
                patch.object(system,'_execute_bounded_api',side_effect=AssertionError('must not probe')), \
                patch.object(system,'execute',return_value={'sql':SQL,'result':{'columns':[],'rows':[]},'error':None}):
            output=self.make_system().query(QUESTION)
        self.assertFalse(output['diagnostics']['verified_empty_root_eligibility']['eligible'])

    def test_BM25_model_selection_fill_and_refine_still_run_before_empty_execution(self):
        item=selected();item['api_call']['condition']['constraint'][0]['simple']['value']='{{name}}'
        before=copy.deepcopy(item);session=MemorySession({'CCE_CLUSTER':[]});stages=[]
        # BM25的泛词阈值按文档比例计算；单文档会把全部词视为泛词，使用无关合成背景文档。
        background=[dict(item,id='background_'+str(i),description='专用网络账单监管 namespace_'+str(i),examples=[])
                    for i in range(9)]
        instance=self.make_system();instance.items=[item,*background]
        instance.retriever=RunbookRetriever(instance.items)
        self.assertEqual(instance.retriever.retrieve(QUESTION)[0].id,item['id'])
        def ask(prompt,stage):
            stages.append(stage)
            if stage=='select':return '1'
            if stage=='refine':return SQL
            raise AssertionError('Unexpected model stage: '+stage)
        original=system._execute_bounded_api
        flags={name:'0' for name in ['RUNBOOK_BOUNDED_API','RUNBOOK_COMPLETE_IDENTITY_PROJECTION',
            'RUNBOOK_PRUNE_UNUSED_LOOKUPS','RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES','RUNBOOK_COMPLETE_GROUPED_AGGREGATES',
            'RUNBOOK_COMPLETE_NETWORK_DETAILS','RUNBOOK_COMPLETE_VPC_SUBNETS','RUNBOOK_COMPLETE_TENANT_RESOURCES',
            'RUNBOOK_COMPLETE_VM_VOLUME_DETAILS','RUNBOOK_BIND_TENANT_VDC','RUNBOOK_COMPLETE_PARALLEL_LISTS',
            'RUNBOOK_COMPLETE_DETAIL_COUNT','RUNBOOK_PARTIAL_STORAGE_POOLS','RUNBOOK_VALIDATE_API_DEPENDENCIES',
            'RUNBOOK_CALIBRATE_API_LITERAL_ENUMS']}
        flags.update(RUNBOOK_VERIFIED_EMPTY_ROOT='1',RUNBOOK_RULE_ONLY_FILL='1',
                     RUNBOOK_PRESERVE_ROW_SEMANTICS='1',RUNBOOK_PRESERVE_TEMPLATE_COLUMNS='1')
        with patch.dict(os.environ,flags),patch.object(matcher,'_schema_columns',SCHEMA), \
                patch.object(matcher,'_schema_values',{}),patch.object(matcher,'_get_table_schemas',return_value='合成结构'), \
                patch.object(matcher,'llm_ask',side_effect=ask), \
                patch.object(system,'_execute_bounded_api',side_effect=lambda value,diagnostics,**kwargs:
                             original(value,diagnostics,session=session,**kwargs)), \
                patch.object(system,'execute',side_effect=AssertionError('empty root needs no original call')):
            output=instance.query(QUESTION)
        self.assertEqual(stages,['select','refine'])
        self.assertEqual(output['diagnostics']['matching']['parameters']['final']['name'],'demo_cluster')
        self.assertEqual(output['result']['row_count'],0)
        self.assertEqual(output['result']['columns'],['node_name','node_ip','status'])
        self.assertEqual(item,before);self.assertEqual(len(session.requests),1)


if __name__=='__main__':unittest.main()
