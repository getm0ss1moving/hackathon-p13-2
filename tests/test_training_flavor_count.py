"""规格名称角色与空依赖COUNT；不调用模型/服务，不使用题库实体。"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import runbook_matcher as m
import runbook_system as system


class FlavorCountTests(unittest.TestCase):
    def item(self):
        return {'api_call':[
            {'method':'GET','url':'/rest/hackthon/db/instances/FLAVOR',
             'condition':{'constraint':[{'simple':{'name':'name','value':'{{name}}','operator':'equal'}}]}},
            {'method':'GET','url':'/rest/hackthon/db/instances/VM_NOVA',
             'condition':{'constraint':[{'simple':{'name':'flavorId','value':'{{id from step 1}}','operator':'in'}}]}}],
            'sql':'SELECT COUNT(*) AS total FROM CLOUD_FLAVOR f INNER JOIN CLOUD_VM_NOVA v ON f.id=v.flavorId'}

    def test_flavor_name_is_read_from_its_explicit_question_role(self):
        params={};m._auto_fill_params('规格为flavor-demo的ECS实例有多少台',params,['name'],self.item())
        self.assertEqual(params,{'name':'flavor-demo'})
        for prefix in ['规格ID为','规格编码为','规格类型为']:
            params={};m._auto_fill_params(prefix+'flavor-demo的ECS数量',params,['name'],self.item())
            self.assertNotIn('name',params)

    def test_typed_count_route_does_not_claim_lists_or_left_joins(self):
        self.assertTrue(system._dependent_count_eligibility(self.item()))
        for sql in ['SELECT v.name FROM CLOUD_FLAVOR f JOIN CLOUD_VM_NOVA v ON f.id=v.flavorId',
                    'SELECT COUNT(*) AS total FROM CLOUD_FLAVOR f LEFT JOIN CLOUD_VM_NOVA v ON f.id=v.flavorId',
                    'SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA GROUP BY flavorId']:
            self.assertFalse(system._dependent_count_eligibility(dict(self.item(),sql=sql)))

    def execute(self,first_empty):
        item=self.item();item['api_call'][0]['condition']['constraint'][0]['simple']['value']='flavor-demo'
        calls=[]
        def get(url,**kw):
            calls.append(url)
            rows=[] if first_empty or '/VM_NOVA?' in url else [{'id':'flavor-id-a','name':'flavor-demo'}]
            return SimpleNamespace(status_code=200,json=lambda:{'objList':rows,'totalNum':len(rows),
                'totalPageNo':int(bool(rows)),'currentPage':1,'pageSize':10000})
        with patch.dict(m._schema_columns,{'FLAVOR':['id','name'],'VM_NOVA':['id','flavorId']}):
            result=system._execute_bounded_api(item,{},session=SimpleNamespace(get=get))
        return result,calls

    def test_nonempty_flavor_with_no_vm_is_one_zero_row(self):
        result,calls=self.execute(False)
        self.assertEqual(result['result']['rows'],[{'total':0}]);self.assertEqual(len(calls),2)

    def test_empty_flavor_stops_before_vm_and_count_still_has_zero_row(self):
        result,calls=self.execute(True)
        self.assertEqual(result['result']['rows'],[{'total':0}]);self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
