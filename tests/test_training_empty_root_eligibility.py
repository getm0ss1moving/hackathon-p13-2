from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from runbook_empty_root import empty_root_eligibility

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'implementation'));sys.path.insert(0,str(ROOT/'tests'))
import runbook_system as system
import runbook_matcher as matcher
from test_bounded_api import MemorySession,call,book


SCHEMA={
 'CLOUD_CCE_CLUSTER':['id','nativeId','name'],
 'CLOUD_CCE_NODE':['id','name','ref_clusterId','clusterId','privateIP','status','managedStatus','cpu'],
 'CLOUD_CCE_POD':['id','name','clusterId','managedStatus'],
 'CLOUD_MODELARTS_INF_SERVICE':['id','name','ref_poolId'],
 'CLOUD_MODELARTS_INF_POOL':['id','name'],
 'CLOUD_MODELARTS_INF_NODE':['id','name','ref_poolId'],
 'SYS_DeployNode':['id','name','mgmtIp'],
 'SYS_DeployInstance':['id','deployNodeId','deployComponentId'],
 'SYS_DeployComponent':['id','serviceId'],
 'SYS_Service':['id','cloudServiceId'],
 'SYS_CloudService':['id','name'],
}
SQL='SELECT DISTINCT n.name AS node_name,n.privateIP AS node_ip,n.status AS status FROM CLOUD_CCE_CLUSTER c INNER JOIN CLOUD_CCE_NODE n ON c.id=n.ref_clusterId'
QUESTION='查询CCE集群cluster_demo下的容器节点列表及节点IP'


def source(value='cluster_demo'):
 return {'api_call':call('CCE_CLUSTER',('name','equal',value)),'sql':SQL}


