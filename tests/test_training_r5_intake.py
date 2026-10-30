"""当前132 compact与r5真实配对、单目标/多义务边界；纯离线、合成问题。"""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import runbook_matcher as matcher
import runbook_retriever as retrieval
import runbook_system as system
from runbook_items import RUNBOOK_ITEMS


class R5CompactIntakeTests(unittest.TestCase):
    def setUp(self):
        self.retriever=retrieval.RunbookRetriever(RUNBOOK_ITEMS)

    def test_exact_current_compact_and_published_strict_r5_are_bound_together(self):
        source,files,variant=matcher._verify_a132_sources()
        self.assertEqual(variant,'strict_r5');self.assertEqual(source['retrieval_revision'],'r5')
        root=Path(matcher.__file__).resolve().parents[1]
        digest=hashlib.sha256((root/'implementation/runbook_retriever.py').read_bytes()).hexdigest()
        self.assertEqual(digest,'b5a1c943fcf4785aa40c39e4905fbbdba2719eed9d458b391c127657b348f3d6')
        self.assertEqual(len(RUNBOOK_ITEMS),132)
        self.assertIn('experiments/b_a132_r5_runtime_20261031/SOURCE_MANIFEST.json',files)

    def test_architecture_type_and_its_count_are_one_goal_with_normal_retrieval(self):
        question='查询区域region_synthetic_r5内部所有的物理服务器CPU架构类型并统计各类数量'
        self.assertEqual(self.retriever.retrieve_obligations(question),[])
        candidates=self.retriever.retrieve(question,top_k=None)
        self.assertTrue(candidates)
        self.assertIn('rb_052',{c.id for c in candidates})

    def test_two_entities_in_same_family_keep_two_original_unicode_spans(self):
        question='查询ECS实例alpha的创建时间以及查询ECS实例beta的创建时间'
        obligations=self.retriever.retrieve_obligations(question)
        self.assertEqual(len(obligations),2)
        self.assertIn('alpha',obligations[0]['text']);self.assertIn('beta',obligations[1]['text'])
        for obligation in obligations:
            self.assertEqual(question[obligation['start']:obligation['end']],obligation['text'])
        candidates=self.retriever.retrieve(question,top_k=None)
        self.assertTrue(any(len(candidate.obligation_spans)==2 for candidate in candidates))

    def test_english_AND_binds_exact_original_clauses_despite_source_edge_whitespace(self):
        question='查询ECS实例alpha的创建时间 AND 查询ECS实例beta的创建时间'
        obligations=self.retriever.retrieve_obligations(question)
        self.assertEqual(len(obligations),2)
        for obligation in obligations:
            bound=system._original_obligation_span(question,obligation)
            self.assertIsNotNone(bound)
            self.assertEqual(question[bound[0]:bound[1]],bound[2])

    def test_span_alignment_rejects_entity_changes_invalid_bounds_and_empty_text(self):
        question='  查询ECS实例alpha的创建时间  '
        for obligation in [{'start':0,'end':len(question),'text':'查询ECS实例beta的创建时间'},
                           {'start':-1,'end':len(question),'text':question.strip()},
                           {'start':0,'end':len(question)+1,'text':question.strip()},
                           {'start':True,'end':len(question),'text':question.strip()},
                           {'start':0,'end':2,'text':''}]:
            with self.subTest(obligation=obligation):
                self.assertIsNone(system._original_obligation_span(question,obligation))

    def test_B_executes_both_AND_obligations_in_original_order_after_alignment(self):
        question='查询ECS实例alpha的创建时间 AND 查询ECS实例beta的创建时间'
        obligations=self.retriever.retrieve_obligations(question)
        instance=system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        calls=[]
        def execute(text,diagnostics):
            calls.append(text);diagnostics.update(selected_template='synthetic',llm_calls=[])
            return {'matched_runbook':'synthetic','api_call':None,'sql':'SELECT 1',
                    'result':{'columns':['value'],'rows':[(1,)],'row_count':1},'error':None}
        with patch.object(instance,'_query',side_effect=execute),patch.object(system,'get_llm_events',return_value=[]):
            result=instance._query_obligations(question,obligations)
        self.assertEqual(calls,['查询ECS实例alpha的创建时间','查询ECS实例beta的创建时间'])
        self.assertEqual(len(result['result']),2)
        self.assertNotIn('rejection',result['diagnostics'])
        self.assertTrue(result['diagnostics']['obligation_span_normalization'])

    def test_AND_inside_quoted_entity_is_not_a_request_separator(self):
        question='查询ECS实例“alpha AND 查询ECSbeta”的创建时间'
        self.assertEqual(self.retriever.retrieve_obligations(question),[])
        self.assertTrue(self.retriever.retrieve(question,top_k=None))

    def test_per_instance_projection_is_not_collapsed_into_group_count(self):
        question='查询每台物理服务器CPU架构类型并统计各类数量'
        parts=retrieval._compound_parts(question)
        self.assertIsNotNone(parts);self.assertEqual(len(parts),2)


if __name__=='__main__':unittest.main()
