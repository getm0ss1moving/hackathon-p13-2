"""CCE真实关系形状的合成守恒检查，无网络、无用例实体。"""
from contextlib import closing
import copy
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_cce_details as c
import runbook_matcher as m
import runbook_system as system

QUESTION='查询区域region_synthetic下CCE集群列表、各集群的节点数量和各集群关联的虚拟机数量'


def item():
    calls=[]
    for ci in c.TABLES:
        call={'method':'GET','url':'/rest/hackthon/db/instances/'+ci+'?pageNo=1&pageSize=10000'}
        if ci!='VM_NOVA':call['condition']={'constraint':[{'simple':{'name':'logicalRegionName','operator':'equal','value':'{{logicalRegionName}}'}}]}
        calls.append(call)
    return {'id':'synthetic_cce_list','name':'synthetic cluster list','resources':list(c.TABLES),'api_call':calls,
            'sql':'SELECT name AS cluster_name, status, clusterType FROM CLOUD_CCE_CLUSTER'}


def schema():return {ci:sorted(fields) for ci,fields in c.FIELDS.items()}


def sql_rows(clusters,nodes,vms):
    with closing(sqlite3.connect(':memory:')) as db:
        db.row_factory=sqlite3.Row
        for ci,rows in zip(c.TABLES,[clusters,nodes,vms]):
            fields=sorted(c.FIELDS[ci]);db.execute('CREATE TABLE '+c.TABLES[ci]+' ('+','.join(f+' TEXT' for f in fields)+')')
            db.executemany('INSERT INTO '+c.TABLES[ci]+' VALUES ('+','.join('?' for _ in fields)+')',[[r.get(f) for f in fields] for r in rows])
        return [dict(r) for r in db.execute(c.compose([('name','cluster_name'),('status','status'),('clusterType','clusterType')]))]


