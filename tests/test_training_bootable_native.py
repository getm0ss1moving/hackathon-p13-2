"""新A bootable合同的B原子绑定；合成实体、零网络、零模型。"""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import runbook_bootable_native as native
import runbook_matcher as matcher
import runbook_system as system
from runbook_items import RUNBOOK_ITEMS


class NativeBootableTests(unittest.TestCase):
    def setUp(self):
        self.item=copy.deepcopy(next(x for x in RUNBOOK_ITEMS if x['id']=='family_volume_rows'))
        self.flags=patch.dict(os.environ,{'RUNBOOK_A132_CANDIDATE':'1','RUNBOOK_A132_NATIVE_BOOTABLE':'1'})
        self.flags.start();self.addCleanup(self.flags.stop)
        self.params={'view':'bootable_scoped_rows','filters':{'logicalRegionName':'region_synthetic_boot',
            'azoneName':'zone_synthetic_boot','bootable':True},
            'required_filters':['logicalRegionName','azoneName','bootable']}
        self.question='查询区域region_synthetic_boot可用区zone_synthetic_boot中可启动云硬盘列表'

    def fill(self,params,question=None):
        diagnostics={}
        with patch.object(matcher,'llm_ask',return_value=json.dumps(params)) as model,\
             patch.object(matcher,'_get_table_schemas',return_value='synthetic schema'),\
             patch.object(matcher,'_refine_sql',side_effect=lambda q,sql,schema,**kw:sql):
            result=matcher._match_a132_changed(question or self.question,self.item,diagnostics)
        model.assert_called_once()
        return result,diagnostics,model.call_args.args[0]

    def test_selection_and_parameter_cards_change_together_without_base_mutation(self):
        before=copy.deepcopy(self.item)
        card=matcher._format_runbook_list([self.item])
        result,diagnostics,prompt=self.fill(self.params)
        self.assertIsNotNone(result,diagnostics)
        self.assertIn('"bootable":["true","false"]',card)
        self.assertIn('"bootable":["true","false"]',prompt)
        self.assertIn('"type":"boolean"',card);self.assertIn('"type":"boolean"',prompt)
        self.assertEqual(self.item,before)
        self.assertTrue(diagnostics['native_bootable_binding']['full_original_question_prepare'])

    def test_true_variants_become_native_string_and_preserve_three_predicates(self):
        for value in [True,'TRUE','tRuE','true']:
            with self.subTest(value=value):
                params=copy.deepcopy(self.params);params['filters']['bootable']=value
                result,diagnostics,_=self.fill(params)
                self.assertIsNotNone(result,diagnostics)
                actual={x['simple']['name']:x['simple']['value'] for x in result['api_call']['condition']['constraint']}
                self.assertEqual(actual,dict(self.params['filters'],bootable='true'))
                self.assertIs(type(actual['bootable']),str)
                self.assertEqual(result['_expected_result_columns'],['name','size','status','bootable'])

    def test_false_requires_explicit_false_and_cannot_flip_natural_true(self):
        params=copy.deepcopy(self.params);params['filters']['bootable']=False
        self.assertIsNone(self.fill(params)[0])
        result,diagnostics,_=self.fill(params,self.question.replace('可启动','bootable FALSE'))
        self.assertIsNotNone(result,diagnostics)
        actual={x['simple']['name']:x['simple']['value'] for x in result['api_call']['condition']['constraint']}
        self.assertEqual(actual['bootable'],'false')

    def test_numeric_null_whitespace_conflicts_and_extra_obligations_are_not_repaired(self):
        for bad in [0,1,None,' true','false ',[],{}]:
            params=copy.deepcopy(self.params);params['filters']['bootable']=bad
            with self.subTest(value=bad):self.assertIsNone(self.fill(params)[0])
        for field in ['logicalRegionName','azoneName']:
            params=copy.deepcopy(self.params);params['filters'][field]='Other_entity'
            self.assertIsNone(self.fill(params)[0])
        self.assertIsNone(self.fill(self.params,self.question+'并统计数量')[0])

    def test_other_view_is_equivalent_and_legacy_registry_remains_original(self):
        base=matcher._a132_module('unified_prepare');record=copy.deepcopy(base._REGISTRY[self.item['id']])
        bound=native.bind(base,self.item)
        self.assertNotEqual(bound._REGISTRY[self.item['id']]['module_sha256'],record['module_sha256'])
        self.assertEqual(base._REGISTRY[self.item['id']],record)
        params={'view':'vdc_scoped_rows','filters':{'vdcName':'SyntheticVDC','logicalRegionName':'region_synthetic_boot'},
                'required_filters':['vdcName','logicalRegionName']}
        question='查询VDCSyntheticVDC在区域region_synthetic_boot中的云硬盘列表及容量'
        self.assertEqual(bound.prepare_candidate(question,self.item,params),
                         base.prepare_candidate(question,self.item,params))

    def test_disabled_or_unrelated_family_stays_on_original_path(self):
        base=matcher._a132_module('unified_prepare')
        with patch.dict(os.environ,{'RUNBOOK_A132_NATIVE_BOOTABLE':'0'}):
            self.assertIs(native.bind(base,self.item),base)
            self.assertIs(native.prompt_item(self.item),self.item)
        unrelated=next(x for x in RUNBOOK_ITEMS if x['id']=='family_f02')
        self.assertIs(native.bind(base,unrelated),base)

    def test_card_source_and_original_registry_drift_are_rejected_even_after_cache(self):
        base=matcher._a132_module('unified_prepare');native.bind(base,self.item)
        changed=copy.deepcopy(self.item);changed['parameter_contract']['bootable']=['true','false']
        with self.assertRaisesRegex(ValueError,'card_drift'):native.prompt_item(changed)
        read=Path.read_bytes
        def drift(path):
            return b'changed' if path==native.ROOT/'experiments/issue3_bootable_contract_20261030/candidate.py' else read(path)
        with patch.object(Path,'read_bytes',drift),self.assertRaisesRegex(ValueError,'drift'):
            native.bind(base,self.item)
        records=copy.deepcopy(base._REGISTRY);records[self.item['id']]['module_sha256']='changed'
        with patch.object(base,'_REGISTRY',records),self.assertRaisesRegex(ValueError,'registry_drift'):
            native.bind(base,self.item)

    def test_system_default_verifies_overlay_but_explicit_zero_keeps_old_path(self):
        for explicit in [None,'0']:
            with patch.dict(os.environ):
                if explicit is None:os.environ.pop('RUNBOOK_A132_NATIVE_BOOTABLE',None)
                else:os.environ['RUNBOOK_A132_NATIVE_BOOTABLE']=explicit
                with patch.object(native,'sources',wraps=native.sources) as check,\
                     patch.object(system,'get_llm'),patch.object(system,'_warm_schema_cache'),\
                     patch.object(system,'RunbookRetriever'):
                    system.RunbookQuerySystem()
                self.assertEqual(os.environ['RUNBOOK_A132_NATIVE_BOOTABLE'],explicit or '1')
                self.assertEqual(check.call_count,1 if explicit is None else 0)


if __name__=='__main__':unittest.main()
