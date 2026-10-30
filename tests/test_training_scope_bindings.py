"""动态租户/VDC绑定：合成跨VDC、共享VDC与原生条件解析，不读取用例或标准答案。"""

import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_executor as executor
import runbook_matcher as m
import runbook_scope_bindings as b


QUESTION = "查询租户tenant-a在区域region_demo中的资源列表"
FIELDS = ["id", "name", "status", "tenantName", "vdcName", "logicalRegionName"]


def source(region=True, as_list=False):
    entries = [("vdcName", "{{vdcName}}", "equal")]
    if region:
        entries.append(("logicalRegionName", "{{logicalRegionName}}", "equal"))
    call = {"method": "GET", "url": "/rest/hackthon/db/instances/WIDGET?pageNo=1&pageSize=10000",
            "condition": b._condition(entries)}
    return {"api_call": [call] if as_list else call, "sql": "SELECT id,name,status FROM CLOUD_WIDGET",
            "default_params": {"vdcName": "never-use-this-default", "logicalRegionName": "region_wrong"}}


def rows():
    return [{"id": "a", "name": "resource-a", "status": "active", "tenantName": "tenant-a", "vdcName": "vdc-one", "logicalRegionName": "region_demo"},
            {"id": "b", "name": "resource-b", "status": "active", "tenantName": "tenant-a", "vdcName": "vdc-two", "logicalRegionName": "region_demo"},
            {"id": "c", "name": "resource-c", "status": "active", "tenantName": "tenant-b", "vdcName": "vdc-one", "logicalRegionName": "region_demo"},
            {"id": "d", "name": "resource-d", "status": "active", "tenantName": "tenant-a", "vdcName": "vdc-three", "logicalRegionName": "region_other"}]


