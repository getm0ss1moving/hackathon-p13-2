"""Synthetic text-index invariants; no models, services, question sets or answers."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'implementation'))
from runbook_retriever import RunbookRetriever


def fixture():
    alias = {'id': 'legacy_red', 'after_id': 'blue',
             'description': '红色旧处理器 cpu', 'examples': ['红色旧处理器 cpu']}
    original = [
        {'id': 'red', 'description': '红色处理器 cpu', 'examples': ['红色处理器 cpu'],
         'retrieval_aliases': [copy.deepcopy(alias)]},
        {'id': 'blue', 'description': '蓝色存储 disk', 'examples': ['蓝色存储 disk']},
        {'id': 'green', 'description': '绿色网络 network', 'examples': ['绿色网络 network']},
    ]
    def view(item_id, description, after):
        return {'id': item_id, 'description': description, 'examples': [],
                'description_repeat': 2, 'after_id': after}
    migrated = copy.deepcopy(alias); migrated['after_id'] = 'family'
    combined = [
        {'id': 'family', 'description': '处理器或存储', 'examples': [],
         'retrieval_aliases': [migrated],
         'retrieval_views': [view('red', '红色处理器 cpu', None),
                             view('blue', '蓝色存储 disk', 'red'),
                             view('legacy_red', '红色旧处理器 cpu', 'blue')]},
        copy.deepcopy(original[2]),
    ]
    return original, combined


def tuples(candidates, normalize=False):
    seen, result = set(), []
    for c in candidates:
        item_id = 'family' if normalize and c.id in {'red', 'blue'} else c.id
        if item_id not in seen:
            result.append((item_id, c.tier, c.score, c.coverage)); seen.add(item_id)
    return result


class RetrievalViewTests(unittest.TestCase):
    def test_no_view_path_and_empty_query(self):
        original, _ = fixture()
        index = RunbookRetriever(original)
        self.assertEqual(index.retrieve(''), [])
        self.assertEqual(index.retrieve('红色处理器 cpu')[0].id, 'red')
        self.assertEqual(RunbookRetriever([]).retrieve('未知'), [])

    def test_identical_corpus_and_final_family_mapping(self):
        original, combined = fixture()
        before = copy.deepcopy(combined)
        a, b = RunbookRetriever(original), RunbookRetriever(combined)
        self.assertEqual([(d.item_id, d.tokens) for d in a._docs],
                         [(d.item_id, d.tokens) for d in b._docs])
        self.assertEqual((a._df, a._idf, a._avg_len), (b._df, b._idf, b._avg_len))
        self.assertEqual(combined, before)
        for query in ['红色处理器 cpu', '蓝色存储 disk', '红色旧处理器 cpu',
                      '绿色网络 network', 'cpu 和 disk', '未知 resource', '']:
            for k in [None, 0, 1, 5, 10]:
                self.assertEqual(tuples(a.retrieve(query, k), True), tuples(b.retrieve(query, k)))

    def test_hidden_executable_fields_rejected(self):
        for key in ['api_call', 'sql', 'default_params', 'params', 'answer']:
            _, combined = fixture()
            combined[0]['retrieval_views'][0][key] = 'not text metadata'
            with self.subTest(key=key), self.assertRaises(ValueError):
                RunbookRetriever(combined)

    def test_initial_and_pending_anchors_rejected(self):
        for slot, anchor in [(0, 'missing'), (0, 'red'), (0, 'green'),
                             (1, 'missing'), (1, 'blue')]:
            _, combined = fixture()
            combined[0]['retrieval_views'][slot]['after_id'] = anchor
            with self.subTest(slot=slot, anchor=anchor), self.assertRaises(ValueError):
                RunbookRetriever(combined)

    def test_alias_conflicts_and_duplicate_profiles_rejected(self):
        _, combined = fixture()
        combined[0]['retrieval_aliases'][0]['description'] = 'conflicting payload'
        with self.assertRaises(ValueError):
            RunbookRetriever(combined)
        _, combined = fixture()
        combined[0]['retrieval_views'][1]['id'] = 'red'
        with self.assertRaises(ValueError):
            RunbookRetriever(combined)

    def test_invalid_text_and_repeat_rejected(self):
        for key, value in [('description', 7), ('examples', [7]),
                           ('description_repeat', 0), ('description_repeat', 5),
                           ('description_repeat', True)]:
            _, combined = fixture()
            combined[0]['retrieval_views'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                RunbookRetriever(combined)


if __name__ == '__main__':
    unittest.main()
