"""VM/EIP接入的范围、真实关联/目录边界及A明细守恒；合成HTTP，零网络。"""
import copy
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs

import runbook_issue3 as c
import runbook_issue4 as shared
import runbook_issue4_vm_links as links
from test_training_issue3 import Session

QUESTION='查询租户tenant_demo的ECS私有IP列表、关联弹性IP列表和所属宿主机列表'


def fixture():
    def row(identity,**kw):return dict(id=identity,logicalRegionName='region_demo',**kw)
    rows={
        'VM_NOVA':[row('v1',name='vm',tenantName='tenant_demo',privateIps='@198.51.100.1@',hostId='h1',resId='res1'),
            row('v2',name='vm2',tenantName='tenant_demo',privateIps=None,floatingIp=None,hostId='missing',resId='res2'),
            row('v3',name='other',tenantName='other',privateIps='198.51.100.2',floatingIp=None,hostId=None,resId='res3')],
        'HOST':[row('h1',name='host',ipAddress='192.0.2.1')],
        'PORT':[row('p1',devId='res1'),row('p1',devId='res1',last_Modified='new'),row('p3',devId='res3')],
        'FLOATING_IPS':[row('e1',tenantName='tenant_demo',portId='p1',floatingIpAddress='203.0.113.1',isInternal=True,status='ACTIVE'),
            row('e2',tenantName='tenant_demo',floatingIpAddress='203.0.113.2',isInternal=False,status='DOWN'),
            row('e_cross',tenantName='other',portId='p1',floatingIpAddress='203.0.113.3',isInternal=False,status='ACTIVE'),
            row('e3',tenantName='other',portId='p3',floatingIpAddress='203.0.113.4',isInternal=False,status='ACTIVE')],
    }
    schemas={ci:sorted(set().union(*(r.keys() for r in values))) for ci,values in rows.items()}
    return schemas,rows


