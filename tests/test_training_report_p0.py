"""报告中的失败形态注入：使用新实体，不调用模型、网络或参考答案。"""
import copy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runbook_matcher as m
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import Candidate


class ReportP0Tests(unittest.TestCase):
    def setUp(self):
        self.items={x['id']:x for x in RUNBOOK_ITEMS}
        context=patch.dict(os.environ,{'RUNBOOK_A132_CANDIDATE':'1','RUNBOOK_ISSUE3_CONTRACTS':'0',
            'RUNBOOK_ISSUE4_NETWORK':'0','RUNBOOK_ISSUE4_VM_LINKS':'0','RUNBOOK_ISSUE4_AZ_COUNTS':'0',
            'RUNBOOK_CLUSTER_RANK_DETAILS':'0','RUNBOOK_COMPLETE_CCE_DETAILS':'0','RUNBOOK_VDC_RESOURCE_COUNTS':'0'})
        context.start();self.addCleanup(context.stop)

    def fill(self,family,q,params):
        item=next(x for x in RUNBOOK_ITEMS if x.get('family_id')==family);diag={}
        with patch.object(m,'llm_ask',return_value=json.dumps(params)), \
                patch.object(m,'_get_table_schemas',return_value='synthetic'), \
                patch.object(m,'_refine_sql',side_effect=lambda q,sql,*a,**kw:sql):
            result=(m._match_a132_changed(q,item,diag) if m._a132_module('unified_prepare').handles_item(item)
                    else m._match_a160_candidate(q,item,diag) if family=='NEXT_N28'
                    else m._match_family_candidate(q,item,diag))
        return result,diag

    def test_wrong_management_group_is_repaired_from_explicit_dimension(self):
        params={'scope':'filtered','group':'none','metrics':'count','count_alias':'total',
                'label':'none','order':'none','filters':{'logicalRegionName':'region_lab8'},'required_filters':['logicalRegionName']}
        result,diag=self.fill('F01','区域region_lab8下管理虚拟机和租户虚拟机分别有多少',params)
        self.assertIsNotNone(result,diag);self.assertIn('GROUP BY management',result['sql'])
        self.assertEqual(diag['family_group_recovery']['to'],'management')
        for q in ['查询区域region_lab8下ECS总数','查询区域region_lab8下仅管理虚拟机有多少台']:
            result,diag=self.fill('F01',q,params)
            self.assertIsNotNone(result,diag);self.assertNotIn('GROUP BY management',result['sql'])

    def test_null_region_is_filled_but_conflicting_nonempty_region_is_rejected(self):
        params={'scope':'filtered','metrics':'count_sum','filters':{'logicalRegionName':None},'required_filters':['logicalRegionName']}
        q='查询区域region_lab8下各VDC的云硬盘数量和总容量'
        result,diag=self.fill('F14',q,params)
        self.assertIsNotNone(result,diag);self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'],'region_lab8')
        params['filters']['logicalRegionName']='region_other'
        self.assertIsNone(self.fill('F14',q,params)[0])

    def test_internal_fragment_recovers_entire_opaque_ip_but_unrelated_value_does_not(self):
        q='@alpha:19@be.ta-2@这个IP是哪台虚拟机的，它跑在哪台宿主机上'
        params={'view':'private_ip_host','filters':{'privateIps':'alpha:19'},'required_filters':['privateIps']}
        result,diag=self.fill('family_vm_host_path',q,params)
        self.assertIsNotNone(result,diag)
        self.assertEqual(diag['parameters']['effective']['filters']['privateIps'],'@alpha:19@be.ta-2@')
        params['filters']['privateIps']='unrelated'
        self.assertIsNone(self.fill('family_vm_host_path',q,params)[0])
        self.assertIsNone(self.fill('family_vm_host_path',q+'和管理员密码',None)[0])

    def test_unique_full_hardware_contract_excludes_partial_status_template(self):
        q='查询区域region_lab8可用区az7.dc9中所有宿主机的主机名、IP、vCPU总量、已分配vCPU和CPU架构'
        hardware=self.items['family_host_hardware'];partial=next(x for x in RUNBOOK_ITEMS if x['id']=='rb_060')
        choices=[partial,hardware];before=copy.deepcopy(choices)
        actual,proof=m._closed_supported_selection(q,choices)
        self.assertEqual(actual,[hardware]);self.assertEqual(choices,before)
        self.assertEqual(proof['parameters']['view'],'host_resources_arch')
        for bad in [q+'和管理员密码',q.replace('region_lab8','region_lab8或region_else')]:
            self.assertIsNone(m._closed_supported_selection(bad,choices)[1])
        retriever=SimpleNamespace(retrieve=lambda *a,**kw:[Candidate(x['id'],'strong',10,1) for x in choices])
        diag={}
        def response(prompt,stage):
            return '2' if stage=='select' else json.dumps({'view':'host_resources_arch','filters':{'logicalRegionName':'region_lab8','azoneName':'az7.dc9'},'required_filters':['logicalRegionName','azoneName']})
        with patch.object(m,'llm_ask',side_effect=response),patch.object(m,'_get_table_schemas',return_value='synthetic'), \
                patch.object(m,'_refine_sql',side_effect=lambda q,sql,*a,**kw:sql):
            result=m.match_runbook(q,choices,retriever,diag)
        self.assertIsNotNone(result,diag);self.assertEqual(result['id'],hardware['id'])
        self.assertNotIn('status',json.dumps(result['api_call']))

    def test_schema_response_and_wrong_VDC_group_use_unchanged_complete_count_parser(self):
        for q,params in [
            ('查询区域region_lab8所有VDC中各VDC的ECS数量、云硬盘数量和VPC数量',{'type':'object','properties':{}}),
            ('查询区域region_lab8下各VDC的VPC数量',{'resource_set':['ROUTER'],'group':'none','layout':'single_scalar','metric':'count_rows','filters':{'logicalRegionName':'region_lab8'},'required_filters':['logicalRegionName']})]:
            result,diag=self.fill('NEXT_N28',q,params)
            self.assertIsNotNone(result,diag);self.assertIn('GROUP BY vdcName',result['sql'])
            self.assertIn('family_parameter_recovery',diag)


if __name__=='__main__':unittest.main()
