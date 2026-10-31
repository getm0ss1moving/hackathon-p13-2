"""A原合同+B原生绑定的合成语义控制，无真实网络或用例实体。"""
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_cluster_rank_details as b
import runbook_matcher as m

Q='查询可用区az9.lab下ECS数量最多的集群，列出该集群下所有宿主机的vCPU总量和运行中虚拟机'


def item():return {'id':'synthetic','name':'counts','resources':['VM_NOVA','CLUSTER','HOST'],
    'sql':'SELECT clusterName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY clusterName'}


class Reader:
    base='http://synthetic.invalid'
    def __init__(self):
        self.data={'CLUSTER':[{'id':'c','name':'leader','logicalRegionName':'region_lab'}],
            'HOST':[{'id':'h','name':'host','logicalRegionName':'region_lab','totalVcpuCores':10}],
            'M_ClusterContainsPhyHost':[{'id':'e','source_Instance_Id':'c','target_Instance_Id':'h'}]}
        self.data['VM_NOVA']=[dict(id=id,name=id,logicalRegionName='region_lab',azoneName=az,
            clusterId=cluster,hostId=host,status=status,clusterName=label) for id,az,cluster,host,status,label in [
                ('v1','az9.lab','c','h','active','leader'),('v2','az9.lab','c','h','active','leader'),
                ('v3','az_other','c','h','active','leader'),('unknown','az9.lab',None,None,'stopped',None)]]
        self.schemas={ci:list(fields) for ci,fields in b.module().SCHEMA.items()}
        self.schemas['VM_NOVA'].append('clusterName');self.actual_calls=[]
    def fetch(self,call):
        ci=call['url'].split('?')[0].rsplit('/',1)[-1];rows=copy.deepcopy(self.data[ci])
        for e in call.get('condition',{}).get('constraint',[]):
            s=e['simple'];rows=[r for r in rows if r.get(s['name'])==s['value']]
        self.actual_calls.append(copy.deepcopy(call))
        page={'currentPage':1,'pageSize':1000,'totalNum':len(rows),'totalPageNo':int(bool(rows)),'objList':rows}
        return {'rows':rows,'columns':self.schemas[ci],'native_pages':[page],'schema_source':'actual_synthetic_HTTP_schema'}


class ClusterRankTests(unittest.TestCase):
    def run_plan(self,reader=None):
        reader=reader or Reader();p=b.prepare(Q,item(),reader.schemas);self.assertIsNotNone(p)
        details={}
        with patch('runbook_issue3._local_readonly_identity',return_value={'synthetic':'stable'}):
            result=b.execute(p,details,reader)
        return result,details,reader,p

    def test_full_original_question_and_extra_obligations(self):
        reader=Reader();self.assertIsNotNone(b.prepare(Q,item(),reader.schemas))
        self.assertIsNone(b.prepare(Q+'和管理员密码',item(),reader.schemas))
        self.assertIsNone(b.prepare(Q.replace('az9.lab',''),item(),reader.schemas))
        reader.schemas['VM_NOVA'].remove('clusterName');self.assertIsNone(b.prepare(Q,item(),reader.schemas))

    def test_all_details_and_unknown_rank_are_retained_without_cpu_or_vm_fanout(self):
        output,d,reader,p=self.run_plan();rows=output['result']['rows']
        self.assertEqual([(r['clusterName'],r['ecs_count']) for r in rows],[(None,1),('leader',2)])
        details=json.loads(rows[0]['observed_leader_details_json']);self.assertEqual(len(details),3)
        self.assertEqual({r['running_vm_id'] for r in details},{'v1','v2','v3'})
        self.assertTrue(all(r['complete_cluster_host_vcpu']==10 for r in details))
        self.assertEqual(rows[0]['unknown_rank_vm_count'],1);self.assertEqual(rows[0]['scope_max_certified'],0)
        self.assertFalse(d['business_complete']);self.assertEqual(len(reader.actual_calls),5)
        self.assertIsNone(rows[1]['observed_leader_details_json'])
        self.assertLessEqual(len(json.dumps({'api_call':p['api_call'],'sql':p['sql']},ensure_ascii=False,separators=(',',':')).encode()),4096)

    def test_true_empty_scope_does_not_claim_zero_VM_catalog_winner(self):
        reader=Reader();reader.data['VM_NOVA']=[]
        result,_,_,_=self.run_plan(reader);self.assertEqual(result['result']['rows'],[])

    def test_duplicate_context_and_wrong_scoped_population_fail_closed(self):
        reader=Reader();reader.data['VM_NOVA'].append(reader.data['VM_NOVA'][0].copy())
        with self.assertRaisesRegex(ValueError,'preflight'):self.run_plan(reader)
        reader=Reader();original=reader.fetch
        def mismatched(call):
            snap=original(call)
            if call.get('condition'):snap['rows']=[]
            return snap
        reader.fetch=mismatched
        with self.assertRaisesRegex(ValueError,'population_mismatch'):self.run_plan(reader)

    def test_sql_drift_stops_before_HTTP(self):
        reader=Reader();p=b.prepare(Q,item(),reader.schemas);p['sql']='SELECT 1'
        with self.assertRaisesRegex(ValueError,'scope_or_sql_drift'):b.execute(p,{},reader)
        self.assertEqual(reader.actual_calls,[])

    def test_matcher_keeps_selection_refinement_and_rejects_preparation_failure(self):
        original=item();retriever=SimpleNamespace(retrieve=lambda q:[SimpleNamespace(id='synthetic')]);diag={}
        with patch.dict(os.environ,{'RUNBOOK_CLUSTER_RANK_DETAILS':'1','RUNBOOK_A132_CANDIDATE':'0'}), \
             patch.object(m,'_schema_columns',Reader().schemas),patch.object(m,'_get_table_schemas',return_value='synthetic schema'), \
             patch.object(m,'llm_ask',side_effect=lambda p,stage:'1' if stage=='select' else 'SELECT 1') as ask:
            actual=m.match_runbook(Q,[original],retriever,diag)
            self.assertIsNotNone(actual,diag);self.assertIn('observed_leader_details_json',actual['sql'])
            self.assertEqual([c.kwargs['stage'] for c in ask.call_args_list],['select','refine'])
            with patch.object(b,'prepare',side_effect=ValueError('synthetic_budget_block')):
                rejected=m.match_runbook(Q,[original],retriever,diag)
            self.assertIsNone(rejected);self.assertEqual(diag['reason'],'cluster_rank_contract_blocked')


if __name__=='__main__':unittest.main()
