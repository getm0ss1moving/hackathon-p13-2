"""合成50验证的冻结/授权/哈希/成员检查；不打开真实封存文件。"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation_data import load_sealed_validation, load_validation_subset, verify_validation_freeze


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ValidationScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root/'implementation').mkdir()
        (self.root/'implementation/synthetic.py').write_text('value = 1\n')
        self.split = self.root/'datasets/whitebox_150_50_v1'
        self.split.mkdir(parents=True)
        self.rows = [{'case_id': 'VALID-' + str(i), 'question': '合成问题'} for i in range(50)]
        self.train = [{'case_id': 'TRAIN-' + str(i)} for i in range(150)]
        self.path = self.split/'sealed_test.json'
        self.config = self.root/'config.json';self.config.write_text('{}\n')
        self.freeze = self.root/'freeze.json'
        self.write_fixture()

    def write_fixture(self):
        self.path.write_text(json.dumps({'partition': 'sealed_test', 'cases': self.rows}))
        self.manifest = {'holdout_count': 50, 'sealed_test_file': 'sealed_test.json',
                         'sealed_test_sha256': digest(self.path)}
        (self.split/'manifest.json').write_text(json.dumps(self.manifest))
        self.frozen = {'authorization': 'user_explicit_validation50_20261030', 'scope': 'sealed50_once',
                       'runtime_sha256': {'implementation/synthetic.py': digest(self.root/'implementation/synthetic.py')},
                       'split_manifest_sha256': digest(self.split/'manifest.json'),
                       'configuration_path': 'config.json', 'configuration_sha256': digest(self.config)}
        self.freeze.write_text(json.dumps(self.frozen))

    def test_exact_fifty_disjoint_members_are_loaded_only_after_freeze(self):
        self.assertEqual(load_sealed_validation(self.root, self.freeze, self.manifest, self.train), self.rows)

    def test_runtime_drift_stops_before_reading_validation_questions(self):
        (self.root/'implementation/synthetic.py').write_text('value = 2\n')
        native = Path.read_text
        def read(path, *a, **k):
            if path.name == 'sealed_test.json': raise AssertionError('不得打开验证内容')
            return native(path, *a, **k)
        with patch.object(Path, 'read_text', read), self.assertRaisesRegex(ValueError, '运行时'):
            load_sealed_validation(self.root, self.freeze, self.manifest, self.train)

    def test_explicit_authorization_and_configuration_are_required(self):
        self.frozen['authorization'] = 'not-authorized'
        self.freeze.write_text(json.dumps(self.frozen))
        with self.assertRaises(ValueError): verify_validation_freeze(self.root, self.freeze)
        self.write_fixture();self.config.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, '配置'): verify_validation_freeze(self.root, self.freeze)

    def test_dataset_hash_count_duplicates_and_train_overlap_stop(self):
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError, '哈希'): load_sealed_validation(self.root, self.freeze, self.manifest, self.train)
        for rows in [self.rows[:-1], [self.rows[0]] * 50, [dict(self.rows[0], case_id='TRAIN-0')] + self.rows[1:]]:
            self.rows = rows;self.write_fixture()
            with self.assertRaises(ValueError): load_sealed_validation(self.root, self.freeze, self.manifest, self.train)

    def test_exposed_failure_subset_is_exact_frozen_and_cannot_expand_to_full50(self):
        self.frozen.update(subset_authorization='user_B_only_and_delivered_contracts_20261031',
                           subset_case_ids=['VALID-4','VALID-1'])
        self.freeze.write_text(json.dumps(self.frozen))
        rows=load_validation_subset(self.root,self.freeze,self.manifest,self.train,['VALID-1','VALID-4'])
        self.assertEqual([r['case_id'] for r in rows],['VALID-1','VALID-4'])
        with self.assertRaisesRegex(ValueError,'完整50'):
            load_sealed_validation(self.root,self.freeze,self.manifest,self.train)
        for bad in [['VALID-1'],['VALID-1','VALID-1'],['TRAIN-1','VALID-4']]:
            with self.assertRaises(ValueError):
                load_validation_subset(self.root,self.freeze,self.manifest,self.train,bad)

    def test_old_full50_freeze_does_not_authorize_arbitrary_subset(self):
        with self.assertRaises(ValueError):
            load_validation_subset(self.root,self.freeze,self.manifest,self.train,['VALID-1'])

    def test_user_reported_log_failure_subset_stays_exact_and_cannot_expand(self):
        self.frozen.update(subset_authorization='user_exposed_log_failures_20261031',
                           subset_case_ids=['VALID-2'])
        self.freeze.write_text(json.dumps(self.frozen))
        rows=load_validation_subset(self.root,self.freeze,self.manifest,self.train,['VALID-2'])
        self.assertEqual([r['case_id'] for r in rows],['VALID-2'])
        with self.assertRaises(ValueError):
            load_validation_subset(self.root,self.freeze,self.manifest,self.train,['VALID-2','VALID-3'])
        with self.assertRaisesRegex(ValueError,'完整50'):
            load_sealed_validation(self.root,self.freeze,self.manifest,self.train)


if __name__ == '__main__': unittest.main()
