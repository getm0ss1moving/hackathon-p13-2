"""有限未知人口的排名边界，以及A投影重验/SQL精调不能改变返回对象。"""
import copy
import unittest
from unittest.mock import patch

import runbook_issue3 as c
from runbook_items import RUNBOOK_ITEMS
from test_training_issue3 import Session,QUESTIONS,fixture


class TenantRankingBoundsTests(unittest.TestCase):
    def prepared(self,counts,unknown=0,metric='volume_count'):
        mod=c.module('tenant');ci='VOLUME' if metric=='volume_count' else 'VM_NOVA'
        schemas,rows=fixture('tenant_volume_rank' if metric=='volume_count' else 'tenant_vm_rank')
        template=rows[ci][0];rows[ci]=[]
        for tenant,count in counts.items():
            rows[ci]+=[dict(template,id=f'{tenant}_{i}',tenantId=tenant) for i in range(count)]
        rows[ci]+=[dict(template,id=f'unknown_{i}',tenantId='\u00a0') for i in range(unknown)]
        params={'logicalRegionName':'region_demo','metric':metric,'tie_policy':'all_ties',
                'unknown_tenant_policy':'exclude_with_diagnostic'}
        plan=mod.build(params);packets={}
        for resource in plan['resources']:
            values=rows.get(resource,[])
            packets[resource]=[{'ok':True,'currentPage':1,'pageSize':1000,'totalPageNo':int(bool(values)),
                               'totalNum':len(values),'objList':values}]
        prepared=mod.preflight(params,packets)
        self.assertEqual(prepared['status'],'ready_for_typed_sql',prepared)
        return mod,params,prepared

    def test_unknown_mass_cannot_bridge_strict_gap_but_detail_count_still_unknown(self):
        mod,params,prepared=self.prepared({'alpha':6,'beta':2},3)
        proof,_=c.tenant_ranking_bounds(mod,params,prepared)
        self.assertTrue(proof['leader_identity_certified'])
        self.assertEqual(proof['certificate'],'strict_unknown_mass_gap')
        self.assertFalse(proof['leader_detail_population_complete'])
        self.assertEqual((proof['observed_leader_count_lower_bound'],proof['observed_leader_count_upper_bound']),(6,9))
        # 枚举未知对象分给两已知租户或一个新租户的所有可能分配。
        for a in range(4):
            for b in range(4-a):
                new=3-a-b
                self.assertGreater(6+a,max(2+b,new))

    def test_gap_equality_can_create_tie_and_is_not_certified(self):
        mod,params,prepared=self.prepared({'alpha':5,'beta':2},3)
        proof,_=c.tenant_ranking_bounds(mod,params,prepared)
        self.assertFalse(proof['leader_identity_certified'])
        self.assertEqual(5,2+3)

    def test_unknown_new_tenant_can_overtake_only_known_tenant(self):
        mod,params,prepared=self.prepared({'alpha':2},3)
        proof,_=c.tenant_ranking_bounds(mod,params,prepared)
        self.assertFalse(proof['leader_identity_certified'])
        self.assertEqual(proof['new_unknown_tenant_count_upper_bound'],3)

    def test_complete_ties_preserved_but_unknown_can_break_tie(self):
        for unknown,expected in [(0,True),(1,False)]:
            mod,params,prepared=self.prepared({'alpha':2,'beta':2},unknown)
            proof,_=c.tenant_ranking_bounds(mod,params,prepared)
            self.assertEqual(proof['observed_leader_identities'],['alpha','beta'])
            self.assertEqual(proof['leader_identity_certified'],expected)

    def test_empty_or_all_unknown_population_does_not_invent_leader(self):
        for unknown in [0,4]:
            mod,params,prepared=self.prepared({},unknown)
            proof,_=c.tenant_ranking_bounds(mod,params,prepared)
            self.assertEqual(proof['observed_leader_identities'],[])
            self.assertFalse(proof['leader_identity_certified'])

    def test_same_count_bound_applies_to_VM_population_without_certifying_mounts(self):
        mod,params,prepared=self.prepared({'alpha':6,'beta':1},2,metric='vm_count')
        proof,_=c.tenant_ranking_bounds(mod,params,prepared)
        self.assertEqual(proof['ranked_resource'],'VM_NOVA')
        self.assertTrue(proof['leader_identity_certified'])
        self.assertFalse(proof['leader_detail_population_complete'])

    def test_tampered_projection_rejected_before_bound_is_claimed(self):
        mod,params,prepared=self.prepared({'alpha':3},1)
        prepared['tables']['VOLUME'][0]['tenantId']='different'
        with self.assertRaisesRegex(c.Unsupported,'projection_recheck_failed'):
            c.tenant_ranking_bounds(mod,params,prepared)

    def execute(self,transform):
        schemas,rows=fixture('tenant_volume_rank')
        rows['VOLUME'].append(dict(rows['VOLUME'][0],id='second_volume',name='second'))
        selected={'id':'synthetic','name':'synthetic','resources':['VOLUME']}
        plan=c.prepare_selected(QUESTIONS['tenant_volume_rank'],selected,RUNBOOK_ITEMS,{})
        plan['sql']=transform(plan['sql'])
        diagnostics={};reader=c.NativeReader(diagnostics,session=Session(schemas,rows))
        with patch.object(c,'_local_readonly_identity',return_value={'synthetic':True}):
            return c.execute_plan(plan,RUNBOOK_ITEMS,diagnostics,reader=reader),diagnostics

    def test_refine_cannot_silently_remove_winning_volume(self):
        with self.assertRaisesRegex(c.Unsupported,'changed_A_row_multiset'):
            self.execute(lambda sql:sql+' LIMIT 1')

    def test_row_order_change_preserves_multiset_and_is_accepted(self):
        result,diagnostics=self.execute(lambda sql:sql+' DESC')
        self.assertEqual(result['result']['row_count'],2)
        self.assertTrue(diagnostics['tenant_ranking_bounds']['leader_identity_certified'])


if __name__=='__main__':unittest.main()
