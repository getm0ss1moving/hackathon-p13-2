"""显式132接入的来源、提示、原文prepare与多义务控制；禁止真实网络。"""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runbook_matcher as matcher
import runbook_system as system
from runbook_items import RUNBOOK_ITEMS
from runbook_retriever import Candidate, RunbookRetriever


@unittest.skipUnless(len(RUNBOOK_ITEMS) == 132, '本模块需显式安装固定132候选')
class A132IntakeTests(unittest.TestCase):
    def setUp(self):
        self.flags = patch.dict(os.environ, {'RUNBOOK_A132_CANDIDATE': '1', 'RUNBOOK_EMPTY_ANSWER_FALLBACK': '0'})
        self.flags.start(); self.addCleanup(self.flags.stop)
        self.by_id = {item['id']: item for item in RUNBOOK_ITEMS}

    def fill(self, item_id, question, parameters):
        diagnostics = {}
        item = copy.deepcopy(self.by_id[item_id]); before = copy.deepcopy(item)
        with patch.object(matcher, 'llm_ask', return_value=json.dumps(parameters)) as ask, \
                patch.object(matcher, '_get_table_schemas', return_value='synthetic schemas'), \
                patch.object(matcher, '_refine_sql', side_effect=lambda q, sql, schemas, **kw: sql):
            result = matcher._match_a132_changed(question, item, diagnostics)
        self.assertEqual(item, before)
        ask.assert_called_once()
        return result, diagnostics, ask.call_args.args[0]

    def test_strict_binding_and_all_changed_modules_have_frozen_sources(self):
        source, files, variant = matcher._verify_a132_sources()
        self.assertIn(variant, {'strict','strict_r5'});self.assertEqual(source['template_count'], 132)
        if variant=='strict_r5':
            self.assertEqual(source['retrieval_revision'],'r5')
            self.assertIn('experiments/a_retriever_r5_increment_20261030/MANIFEST.json',files)
        self.assertEqual(sum(bool(x.get('family_id')) for x in RUNBOOK_ITEMS), 26)
        self.assertGreater(len(files), 40)
        entry = matcher._a132_module('unified_prepare')
        self.assertEqual(sum(entry.handles_item(x) for x in RUNBOOK_ITEMS), 12)
        ordinary = next(x for x in RUNBOOK_ITEMS if not x.get('family_id'))
        self.assertFalse(entry.handles_item(ordinary))
        with self.assertRaises(LookupError): entry.prepare_candidate('合成查询', ordinary, {})

    def test_engine_binding_drift_is_rejected(self):
        read = Path.read_bytes
        def changed(path):
            return b'changed' if path.name == 'runbook_retriever.py' and path.parent.name == 'implementation' else read(path)
        with patch.object(Path, 'read_bytes', changed), self.assertRaisesRegex(ValueError, 'binding'):
            matcher._verify_a132_sources()

    def test_compact_f03_metadata_is_restored_at_both_prompt_boundaries(self):
        item = self.by_id['family_f03_spec']; before = copy.deepcopy(item)
        card = matcher._format_runbook_list([item])
        result, diagnostics, prompt = self.fill('family_f03_spec', '查询ECS实例demo_vm的状态和规格',
            {'view':'vm_status_size','filters':{'name':'demo_vm'},'required_filters':['name']})
        self.assertIsNotNone(result, diagnostics)
        self.assertIn('per_view_keys', card);self.assertIn('per_view_keys', prompt)
        self.assertIn('flavor_topk', card);self.assertIn('top_k', prompt)
        self.assertEqual(item, before);self.assertNotIn('examples', item)
        self.assertEqual(result['_expected_result_columns'], ['vm_name','status','vcpuSize','ramSize','diskSize'])

    def test_f02_new_alias_view_is_prompted_and_prepared(self):
        result, diagnostics, prompt = self.fill('family_f02', '查询区域region_demo下各租户各可用区的ECS实例名和IP',
            {'view':'ecs_tenant_zone_ip_alias','filters':{'logicalRegionName':'region_demo'},'required_filters':['logicalRegionName']})
        self.assertIsNotNone(result, diagnostics)
        self.assertIn('ecs_tenant_zone_ip_alias', prompt)
        self.assertIn('tenant_name', result['sql']);self.assertIn('private_ips', result['sql'])

    def test_polite_wrappers_keep_supported_volume_query_and_do_not_drop_extra_obligation(self):
        parameters = {'view':'vm_volumes','filters':{'name':'demo_vm'},'required_filters':['name']}
        base = '查询ECS实例demo_vm挂载的云硬盘列表'
        result, diagnostics, _ = self.fill('family_vm_volume', '麻烦帮我'+base+'，谢谢', parameters)
        self.assertIsNotNone(result, diagnostics)
        self.assertIn('prepare_question_normalization', diagnostics)
        result, _, _ = self.fill('family_vm_volume', '麻烦帮我'+base+'和管理员密码，谢谢', parameters)
        self.assertIsNone(result)

    def test_f03_ordered_projection_normalization_preserves_exact_column_order(self):
        item = self.by_id['family_f03_spec']; parsed={'view':'flavor_topk'}
        prefix='查询所有ECS实例使用最多的前10种规格，'
        right=prefix+'仅依次输出 flavor_name,vcpuSize,ramSize,diskSize,count'
        wrong=prefix+'仅依次输出 count,flavor_name,vcpuSize,ramSize,diskSize'
        self.assertIn('仅输出', matcher._a132_prepare_question(right,item,parsed))
        self.assertEqual(matcher._a132_prepare_question(wrong,item,parsed), wrong)
        quoted='查询ECS实例“仅依次输出flavor_name”的状态和规格'
        self.assertEqual(matcher._a132_prepare_question(quoted,item,parsed), quoted)

    def test_legacy_family_continues_existing_B_route(self):
        item=self.by_id['family_f01']; retriever=SimpleNamespace(retrieve=lambda *a, **k:[Candidate(item['id'],'strong',10,1)])
        ordinary={'id':item['id'],'name':'synthetic','api_call':{},'sql':'SELECT 1'}
        with patch.object(matcher,'llm_ask',return_value='1'), \
                patch.object(matcher,'_match_family_candidate',return_value=ordinary) as old, \
                patch.object(matcher,'_match_a132_changed',side_effect=AssertionError('不能交给12族入口')):
            result=matcher.match_runbook('查询所有ECS实例数量',RUNBOOK_ITEMS,retriever,{})
        self.assertEqual(result,ordinary);old.assert_called_once()

    def test_r4_original_unicode_spans_preserve_same_family_two_entities(self):
        question='查询ECS实例alpha的创建时间；同时查询ECS实例beta的创建时间'
        retriever=RunbookRetriever(RUNBOOK_ITEMS)
        obligations=retriever.retrieve_obligations(question)
        self.assertEqual(len(obligations),2)
        for part in obligations:self.assertEqual(question[part['start']:part['end']],part['text'])
        candidates=retriever.retrieve(question,top_k=None)
        self.assertTrue(any(len(c.obligation_spans)==2 for c in candidates))
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem);instance.retriever=retriever
        calls=[]
        def query(text,diagnostics):
            calls.append(text);diagnostics.update(selected_template='family_f02',llm_calls=[])
            return {'matched_runbook':'same_family','api_call':{'method':'GET','url':'/synthetic'},
                    'sql':'SELECT name FROM synthetic','result':{'columns':['name'],'rows':[],'row_count':0},'error':None}
        with patch.object(instance,'_query',side_effect=query),patch.object(system,'get_llm_events',return_value=[]):
            result=instance.query(question)
        self.assertEqual(len(calls),2);self.assertEqual(len(result['result']),2)
        self.assertEqual(len(result['diagnostics']['obligations']),2)

    def test_failed_subquestion_cannot_be_reported_as_complete(self):
        question='甲；乙'; obligations=[{'start':0,'end':1,'text':'甲'},{'start':2,'end':3,'text':'乙'}]
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        good={'matched_runbook':'same','api_call':None,'sql':'SELECT 1','result':{'columns':['x'],'rows':[],'row_count':0},'error':None}
        bad={'matched_runbook':None,'api_call':None,'sql':None,'result':None,'error':None}
        with patch.object(instance,'_query',side_effect=[good,bad]),patch.object(system,'get_llm_events',return_value=[]):
            result=instance._query_obligations(question,obligations)
        self.assertIsNone(result['matched_runbook'])
        self.assertEqual(result['diagnostics']['rejection']['reason'],'incomplete_obligation')

    def test_invalid_original_span_stops_before_execution(self):
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        with patch.object(instance,'_query') as execute,patch.object(system,'get_llm_events',return_value=[]):
            output=instance._query_obligations('甲乙',[{'start':0,'end':2,'text':'错误原文'}])
        execute.assert_not_called();self.assertIsNone(output['matched_runbook'])

    def test_x86_selection_reaches_model_without_native_requests(self):
        retriever=RunbookRetriever(RUNBOOK_ITEMS)
        with patch.object(matcher,'llm_ask',return_value='0') as model:
            result=matcher.match_runbook('查询区域region_demo下X86服务器列表',RUNBOOK_ITEMS,retriever,{})
        self.assertIsNone(result);model.assert_called_once()

    def test_role_prefix_recovery_preserves_quoted_entity_and_rejects_conflicting_name(self):
        raw = {'view':'ecs_creation_time','filters':{'name':'ECSdemo_unique'},'required_filters':['name']}
        result, diagnostics, prompt = self.fill('family_f02', '查询ECSdemo_unique的创建时间', raw)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['filters']['name'], 'demo_unique')
        self.assertIn('原文保留', prompt)
        result, diagnostics, _ = self.fill('family_f02', '查询名称为“ECSdemo_unique”的ECS实例创建时间', raw)
        self.assertIsNotNone(result, diagnostics)
        self.assertNotIn('parameter_recovery', diagnostics)
        wrong = copy.deepcopy(raw);wrong['filters']['name']='unrelated_vm'
        result, _, _ = self.fill('family_f02', '查询ECSdemo_unique的创建时间', wrong)
        self.assertIsNone(result)

    def test_null_f02_is_recovered_only_when_full_question_has_one_legal_plan(self):
        question='查询租户demo_tenant在区域region_demo可用区az0.dc0中的ECS IP列表'
        result, diagnostics, _ = self.fill('family_f02', question, None)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['filters'],
                         {'tenantName':'demo_tenant','logicalRegionName':'region_demo','azoneName':'az0.dc0'})
        self.assertEqual(diagnostics['parameter_recovery']['additional_model_requests'], 0)
        for extra in ['和管理员密码', '，排除实例bad_vm', '，租户也可以是other_tenant']:
            with self.subTest(extra=extra):
                result, _, _ = self.fill('family_f02', question+extra, None)
                self.assertIsNone(result)

    def test_missing_structural_view_preserves_filters_and_requires_unique_full_question(self):
        raw={'filters':{'tenantName':'SyntheticTenant','logicalRegionName':'region_synthetic'},
             'required_filters':['tenantName','logicalRegionName']}
        question='查询租户SyntheticTenant在区域region_synthetic中的ECS实例列表'
        result,diagnostics,_=self.fill('family_f02',question,raw)
        self.assertIsNotNone(result,diagnostics)
        effective=diagnostics['parameters']['effective']
        self.assertEqual(effective['filters'],raw['filters'])
        self.assertIn('view',effective)
        for wrong in ['和管理员密码','，排除实例bad_vm']:
            self.assertIsNone(self.fill('family_f02',question+wrong,raw)[0])
        bad=copy.deepcopy(raw);bad['filters']['tenantName']='DifferentTenant'
        self.assertIsNone(self.fill('family_f02',question,bad)[0])

    def test_graph_output_alias_as_filter_key_is_repaired_only_by_closed_question_prepare(self):
        question='云服务ExampleService的微服务部署在哪些节点上，节点类型是虚拟机还是物理机'
        raw={'view':'node_cloud_services','filters':{'cloud_service_name':'ExampleService'},
             'required_filters':['cloud_service_name']}
        # 与真实入口一致：只有已获schema证据并启用属性角色保护，VM/PM才是hostClass枚举。
        with patch.dict(os.environ,{'RUNBOOK_RESOURCE_ATTRIBUTE_ROLES':'1'}),\
             patch.object(matcher,'_schema_columns',{'S_DeployNode':['hostClass']}):
            result,diagnostics,_=self.fill('family_deployment_graph',question,raw)
            self.assertIsNotNone(result,diagnostics)
            self.assertEqual(diagnostics['parameters']['effective'],{'view':'service_node_kind',
                'filters':{'indexName':'ExampleService'},'required_filters':['indexName']})
            self.assertEqual(result['api_call']['condition']['constraint'][0]['simple']['operator'],'contain')
            bad=copy.deepcopy(raw);bad['filters']['cloud_service_name']='DifferentService'
            self.assertIsNone(self.fill('family_deployment_graph',question,bad)[0])
            self.assertIsNone(self.fill('family_deployment_graph',question+'和管理员密码',raw)[0])

    def test_vm_status_alias_recovery_does_not_override_opposite_status(self):
        raw={'view':'scoped_vm_ip_flavor','filters':{'logicalRegionName':'region_demo','status':'运行中'},
             'required_filters':['logicalRegionName','status']}
        question='查询区域region_demo下运行中的ECS实例名、IP和所属规格'
        result, diagnostics, _ = self.fill('family_f03_spec', question, raw)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['filters']['status'], 'active')
        raw['filters']['status']='stopped'
        result, _, _ = self.fill('family_f03_spec', question, raw)
        self.assertIsNone(result)

    def test_vdc_role_recovery_preserves_both_scope_filters(self):
        raw={'view':'vdc_scoped_rows','filters':{'vdcName':'VDCdemo_vdc','logicalRegionName':'region_demo'},
             'required_filters':['vdcName','logicalRegionName']}
        result, diagnostics, _ = self.fill('family_volume_rows',
            '查询VDCdemo_vdc在区域region_demo中的云硬盘列表及容量', raw)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['filters'],
                         {'vdcName':'demo_vdc','logicalRegionName':'region_demo'})

    def test_ambiguous_recovery_plans_are_not_chosen(self):
        item = self.by_id['family_f02']
        entry=matcher._a132_module('unified_prepare')
        original=entry.prepare_candidate
        def ambiguous(question, selected, parsed, evidence):
            if parsed is None:return None
            if parsed['filters'] == {'name':'demo_vm'}:
                return dict(id='synthetic',name='synthetic',resources=['VM_NOVA'],api_call={},sql='SELECT '+parsed['view'])
            return original(question, selected, parsed, evidence)
        with patch.object(entry,'prepare_candidate',side_effect=ambiguous):
            result, diagnostics, _ = self.fill('family_f02','查询ECSdemo_vm的创建时间',None)
        self.assertIsNone(result)
        self.assertNotIn('parameter_recovery', diagnostics)

    def test_wrong_known_view_repair_keeps_all_filters_and_unknown_view_rejected(self):
        raw={'view':'ecs_tenant_zone_ip_alias',
             'filters':{'tenantName':'demo_tenant','logicalRegionName':'region_demo','azoneName':'az0.dc0'},
             'required_filters':['tenantName','logicalRegionName','azoneName']}
        question='查询租户demo_tenant在区域region_demo可用区az0.dc0中的ECS IP列表'
        result, diagnostics, _ = self.fill('family_f02', question, raw)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['view'], 'ecs_filtered_list')
        self.assertEqual(diagnostics['parameters']['effective']['filters'], raw['filters'])
        raw['view']='unpublished_view'
        result, _, _ = self.fill('family_f02', question, raw)
        self.assertIsNone(result)

    def test_f02_explicit_format_can_recover_only_identical_natural_plan(self):
        raw={'scope':'filtered','projection':['name','privateIps','status'],'order':'none',
             'filters':{'tenantName':'demo_tenant','logicalRegionName':'region_demo'},
             'required_filters':['tenantName','logicalRegionName']}
        question='查询租户demo_tenant在区域region_demo中的ECS实例列表'
        result, diagnostics, _ = self.fill('family_f02', question, raw)
        self.assertIsNotNone(result, diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['view'], 'ecs_filtered_list')
        self.assertEqual(diagnostics['parameters']['effective']['filters'], raw['filters'])
        for changes in [{'projection':['name','createdAt']}, {'order':'name'},
                        {'scope':'global'}, {'required_filters':['tenantName']}]:
            with self.subTest(changes=changes):
                result, _, _ = self.fill('family_f02', question, dict(raw, **changes))
                self.assertIsNone(result)

    def test_f02_filters_name_array_recovers_only_explicit_bound_keys(self):
        raw={'view':'ecs_ip_tenant','filters':['logicalRegionName','azoneName'],
             'required_filters':['logicalRegionName','azoneName']}
        result, diagnostics, _=self.fill('family_f02',
            '查询区域region_demo可用区az0.dc0中所有ECS的IP列表和租户归属',raw)
        self.assertIsNotNone(result,diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['filters'],
                         {'logicalRegionName':'region_demo','azoneName':'az0.dc0'})
        raw['filters'].append('unknown_field');raw['required_filters'].append('unknown_field')
        result, _, _=self.fill('family_f02',
            '查询区域region_demo可用区az0.dc0中所有ECS的IP列表和租户归属',raw)
        self.assertIsNone(result)

    def test_host_vm_natural_uppercase_status_uses_observed_canonical_enum(self):
        raw={'view':'host_vm_total','filters':{'name':'demo_host','status':'ACTIVE'},
             'required_filters':['name','status']}
        with patch.dict(matcher._schema_values,{'VM_NOVA':{'status':['active','stopped']}}), \
                patch.dict(matcher._schema_columns,{'HOST':['id','name'], 'VM_NOVA':['id','hostId','status']}):
            result, diagnostics, _=self.fill('family_vm_host_path',
                '宿主机demo_host上目前有多少台处于ACTIVE状态的虚拟机',raw)
        self.assertIsNotNone(result,diagnostics)
        self.assertEqual(diagnostics['parameters']['effective']['filters']['status'],'active')
        self.assertEqual(raw['filters']['status'],'ACTIVE')

    def test_f02_null_natural_bare_az_and_new_alias_view_recover(self):
        for question,view in [
            ('az0.dc0里正在跑的ECS有哪些IP，分别属于哪个租户','ecs_ip_tenant'),
            ('查询区域region_demo下各租户在各个可用区中的ECS实例名和IP','ecs_tenant_zone_ip_alias')]:
            with self.subTest(view=view):
                result, diagnostics, _=self.fill('family_f02',question,None)
                self.assertIsNotNone(result,diagnostics)
                self.assertEqual(diagnostics['parameters']['effective']['view'],view)

    def test_existing_vm_port_view_repairs_wrong_subnet_view_without_extra_output(self):
        raw={'view':'vm_port_subnets','filters':{'name':'demo_vm'},'required_filters':['name']}
        result,diagnostics,_=self.fill('family_vm_port_path','查询ECS demo_vm的网卡列表',raw)
        self.assertIsNotNone(result,diagnostics)
        self.assertNotEqual(diagnostics['parameters']['effective']['view'],'vm_port_subnets')

    def test_f01_repeated_count_phrases_reuse_existing_three_bucket_sql(self):
        parameters={'scope':'filtered','group':'azoneName','metrics':'status_counts','count_alias':'count',
                    'label':'none','order':'none','filters':{'vdcName':'demo_vdc','logicalRegionName':'region_demo'},
                    'required_filters':['vdcName','logicalRegionName']}
        question='查询VDCdemo_vdc在区域region_demo中各可用区的ECS运行中数量、停止数量和异常数量'
        matcher._ground_family_parameters(question,'F01',parameters)
        result=matcher._materialize_family(self.by_id['family_f01'],parameters)
        self.assertIn("status NOT IN ('active', 'stopped', 'building')",result['sql'])
        for extra in ['和paused数量','，或VDCother_vdc','，CPU利用率']:
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                matcher._ground_family_parameters(question+extra,'F01',parameters)

    def test_external_access_direction_is_guarded_by_rule_context(self):
        owner={'api_call':{'url':'/rest/hackthon/db/instances/SECURITY_GROUP_RULE',
               'condition':{'constraint':[{'simple':{'name':'direction','value':'{{direction}}'}}]}}}
        self.assertEqual(matcher._semantic_values('安全组demo中哪些规则允许了外部访问，关联多少端口',owner,'direction'),['ingress'])
        for question in ['安全组demo中哪些规则不允许外部访问','查询名称为“规则允许外部访问”的安全组','出站规则允许外部访问']:
            with self.subTest(question=question):
                self.assertNotIn('ingress',matcher._semantic_values(question,owner,'direction'))


if __name__ == '__main__':unittest.main()
