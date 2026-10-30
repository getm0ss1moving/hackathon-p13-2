"""仅空schema EXPLAIN/authorizer合成测试；不读数据，不执行候选查询。"""

import unittest
from pathlib import Path
import os
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))

import runbook_measurement_guard as g
import runbook_matcher as m


SCHEMA = {"CLOUD_SUBNET": ["name", "cidr", "created_at", "updated_at", "value", "random"]}
BASE = "SELECT name AS subnet_name,cidr AS subnet_cidr FROM CLOUD_SUBNET"


class MeasurementSourceGuardTests(unittest.TestCase):
    def inspect(self, sql, schema=None):
        return g.inspect_measurement_sources(sql, SCHEMA if schema is None else schema)

    def assert_safe(self, sql, schema=None):
        result = self.inspect(sql, schema)
        self.assertTrue(result["compiled"], result)
        self.assertTrue(result["valid"], result)
        return result

    def assert_rejected(self, sql, source=None):
        result = self.inspect(sql)
        self.assertFalse(result["valid"], result)
        if source:
            self.assertTrue(any(h["source"] == source for h in result["hazards"]), result)
        return result

    def test_nested_epoch_clock_as_fake_measurement_is_rejected_despite_shape_change(self):
        candidate = "SELECT SUM(CAST(ABS(CAST(strftime('%s','now') AS INTEGER)) AS INTEGER)) AS dummy FROM CLOUD_SUBNET"
        decision = g.measurement_source_contract(BASE, candidate, SCHEMA)
        self.assertTrue(decision["reject"], decision)
        self.assertTrue(decision["safe_original_fallback"])
        self.assertFalse(decision["original_requires_review"])
        self.assertIn("sum", decision["candidate"]["functions"])
        self.assertTrue(any(h["source"] == "clock" for h in decision["candidate"]["hazards"]))
        self.assertEqual(decision["candidate"]["reads"], [{"table": "CLOUD_SUBNET", "column": ""}])

    def test_function_name_alone_cannot_hide_column_to_clock_argument_change(self):
        original = "SELECT SUM(CAST(strftime('%s',created_at) AS REAL)) FROM CLOUD_SUBNET"
        candidate = original.replace("created_at", "'now'")
        result = g.measurement_source_contract(original, candidate, SCHEMA)
        self.assertEqual(result["original"]["functions"], result["candidate"]["functions"])
        self.assertTrue(result["reject"])

    def test_legal_row_count_and_real_column_aggregates_need_no_blanket_read_rule(self):
        for expression in ["COUNT(*)", "COUNT(1)", "COUNT(DISTINCT name)", "SUM(value)", "AVG(value)",
                           "SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END)", "ROUND(SUM(value)*100.0/COUNT(*),2)"]:
            with self.subTest(expression=expression): self.assert_safe("SELECT " + expression + " FROM CLOUD_SUBNET")
        result = self.assert_safe("SELECT COUNT(*) FROM CLOUD_SUBNET")
        self.assertEqual(result["reads"], [{"table": "CLOUD_SUBNET", "column": ""}])

    def test_template_constant_labels_and_function_text_are_not_calls(self):
        for sql in ["SELECT 'random() strftime(now) CURRENT_TIMESTAMP' AS label,COUNT(*) FROM CLOUD_SUBNET",
                    "SELECT 'it''s random() -- now /* datetime() */' AS label,name FROM CLOUD_SUBNET",
                    "SELECT 'now' AS label,1 AS fixed_value FROM CLOUD_SUBNET",
                    "SELECT random AS stored_value,name FROM CLOUD_SUBNET"]:
            with self.subTest(sql=sql): self.assert_safe(sql)

    def test_line_block_comments_do_not_create_sources_or_hide_actual_calls(self):
        self.assert_safe("SELECT name /* random(),datetime('now') */,cidr -- CURRENT_TIMESTAMP\nFROM CLOUD_SUBNET")
        self.assert_rejected("SELECT strftime /* harmless */ ('%s',/* real call */'now') FROM CLOUD_SUBNET", "clock")
        self.assert_rejected("SELECT SUM(/* A */abs(/* B */random())) FROM CLOUD_SUBNET", "random")

    def test_no_argument_and_format_only_temporal_calls_use_clock(self):
        for expression in ["date()", "time()", "datetime()", "julianday()", "unixepoch()", "strftime('%Y')"]:
            with self.subTest(expression=expression): self.assert_rejected("SELECT " + expression + " FROM CLOUD_SUBNET", "clock")

    def test_explicit_now_shortcut_and_keywords_are_clock_sources(self):
        for expression in ["date('NOW')", "datetime('subsec')", "unixepoch('subsecond')", "strftime('%s','subsec')",
                           "CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME", "timediff('now',created_at)"]:
            with self.subTest(expression=expression): self.assert_rejected("SELECT " + expression + " FROM CLOUD_SUBNET", "clock")

    def test_random_and_environment_sources_are_actual_function_calls(self):
        for expression, source in [("random()", "random"), ("randomblob(4)", "random"),
                                   ("changes()", "sqlite_environment"), ("total_changes()", "sqlite_environment"),
                                   ("last_insert_rowid()", "sqlite_environment"), ("sqlite_version()", "sqlite_environment"),
                                   ("sqlite_source_id()", "sqlite_environment"), ("sqlite_compileoption_used('THREADSAFE')", "sqlite_environment")]:
            with self.subTest(expression=expression): self.assert_rejected("SELECT " + expression + " FROM CLOUD_SUBNET", source)

    def test_real_column_date_formatting_static_dates_and_unit_modifiers_are_safe(self):
        for expression in ["strftime('%Y-%m',created_at)", "date(created_at)", "datetime(s.created_at,'+1 day')",
                           "datetime(created_at,'unixepoch')", "strftime('%s',created_at,'subsec')",
                           "strftime('now',created_at)", "strftime('localtime utc',created_at)",
                           "date('2020-01-01')", "julianday(0)", "datetime(NULL)",
                           "timediff(updated_at,created_at)", "strftime('%Y',date(created_at))",
                           "date(CAST(created_at AS TEXT))", "date(coalesce(created_at,'2020-01-01'))",
                           "date(ifnull(created_at,updated_at))", "date(nullif(created_at,'now'))"]:
            with self.subTest(expression=expression): self.assert_safe("SELECT " + expression + " FROM CLOUD_SUBNET AS s")

    def test_nested_clock_fallback_and_timezone_environment_are_not_column_measurements(self):
        for expression, source in [("strftime('%Y',datetime('now'))", "clock"),
                                   ("date(coalesce(created_at,'now'))", "clock"),
                                   ("date(CAST('now' AS TEXT))", "clock"),
                                   ("datetime(created_at,'localtime')", "sqlite_environment"),
                                   ("strftime('%Y',created_at,'utc')", "sqlite_environment")]:
            with self.subTest(expression=expression): self.assert_rejected("SELECT " + expression + " FROM CLOUD_SUBNET", source)

    def test_unproven_computed_time_values_and_modifiers_fail_closed(self):
        for expression in ["date('n'||'ow')", "date(lower('NOW'))", "date(char(110,111,119))",
                           "date(coalesce(created_at,'n'||'ow'))", "date(CASE WHEN value IS NULL THEN 'now' ELSE created_at END)",
                           "datetime(created_at,lower('localtime'))", "date('n'||'ow'||substr(created_at,1,0))"]:
            with self.subTest(expression=expression): self.assert_rejected("SELECT " + expression + " FROM CLOUD_SUBNET", "unproven")

    def test_quoted_function_and_identifier_boundaries_follow_sqlite(self):
        self.assert_rejected('SELECT "strftime"(\'%s\',\'now\') FROM CLOUD_SUBNET', "clock")
        self.assert_rejected('SELECT strftime(\'%s\',"now") FROM CLOUD_SUBNET', "clock")
        schema = {"CLOUD_SUBNET": SCHEMA["CLOUD_SUBNET"] + ["now", "CURRENT_TIMESTAMP"]}
        self.assert_safe('SELECT strftime(\'%Y\',"now"),"CURRENT_TIMESTAMP" FROM CLOUD_SUBNET', schema)
        self.assert_safe('SELECT strftime(\'%Y\',[created_at]),`random` FROM CLOUD_SUBNET')

    def test_schema_reads_are_recorded_and_runtime_metadata_is_not_cmdb(self):
        result = self.assert_safe("SELECT SUM(value),strftime('%Y',created_at),name FROM CLOUD_SUBNET")
        self.assertEqual({row["column"] for row in result["reads"]}, {"value", "created_at", "name"})
        result = self.assert_rejected("SELECT name FROM sqlite_master")
        self.assertIn("read_outside_cmdb_schema", result["denied"])

    def test_unknown_functions_missing_columns_nonselect_and_multistatement_are_unproven(self):
        for sql in ["SELECT not_a_builtin(value) FROM CLOUD_SUBNET", "SELECT missing FROM CLOUD_SUBNET",
                    "UPDATE CLOUD_SUBNET SET value=1", "SELECT name FROM CLOUD_SUBNET; SELECT random()"]:
            with self.subTest(sql=sql): self.assertFalse(self.inspect(sql)["valid"])

    def test_original_is_also_checked_and_unsafe_fallback_is_explicit(self):
        unsafe = "SELECT strftime('%s','now') AS value FROM CLOUD_SUBNET"
        unchanged = g.measurement_source_contract(unsafe, unsafe, SCHEMA)
        self.assertTrue(unchanged["reject"])
        self.assertTrue(unchanged["original_requires_review"])
        self.assertFalse(unchanged["safe_original_fallback"])
        self.assertEqual(unchanged["new_source_counts"], [])
        fixed = g.measurement_source_contract(unsafe, BASE, SCHEMA)
        self.assertFalse(fixed["reject"])
        self.assertTrue(fixed["original_requires_review"])

    def test_no_full_lineage_or_answer_claim_for_arbitrary_fixed_constants(self):
        result = g.measurement_source_contract(BASE, "SELECT SUM(42) FROM CLOUD_SUBNET", SCHEMA)
        self.assertFalse(result["reject"])
        self.assertEqual(result["scope"], "runtime_source_guard_not_full_numeric_lineage_or_answer_correctness")

    def test_integrated_refinement_gate_reverts_runtime_dummy_despite_aggregate_shape_change(self):
        proposed = "SELECT SUM(CAST(ABS(CAST(strftime('%s','now') AS INTEGER)) AS INTEGER)) AS dummy FROM CLOUD_SUBNET"
        diagnostics = {}
        with patch.object(m, "_schema_columns", {"SUBNET": SCHEMA["CLOUD_SUBNET"]}), \
                patch.dict(os.environ, {"RUNBOOK_GROUND_SQL_MEASURES": "1"}):
            final = m._validated_refinement(proposed, BASE, "查询子网IP总量和已分配量", diagnostics)
        self.assertEqual(final, BASE)
        self.assertTrue(diagnostics["measurement_source_contract"]["reject"])
        self.assertTrue(diagnostics["measurement_source_contract"]["safe_original_fallback"])

    def test_integrated_gate_keeps_original_labels_and_true_aggregates(self):
        original = "SELECT SUM(value) AS amount FROM CLOUD_SUBNET"
        proposed = "SELECT SUM(value) AS amount,COUNT(*) AS resource_count FROM CLOUD_SUBNET"
        with patch.object(m, "_schema_columns", {"SUBNET": SCHEMA["CLOUD_SUBNET"]}), \
                patch.dict(os.environ, {"RUNBOOK_GROUND_SQL_MEASURES": "1", "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1"}):
            diagnostics = {}
            self.assertEqual(m._validated_refinement(proposed, original, "查询总量和数量", diagnostics), proposed)
            self.assertFalse(diagnostics["measurement_source_contract"]["reject"])


if __name__ == "__main__":
    unittest.main()