class CCEDetailsTests(unittest.TestCase):
    def setUp(self):
        self.cluster=lambda id,region='region_synthetic':dict(id=id,name='same display name',status='Available',clusterType='VirtualMachine',logicalRegionName=region)
        self.node=lambda id,vm,cluster='c1',region='region_synthetic':dict(id=id,ref_vmId=vm,ref_clusterId=cluster,logicalRegionName=region)
        self.vm=lambda id,region='region_synthetic':dict(id=id,logicalRegionName=region)

    def test_complete_and_unknown_links_do_not_turn_missing_vm_into_zero(self):
        rows=sql_rows([self.cluster('c1')],[self.node('n1','v1'),self.node('n2','missing')],[self.vm('v1')])
        self.assertEqual((rows[0]['node_count'],rows[0]['known_vm_count'],rows[0]['vm_count'],rows[0]['unresolved_vm_node_count']),(2,1,None,1))

    def test_no_nodes_is_verified_zero_and_same_name_clusters_remain_distinct(self):
        rows=sql_rows([self.cluster('c1'),self.cluster('c2')],[],[])
        self.assertEqual(len(rows),2)
        self.assertTrue(all((r['node_count'],r['vm_count'])==(0,0) for r in rows))
        self.assertEqual(sql_rows([],[],[]),[])

    def test_repeated_reference_counts_vm_identity_once_and_cross_region_link_is_unknown(self):
        rows=sql_rows([self.cluster('c1')],[self.node('n1','v1'),self.node('n2','v1')],[self.vm('v1')])
        self.assertEqual((rows[0]['node_count'],rows[0]['vm_count']),(2,1))
        row=sql_rows([self.cluster('c1')],[self.node('n1','v1')],[self.vm('v1','region_else')])[0]
        self.assertEqual((row['known_vm_count'],row['vm_count'],row['unresolved_vm_node_count']),(0,None,1))

    def test_complete_question_shape_and_scope_are_required_without_mutation(self):
        original=item();snapshot=copy.deepcopy(original);prepared=c.prepare(QUESTION,original,schema())
        self.assertIsNotNone(prepared);self.assertEqual(original,snapshot)
        self.assertEqual(prepared['api_call'][0]['condition']['constraint'][0]['simple']['value'],'region_synthetic')
        for q in [QUESTION+'，只统计运行中节点',QUESTION.replace('region_synthetic',''),QUESTION.replace('虚拟机数量','云硬盘数量')]:
            self.assertIsNone(c.prepare(q,original,schema()))
        altered=item();altered['api_call'][2]['condition']={'constraint':[{'simple':{'name':'name','value':'guess','operator':'equal'}}]}
        self.assertIsNone(c.prepare(QUESTION,altered,schema()))
        altered_schema=schema();altered_schema['CCE_NODE'].remove('ref_vmId')
        self.assertIsNone(c.prepare(QUESTION,original,altered_schema))

    def test_identity_types_required_fields_and_scope_guard(self):
        for rows in [[self.node('n','v'),self.node('n','v')],[self.node('n','v',region='region_else')],
                     [dict(id='n')],[self.node('n',[])]]:
            with self.assertRaises(ValueError):c.validate_rows('CCE_NODE',rows,'region_synthetic')
        c.validate_rows('CCE_NODE',[],'region_synthetic')

    def test_declared_sparse_attributes_and_missing_vm_reference_remain_unknown(self):
        raw={'id':'c1','name':'display','logicalRegionName':'region_synthetic'}
        normalized=c.validate_rows('CCE_CLUSTER',[raw],'region_synthetic')[0]
        self.assertNotIn('status',raw);self.assertIsNone(normalized['status']);self.assertIsNone(normalized['clusterType'])
        node=c.validate_rows('CCE_NODE',[{'id':'n','ref_clusterId':'c1','logicalRegionName':'region_synthetic'}],'region_synthetic')[0]
        self.assertIsNone(node['ref_vmId'])
        row=sql_rows([normalized],[node],[])[0]
        self.assertEqual((row['node_count'],row['vm_count'],row['unresolved_vm_node_count']),(1,None,1))

    def test_unassigned_parent_is_not_silently_discarded(self):
        tables={c.TABLES['CCE_CLUSTER']:[self.cluster('c1')],c.TABLES['CCE_NODE']:[self.node('n','v','absent')],c.TABLES['VM_NOVA']:[]}
        with self.assertRaisesRegex(ValueError,'unassigned_node_parent'):c.validate_population(tables)

    def test_bounded_native_path_consumes_real_fetches_and_handles_empty_vm_table(self):
        snapshots={'CCE_CLUSTER':[self.cluster('c1')],'CCE_NODE':[self.node('n1','absent')],'VM_NOVA':[]}
        class Session:
            def get(self,url,**kwargs):
                ci=url.split('?')[0].rsplit('/',1)[-1];rows=snapshots[ci]
                return SimpleNamespace(status_code=200,json=lambda:{'objList':rows,'totalNum':len(rows),
                    'totalPageNo':1 if rows else 0,'currentPage':1,'pageSize':10000})
        prepared=c.prepare(QUESTION,item(),schema());details={}
        with patch.object(m,'_schema_columns',schema()):
            output=system._execute_bounded_api(prepared,details,session=Session(),request_line_limit=4096)
        self.assertTrue(details['sql_executed']);self.assertEqual(details['http_requests'],3)
        self.assertIsNone(output['result']['rows'][0]['vm_count'])
        self.assertFalse(details['cce_population']['complete_vm_counts'])

    def test_existing_matcher_keeps_selection_and_refinement_and_pins_complete_contract(self):
        original=item();retriever=SimpleNamespace(retrieve=lambda q:[SimpleNamespace(id=original['id'])]);diag={}
        with patch.dict(os.environ,{'RUNBOOK_COMPLETE_CCE_DETAILS':'1','RUNBOOK_ISSUE3_CONTRACTS':'0','RUNBOOK_A132_CANDIDATE':'0'}), \
                patch.object(m,'_schema_columns',schema()),patch.object(m,'_get_table_schemas',return_value='synthetic schema'), \
                patch.object(m,'llm_ask',side_effect=lambda p,stage:'1' if stage=='select' else original['sql']) as llm:
            actual=m.match_runbook(QUESTION,[original],retriever,diag)
        self.assertIsNotNone(actual);self.assertIn('unresolved_vm_node_count',actual['sql'])
        self.assertEqual([x.kwargs['stage'] for x in llm.call_args_list],['select','refine'])
        self.assertIn('cce_details_contract',diag)


if __name__=='__main__':unittest.main()
