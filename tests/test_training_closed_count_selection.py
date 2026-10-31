"""原文全消费的已有N28合同证明；保留选择/填参/精调调用，拒绝额外义务。"""
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_matcher as m
from runbook_items import RUNBOOK_ITEMS

QUESTION='查询区域region_lab7所有VDC中各VDC的ECS数量、云硬盘数量和VPC数量'


class ClosedSelectionTests(unittest.TestCase):
    def setUp(self):
        self.closed={'id':'synthetic_closed','family_id':'NEXT_N28','name':'closed counts','resources':['VM_NOVA','VOLUME','ROUTER'],'sql':''}
        self.partial={'id':'synthetic_partial','name':'partial VM count','resources':['VM_NOVA','VOLUME','ROUTER'],
                      'sql':'SELECT azoneName,COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY azoneName'}

    def test_only_a_unique_retrieved_complete_contract_can_filter_selection(self):
        offered=[self.partial,self.closed];original=copy.deepcopy(offered)
        actual,proof=m._closed_count_selection(QUESTION,offered)
        self.assertEqual(actual,[self.closed]);self.assertEqual(offered,original)
        self.assertEqual(proof['parameters']['group'],'vdcName')
        for candidates in [[self.partial],[self.closed,dict(self.closed,id='another_closed')]]:
            self.assertIsNone(m._closed_count_selection(QUESTION,candidates)[1])

    def test_extra_output_or_negated_filter_cannot_be_discarded_to_fit_contract(self):
        for question in [QUESTION+'和管理员密码',QUESTION.replace('region_lab7','region_lab7或region_else')]:
            actual,proof=m._closed_count_selection(question,[self.partial,self.closed])
            self.assertIsNone(proof);self.assertEqual(len(actual),2)

    def test_null_fill_and_invalid_selector_recover_from_unique_full_question_contract(self):
        schema={ci:['id','logicalRegionName','vdcName','azoneName'] for ci in ['VM_NOVA','VOLUME','ROUTER']}
        retriever=SimpleNamespace(retrieve=lambda q:[SimpleNamespace(id=x['id']) for x in [self.partial,self.closed]])
        diag={}
        with patch.dict(os.environ,{'RUNBOOK_A132_CANDIDATE':'0','RUNBOOK_ISSUE3_CONTRACTS':'0'}), \
             patch.object(m,'_schema_columns',schema),patch.object(m,'_get_table_schemas',return_value='synthetic schemas'), \
             patch.object(m,'llm_ask',side_effect=lambda p,stage:'4' if stage=='select' else 'null' if stage=='family_fill' else 'SELECT 1') as ask:
            result=m.match_runbook(QUESTION,[self.partial,self.closed],retriever,diag)
        self.assertIsNotNone(result,diag)
        self.assertEqual(diag['selection']['model_index'],4);self.assertEqual(diag['selection']['effective_index'],1)
        self.assertEqual(len(result['api_call']),3);self.assertIn('CLOUD_VOLUME',result['sql']);self.assertIn('CLOUD_ROUTER',result['sql'])
        self.assertEqual([call.kwargs['stage'] for call in ask.call_args_list],['select','family_fill','refine'])

    def test_f02_null_response_with_adjacent_scope_uses_existing_complete_prepare(self):
        item=next(x for x in RUNBOOK_ITEMS if x.get('family_id')=='F02');diag={}
        with patch.object(m,'llm_ask',return_value='null'),patch.object(m,'_get_table_schemas',return_value='synthetic'), \
             patch.object(m,'_refine_sql',side_effect=lambda q,sql,s,**kw:sql):
            actual=m._match_a132_changed('查询VDCdemo_vdc在区域region_lab7可用区az0.dc0中各租户的ECS实例名和IP',item,diag)
        self.assertIsNotNone(actual,diag);self.assertIn('ORDER BY tenantName',actual['sql'])
        values=[e['simple']['value'] for e in actual['api_call']['condition']['constraint']]
        self.assertEqual(set(values),{'demo_vdc','region_lab7','az0.dc0'})


if __name__=='__main__':unittest.main()
