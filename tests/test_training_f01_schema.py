"""F01提示Schema与原物化合同一致性；仅固定合法过滤的合成结构轴。"""
import copy,itertools,json
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m

def dialect_accepts(schema, value):
    """Exact semantics for the small keyword set emitted by these schemas."""
    supported = {"type", "enum", "const", "properties", "required",
                 "additionalProperties", "items", "uniqueItems", "oneOf"}
    if set(schema) - supported:
        raise AssertionError("unsupported schema keywords: " + repr(set(schema) - supported))
    types = {"object": lambda x: isinstance(x, dict),
             "array": lambda x: isinstance(x, list),
             "string": lambda x: isinstance(x, str),
             "boolean": lambda x: type(x) is bool,
             "null": lambda x: x is None}
    if "type" in schema:
        requested = schema["type"]
        requested = requested if isinstance(requested, list) else [requested]
        if not any(types[kind](value) for kind in requested):
            return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= set(value):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        if any(key in value and not dialect_accepts(rule, value[key])
               for key, rule in properties.items()):
            return False
    if isinstance(value, list):
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            return False
        if "items" in schema and not all(dialect_accepts(schema["items"], x) for x in value):
            return False
    if "oneOf" in schema and sum(dialect_accepts(branch, value) for branch in schema["oneOf"]) != 1:
        return False
    return True

class F01StructuralSchemaTests(unittest.TestCase):
    item={"id":"synthetic_f01","family_id":"F01","resources":["VM_NOVA"]}

    def schema(self):
        captured=[]
        def ask(prompt,stage=None):
            self.assertEqual(stage,"family_fill")
            line=prompt.split("JSON Schema：",1)[1].split("\n",1)[0]
            captured.append(json.loads(line))
            raise ValueError("synthetic_stop_after_prompt")
        with patch.object(m,"llm_ask",side_effect=ask):
            self.assertIsNone(m._match_family_candidate("区域region_demo下各VDC的ECS数量",self.item,{}))
        self.assertEqual(len(captured),1)
        return captured[0]

    def params(self):
        return {"scope":"filtered","filters":{"logicalRegionName":"region_demo"},
                "required_filters":["logicalRegionName"],"group":"vdcName","metrics":"count"}

    def test_all486_axis_combinations_match_the_unchanged_materializer(self):
        schema=self.schema();missing=object();mismatches=[];accepted=0;seen=0
        for group,metric,alias,label,order in itertools.product(
                m._FAMILY_SPECS['F01']['axes']['group'],['count','total_active','status_counts'],
                [missing,'count','total'],[missing,'none','ECS'],[missing,'none','count_desc']):
            params=self.params();params.update(group=group,metrics=metric)
            for key,value in [('count_alias',alias),('label',label),('order',order)]:
                if value is not missing:params[key]=value
            try:m._materialize_family(self.item,copy.deepcopy(params));actual=True
            except ValueError:actual=False
            predicted=dialect_accepts(schema,params);accepted+=actual;seen+=1
            if predicted!=actual:mismatches.append(params)
        self.assertEqual(seen,486);self.assertEqual(accepted,86);self.assertEqual(mismatches,[])

    def test_real_failure_shape_is_rejected_but_legal_options_and_defaults_remain(self):
        schema=self.schema();bad=self.params();bad.update(metrics='total_active',label='ECS')
        self.assertFalse(dialect_accepts(schema,bad))
        with self.assertRaisesRegex(ValueError,'unreviewed_metric_options'):
            m._materialize_family(self.item,bad)
        for params in [dict(bad,label='none'),dict(self.params(),label='ECS'),
                       dict(self.params(),group='none',count_alias='total')]:
            with self.subTest(params=params):
                self.assertTrue(dialect_accepts(schema,params));self.assertIsInstance(m._materialize_family(self.item,params),dict)


if __name__=='__main__':unittest.main()
