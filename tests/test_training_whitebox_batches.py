"""分批全200的守恒、冻结来源及中止拒绝；纯合成记录，不调用模型或数据服务。"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from analyze_whitebox_batches import combine_batches


class WhiteboxBatchReportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.dataset=[{'case_id':f'SYNTH-{i}','question':f'合成问题{i}'} for i in range(1,201)]
        self.one=self.fixture(1,100);self.two=self.fixture(101,200)

    def fixture(self,first,last):
        out=self.root/f'{first}-{last}';out.mkdir()
        raw=json.dumps({'cases':self.dataset},ensure_ascii=False).encode()
        files={'CMDB用例集-白盒200.json':hashlib.sha256(raw).hexdigest()}
        plan={'type':'validation_plan','scope':'whitebox200_batch','holdout_evaluated':True,
              'case_count':last-first+1,'whitebox_range':[first,last],
              'case_ids':[r['case_id'] for r in self.dataset[first-1:last]],'source_sha256':files,
              'model':'deepseek-flash','base_url':'https://example.invalid','thinking_mode':'disabled',
              'thinking_extra_body':{'thinking':{'type':'disabled'}},'max_output_tokens':1024,
              'sdk_max_retries':0,'max_requests':3*(last-first+1),'feature_flags':{'synthetic':'1'},
              'scoring_revision':{},'template_count':132,'evaluation_sha256':files['CMDB用例集-白盒200.json']}
        rows=[{'type':'case','case_id':c['case_id'],'question':c['question'],'case_index':i,
               'training_case_index':i if i<=150 else None,'score':5,'score_without_time_penalty':5,
               'reason':'synthetic correct','matched_runbook':'synthetic','diagnostics':{}}
              for i,c in enumerate(self.dataset[first-1:last],first)]
        requests=[{'type':'request','case_id':r['case_id'],'status':'ok',
                   'requested_model':'deepseek-flash','response_model':'deepseek-flash'} for r in rows]
        summary={'type':'summary','status':'complete','completed_cases':len(rows),'planned_cases':len(rows),
                 'generation_requests':len(requests),'failed_requests':0,'total_score':5*len(rows),
                 'untimed_score':5*len(rows),'max_requests':plan['max_requests']}
        budget={'used':len(requests),'failed':0,'child_exit_code':0,'maximum':plan['max_requests']}
        for name,value in [('plan.json',plan),('summary.json',summary),('case_results.json',rows),('budget.json',budget)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False))
        (out/'live.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in [plan,*requests,*rows,summary])+'\n')
        with zipfile.ZipFile(out/'source.zip','w') as archive:archive.writestr('runtime/CMDB用例集-白盒200.json',raw)
        return out

    def test_exact200_original_order_and_original_partitions_without_rescoring(self):
        report,rows=combine_batches([self.one,self.two])
        self.assertEqual(len(rows),200);self.assertEqual(report['overall']['untimed_score'],1000)
        self.assertEqual(report['original_train150_members']['cases'],150)
        self.assertEqual(report['original_validation50_members']['cases'],50)
        self.assertEqual(report['last30']['cases'],30)
        self.assertFalse(report['source_rows_rescored']);self.assertFalse(report['single_process_round'])

    def test_overlap_gap_or_reordering_cannot_be_called_full200(self):
        for batches in [[self.one,self.one],[self.two,self.one],[self.one],[self.two]]:
            with self.subTest(batches=batches),self.assertRaises(ValueError):combine_batches(batches)

    def test_incomplete_batch_cannot_be_combined(self):
        path=self.two/'summary.json';summary=json.loads(path.read_text());summary['status']='incomplete'
        path.write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError,'incomplete'):combine_batches([self.one,self.two])

    def test_changed_query_flags_do_not_merge_even_if_each_batch_has_valid_records(self):
        path=self.two/'plan.json';plan=json.loads(path.read_text());plan['feature_flags']['synthetic']='changed'
        path.write_text(json.dumps(plan));trace=(self.two/'live.jsonl').read_text().splitlines();trace[0]=json.dumps(plan)
        (self.two/'live.jsonl').write_text('\n'.join(trace)+'\n')
        with self.assertRaisesRegex(ValueError,'changed between batches'):combine_batches([self.one,self.two])

    def test_source_zip_or_budget_tamper_is_rejected(self):
        with zipfile.ZipFile(self.two/'source.zip','w') as archive:
            archive.writestr('runtime/CMDB用例集-白盒200.json','changed')
        with self.assertRaisesRegex(ValueError,'source archive'):combine_batches([self.one,self.two])


if __name__=='__main__':unittest.main()
