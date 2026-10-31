"""完整测试不得被进程级450上限截断；合成流程验证，不调用网络。"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import run_a132_eval as entry


class A132BudgetEntryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'scripts').mkdir()
        for name in ['run_a132_eval.py','run_saved_training.py','analyze_whitebox_batches.py']:
            (self.root/'scripts'/name).write_text('synthetic source')
        self.environment={name:'1' for name in entry.TRAINING_FLAGS}
        self.environment.update({name:'1' for name in ['RUNBOOK_PRESERVE_AGGREGATE_GRAIN',
            'RUNBOOK_PRESERVE_LITERAL_LABELS','RUNBOOK_PRUNE_UNUSED_LOOKUPS','RUNBOOK_GROUND_ENUM_LABELS']})
        self.environment.update(RUNBOOK_THINKING_MODE='disabled',RUNBOOK_EMPTY_ANSWER_FALLBACK='1',
            RUNBOOK_ISSUE3_PROFILES='["namespace_counts"]',RUNBOOK_ISSUE4_NETWORK_FAMILIES='["hierarchy"]')
        self.calls=[];self.run_count=0;self.preflight_count=0

    def simulate(self,command,**kwargs):
        config=json.loads(Path(command[command.index('--config')+1]).read_text())
        directory=Path(config['output_dir']);self.calls.append(command)
        if '--run' in command:
            self.run_count+=1
            return SimpleNamespace(returncode=0)
        self.preflight_count+=1;directory.mkdir()
        flags=config['arguments'];first=int(flags[flags.index('--whitebox-first')+1]);last=int(flags[flags.index('--whitebox-last')+1])
        plan={key:{} for key in ('source_sha256','feature_flags','scoring_revision')}
        plan.update(model='deepseek-flash',base_url='https://example.invalid',thinking_mode='disabled',
            max_output_tokens=1024,sdk_max_retries=0,evaluation_sha256='synthetic',code_base='synthetic',
            max_requests=3*(last-first+1),whitebox_range=[first,last])
        (directory/'plan.json').write_text(json.dumps(plan))
        return SimpleNamespace(returncode=0,stdout='synthetic preflight',stderr='')

    def run_batches(self,output,**kwargs):
        with patch.object(entry,'ROOT',self.root),patch.object(entry.subprocess,'run',side_effect=self.simulate),contextlib.redirect_stdout(io.StringIO()):
            return entry.run_bounded_batches(self.environment,200,100,output,**kwargs)

    def test_200_maximum_call_load_has_two_independent_budgets_and_no_prefix_loss(self):
        ranges=entry.bounded_ranges(200,20)
        self.assertEqual([n for first,last in ranges for n in range(first,last+1)],list(range(1,201)))
        self.assertEqual(sum(3*(last-first+1) for first,last in ranges),600)
        self.assertTrue(all(3*(last-first+1)<=450 for first,last in ranges))
        import runbook_matcher as matcher
        response=SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content='synthetic answer',reasoning_content=None))])
        create=Mock(return_value=response)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        # 使用真实llm_ask预算门禁，SDK换成本地对象。旧450进程的第451次确实被拦截。
        with patch.dict(os.environ,RUNBOOK_MAX_LLM_CALLS='450',RUNBOOK_THINKING_MODE='disabled'), \
                patch.object(matcher,'_llm_events',[{}]*450),patch.object(matcher,'get_llm',return_value=client):
            with self.assertRaisesRegex(RuntimeError,'450'):matcher.llm_ask('synthetic')
        create.assert_not_called()
        # 每批独立进程用新事件列表，600次合成SDK调用完整覆盖最后一题。
        for first,last in entry.bounded_ranges(200,150):
            limit=3*(last-first+1)
            with patch.dict(os.environ,RUNBOOK_MAX_LLM_CALLS=str(limit),RUNBOOK_THINKING_MODE='disabled'), \
                    patch.object(matcher,'_llm_events',[]),patch.object(matcher,'get_llm',return_value=client):
                for case in range(first,last+1):
                    for _ in range(3):matcher.llm_ask('synthetic')
                self.assertEqual(len(matcher.get_llm_events()),limit)
                with self.assertRaises(RuntimeError):matcher.llm_ask('over budget')
        self.assertEqual(create.call_count,600)

    def test_plan_only_freezes_every_batch_before_any_model_process(self):
        out=self.root/'result';self.assertEqual(self.run_batches(out,plan_only=True),0)
        self.assertEqual(self.run_count,0);self.assertEqual(self.preflight_count,2)
        manifest=json.loads((out/'batch_plan.json').read_text())
        self.assertEqual(manifest['maximum_total_requests'],600)
        self.assertEqual([job['range'] for job in manifest['jobs']],[[1,100],[101,200]])
        self.assertFalse((out/'combined').exists())
        for config_path in out.glob('*.config.json'):
            flags=json.loads(config_path.read_text())['arguments']
            self.assertIn('--issue4-network',flags)
            self.assertIn('--issue4-vm-links',flags)
            self.assertIn('--issue4-az-counts',flags)
            self.assertEqual(flags[flags.index('--issue4-network-family')+1],'hierarchy')
            self.assertNotIn('named_vpc',flags)

    def test_failed_first_child_never_runs_second_or_generates_full_score(self):
        original=self.simulate
        def failing(command,**kwargs):
            result=original(command,**kwargs)
            if '--run' in command:result.returncode=1
            return result
        out=self.root/'result'
        with patch.object(self,'simulate',side_effect=failing),self.assertRaisesRegex(ValueError,'分批中断'):
            self.run_batches(out)
        self.assertEqual(self.preflight_count,2);self.assertEqual(self.run_count,1)
        self.assertFalse((out/'combined').exists())

    def test_wrapper_drift_after_freeze_prevents_first_model_child(self):
        original=self.simulate
        def changed(command,**kwargs):
            result=original(command,**kwargs)
            if self.preflight_count==2:(self.root/'scripts/run_saved_training.py').write_text('changed')
            return result
        with patch.object(self,'simulate',side_effect=changed),self.assertRaisesRegex(ValueError,'启动器漂移'):
            self.run_batches(self.root/'result')
        self.assertEqual(self.run_count,0)

    def test_candidate_drift_during_preflight_prevents_any_model_child(self):
        original=self.simulate
        def changed(command,**kwargs):
            result=original(command,**kwargs)
            if self.preflight_count==2:
                path=self.root/'result/part02/plan.json';plan=json.loads(path.read_text())
                plan['source_sha256']={'changed':'synthetic'};path.write_text(json.dumps(plan))
            return result
        with patch.object(self,'simulate',side_effect=changed),self.assertRaisesRegex(ValueError,'候选/配置漂移'):
            self.run_batches(self.root/'result')
        self.assertEqual(self.run_count,0)

    def test_incomplete_artifact_after_successful_child_stops_before_second(self):
        with patch('analyze_whitebox_batches.read_batch',side_effect=ValueError('batch incomplete')):
            with self.assertRaisesRegex(ValueError,'incomplete'):self.run_batches(self.root/'result')
        self.assertEqual(self.run_count,1)

    def test_output_reuse_and_bad_ranges_stop_before_subprocess(self):
        out=self.root/'result';out.mkdir()
        with self.assertRaises(FileExistsError):self.run_batches(out,plan_only=True)
        self.assertEqual(self.calls,[])
        for cases,size in [(201,20),(0,20),(200,151),(True,20),(200,False)]:
            with self.subTest(cases=cases,size=size),self.assertRaises(ValueError):entry.bounded_ranges(cases,size)

    def test_successful_synthetic_batches_use_real_artifact_validator_and_combiner(self):
        from test_training_whitebox_batches import WhiteboxBatchReportTests
        fixture=WhiteboxBatchReportTests();fixture.root=self.root/'fixtures';fixture.root.mkdir()
        fixture.dataset=[{'case_id':f'SYNTH-{i}','question':f'合成问题{i}'} for i in range(1,201)]
        results={}
        def complete(command,**kwargs):
            config=json.loads(Path(command[command.index('--config')+1]).read_text())
            directory=Path(config['output_dir'])
            if '--run' in command:
                self.run_count+=1
                for name,raw in results[directory].items():(directory/name).write_bytes(raw)
                return SimpleNamespace(returncode=0)
            self.preflight_count+=1
            flags=config['arguments'];first=int(flags[flags.index('--whitebox-first')+1]);last=int(flags[flags.index('--whitebox-last')+1])
            source=fixture.fixture(first,last)
            plan=json.loads((source/'plan.json').read_text());plan['code_base']='synthetic'
            (source/'plan.json').write_text(json.dumps(plan))
            trace=(source/'live.jsonl').read_text().splitlines();trace[0]=json.dumps(plan)
            (source/'live.jsonl').write_text('\n'.join(trace)+'\n')
            results[directory]={p.name:p.read_bytes() for p in source.iterdir()}
            directory.mkdir();(directory/'plan.json').write_bytes(results[directory]['plan.json'])
            return SimpleNamespace(returncode=0,stdout='synthetic preflight',stderr='')
        out=self.root/'result'
        with patch.object(self,'simulate',side_effect=complete):self.assertEqual(self.run_batches(out),0)
        report=json.loads((out/'combined/analysis.json').read_text())
        self.assertEqual(self.preflight_count,2);self.assertEqual(self.run_count,2)
        self.assertTrue(report['full_coverage_verified'])
        self.assertEqual(report['case_count'],200)
        self.assertEqual(len(json.loads((out/'combined/case_results.json').read_text())),200)


if __name__=='__main__':unittest.main()
