"""已审稀疏投影必须保留缺列/空行语义，不用假空替代缺失字段。"""
from contextlib import closing
import os
import sqlite3
import unittest
from unittest.mock import patch
import runbook_matcher as m


SQL = ('SELECT x.hostName AS name, x.hostIpAddress AS ip_address, x.hostType AS type '
       'FROM (SELECT *, NULL AS hostName, NULL AS hostIpAddress, NULL AS hostType, NULL AS _empty '
       'FROM SYS_X86Server) AS x WHERE x._empty IS NULL')


class SparseRefinementTests(unittest.TestCase):
    def setUp(self):
        flag = patch.dict(os.environ, {'RUNBOOK_PRESERVE_SPARSE_NULLS': '1'})
        flag.start();self.addCleanup(flag.stop)

    def test_candidate_remains_disabled_by_default(self):
        proposal = 'SELECT x.hostName AS name, x.hostIpAddress AS ip_address, x.hostType AS type FROM SYS_X86Server AS x'
        with patch.dict(os.environ, {'RUNBOOK_PRESERVE_SPARSE_NULLS': '0', 'RUNBOOK_GROUND_SQL_MEASURES': '0',
              'RUNBOOK_PRESERVE_ROW_SEMANTICS': '0', 'RUNBOOK_PRESERVE_LITERAL_LABELS': '0', 'RUNBOOK_PRESERVE_TEMPLATE_COLUMNS': '0'}), \
                patch.dict(m._schema_columns, {'S_X86Server': ['hostName', 'hostIpAddress', 'hostType']}):
            diagnostics = {}
            m._validated_refinement(proposal, SQL, '合成查询', diagnostics)
        self.assertNotIn('sparse_projection_contract', diagnostics)

    def test_dropped_fallback_reverts_and_original_executes_missing_columns(self):
        proposal = 'SELECT x.hostName AS name, x.hostIpAddress AS ip_address, x.hostType AS type FROM SYS_X86Server AS x'
        diagnostics = {}
        kept = m._validated_refinement(proposal, SQL, '查询区域region_alpha下服务器列表', diagnostics)
        self.assertEqual(kept, SQL)
        self.assertTrue(diagnostics['sparse_projection_contract']['preserved'])
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE SYS_X86Server(id TEXT,hostType TEXT)')
            connection.execute("INSERT INTO SYS_X86Server VALUES ('synthetic','server')")
            self.assertEqual(connection.execute(kept).fetchall(), [(None, None, 'server')])
            with self.assertRaises(sqlite3.OperationalError): connection.execute(proposal)

    def test_real_empty_and_original_loader_placeholder_do_not_produce_a_resource(self):
        for schema, insert in [('id TEXT', None), ('_empty INTEGER', 'INSERT INTO SYS_X86Server VALUES (1)')]:
            with self.subTest(schema=schema), closing(sqlite3.connect(':memory:')) as connection:
                connection.execute('CREATE TABLE SYS_X86Server(' + schema + ')')
                if insert: connection.execute(insert)
                self.assertEqual(connection.execute(SQL).fetchall(), [])

    def test_existing_real_fields_are_not_overwritten_with_null(self):
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE SYS_X86Server(hostName TEXT,hostIpAddress TEXT,hostType TEXT)')
            connection.execute("INSERT INTO SYS_X86Server VALUES ('synthetic_host','synthetic_ip','server')")
            self.assertEqual(connection.execute(SQL).fetchall(), [('synthetic_host','synthetic_ip','server')])


if __name__ == '__main__': unittest.main()
