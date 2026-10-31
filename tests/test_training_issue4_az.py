"""AZ独立人口及完整A分组守恒，未知VPC归属不借VM区域，零网络。"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import runbook_issue3 as c
import runbook_issue4 as shared
import runbook_issue4_az as az
from test_training_issue3 import Session

QUESTION='查询区域region_demo下各可用区的ECS数量、云硬盘数量和VPC数量，按可用区分别展示'


def fixture():
    def row(identity,**kw):return dict(id=identity,logicalRegionName='region_demo',**kw)
    rows={
        'VM_NOVA':[row('e1',azoneName='az_A'),row('e2',azoneName='az_A'),row('e3',azoneName=None),row('e4'),row('e5',azoneName='')],
        'VOLUME':[row('v1',azoneName='az_B'),row('v2',azoneName='az_B'),row('v3',azoneName='az_C')],
        'ROUTER':[row('r1'),row('r2')],
        'AZONE':[row('z1',name='az_A'),row('z2',name='az_B')],
    }
    schemas={ci:list(fields) for ci,fields in az.module().SCHEMA.items()}
    return schemas,rows


class Issue4AZTests(unittest.TestCase):
    def plan(self,question,schemas):
        result=az.prepare(question,{'id':'synthetic','name':'synthetic','resources':['VM_NOVA','VOLUME','ROUTER']},schemas)
        self.assertIsNotNone(result);return result

    def execute(self,*,question=QUESTION,rows=None,schemas=None,**options):
        default_schemas,default_rows=fixture();rows=copy.deepcopy(default_rows if rows is None else rows)
        schemas=default_schemas if schemas is None else schemas;before=copy.deepcopy(rows)
        diagnostics={};session=Session(schemas,rows,**options);reader=c.NativeReader(diagnostics,session=session)
        with patch.object(c,'_local_readonly_identity',return_value={'synthetic':True}):
            result=c.execute_plan(self.plan(question,schemas),[],diagnostics,reader=reader)
        self.assertEqual(rows,before)
        return result,diagnostics,session

    def unpack(self,result):
        rows=[]
        for row in result['result']['rows']:
            if row['az_rows_json'] is not None:
                columns=json.loads(row['az_columns_json'])
                rows += [dict(zip(columns,v)) for v in json.loads(row['az_rows_json'])]
        return rows

    def test_resource_populations_independent_and_A_union_domain_retained(self):
        result,d,_=self.execute();full=self.unpack(result)
        self.assertEqual({r['azone_name'] for r in full},{None,'az_A','az_B','az_C'})
        self.assertEqual(sum(r['known_ecs_count'] for r in full),5)
        self.assertEqual(sum(r['known_volume_count'] for r in full),3)
        self.assertEqual(sum(r['known_vpc_count'] for r in full),2)
        self.assertTrue(d['all_A_groups_retained']);self.assertFalse(d['full_requested_operation_supported'])

    def test_raw_NULL_and_empty_labels_separate_but_never_claimed_real_AZs(self):
        result,d,_=self.execute();by={r['azoneName']:r for r in result['result']['rows']}
        self.assertEqual(set(by),{None,'','az_A'})
        self.assertEqual((by[None]['ecs_count'],by['']['ecs_count']),(2,1))
        self.assertEqual(by[None]['row_kind'],'unknown_native_az_label')
        self.assertEqual(by['']['row_kind'],'unknown_native_az_label')
        self.assertEqual(d['A_diagnostics']['unknown_az_object_counts']['VM_NOVA'],3)

    def test_unicode_whitespace_label_stays_unknown_without_renaming_raw_value(self):
        schemas,rows=fixture();rows['VM_NOVA'].append(dict(rows['VM_NOVA'][0],id='space_vm',azoneName='\u3000'))
        result,_,_=self.execute(rows=rows,schemas=schemas)
        row=next(r for r in result['result']['rows'] if r['azoneName']=='\u3000')
        self.assertEqual(row['row_kind'],'unknown_native_az_label')

    def test_VPC_population_occurs_once_as_unknown_not_allocated_to_VM_AZ(self):
        result,d,_=self.execute();full=self.unpack(result)
        unknown=next(r for r in full if r['azone_name'] is None)
        self.assertEqual(unknown['known_vpc_count'],2)
        self.assertTrue(all(r['known_vpc_count']==0 and r['vpc_count_if_complete'] is None for r in full if r['azone_name'] is not None))
        self.assertFalse(d['business_complete'])

    def test_more_volumes_do_not_multiply_ECS_or_VPC_counts(self):
        schemas,rows=fixture();rows['VOLUME'] += [dict(rows['VOLUME'][0],id='extra'+str(i)) for i in range(8)]
        result,_,_=self.execute(rows=rows,schemas=schemas);full=self.unpack(result)
        self.assertEqual(sum(r['known_ecs_count'] for r in full),5)
        self.assertEqual(sum(r['known_volume_count'] for r in full),11)
        self.assertEqual(sum(r['known_vpc_count'] for r in full),2)

    def test_empty_VM_still_keeps_nonempty_other_resources_and_summary_role(self):
        schemas,rows=fixture();rows['VM_NOVA']=[]
        result,_,_=self.execute(rows=rows,schemas=schemas)
        self.assertEqual(result['result']['row_count'],1)
        self.assertEqual(result['result']['rows'][0]['row_kind'],'summary_only')
        self.assertIsNone(result['result']['rows'][0]['ecs_count'])
        self.assertEqual(sum(r['known_volume_count'] for r in self.unpack(result)),3)

    def test_complete_empty_does_not_invent_count1_or_AZ_row(self):
        schemas,rows=fixture();rows={ci:[] for ci in rows}
        result,_,_=self.execute(rows=rows,schemas=schemas)
        self.assertEqual(result['result']['row_count'],0)
        self.assertEqual(result['result']['columns'],az.OUTPUT)

    def test_volume_missing_AZ_key_or_missing_schema_remains_A_contract_failure(self):
        schemas,rows=fixture();rows['VOLUME'][0].pop('azoneName')
        with self.assertRaisesRegex(ValueError,'missing identity/scope/required field'):
            self.execute(rows=rows,schemas=schemas)
        schemas['AZONE'].remove('name')
        self.assertIsNone(az.prepare(QUESTION,{'resources':['VM_NOVA','VOLUME','ROUTER']},schemas))

    def test_wrong_scope_HTTP_failure_and_duplicate_identity_do_not_become_zero(self):
        for options in [{'status':503},{'corrupt':True}]:
            with self.subTest(options=options),self.assertRaises(c.Unsupported):self.execute(**options)
        schemas,rows=fixture();rows['VOLUME'].append(copy.deepcopy(rows['VOLUME'][0]))
        with self.assertRaises(c.Unsupported):self.execute(rows=rows,schemas=schemas)
        schemas,rows=fixture();rows['VM_NOVA'][0]['logicalRegionName']='other'
        with self.assertRaises(c.Unsupported):self.execute(rows=rows,schemas=schemas,ignore_scope=True)

    def test_extra_obligation_default_region_or_lost_literal_rejected(self):
        for question in [QUESTION+'和管理员密码',QUESTION.replace('区域region_demo下',''),QUESTION+'或区域other']:
            self.assertIsNone(az.parameters(question))
        self.assertEqual(az.parameters(QUESTION.replace('region_demo','“地区 丁”')),{'logicalRegionName':'地区 丁'})
        with self.assertRaisesRegex(ValueError,'budget|4096'):az.layout({'logicalRegionName':'x'*5000})

    def test_question_or_plan_drift_stops_before_requests(self):
        schemas,rows=fixture();plan=self.plan(QUESTION,schemas);plan['_issue3']['question_text']+= '以及额外资源'
        session=Session(schemas,rows);reader=c.NativeReader({},session=session)
        with self.assertRaisesRegex(ValueError,'question_binding_changed'):c.execute_plan(plan,[],{},reader=reader)
        self.assertEqual(session.calls,[])

    def test_matching_ECS_summary_cannot_hide_missing_volume_or_VPC_groups(self):
        original=shared.typed_sql
        def lost(sql,tables):
            result=original(sql,tables)
            if result['columns']==az.OUTPUT and result['rows']:result['rows'][0]['az_rows_json']='[]'
            return result
        with patch.object(shared,'typed_sql',side_effect=lost),self.assertRaisesRegex(ValueError,'group_conservation_failed'):
            self.execute()

    def test_source_pin_checked_even_when_A_module_cached(self):
        az.module();read=Path.read_bytes
        def changed(path):
            if path.name=='az_counts.py' and 'a_issue4_r1_20261031' in path.parts:return b'drift'
            return read(path)
        with patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'source_drift'):az.module()


if __name__=='__main__':unittest.main()