class Issue4VMLinkTests(unittest.TestCase):
    def plan(self,question,schemas):
        result=links.prepare(question,{'id':'synthetic','name':'synthetic','resources':['VM_NOVA','FLOATING_IPS','HOST']},schemas)
        self.assertIsNotNone(result)
        return result

    def execute(self,*,question=QUESTION,rows=None,schemas=None,session_class=Session,**options):
        default_schemas,default_rows=fixture();rows=copy.deepcopy(default_rows if rows is None else rows)
        schemas=default_schemas if schemas is None else schemas;before=copy.deepcopy(rows)
        diagnostics={};session=session_class(schemas,rows,**options)
        reader=c.NativeReader(diagnostics,session=session,raw_duplicate_resources={'PORT'})
        with patch.object(c,'_local_readonly_identity',return_value={'synthetic':True}):
            result=c.execute_plan(self.plan(question,schemas),[],diagnostics,reader=reader)
        self.assertEqual(rows,before)
        return result,diagnostics,session

    def unpack(self,result):
        out=[]
        for row in result['result']['rows']:
            if row['vm_host_rows_json'] is not None:
                columns=json.loads(row['vm_host_columns_json'])
                out += [dict(zip(columns,values)) for values in json.loads(row['vm_host_rows_json'])]
        return out

    def test_catalog_and_actual_links_are_different_roles_and_all_A_details_kept(self):
        result,d,_=self.execute();rows=result['result']['rows']
        self.assertEqual({r['eip_id'] for r in rows},{'e1','e2'})
        self.assertEqual({r['eip_id']:r['relation_state'] for r in rows},{'e1':'known_port_link','e2':'catalog_only_binding_unproven'})
        full=self.unpack(result)
        self.assertEqual({r['vm_id'] for r in full},{'v1','v2'})
        self.assertIn('e_cross',{r['eip_id'] for r in full})
        self.assertEqual(len(full),3)
        self.assertTrue(d['all_A_details_retained']);self.assertFalse(d['full_original_question_certified'])
        self.assertFalse(d['business_complete']);self.assertFalse(d['full_eip_objects_binding_complete'])

    def test_actual_VM_and_EIP_tenant_requests_and_context_only_PORT_are_reported_truthfully(self):
        _,d,session=self.execute()
        selected=[url for url in session.calls if 'condition=' in url]
        self.assertTrue(any('/VM_NOVA?' in url for url in selected))
        self.assertTrue(any('/FLOATING_IPS?' in url for url in selected))
        self.assertTrue(d['actual_tenant_VM_selection_proven']);self.assertTrue(d['actual_tenant_EIP_catalog_selection_proven'])
        self.assertFalse(d['port_scoped_batch_set_executed'])
        self.assertFalse(any('/PORT?' in url and 'condition=' in url for url in session.calls))

    def test_provider_raw_and_canonical_populations_separate_and_native_bool_unchanged(self):
        result,d,session=self.execute();p=d['provider_canonical_receipt']
        self.assertEqual((p['raw_observation_count'],p['canonical_object_count']),(3,2))
        self.assertIs(session.rows['FLOATING_IPS'][0]['isInternal'],True)
        self.assertIn('true',{r['eip_internal_role_raw'] for r in self.unpack(result)})

    def test_full_original_question_kept_even_with_outer_whitespace(self):
        schemas,_=fixture();question=' \n'+QUESTION+'\t'
        plan=self.plan(question,schemas)
        self.assertEqual(plan['_issue3']['question_text'],question)
        result,d,_=self.execute(question=question)
        self.assertEqual(result['result']['row_count'],2)

    def test_sparse_and_unknown_host_private_IP_are_not_empty_success_or_guessed_values(self):
        result,d,_=self.execute();full=self.unpack(result)
        self.assertEqual(next(r for r in full if r['vm_id']=='v2')['host_link_status'],'unresolved_host_reference')
        self.assertIsNone(next(r for r in full if r['vm_id']=='v2')['private_ips_raw'])
        self.assertEqual(d['A_diagnostics']['selected_unknown_private_ip_vm_count'],1)

    def test_empty_catalog_with_VM_parents_preserves_summary_not_fake_EIP(self):
        schemas,rows=fixture();rows['FLOATING_IPS']=[]
        result,d,_=self.execute(rows=rows,schemas=schemas)
        self.assertEqual(result['result']['row_count'],1)
        row=result['result']['rows'][0]
        self.assertIsNone(row['eip_id']);self.assertEqual(row['row_kind'],'vm_host_summary_only')
        self.assertEqual({r['vm_id'] for r in self.unpack(result)},{'v1','v2'})
        self.assertEqual(d['selected_tenant_EIP_catalog_count'],0)

    def test_complete_empty_has_declared_columns_and_zero_rows(self):
        schemas,rows=fixture();rows={ci:[] for ci in rows}
        result,_,_=self.execute(rows=rows,schemas=schemas)
        self.assertEqual(result['result']['columns'],links.OUTPUT);self.assertEqual(result['result']['row_count'],0)

    def test_EIP_selection_missing_object_cannot_be_filled_from_global_context(self):
        class MissingSelection(Session):
            def get(self,url,**kwargs):
                response=super().get(url,**kwargs)
                if '/FLOATING_IPS?' in url and 'condition=' in url:
                    body=response.json();body['objList']=body['objList'][:1];body['totalNum']=1
                return response
        with self.assertRaisesRegex(ValueError,'EIP_selection_context_mismatch'):self.execute(session_class=MissingSelection)

    def test_VM_selection_missing_key_vs_NULL_drift_is_not_laundered_by_projection(self):
        class ChangedSelection(Session):
            def get(self,url,**kwargs):
                response=super().get(url,**kwargs)
                if '/VM_NOVA?' in url and 'condition=' in url:
                    response.json()['objList'][0]['floatingIp']=None
                return response
        with self.assertRaisesRegex(ValueError,'field presence/null state'):self.execute(session_class=ChangedSelection)

    def test_PORT_business_conflict_and_failed_HTTP_or_pagination_stay_failures(self):
        schemas,rows=fixture();rows['PORT'][1]['future_business']='conflict'
        with self.assertRaises(ValueError):self.execute(rows=rows,schemas=schemas)
        for options in [{'status':503},{'corrupt':True}]:
            with self.subTest(options=options),self.assertRaises(c.Unsupported):self.execute(**options)

    def test_contradictory_body_metadata_is_not_overwritten_as_HTTP_success(self):
        class Contradictory(Session):
            def get(self,url,**kwargs):
                response=super().get(url,**kwargs)
                if '/instances/' in url:response.json()['http_status']=503
                return response
        with self.assertRaisesRegex(ValueError,'contradictory_raw_metadata'):self.execute(session_class=Contradictory)

    def test_extra_obligation_missing_tenant_or_scope_and_long_core_do_not_broaden(self):
        for question in [QUESTION+'和管理员密码',QUESTION+'或区域another','查询租户的ECS私有IP列表、关联弹性IP列表和所属宿主机列表']:
            self.assertIsNone(links.parameters(question))
        with self.assertRaisesRegex(ValueError,'exceeds4096'):
            links.layout({'view':'known_port_eip_host_rows','tenantName':'x'*5000})

    def test_plan_or_full_question_drift_rejected_before_native_reads(self):
        schemas,rows=fixture();plan=self.plan(QUESTION,schemas);plan['_issue3']['question_text']=QUESTION+'额外内容'
        session=Session(schemas,rows);reader=c.NativeReader({},session=session,raw_duplicate_resources={'PORT'})
        with self.assertRaisesRegex(ValueError,'full_question_binding_changed'):c.execute_plan(plan,[],{},reader=reader)
        self.assertEqual(session.calls,[])

    def test_packed_A_detail_loss_never_hidden_by_matching_catalog_size(self):
        original=shared.typed_sql
        def lost(sql,tables):
            result=original(sql,tables)
            if result['columns']==links.OUTPUT and result['rows']:result['rows'][0]['vm_host_rows_json']='[]'
            return result
        with patch.object(shared,'typed_sql',side_effect=lost),self.assertRaisesRegex(ValueError,'detail_conservation_failed'):
            self.execute()

    def test_B_catalog_extension_keeps_A_prepared_projection_recheckable(self):
        consumer=links.module();original=consumer.recheck_tenant_prepared;retained=[]
        def checked(prepared):
            result=original(prepared);retained.append(result);return result
        with patch.object(consumer,'recheck_tenant_prepared',side_effect=checked):self.execute()
        self.assertEqual(len(retained),1)
        self.assertNotIn('B_TENANT_EIP_CATALOG',retained[0]['typed_tables'])
        self.assertEqual(consumer.recheck_tenant_prepared(retained[0]),retained[0])
