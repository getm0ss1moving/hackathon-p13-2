"""A合同的B原生回执/预检/typed SQL接入，合成HTTP替身，无真实网络/模型。"""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit

import runbook_issue3 as c
import runbook_system as system
from runbook_items import RUNBOOK_ITEMS


class Session:
    def __init__(self,schemas,rows,*,status=200,corrupt=False,ignore_scope=False):
        self.schemas=schemas;self.rows=rows;self.status=status;self.corrupt=corrupt;self.ignore_scope=ignore_scope
        self.calls=[]

    def get(self,url,**kwargs):
        self.calls.append(url);parsed=urlsplit(url);ci=parsed.path.rsplit('/',1)[-1]
        if '/schema/' in parsed.path:
            body={'ci_name':ci,'columns':self.schemas[ci]}
        else:
            query=parse_qs(parsed.query);page=int(query['pageNo'][0]);size=int(query['pageSize'][0])
            rows=copy.deepcopy(self.rows.get(ci,[]))
            if query.get('condition') and not self.ignore_scope:
                condition=json.loads(query['condition'][0])
                for entry in condition['constraint']:
                    simple=entry['simple'];rows=[r for r in rows if r.get(simple['name'])==simple['value']]
            total=len(rows)
            body={'currentPage':page,'pageSize':size,'totalNum':total,'totalPageNo':(total+size-1)//size,
                  'objList':rows[(page-1)*size:page*size]}
            if self.corrupt:body['currentPage']+=1
        return SimpleNamespace(status_code=self.status,json=lambda:body)


QUESTIONS={
 'vdc_counts':'查询区域region_demo下各VDC的ECS数量、云硬盘数量和GaussDB实例数量',
 'vdc_network':'查询VDCdemo_vdc在区域region_demo中的VPC名称、子网CIDR和弹性IP数量',
 'tenant_lists':'查询租户demo_tenant的ECS实例列表、安全组列表和云硬盘列表',
 'network':'查询VDCdemo_vdc在区域region_demo中各VPC的子网数量和弹性IP数量',
 'tenant_vm_rank':'查询区域region_demo下ECS数量最多的租户，列出该租户下所有ECS的IP和挂载云硬盘',
 'tenant_volume_rank':'查询区域region_demo下云硬盘数量最多的租户，列出该租户的云硬盘名称和容量',
 'capacity':'查询区域region_demo下各VDC的ECS总vCPU核数、云硬盘总容量和GaussDB节点总数',
 'namespace_counts':'查询区域region_demo下GaussDB实例数量、中间件实例数量和OBS桶数量'}


def fixture(kind):
    if kind=='namespace_counts':
        schemas={'AZONE':['id','logicalRegionName','logicalRegionId'],'MIDDLEWARE':['id','logicalRegionId'],
                 'GAUSSDB_INSTANCE':['id','logicalRegionName'],'OBS_BUCKET':['id','logicalRegionName']}
    elif kind.startswith('tenant_') and kind!='tenant_lists':
        m=c.module('tenant');schemas={ci:list(columns) for ci,columns in m.SCHEMAS.items()}
    elif kind=='capacity':schemas={ci:list(keys) for ci,keys in c.module(kind).REQUIRED_COLUMNS.items()}
    elif kind=='vdc_counts':
        m=c.module(kind);schemas={ci:list(m.COLUMNS) for ci in m.RESOURCES}
    elif kind=='tenant_lists':
        schemas={ci:['id','name','tenantName'] for ci in c.module(kind).RESOURCES}
    else:schemas={ci:list(keys) for ci,keys in c.module(kind).COLUMNS.items()}
    if kind=='vdc_network':schemas['SUBNET'].append('name')
    if kind=='tenant_lists':schemas['VOLUME']+=['size','status']
    rows={}
    for ci,columns in schemas.items():
        row={key:'x' for key in columns}
        values={'id':ci+'_id','logicalRegionName':'region_demo','logicalRegionId':'rid','vdcName':'demo_vdc',
                'name':ci+'_name','tenantName':'demo_tenant','tenantId':'tenant_id','size':'7','vcpuSize':'2','cidr':'198.51.100.0/24',
                'nativeId':'router_native','devNativeId':'router_native','routerId':'ROUTER_id',
                'portId':'PORT_id','subnetId':'SUBNET_id','vmId':'VM_NOVA_id','volumeId':'VOLUME_id','flavorId':'FLAVOR_id'}
        row.update({key:value for key,value in values.items() if key in columns});rows[ci]=[row]
    return schemas,rows