class EmptyRootEligibilityTests(unittest.TestCase):
 def check(self,question=QUESTION,item=None,schema=None):
  return empty_root_eligibility(question,source() if item is None else item,SCHEMA if schema is None else schema)

 def test_baseline_is_empty_only_and_keeps_API_SQL_and_inputs(self):
  item=source();original=copy.deepcopy(item);result=self.check(item=item)
  self.assertTrue(result['eligible'],result)
  self.assertTrue(result['requires_complete_zero_response']);self.assertFalse(result['may_execute_nonempty'])
  self.assertFalse(result['certifies_positive_join_coverage'])
  self.assertEqual(result['expected_api_call'],item['api_call']);self.assertEqual(result['sql'],SQL)
  self.assertEqual(item,original)

 def test_complete_grammar_rejects_extra_scope_and_unknown_tail(self):
  for tail in ['，区域region_demo','且租户tenant_demo','可用区az0.dc0','以及ECS数量','并只要运行中节点','前十个']:
   with self.subTest(tail=tail):self.assertFalse(self.check(question=QUESTION+tail)['eligible'])

 def test_multiple_entities_OR_negation_not_consumed(self):
  for question in ['查询CCE集群a和b下的容器节点列表及节点IP',
                   '查询CCE集群a或b下的容器节点列表及节点IP',
                   '查询非CCE集群cluster_demo下的容器节点列表及节点IP']:
   with self.subTest(question=question):self.assertFalse(self.check(question=question)['eligible'])

 def test_entity_words_are_opaque_when_role_and_value_match(self):
  for value in ['cluster_OR_LEFT_region_demo','KVM','tenant_demo','“区域region_demo和ECS数量”']:
   actual=value.strip('“”')
   question='查询CCE集群'+value+'下的容器节点列表及节点IP'
   with self.subTest(value=value):self.assertTrue(self.check(question=question,item=source(actual))['eligible'])

 def test_wrong_root_field_CI_or_entity_never_qualifies(self):
  for field,value,ci in [('id','cluster_demo','CCE_CLUSTER'),('name','different','CCE_CLUSTER'),
                         ('name','cluster_demo','MODELARTS_INF_SERVICE')]:
   item=source();item['api_call']=call(ci,(field,'equal',value))
   with self.subTest(field=field,value=value,ci=ci):self.assertFalse(self.check(item=item)['eligible'])

 def test_extra_API_constraint_OR_and_unknown_query_not_ignored(self):
  cases=[]
  item=source();item['api_call']['condition']['constraint'].append({'simple':{'name':'name','value':'other','operator':'equal'},'logOp':'or'});cases.append(item)
  item=source();item['api_call']['condition']['constraint'][0]['logOp']='or';cases.append(item)
  item=source();item['api_call']['url']+='?condition=hidden';cases.append(item)
  item=source();item['api_call']['url']='https://example.invalid'+item['api_call']['url'];cases.append(item)
  for item in cases:self.assertFalse(self.check(item=item)['eligible'])

 def test_only_single_get_and_supported_pagination(self):
  item=source();item['api_call']=[item['api_call'],copy.deepcopy(item['api_call'])]
  self.assertFalse(self.check(item=item)['eligible'])
  for suffix in ['?pageNo=2&pageSize=10000','?pageNo=1&pageNo=1','?pageSize=10']:
   item=source();item['api_call']['url']+=suffix;self.assertFalse(self.check(item=item)['eligible'])
  item=source();item['api_call']['url']+='?pageNo=1&pageSize=10000'
  self.assertTrue(self.check(item=item)['eligible'])

 def test_missing_schema_cannot_be_invented_for_empty_table(self):
  schema=copy.deepcopy(SCHEMA);schema['CLOUD_CCE_NODE'].remove('privateIP')
  self.assertFalse(self.check(schema=schema)['eligible'])
  schema=copy.deepcopy(SCHEMA);schema['CLOUD_CCE_NODE']+=['NAME']
  self.assertFalse(self.check(schema=schema)['eligible'])

 def test_root_filter_field_must_exist_even_if_SQL_only_uses_root_id(self):
  schema=copy.deepcopy(SCHEMA);schema['CLOUD_CCE_CLUSTER'].remove('name')
  result=self.check(schema=schema)
  self.assertFalse(result['eligible']);self.assertEqual(result['reason'],'root_filter_field_unavailable')
  schema=copy.deepcopy(SCHEMA);schema['SYS_DeployNode'].remove('mgmtIp')
  item={'api_call':call('S_DeployNode',('mgmtIp','contain','ip_demo')),
        'sql':'SELECT d.name AS node_name,c.name AS cloud_service_name FROM SYS_DeployNode d JOIN SYS_DeployInstance i ON d.id=i.deployNodeId JOIN SYS_DeployComponent p ON i.deployComponentId=p.id JOIN SYS_Service s ON p.serviceId=s.id JOIN SYS_CloudService c ON s.cloudServiceId=c.id'}
  result=self.check('查询部署节点管理IPip_demo对应的部署节点名称和所属云服务',item,schema)
  self.assertFalse(result['eligible']);self.assertEqual(result['reason'],'root_filter_field_unavailable')

 def test_direct_projection_must_belong_to_requested_node_role(self):
  item=source();item['sql']=SQL.replace('n.name AS node_name','c.name AS node_name')
  self.assertFalse(self.check(item=item)['eligible'])
  item=source();item['sql']=SQL.replace('n.name AS node_name','n.name AS vmName')
  self.assertFalse(self.check(item=item)['eligible'])
  item=source();item['sql']=SQL.replace('n.privateIP AS node_ip,','')
  self.assertFalse(self.check(item=item)['eligible'])

 def test_neutral_unique_alias_is_preserved_but_normalized_collision_refused(self):
  item=source();item['sql']=SQL.replace('AS node_name','AS first').replace('AS node_ip','AS second')
  self.assertTrue(self.check(item=item)['eligible'])
  item['sql']=item['sql'].replace('AS first','AS h_n').replace('AS second','AS hn')
  self.assertFalse(self.check(item=item)['eligible'])

 def test_LEFT_OR_UNION_SUBQUERY_aggregate_and_limit_are_outside_probe(self):
  for sql in [SQL.replace('INNER JOIN','LEFT JOIN'),SQL+' UNION ALL '+SQL,
              SQL+' WHERE n.status=1',SQL+' ORDER BY n.name',SQL+' LIMIT 1',
              SQL.replace('ON c.id=n.ref_clusterId','ON c.id=n.ref_clusterId OR 1=1'),
              'SELECT COUNT(*) AS total FROM CLOUD_CCE_CLUSTER c INNER JOIN CLOUD_CCE_NODE n ON c.id=n.ref_clusterId',
              'SELECT n.name AS node_name FROM (SELECT * FROM CLOUD_CCE_CLUSTER) c JOIN CLOUD_CCE_NODE n ON c.id=n.ref_clusterId']:
   item=source();item['sql']=sql
   with self.subTest(sql=sql):self.assertFalse(self.check(item=item)['eligible'])

 def test_repeated_SQL_CI_and_unconnected_join_refused(self):
  item=source();item['sql']=SQL+' INNER JOIN CLOUD_CCE_CLUSTER c2 ON c2.id=n.ref_clusterId'
  self.assertFalse(self.check(item=item)['eligible'])
  item=source();item['sql']=SQL.replace('ON c.id=n.ref_clusterId','ON c.id=c.nativeId')
  self.assertFalse(self.check(item=item)['eligible'])

 def test_POD_profile_and_role_are_distinct_from_NODE(self):
  item=source();item['sql']='SELECT DISTINCT p.name AS pod_name,p.managedStatus AS status FROM CLOUD_CCE_CLUSTER c JOIN CLOUD_CCE_POD p ON c.nativeId=p.clusterId'
  self.assertTrue(self.check(question='查询CCE集群cluster_demo下的Pod列表',item=item)['eligible'])
  self.assertFalse(self.check(question=QUESTION,item=item)['eligible'])
  item['sql']=item['sql'].replace('AS pod_name','AS node_name')
  self.assertFalse(self.check(question='查询CCE集群cluster_demo下的Pod列表',item=item)['eligible'])

 def test_ModelArts_profile_all_three_roles_needed(self):
  item={'api_call':call('MODELARTS_INF_SERVICE',('name','equal','service_demo')),
        'sql':'SELECT s.name AS service_name,p.name AS pool_name,n.name AS node_name FROM CLOUD_MODELARTS_INF_SERVICE s JOIN CLOUD_MODELARTS_INF_POOL p ON s.ref_poolId=p.id JOIN CLOUD_MODELARTS_INF_NODE n ON p.id=n.ref_poolId'}
  q='查询ModelArts推理服务service_demo及关联资源池和节点'
  self.assertTrue(self.check(q,item)['eligible'])
  item['sql']=item['sql'].replace('n.name AS node_name','s.name AS node_name')
  self.assertFalse(self.check(q,item)['eligible'])

 def test_deployment_IP_is_qualified_role_not_generic_IP(self):
  item={'api_call':call('S_DeployNode',('mgmtIp','contain','ip_demo')),
        'sql':'SELECT d.name AS node_name,d.mgmtIp AS node_ip,c.name AS cloud_service_name FROM SYS_DeployNode d JOIN SYS_DeployInstance i ON d.id=i.deployNodeId JOIN SYS_DeployComponent p ON i.deployComponentId=p.id JOIN SYS_Service s ON p.serviceId=s.id JOIN SYS_CloudService c ON s.cloudServiceId=c.id'}
  for role in ['管理IP','mgmtIp']:
   self.assertTrue(self.check('查询部署节点'+role+'ip_demo对应的部署节点名称和所属云服务',item)['eligible'])
  self.assertFalse(self.check('查询部署节点IPip_demo对应的部署节点名称和所属云服务',item)['eligible'])
  self.assertFalse(self.check('ip_demo这个IP是哪台弹性IP，绑定了哪台ECS',item)['eligible'])
  item['api_call']['condition']['constraint'][0]['simple']['name']='nodeIp'
  self.assertFalse(self.check('查询部署节点管理IPip_demo对应的部署节点名称和所属云服务',item)['eligible'])

 def test_current_bounded_still_fetches_implicit_VM_after_empty_single_root(self):
  schemas={'HOST':['id','name'],'VM_NOVA':['id','name','hostId']}
  item=book(call('HOST',('name','equal','missing')),
            sql='SELECT h.name AS host_name,v.name AS vm_name FROM CLOUD_HOST h JOIN CLOUD_VM_NOVA v ON v.hostId=h.id')
  transport=MemorySession({'HOST':[],'VM_NOVA':[{'id':'v1','name':'demo','hostId':'h1'}]})
  with patch.object(matcher,'_schema_columns',schemas),patch.object(matcher,'llm_ask',side_effect=AssertionError('no model')):
   result=system._execute_bounded_api(item,{},session=transport)
  self.assertEqual(result['result']['rows'],[])
  self.assertEqual([entry['ci'] for entry in transport.requests],['HOST','VM_NOVA'])

 def test_COUNT_zero_belongs_to_existing_bounded_separate_path(self):
  schemas={'FLAVOR':['id','name'],'VM_NOVA':['id','name','flavorId']}
  item=book(call('FLAVOR',('name','equal','flavor_demo')),
            call('VM_NOVA',('flavorId','equal','{{id from step 1}}')),
            sql='SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA v JOIN CLOUD_FLAVOR f ON v.flavorId=f.id')
  transport=MemorySession({'FLAVOR':[{'id':'f1','name':'flavor_demo'},{'id':'f2','name':'flavor_demo'}],'VM_NOVA':[]})
  with patch.object(matcher,'_schema_columns',schemas),patch.object(matcher,'llm_ask',side_effect=AssertionError('no model')):
   result=system._execute_bounded_api(item,{},session=transport)
  self.assertEqual(result['result'],{'columns':['total'],'rows':[{'total':0}],'row_count':1})
  self.assertEqual(len(transport.requests),2)
  self.assertEqual(transport.requests[1]['constraints'][0]['simple']['value'],['f1','f2'])
  self.assertFalse(self.check('规格为flavor_demo的ECS实例目前有多少台',item)['eligible'])


if __name__=='__main__':unittest.main()