def native_store():
    path = Path(executor.__file__).resolve().parents[1] / "output-server" / "data_server.py"
    spec = importlib.util.spec_from_file_location("scope_binding_native_data_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DataStore.__new__(module.DataStore)


def native_filter(records, native):
    wire = b._condition([(entry["key"], entry["value"], entry["operator"]) for entry in native])
    where, values = native_store()._build_where(json.dumps(wire, ensure_ascii=False))
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("CREATE TABLE fixture(row_number INTEGER," + ','.join(field + ' TEXT' for field in FIELDS) + ")")
        connection.executemany("INSERT INTO fixture VALUES (" + ','.join('?' for _ in range(len(FIELDS) + 1)) + ")",
                               [(i, *(row.get(field) for field in FIELDS)) for i, row in enumerate(records)])
        selected = [row[0] for row in connection.execute("SELECT row_number FROM fixture WHERE " + where, values)]
    return [copy.deepcopy(records[i]) for i in selected]


class TenantVdcBindingTests(unittest.TestCase):
    def setUp(self):
        for name, value in [("_schema_columns", {"WIDGET": FIELDS, "OTHER": FIELDS}),
                            ("_ORIG_TO_DESENS", {"CLOUD_WIDGET": "WIDGET", "CLOUD_OTHER": "OTHER"})]:
            context = patch.object(m, name, copy.deepcopy(value))
            context.start(); self.addCleanup(context.stop)

    def lookup(self, call, previous=None):
        return native_filter(rows(), b._native_conditions(call)), "CLOUD_WIDGET"

    def resolve(self, item=None, question=QUESTION, records=None):
        response = (copy.deepcopy(records), "CLOUD_WIDGET") if records is not None else None
        context = (patch.object(m, "_execute_lookup_api", return_value=response) if records is not None
                   else patch.object(m, "_execute_lookup_api", side_effect=self.lookup))
        with context as lookup:
            updated, evidence = b.resolve_tenant_vdc(question, item or source())
        return updated, evidence, lookup

    def test_tenant_spans_multiple_distinct_vdcs_without_aliasing_or_cross_tenant_rows(self):
        item = source(); before = copy.deepcopy(item)
        updated, evidence, lookup = self.resolve(item)
        self.assertTrue(evidence["valid"], evidence)
        self.assertEqual(item, before)
        self.assertIsNot(updated, item)
        self.assertEqual(lookup.call_count, 1)
        final = b._native_conditions(updated["api_call"])
        self.assertEqual(final[0], {"key": "vdcName", "value": ["vdc-one", "vdc-two"], "operator": "in"})
        self.assertIn({"key": "tenantName", "value": "tenant-a", "operator": "equal"}, final)
        selected = native_filter(rows(), final)
        self.assertEqual({row["id"] for row in selected}, {"a", "b"})
        self.assertEqual(evidence["scope_proof"]["grounded_scope_rows"], 2)
        self.assertTrue(evidence["pagination_proof"]["complete_under_native_contract"])
        self.assertFalse(evidence["pagination_proof"]["http_page_status_observed"])
        updated["api_call"]["condition"]["constraint"][0]["simple"]["value"].append("caller-mutated")
        self.assertEqual(evidence["observed_vdc_values"], ["vdc-one", "vdc-two"])

    def test_single_observed_vdc_uses_equal_and_never_question_tenant_as_vdc(self):
        records = rows()[:2]
        records[1]["vdcName"] = records[0]["vdcName"]
        updated, evidence, lookup = self.resolve(records=records)
        self.assertTrue(evidence["valid"], evidence)
        self.assertEqual(b._native_conditions(updated["api_call"])[0],
                         {"key": "vdcName", "value": "vdc-one", "operator": "equal"})
        self.assertNotEqual(evidence["observed_vdc_values"], ["tenant-a"])
        self.assertEqual(evidence["scope_proof"]["grounded_scope_rows"], 2)
        self.assertEqual(lookup.call_count, 1)

    def test_scope_words_inside_quoted_tenant_do_not_add_region_or_vdc_scope(self):
        tenant = "VDC-label区域region_fake"
        record = copy.deepcopy(rows()[0]); record["tenantName"] = tenant
        item = source(False)
        updated, evidence, _ = self.resolve(item, "查询租户'" + tenant + "'的资源列表", [record])
        self.assertTrue(evidence["valid"], evidence)
        self.assertEqual(evidence["question_scope"], {"tenantName": tenant})
        self.assertEqual({entry["key"] for entry in b._native_conditions(updated["api_call"])}, {"tenantName", "vdcName"})

    def test_unquoted_multiword_or_ambiguous_tenant_never_queries_its_first_word(self):
        questions = ["查询租户Team Alpha的资源列表", "查询租户Team 平台的资源列表",
                     "查询租户Team 中国平台的资源列表", "查询租户Team 和平平台的资源列表",
                     "tenantName=Team Alpha logicalRegionName=region_demo", "查询租户O'Brien的资源列表",
                     "查询租户Team.的资源列表", "查询租户Team的资源且租户Alpha的资源",
                     "查询租户'Team Alpha的资源列表", '查询租户“Team Alpha"的资源列表']
        for question in questions:
            item = source(False); before = copy.deepcopy(item)
            with self.subTest(question=question), patch.object(m, "_execute_lookup_api") as lookup:
                unchanged, evidence = b.resolve_tenant_vdc(question, item)
                self.assertIs(unchanged, item)
                self.assertEqual(item, before)
                self.assertIsNotNone(evidence)
                self.assertFalse(evidence["valid"], evidence)
                self.assertEqual(evidence["lookup_calls"], 0)
                lookup.assert_not_called()

    def test_paired_quotes_preserve_full_multiword_tenant_and_name_punctuation(self):
        for opening, closing, tenant in [('"', '"', "Team Alpha"), ("'", "'", "Team Alpha."),
                                         ("“", "”", "团队 Alpha"), ("‘", "’", "Team Alpha"),
                                         ("「", "」", "Team Alpha")]:
            records = rows()[:2]
            for row in records: row["tenantName"] = tenant
            question = "查询租户" + opening + tenant + closing + "的资源列表"
            with self.subTest(question=question):
                updated, evidence, lookup = self.resolve(source(False), question, records)
                self.assertTrue(evidence["valid"], evidence)
                self.assertEqual(evidence["question_scope"], {"tenantName": tenant})
                self.assertEqual(b._native_conditions(lookup.call_args.args[0]),
                                 [{"key": "tenantName", "value": tenant, "operator": "equal"}])
                self.assertIn({"key": "tenantName", "value": tenant, "operator": "equal"},
                              b._native_conditions(updated["api_call"]))

    def test_unquoted_singleword_scope_boundaries_remain_explicit(self):
        for question in ["查询租户tenant-a 在区域region_demo中的资源列表",
                         "tenantName=tenant-a logicalRegionName=region_demo"]:
            with self.subTest(question=question):
                _, evidence, _ = self.resolve(question=question)
                self.assertTrue(evidence["valid"], evidence)
        for question in ["查询租户tenant-a在区域Team Alpha中的资源列表", "查询租户tenant-a在区域'Team Alpha中的资源列表"]:
            with self.subTest(question=question), patch.object(m, "_execute_lookup_api") as lookup:
                _, evidence = b.resolve_tenant_vdc(question, source())
                self.assertFalse(evidence["valid"], evidence)
                lookup.assert_not_called()

    def test_no_region_question_uses_tenant_only_and_keeps_all_its_observed_vdcs(self):
        updated, evidence, _ = self.resolve(source(False), "查询租户tenant-a的资源列表")
        self.assertTrue(evidence["valid"], evidence)
        self.assertEqual(evidence["observed_vdc_values"], ["vdc-one", "vdc-three", "vdc-two"])
        self.assertNotIn("logicalRegionName", {entry["key"] for entry in b._native_conditions(updated["api_call"])})

    def test_explicit_region_is_added_only_with_schema_and_list_container_is_preserved(self):
        updated, evidence, _ = self.resolve(source(False, True))
        self.assertTrue(evidence["valid"], evidence)
        self.assertIsInstance(updated["api_call"], list)
        self.assertIn({"key": "logicalRegionName", "value": "region_demo", "operator": "equal"},
                      b._native_conditions(updated["api_call"][0]))
        with patch.object(m, "_schema_columns", {"WIDGET": [field for field in FIELDS if field != "logicalRegionName"]}):
            item = source(False)
            with patch.object(m, "_execute_lookup_api") as lookup:
                unchanged, rejected = b.resolve_tenant_vdc(QUESTION, item)
            self.assertIs(unchanged, item)
            self.assertEqual(rejected["reason"], "missing_region_schema")
            lookup.assert_not_called()

    def test_unknown_empty_or_nonliteral_vdc_fails_without_mutating_original(self):
        for value in [None, "", " ", False, [], "{{hidden}}", "x" * 257]:
            item = source(); before = copy.deepcopy(item); records = rows()[:2]; records[0]["vdcName"] = value
            unchanged, evidence, lookup = self.resolve(item, records=records)
            with self.subTest(value=value):
                self.assertIs(unchanged, item)
                self.assertEqual(item, before)
                self.assertFalse(evidence["valid"], evidence)
                self.assertEqual(evidence["reason"], "unusable_observed_vdc")
                self.assertEqual(lookup.call_count, 1)

    def test_empty_lookup_and_returned_scope_mismatch_are_closed(self):
        for change in ["empty", "tenant", "region", "missing_vdc"]:
            records = rows()[:2]
            if change == "empty": records = []
            elif change == "tenant": records[0]["tenantName"] = "tenant-b"
            elif change == "region": records[0]["logicalRegionName"] = "region_other"
            else: records[0].pop("vdcName")
            _, evidence, lookup = self.resolve(records=records)
            with self.subTest(change=change):
                self.assertFalse(evidence["valid"], evidence)
                self.assertEqual(lookup.call_count, 1)

    def test_existing_tenant_filter_explicit_dual_scope_and_no_tenant_are_not_applicable(self):
        item = source(); item["api_call"]["condition"]["constraint"].append({"simple": {"name": "tenantName", "value": "tenant-a"}})
        variants = [(QUESTION, item), (QUESTION + "且VDC为vdc-one", source()),
                    ("查询区域region_demo下各VDC的资源列表", source()),
                    ("查询租户tenant-a在区域region_demo可用区az0.dc0的资源列表", source()),
                    ("查询运行中租户tenant-a的资源列表", source(False))]
        for question, item in variants:
            before = copy.deepcopy(item)
            with self.subTest(question=question), patch.object(m, "_execute_lookup_api") as lookup:
                unchanged, evidence = b.resolve_tenant_vdc(question, item)
                self.assertIs(unchanged, item)
                self.assertEqual(item, before)
                self.assertIsNone(evidence)
                lookup.assert_not_called()

    def test_other_ci_multicall_dependency_and_unknown_filters_are_not_applicable(self):
        for change in ["other_table", "multicall", "filter", "dependency", "method", "relation", "query_filter", "params"]:
            item = source()
            if change == "other_table": item["sql"] = item["sql"].replace("CLOUD_WIDGET", "CLOUD_OTHER")
            elif change == "multicall": item["api_call"] = [item["api_call"], copy.deepcopy(item["api_call"])]
            elif change == "filter": item["api_call"]["condition"]["constraint"][0]["simple"]["name"] = "status"
            elif change == "dependency": item["api_call"]["condition"]["constraint"][0]["simple"]["value"] = "{{id from step 1}}"
            elif change == "method": item["api_call"]["method"] = "POST"
            elif change == "relation": item["api_call"]["url"] = item["api_call"]["url"].replace("/instances/", "/relations/")
            elif change == "query_filter": item["api_call"]["url"] += "&condition=unknown"
            else: item["params"] = {"value": "{{vdcName}}"}
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api") as lookup:
                unchanged, evidence = b.resolve_tenant_vdc(QUESTION, item)
                self.assertIs(unchanged, item)
                self.assertIsNone(evidence)
                lookup.assert_not_called()

    def test_required_question_region_is_not_filled_from_defaults(self):
        for question in ["查询租户tenant-a的资源列表", "查询租户tenant-a在区域未知区域的资源列表",
                         "查询租户tenant-a在区域region_one和区域region_two的资源列表"]:
            with self.subTest(question=question), patch.object(m, "_execute_lookup_api") as lookup:
                unchanged, evidence = b.resolve_tenant_vdc(question, source())
                self.assertFalse(evidence["valid"], evidence)
                lookup.assert_not_called()

    def test_observed_set_limit_and_encoded_uri_are_both_checked(self):
        for count, character, reason in [(129, "a", "observed_vdc_set_too_large"),
                                         (128, "%", "tenant_vdc_grounded_uri_too_large"),
                                         (128, "汉", "tenant_vdc_grounded_uri_too_large")]:
            records = []
            for i in range(count):
                row = copy.deepcopy(rows()[0]); row["vdcName"] = str(i).zfill(3) + "-" + character * 252
                records.append(row)
            _, evidence, lookup = self.resolve(records=records)
            with self.subTest(count=count, character=character):
                self.assertFalse(evidence["valid"], evidence)
                self.assertEqual(evidence["reason"], reason)
                self.assertEqual(lookup.call_count, 1)

    def test_oversized_prefill_uri_makes_no_lookup(self):
        question = "查询租户t" + "%" * 22000 + "在区域region_demo中的资源列表"
        with patch.object(m, "_execute_lookup_api") as lookup:
            _, evidence = b.resolve_tenant_vdc(question, source())
        self.assertFalse(evidence["valid"], evidence)
        self.assertEqual(evidence["reason"], "tenant_vdc_lookup_uri_too_large")
        self.assertGreater(evidence["lookup_request_line_bytes"], 60000)
        lookup.assert_not_called()

    def test_uri_budget_reserves_page_digits_before_lookup_and_after_grounding(self):
        first = b._url_bytes("WIDGET", [{"key": "tenantName", "value": "t", "operator": "equal"}])
        tenant = "t" + "%" * ((b._MAX_URL_BYTES - first) // 3)
        question = "查询租户'" + tenant + "'的资源列表"
        with patch.object(m, "_execute_lookup_api") as lookup:
            _, evidence = b.resolve_tenant_vdc(question, source(False))
        self.assertFalse(evidence["valid"], evidence)
        self.assertLessEqual(evidence["lookup_request_line_bytes"], 60000)
        self.assertGreater(evidence["lookup_uri_bound"]["max_page_request_line_bytes"], 60000)
        lookup.assert_not_called()
        _, original, _ = self.resolve()
        limit = original["grounded_request_line_bytes"] + 1
        self.assertLess(original["lookup_uri_bound"]["max_page_request_line_bytes"], limit)
        with patch.object(b, "_MAX_URL_BYTES", limit):
            unchanged, rejected, lookup = self.resolve()
        self.assertFalse(rejected["valid"], rejected)
        self.assertEqual(rejected["reason"], "tenant_vdc_grounded_uri_too_large")
        self.assertLessEqual(rejected["grounded_request_line_bytes"], limit)
        self.assertGreater(rejected["grounded_uri_bound"]["max_page_request_line_bytes"], limit)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(unchanged, source())

    def test_native_parser_and_server_where_match_recorded_grounded_conditions(self):
        updated, evidence, _ = self.resolve()
        captured = []

        def query_server(ci, conditions):
            captured.append((ci, copy.deepcopy(conditions)))
            return native_filter(rows(), conditions)

        with patch.object(executor, "_query_server", side_effect=query_server):
            final_rows, _ = executor._execute_single_api_call(updated["api_call"])
        self.assertEqual(captured, [("WIDGET", evidence["grounded_native_conditions"])])
        self.assertEqual({row["id"] for row in final_rows}, {"a", "b"})
        wire = b._condition([(entry["key"], entry["value"], entry["operator"])
                             for entry in evidence["grounded_native_conditions"]])
        url = (executor.BASE_URL + "/rest/hackthon/db/instances/WIDGET?pageNo=1&pageSize=" + str(executor.PAGE_SIZE) +
               "&condition=" + quote(json.dumps(wire, ensure_ascii=False)))
        self.assertEqual(evidence["grounded_request_line_bytes"], len(url.encode("utf-8")))

    def test_complete_source_with_full_page_boundary_is_not_guessed(self):
        with patch.object(executor, "PAGE_SIZE", 2):
            _, evidence, lookup = self.resolve(records=rows()[:2])
        self.assertFalse(evidence["valid"], evidence)
        self.assertEqual(evidence["reason"], "native_scope_completeness_unproven")
        self.assertEqual(lookup.call_count, 1)
        records = rows()[:2] + [copy.deepcopy(rows()[0])]
        with patch.object(executor, "PAGE_SIZE", 2):
            _, evidence, lookup = self.resolve(records=records)
        self.assertTrue(evidence["valid"], evidence)
        self.assertEqual(evidence["pagination_proof"]["tail_rows"], 1)
        self.assertEqual(evidence["pagination_proof"]["basis"], "native_short_last_page")
        self.assertIn("fixed_native_data_server_static_data", evidence["pagination_proof"]["assumptions"])
        self.assertIn("all_nonfinal_pages_full", evidence["pagination_proof"]["assumptions"])
        self.assertFalse(evidence["pagination_proof"]["http_page_status_observed"])
        for size in [0, -1, False, 1.5]:
            with self.subTest(page_size=size), patch.object(executor, "PAGE_SIZE", size), \
                    patch.object(m, "_execute_lookup_api") as lookup:
                _, rejected = b.resolve_tenant_vdc(QUESTION, source())
                self.assertFalse(rejected["valid"], rejected)
                self.assertEqual(rejected["reason"], "invalid_native_page_size")
                lookup.assert_not_called()

    def test_sql_aggregation_stays_unchanged_and_schema_is_required(self):
        item = source(); item["sql"] = "SELECT status,COUNT(*) AS count FROM CLOUD_WIDGET GROUP BY status"
        updated, evidence, _ = self.resolve(item)
        self.assertTrue(evidence["valid"], evidence)
        self.assertEqual(updated["sql"], item["sql"])
        with patch.object(m, "_schema_columns", {"WIDGET": [field for field in FIELDS if field != "vdcName"]}), \
                patch.object(m, "_execute_lookup_api") as lookup:
            unchanged, evidence = b.resolve_tenant_vdc(QUESTION, item)
        self.assertIs(unchanged, item)
        self.assertIsNone(evidence)
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