class Issue3Tests(unittest.TestCase):
    def plan(self,kind):
        parsed=c.parse_question(QUESTIONS[kind]);self.assertEqual(parsed[0],kind)
        selected={'id':'synthetic_selected','name':'合成选择','resources':list(c._MINIMUM[kind])}
        return c.prepare_selected(QUESTIONS[kind],selected,RUNBOOK_ITEMS,{})

    def execute(self,kind,schemas,rows,**options):
        diagnostics={};session=Session(schemas,rows,**options)
        reader=c.NativeReader(diagnostics,session=session,base_url='http://127.0.0.1:8080')
        with patch.object(c,'_local_readonly_identity',return_value={'verified_synthetic_source':True}):
            result=c.execute_plan(self.plan(kind),RUNBOOK_ITEMS,diagnostics,reader=reader)
        return result,diagnostics,session

    def test_all_eight_declared_profiles_use_projected_native_inputs(self):
        for kind in QUESTIONS:
            with self.subTest(kind=kind):
                schemas,rows=fixture(kind);before=copy.deepcopy(rows)
                result,d,session=self.execute(kind,schemas,rows)
                self.assertIsNone(result['error']);self.assertTrue(d['sql_executed'])
                self.assertTrue(d['projection_loaded_not_raw']);self.assertEqual(rows,before)
                self.assertEqual(result['result']['columns'],self.plan(kind)['_expected_result_columns'])
                self.assertGreater(len(session.calls),0)

    def test_complete_question_rejects_extra_scope_output_or_or(self):
        for question in QUESTIONS.values():
            for suffix in ['以及管理员密码','，可用区az0.dc0','或另一区域region_other']:
                self.assertIsNone(c.parse_question(question+suffix))

    def test_native_failure_wrong_scope_duplicate_and_bad_page_do_not_become_zero(self):
        schemas,rows=fixture('vdc_counts')
        variants=[({'status':500},copy.deepcopy(rows)),({'corrupt':True},copy.deepcopy(rows))]
        duplicate=copy.deepcopy(rows);duplicate['VM_NOVA'].append(copy.deepcopy(duplicate['VM_NOVA'][0]));variants.append(({},duplicate))
        wrong=copy.deepcopy(rows);wrong['VM_NOVA'][0]['logicalRegionName']='region_other';variants.append(({'ignore_scope':True},wrong))
        for options,data in variants:
            with self.subTest(options=options),self.assertRaises(c.Unsupported):
                self.execute('vdc_counts',schemas,data,**options)

    def test_true_empty_network_branch_keeps_parent_and_real_count0(self):
        schemas,rows=fixture('vdc_network');rows['SUBNET']=[];rows['FLOATING_IPS']=[]
        result,d,_=self.execute('vdc_network',schemas,rows)
        output=result['result']['rows']
        self.assertEqual(len(output),1)
        self.assertEqual(output[0]['scope_eip_count'],0)
        self.assertEqual(len(json.loads(output[0]['vpc_list_json'])),1)
        self.assertEqual(output[0]['row_kind'],'summary_only')

    def test_schema_must_come_from_HTTP_even_if_result_empty(self):
        schemas,rows=fixture('vdc_network');rows['SUBNET']=[];schemas['SUBNET']=[]
        with self.assertRaises(c.Unsupported):self.execute('vdc_network',schemas,rows)

    def test_unknown_tenant_identity_is_excluded_only_with_visible_partial_population(self):
        schemas,rows=fixture('tenant_volume_rank')
        unknown=copy.deepcopy(rows['VOLUME'][0]);unknown.update(id='unknown_volume',tenantId='\u00a0')
        rows['VOLUME'].append(unknown)
        result,d,_=self.execute('tenant_volume_rank',schemas,rows)
        self.assertFalse(d['business_complete'])
        self.assertEqual(d['ranking_policy']['population'],'known_tenant_ids_only')
        self.assertEqual(len(result['result']['rows']),1)

    def test_namespace_caller_flags_do_not_replace_host_capture(self):
        schemas,rows=fixture('namespace_counts');diagnostics={}
        reader=c.NativeReader(diagnostics,session=Session(schemas,rows),base_url='http://127.0.0.1:8080')
        with patch.object(c,'_local_readonly_identity',side_effect=c.Unsupported('no_verified_source')),self.assertRaises(c.Unsupported):
            c.execute_plan(self.plan('namespace_counts'),RUNBOOK_ITEMS,diagnostics,reader=reader)
        self.assertFalse(diagnostics['sql_executed'])

    def test_typed_SQL_cannot_write_or_load_empty_placeholder(self):
        with self.assertRaises(sqlite3.DatabaseError):
            c._typed_sql('DELETE FROM TEST',{'TEST':[]},{'TEST':['id']})
        result=c._typed_sql('SELECT COUNT(*) AS n FROM TEST',{'TEST':[]},{'TEST':['id']})
        self.assertEqual(result['rows'],[{'n':0}])

    def test_system_keeps_partial_status_and_actual_executed_API_ledger(self):
        import time
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem);instance.items=RUNBOOK_ITEMS
        plan=self.plan('tenant_lists');diag={}
        def executed(item,items,execution):
            execution.update(executed_api_calls=[{'method':'GET','url':'/actual'}],
                answer_completeness='partial_with_explicit_unknowns',business_complete=False)
            return {'sql':item['sql'],'result':{'columns':item['_expected_result_columns'],'rows':[],'row_count':0},'error':None}
        with patch.object(c,'execute_plan',side_effect=executed):
            result=instance._query_issue3('合成问题',plan,diag,time.perf_counter())
        self.assertEqual(result['api_call'],[{'method':'GET','url':'/actual'}])
        self.assertEqual(diag['answer_completeness'],'partial_with_explicit_unknowns')

    def test_system_preflight_failure_keeps_reason_and_never_claims_real_empty(self):
        import time
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem);instance.items=RUNBOOK_ITEMS
        diag={}
        with patch.object(c,'execute_plan',side_effect=c.Unsupported('native_missing_schema')):
            result=instance._query_issue3('合成问题',self.plan('vdc_counts'),diag,time.perf_counter())
        self.assertIsNone(result['matched_runbook']);self.assertIsNone(result['result'])
        self.assertEqual(diag['issue3_execution']['reason'],'native_missing_schema')

    def test_list_layout_preserves_all_CI_identities_without_extra_detail_rows(self):
        schemas,rows=fixture('tenant_lists')
        second=copy.deepcopy(rows['VOLUME'][0]);second['id']='volume_second'
        rows['VOLUME'].append(second)
        result,d,_=self.execute('tenant_lists',schemas,rows)
        answer=result['result']['rows'];self.assertEqual(len(answer),2)
        self.assertEqual({r['volume_id'] for r in answer},{'VOLUME_id','volume_second'})
        carriers=[r for r in answer if r['ecs_list_json'] is not None]
        self.assertEqual(len(carriers),1)
        self.assertEqual(json.loads(carriers[0]['ecs_list_json']),[{'id':'VM_NOVA_id','name':'VM_NOVA_name'}])
        self.assertEqual(json.loads(carriers[0]['security_group_list_json']),[{'id':'SECURITY_GROUP_id','name':'SECURITY_GROUP_name'}])
        self.assertTrue(d['projection_loaded_not_raw'])

    def test_empty_volume_list_does_not_hide_nonempty_other_lists(self):
        schemas,rows=fixture('tenant_lists');rows['VOLUME']=[]
        result,_,_=self.execute('tenant_lists',schemas,rows)
        output=result['result']['rows']
        self.assertEqual(len(output),1);self.assertEqual(output[0]['row_kind'],'summary_only')
        self.assertIsNone(output[0]['volume_id'])
        self.assertEqual(len(json.loads(output[0]['ecs_list_json'])),1)

    def test_default_profile_list_keeps_unaccepted_native_contracts_isolated(self):
        for kind,q in QUESTIONS.items():
            item={'id':'synthetic','name':'合成','resources':list(c._MINIMUM[kind])}
            result=c.prepare_selected(q,item,RUNBOOK_ITEMS,{},enabled_profiles=list(c.VERIFIED_PROFILES))
            self.assertEqual(result is not None,kind in c.VERIFIED_PROFILES)
        with self.assertRaises(c.Unsupported):
            c.prepare_selected(QUESTIONS['tenant_lists'],item,RUNBOOK_ITEMS,{},enabled_profiles=['unknown'])


import sqlite3
if __name__=='__main__':unittest.main()
