"""Synthetic display/SELECT-capture contracts only; never calls a model/service."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import runbook_matcher as matcher
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import Candidate
from a160_fixtures import family_item


def family_fixture(family):
    original = family_item(family)
    return {'id':'family_'+family.lower(), 'family_id':family,
            'name':'属性族'+family, 'description':'只接受已审组合',
            'resources':copy.deepcopy(original['resources']), 'examples':['按名称查创建时间'],
            'parameter_contract':copy.deepcopy(original['parameter_contract'])}


F02_BASE='1. 属性族F02 - 只接受已审组合 [资源类型：VM_NOVA] (示例：按名称查创建时间)'
F19_BASE='1. 属性族F19 - 只接受已审组合 [资源类型：GAUSSDB_INSTANCE] (示例：按名称查创建时间)'


class SelectorCardTests(unittest.TestCase):
    def setUp(self):
        self.f02=family_fixture('F02');self.f19=family_fixture('F19')

    def capture(self, question, items):
        candidates=[Candidate(item['id'],'strong' if i<2 else 'weak',100-i,1-i/100)
                    for i,item in enumerate(items)]
        returned=copy.deepcopy(candidates);calls=[]
        retriever=SimpleNamespace(retrieve=lambda *a,**k: returned)
        def select(prompt,stage):
            self.assertEqual(stage,'select');calls.append(prompt);return '0'
        diagnostics={}
        with patch.object(matcher,'llm_ask',side_effect=select):
            result=matcher.match_runbook(question,items,retriever,diagnostics)
        self.assertIsNone(result);self.assertEqual(diagnostics['reason'],'selector_refused')
        self.assertEqual(candidates,returned)
        self.assertEqual(diagnostics['candidate_ids'],[item['id'] for item in items])
        self.assertEqual(len(calls),1)
        return calls[0],diagnostics

    def test_real_closed_F02_F19_pairings_all_visible_beyond_creation_time(self):
        a=matcher._format_runbook_list([self.f02]);b=matcher._format_runbook_list([self.f19])
        self.assertTrue(a.startswith(F02_BASE));self.assertTrue(b.startswith(F19_BASE))
        self.assertEqual(a.count('←全部等值筛选('),7);self.assertEqual(b.count('←全部等值筛选('),4)
        self.assertIn('输出(name,clusterName,azoneName)←全部等值筛选(name),排序=none',a)
        self.assertIn('输出(tenantName,name,privateIps)←全部等值筛选(vdcName,logicalRegionName,azoneName),排序=tenantName',a)
        self.assertIn('输出(haMode,dataVip)←全部等值筛选(name),排序=none',b)
        self.assertIn('逐条明细，排序不是分组统计',a)

    def test_ordinary_templates_and_unknown_families_keep_exact_legacy_line(self):
        item={'id':'ordinary','name':'普通','description':'原说明','resources':['HOST'],
              'examples':['示例甲','示例乙'],'family_id':'F01',
              'parameter_contract':copy.deepcopy(self.f02['parameter_contract'])}
        expected='1. 普通 - 原说明 [资源类型：HOST] (示例：示例甲; 示例乙)'
        self.assertEqual(matcher._format_runbook_list([item]),expected)
        for family in [None,[],{},0,'F27','future']:
            with self.subTest(family=family):
                item['family_id']=family
                self.assertEqual(matcher._format_runbook_list([item]),expected)

    def test_empty_and_nonmutation(self):
        self.assertEqual(matcher._format_runbook_list([]),'')
        items=[self.f02,self.f19];before=copy.deepcopy(items)
        matcher._format_runbook_list(items)
        self.assertEqual(items,before)

    def test_captured_SELECT_preserves_11_candidate_order_and_no_forced_selection(self):
        ordinary=[{'id':'ordinary_'+str(i),'name':'普通'+str(i),'description':'原说明',
                   'resources':['HOST'],'examples':[]} for i in range(9)]
        items=[ordinary[0],self.f02,*ordinary[1:5],self.f19,*ordinary[5:]]
        prompt,diagnostics=self.capture('查询实例的集群和可用区',items)
        self.assertEqual(len(items),11)
        self.assertIn('2. 属性族F02',prompt);self.assertIn('7. 属性族F19',prompt)
        self.assertIn('11. 普通8',prompt)
        self.assertEqual(diagnostics['selection']['offered_ids'],[i['id'] for i in items])
        self.assertNotIn('selected_id',diagnostics['selection'])

    def test_quoted_and_replaced_entities_change_question_only_not_cards(self):
        questions=['查询ECS unit_alpha的集群和可用区',
                   '查询ECS "unit beta"的集群和可用区',
                   '查询VDC "tenant_name_is_data"下各租户的实例名和IP']
        cards=[]
        for question in questions:
            prompt,_=self.capture(question,[self.f02,self.f19])
            self.assertIn('用户问题：'+question,prompt)
            cards.append(prompt.split('候选手册：\n',1)[1].rsplit('\n输出编号：',1)[0])
        self.assertEqual(cards,[cards[0]]*3)

    def test_cross_profile_pairs_do_not_become_legal_by_individual_field_membership(self):
        bad=[{'projection':['name','createdAt'],'order':'none','filters':['logicalRegionName','azoneName']},
             {'projection':['name','privateIps','tenantName'],'order':'none','filters':['tenantName','logicalRegionName']},
             {'projection':['name','createdAt'],'order':'tenantName','filters':['name']},
             {'projection':['name','createdAt'],'order':'DESC','filters':['name']}]
        for profile in bad:
            with self.subTest(profile=profile):
                item=copy.deepcopy(self.f02);item['parameter_contract']['profiles']=[profile]
                self.assertEqual(matcher._format_runbook_list([item]),F02_BASE)

    def test_F19_contracts_cannot_mix_projection_filter_or_add_a_column(self):
        bad=[{'projection':['name','engineVersion','dataVip'],'order':'none','filters':['name']},
             {'projection':['haMode','dataVip'],'order':'none','filters':['logicalRegionName']},
             {'projection':['name','haMode','dataVip'],'order':'none','filters':['name']}]
        for profile in bad:
            with self.subTest(profile=profile):
                item=copy.deepcopy(self.f19);item['parameter_contract']['profiles']=[profile]
                self.assertEqual(matcher._format_runbook_list([item]),F19_BASE)

    def test_bad_metadata_whole_family_falls_back_without_partial_advertisement(self):
        def changed(**updates):
            item=copy.deepcopy(self.f02);item['parameter_contract'].update(updates);return item
        bad=[changed(scope=['global']),changed(profiles=[]),changed(profiles=None),changed(profiles='name'),
             changed(unknown='unsupported'),dict(self.f02,parameter_contract=None)]
        for profile_change in [dict(projection=['createdAt','name']),dict(projection=['name','name']),
                               dict(filters=[]),dict(filters=['name','name']),dict(filters=['name','status']),
                               dict(filters='name'),dict(order=None),dict(extra='unknown')]:
            item=copy.deepcopy(self.f02);profile=copy.deepcopy(item['parameter_contract']['profiles'][1])
            profile.update(profile_change)
            item['parameter_contract']['profiles']=[item['parameter_contract']['profiles'][0],profile]
            bad.append(item)
        for item in bad:
            with self.subTest(contract=item.get('parameter_contract')):
                self.assertEqual(matcher._format_runbook_list([item]),F02_BASE)

    def test_CI_or_family_mismatch_and_retrieval_attributes_never_advertise_execution(self):
        item=copy.deepcopy(self.f02);item['parameter_contract']=copy.deepcopy(self.f19['parameter_contract'])
        self.assertEqual(matcher._format_runbook_list([item]),F02_BASE)
        item=copy.deepcopy(self.f02);item['resources']=['HOST']
        expected=F02_BASE.replace('VM_NOVA','HOST')
        self.assertEqual(matcher._format_runbook_list([item]),expected)
        item=copy.deepcopy(self.f02);del item['parameter_contract']
        item['retrieval_attributes']={'views':[{'output':'all_unknown_fields','filters':'unbounded'}]}
        self.assertEqual(matcher._format_runbook_list([item]),F02_BASE)

    def test_retrieval_attribute_mutation_does_not_change_valid_card(self):
        before=matcher._format_runbook_list([self.f02])
        self.f02['retrieval_attributes']={'resource_terms':'OTHER','views':[{'output':'class_Name secret','filters':'fake'}]}
        self.assertEqual(matcher._format_runbook_list([self.f02]),before)

    def test_legal_profile_subset_is_not_expanded_and_filter_order_is_not_new_semantics(self):
        item=copy.deepcopy(self.f02)
        item['parameter_contract']['profiles']=[copy.deepcopy(item['parameter_contract']['profiles'][2])]
        card=matcher._format_runbook_list([item]);self.assertEqual(card.count('←全部等值筛选('),1)
        self.assertIn('clusterName',card);self.assertNotIn('输出(name,createdAt)',card)
        item=copy.deepcopy(self.f02);item['parameter_contract']['profiles']=[item['parameter_contract']['profiles'][-1]]
        item['parameter_contract']['profiles'][0]['filters'].reverse()
        self.assertIn('全部等值筛选(azoneName,logicalRegionName,vdcName)',matcher._format_runbook_list([item]))

    def test_two_legal_same_projection_scopes_stay_two_complete_pairs(self):
        item=copy.deepcopy(self.f02)
        item['parameter_contract']['profiles']=copy.deepcopy(item['parameter_contract']['profiles'][3:5])
        card=matcher._format_runbook_list([item]);self.assertEqual(card.count('←全部等值筛选('),2)
        self.assertIn('全部等值筛选(tenantName,logicalRegionName),排序=none',card)
        self.assertIn('全部等值筛选(tenantName,logicalRegionName,azoneName),排序=none',card)
        self.assertNotIn('|',card)


if __name__=='__main__':unittest.main()
