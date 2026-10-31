"""中文范围边界与COUNT人口保护：仅合成实体、内存SQL。"""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_matcher as m


class RegionLiteralTests(unittest.TestCase):
    def test_full_chinese_name_overrides_a_short_model_prefix(self):
        values = {'logicalRegionName': '华北9'}
        m._auto_fill_params('查询区域华北9研发虚拟内所有服务器的架构', values, ['logicalRegionName'])
        self.assertEqual(values['logicalRegionName'], '华北9研发虚拟')

    def test_internal_scope_character_and_quoted_name_are_preserved(self):
        for question, expected in [('查询区域内蒙古研发中所有宿主机', '内蒙古研发'),
                                   ('区域“华南 下属区”中的ECS', '华南 下属区'),
                                   ('查询区域region_lab7下所有虚拟机', 'region_lab7')]:
            with self.subTest(question=question):
                self.assertEqual(m._explicit_region_value(question), expected)

    def test_missing_negated_or_multiple_chinese_scope_does_not_supply_a_default(self):
        for question in ['查询整个Region内部所有服务器', '查询区域中的所有服务器',
                         '不在区域华北9下所有服务器',
                         '查询区域华北9下所有服务器和区域华南8下所有服务器']:
            with self.subTest(question=question):
                self.assertIsNone(m._explicit_region_value(question))

    def test_adjacent_zone_is_not_swallowed_into_region(self):
        self.assertEqual(m._explicit_region_value('查询VDCdemo_vdc在区域region_lab7可用区az0.dc0中各租户的ECS实例名和IP'),'region_lab7')
        self.assertEqual(m._explicit_region_value('查询区域华北研发可用区az0.dc0中所有ECS'),'华北研发')


class CountPopulationTests(unittest.TestCase):
    def setUp(self):
        flag = patch.dict(os.environ, {'RUNBOOK_PRESERVE_AGGREGATE_GRAIN':'1'})
        flag.start(); self.addCleanup(flag.stop)

    def test_conditional_count_changes_real_population_and_is_rejected(self):
        original = "SELECT COUNT(*) AS total FROM CLOUD_VOLUME"
        proposal = "SELECT COUNT(CASE WHEN status='ready' THEN 1 END) AS total FROM CLOUD_VOLUME"
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.execute('CREATE TABLE CLOUD_VOLUME(status TEXT)')
            conn.executemany('INSERT INTO CLOUD_VOLUME VALUES (?)', [('ready',),('other',),(None,)])
            self.assertEqual(conn.execute(original).fetchone(), (3,))
            self.assertEqual(conn.execute(proposal).fetchone(), (1,))
        self.assertEqual(m._row_semantics_contract(original, proposal, '资源计数')['reason'], 'changed_count_null_population')

    def test_nullable_column_and_reverse_population_changes_are_rejected(self):
        a = 'SELECT COUNT(*) AS n FROM CLOUD_VOLUME'
        b = 'SELECT COUNT(status) AS n FROM CLOUD_VOLUME'
        self.assertTrue(m._row_semantics_contract(a,b,'数量')['reject'])
        self.assertTrue(m._row_semantics_contract(b,a,'数量')['reject'])

    def test_constant_count_alias_change_and_comment_are_equivalent(self):
        a = 'SELECT COUNT(*) AS old_count FROM CLOUD_VOLUME'
        b = "SELECT COUNT(/* row population */ 1) AS new_count FROM CLOUD_VOLUME"
        self.assertFalse(m._row_semantics_contract(a,b,'数量')['reject'])
        c = "SELECT COUNT('COUNT(CASE)') AS old_count FROM CLOUD_VOLUME"
        self.assertFalse(m._row_semantics_contract(a,c,'数量')['reject'])

    def test_explicit_nonnull_request_can_change_population(self):
        self.assertFalse(m._row_semantics_contract('SELECT COUNT(*) AS n FROM CLOUD_VOLUME',
                         'SELECT COUNT(status) AS n FROM CLOUD_VOLUME','统计status非空记录')['reject'])


if __name__ == '__main__': unittest.main()
