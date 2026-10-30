"""显式全200仅使用固定来源、保留训练成员及原题序；完全合成，无网络。"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation_data import load_explicit_whitebox200,select_whitebox_batch


class ExplicitWhiteboxScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'CMDB用例集-白盒200.json'
        self.cases = [{'case_id': f'SYNTH-{i}', 'question': f'合成问题{i}'} for i in range(200)]
        self.training = self.cases[:150]
        self.manifest = {'train_count': 150, 'holdout_count': 50}
        self.write()

    def write(self):
        self.path.write_text(json.dumps({'cases': self.cases}))
        self.manifest['source_dataset_sha256'] = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_loads_exact200_in_original_order(self):
        self.assertEqual(load_explicit_whitebox200(self.root, self.manifest, self.training), self.cases)

    def test_source_drift_is_rejected(self):
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError, '哈希'):
            load_explicit_whitebox200(self.root, self.manifest, self.training)

    def test_missing_duplicate_or_extra_cases_are_rejected(self):
        original = self.cases
        for changed in [original[:-1], original+[{'case_id': 'EXTRA', 'question': '额外'}],
                        [original[0], *original[0:199]]]:
            self.cases = changed; self.write()
            with self.assertRaises(ValueError): load_explicit_whitebox200(self.root, self.manifest, self.training)

    def test_training_members_text_and_order_are_preserved(self):
        for training in [list(reversed(self.training)),
                         [dict(self.training[0], question='篡改'), *self.training[1:]],
                         [dict(self.training[0], case_id='UNKNOWN'), *self.training[1:]]]:
            with self.assertRaisesRegex(ValueError, '成员/题序'):
                load_explicit_whitebox200(self.root, self.manifest, training)

    def test_two_contiguous_batches_cover_exact200_without_overlap_or_reordering(self):
        one=select_whitebox_batch(self.cases,1,100);two=select_whitebox_batch(self.cases,101,200)
        self.assertEqual(one+two,self.cases)
        self.assertFalse({c['case_id'] for c in one}&{c['case_id'] for c in two})

    def test_invalid_unpaired_boolean_out_of_range_and_oversized_batches_are_rejected(self):
        for first,last in [(None,100),(1,None),(True,100),(1,False),(0,100),(101,201),(100,99),(1,151),(1,200)]:
            with self.subTest(first=first,last=last),self.assertRaises(ValueError):
                select_whitebox_batch(self.cases,first,last)


if __name__ == '__main__':
    unittest.main()
