"""深复制语义与类型保真；不调用网络或模型。"""
import copy
import json
import math
import random
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runbook_copy import deepcopy,bind


class JsonCopyTests(unittest.TestCase):
    def test_native_types_and_nested_containers_are_preserved(self):
        value={'rows':[{'missing':None,'boolean':True,'integer':1,'float':1.0,'negative_zero':-0.0,'unicode':'区域@a@'}]}
        actual=deepcopy(value)
        self.assertEqual(json.dumps(actual),json.dumps(copy.deepcopy(value)))
        self.assertIsNot(actual,value);self.assertIsNot(actual['rows'],value['rows'])
        self.assertIs(type(actual['rows'][0]['boolean']),bool)
        self.assertIs(type(actual['rows'][0]['float']),float)
        self.assertEqual(math.copysign(1,actual['rows'][0]['negative_zero']),-1)
        actual['rows'][0]['integer']=99;self.assertEqual(value['rows'][0]['integer'],1)

    def test_aliases_cycles_and_external_memo_have_standard_copy_semantics(self):
        child={'x':[]};source={'a':child,'b':child};source['self']=source
        memo={};result=deepcopy(source,memo)
        self.assertIs(result['a'],result['b']);self.assertIs(result['self'],result)
        self.assertIs(deepcopy(source,memo),result)
        self.assertIsNot(result['a'],child)
        self.assertEqual(deepcopy(1,{id(1):'replacement'}),copy.deepcopy(1,{id(1):'replacement'}))

    def test_non_json_types_and_non_string_keys_fall_back_to_standard_library(self):
        source={1:({'items':{1,2}},), 'set':{3,4}, 'bytes':b'raw'}
        result=deepcopy(source);self.assertEqual(result,copy.deepcopy(source))
        self.assertIs(type(result[1]),tuple);self.assertIs(type(result['set']),set)

    def test_seeded_finite_JSON_trees_equal_standard_copy(self):
        rng=random.Random(194)
        def tree(depth):
            if depth==0:return rng.choice([None,True,False,0,1,-4,1.25,'','原文@opaque@'])
            return [tree(depth-1) for _ in range(rng.randrange(4))] if rng.randrange(2) else {str(i):tree(depth-1) for i in range(rng.randrange(4))}
        for _ in range(200):
            source=tree(4);self.assertEqual(json.dumps(deepcopy(source),ensure_ascii=False),json.dumps(copy.deepcopy(source),ensure_ascii=False))

    def test_execution_binding_keeps_A_loader_checks_and_is_reversible(self):
        calls=[]
        def loader(name):
            calls.append(name)
            return SimpleNamespace(deepcopy=copy.deepcopy)
        module=SimpleNamespace(deepcopy=copy.deepcopy,_module=loader)
        with patch.dict(os.environ,RUNBOOK_JSON_COPY_MODE='fast'):
            self.assertIs(bind(module).deepcopy,deepcopy)
            child=module._module('pinned_source')
            self.assertIs(child.deepcopy,deepcopy);self.assertEqual(calls,['pinned_source'])
        with patch.dict(os.environ,RUNBOOK_JSON_COPY_MODE='standard'):
            bind(module)
            self.assertIs(module.deepcopy,copy.deepcopy);self.assertIs(module._module,loader)


if __name__=='__main__':unittest.main()
