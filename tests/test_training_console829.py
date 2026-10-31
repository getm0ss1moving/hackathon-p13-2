"""控制台退步形态的合成注入；不读取题目或答案，不访问网络。"""
import copy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runbook_matcher as m
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import Candidate


class ConsoleRegressionTests(unittest.TestCase):
    def setUp(self):
        self.items={item['id']:item for item in RUNBOOK_ITEMS}
        flags=patch.dict(os.environ,{'RUNBOOK_A132_CANDIDATE':'1','RUNBOOK_ISSUE3_CONTRACTS':'0',
            'RUNBOOK_ISSUE4_NETWORK':'0','RUNBOOK_ISSUE4_VM_LINKS':'0','RUNBOOK_ISSUE4_AZ_COUNTS':'0'})
        flags.start();self.addCleanup(flags.stop)

    def fill(self,item_id,question,parameters):
        item=self.items[item_id];before=copy.deepcopy(item);diag={}
        with patch.object(m,'llm_ask',return_value=json.dumps(parameters)) as ask, \
                patch.object(m,'_get_table_schemas',return_value='synthetic'), \
                patch.object(m,'_refine_sql',side_effect=lambda q,s,*a,**k:s):
            result=(m._match_a132_changed(question,item,diag) if item_id=='family_gauss_compute_path'
                    else m._match_family_candidate(question,item,diag))
        self.assertEqual(before,item);ask.assert_called_once()
        return result,diag

    def test_named_gauss_null_uses_complete_original_question_contract(self):
        q='查询GaussDB实例lab-db-17使用的ECS实例'
        result,diag=self.fill('family_gauss_compute_path',q,None)
        self.assertIsNotNone(result,diag)
        self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'],'lab-db-17')
        self.assertIn('CLOUD_GAUSSDB_NODE.ref_vmbmsId = CLOUD_VM_NOVA.id',result['sql'])
        for bad in [q+'和管理员密码',q.replace('lab-db-17','指定'),q+'，实例名包含lab']:
            self.assertIsNone(self.fill('family_gauss_compute_path',bad,None)[0])

    def test_unique_gauss_contract_recovers_selector_zero_with_other_partial_candidate(self):
        q='查询GaussDB实例lab-db-17使用的ECS实例'
        choices=[self.items['family_f19'],self.items['family_gauss_compute_path']]
        retriever=SimpleNamespace(retrieve=lambda *a,**k:[Candidate(x['id'],'strong',2,1) for x in choices])
        diag={}
        with patch.object(m,'llm_ask',side_effect=['0','null']), \
                patch.object(m,'_get_table_schemas',return_value='synthetic'), \
                patch.object(m,'_refine_sql',side_effect=lambda q,s,*a,**k:s):
            result=m.match_runbook(q,choices,retriever,diag)
        self.assertIsNotNone(result,diag);self.assertEqual(result['id'],'family_gauss_compute_path')

    def test_obs_null_and_null_region_recover_both_views_but_not_conflicting_entities(self):
        for suffix,view in [('OBS桶列表','rows'),('各租户的OBS桶数量','tenant_count')]:
            q='查询区域region_lab17下'+suffix
            for params in [None,{'scope':'filtered','view':view,'filters':{'logicalRegionName':None},
                                 'required_filters':['logicalRegionName']}]:
                result,diag=self.fill('family_f27',q,params)
                self.assertIsNotNone(result,diag)
                self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['value'],'region_lab17')
                self.assertEqual('GROUP BY tenantName' in result['sql'],view=='tenant_count')
            conflict={'scope':'filtered','view':view,'filters':{'logicalRegionName':'region_else'},
                      'required_filters':['logicalRegionName']}
            self.assertIsNone(self.fill('family_f27',q,conflict)[0])
        for q in ['查询区域region_lab17或region_other下OBS桶列表','查询整个Region下OBS桶列表',
                  '查询区域region_lab17下OBS桶列表和总容量','查询区域region_lab17下OBS桶列表，只返回name']:
            self.assertIsNone(self.fill('family_f27',q,None)[0])

    def test_obs_complete_contract_recovers_selector_zero(self):
        q='查询区域region_lab17下OBS桶列表';item=self.items['family_f27'];diag={}
        retriever=SimpleNamespace(retrieve=lambda *a,**k:[Candidate(item['id'],'strong',2,1)])
        with patch.object(m,'llm_ask',side_effect=['0','null']), \
                patch.object(m,'_get_table_schemas',return_value='synthetic'), \
                patch.object(m,'_refine_sql',side_effect=lambda q,s,*a,**k:s):
            result=m.match_runbook(q,[item],retriever,diag)
        self.assertIsNotNone(result,diag)
        self.assertEqual(result['sql'],'SELECT name, bucketName, managedStatus FROM CLOUD_OBS_BUCKET')

    def test_vdc_vm_count_restores_declared_default_label_without_touching_explicit_projection(self):
        params={'scope':'filtered','group':'vdcName','metrics':'count','count_alias':'count',
                'label':'none','order':'none','filters':{'logicalRegionName':'region_lab17'},
                'required_filters':['logicalRegionName']}
        q='查询区域region_lab17下各VDC的ECS数量'
        result,diag=self.fill('family_f01',q,params)
        self.assertIsNotNone(result,diag);self.assertIn("'ECS' AS type",result['sql'])
        self.assertIn('GROUP BY vdcName',result['sql'])
        for explicit in [q+'，只返回vdcName和count',q+'，不要type标签列']:
            unchanged,proof=m._restore_default_count_label(explicit,'F01',params)
            self.assertEqual(unchanged,params);self.assertIsNone(proof)
            result,diag=self.fill('family_f01',explicit,params)
            if result is not None:self.assertNotIn('AS type',result['sql'])


if __name__=='__main__':unittest.main()
