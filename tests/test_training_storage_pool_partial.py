"""纯合成存储池属性测试；不读训练/答案、不发原生GET、不调用评分器或模型。"""

import copy
import json
import os
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_storage_pool_partial as p


QUESTION = "查询区域region_demo下各可用区的存储池名称、磁盘类型、物理容量总量、已用量、可用量和超配比"
BASE_SQL = ("SELECT azoneName, storageProtocol, SUM(totalCapacityGB) AS total_capacity, "
            "SUM(totalCapacityGB - freeCapacityGB) AS used_capacity, SUM(freeCapacityGB) AS free_capacity, "
            "ROUND(SUM(provisionedCapacityGB) * 100.0 / SUM(totalCapacityGB), 2) AS over_subscription_ratio "
            "FROM CLOUD_STORAGE_POOL GROUP BY azoneName, storageProtocol")


def source(as_list=False):
    call = {"method": "GET", "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
            "condition": {"constraint": [{"simple": {"name": "logicalRegionName", "value": "{{logicalRegionName}}", "operator": "equal"}}]}}
    return {"api_call": [call] if as_list else call, "sql": BASE_SQL,
            "default_params": {"logicalRegionName": "unused_default_region"}}


def pool(identity, zone, protocol, total, free, provisioned):
    return {"id": identity, "name": "same-display-name", "poolName": "0", "nativeId": identity + "-native",
            "logicalRegionName": "region_demo", "azoneName": zone, "storageProtocol": protocol,
            "totalCapacityGB": str(total), "freeCapacityGB": str(free), "provisionedCapacityGB": str(provisioned)}


def data():
    return [pool("pool-a", "zone-a", "protocol-a", 100, 40, 130),
            pool("pool-b", "zone-a", "protocol-a", 200, 20, 230),
            pool("pool-c", "zone-a", None, 50, 10, 60),
            pool("pool-d", None, "protocol-a", 70, 15, 80)]


class StoragePoolPartialCandidateTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(p.m, "_schema_columns", {"STORAGE_POOL": list(p._FIELDS)})
        patcher.start(); self.addCleanup(patcher.stop)

    def plan(self, item=None, question=QUESTION):
        plan = p.plan_storage_pool_partial(question, item or source())
        self.assertIsNotNone(plan)
        return plan

    def filled(self, plan):
        item = copy.deepcopy(plan["item"])
        p._call(item)["condition"]["constraint"][0]["simple"]["value"] = plan["scope_values"]["logicalRegionName"]
        return item

    def query(self, plan, rows):
        with closing(sqlite3.connect(":memory:")) as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE CLOUD_STORAGE_POOL (" + ','.join('"' + f + '" TEXT' for f in p._FIELDS) + ")")
            db.executemany("INSERT INTO CLOUD_STORAGE_POOL VALUES (" + ','.join('?' for _ in p._FIELDS) + ")",
                           [tuple(row.get(field) for field in p._FIELDS) for row in rows])
            before = [dict(row) for row in db.execute(plan["base_sql"])]
            after = [dict(row) for row in db.execute(p.compose_storage_pool_partial(plan["base_sql"], plan))]
            return before, after

    def validate(self, plan, rows, question=QUESTION):
        with patch.object(p.m, "_execute_lookup_api", return_value=(copy.deepcopy(rows), "CLOUD_STORAGE_POOL")) as lookup:
            result = p.validate_storage_pool_partial(question, self.filled(plan), plan)
        return result, lookup

    def test_original_six_columns_values_and_group_grain_are_preserved(self):
        plan = self.plan(); before, after = self.query(plan, data())
        self.assertEqual(len(before), 3); self.assertEqual(len(after), 3)
        original_columns = list(before[0])
        self.assertEqual(original_columns, p._COLUMNS)
        key = lambda row: (row["azoneName"], row["storageProtocol"])
        self.assertEqual({key(row): row for row in before},
                         {key(row): {field: row[field] for field in original_columns} for row in after})
        group = next(row for row in after if row["azoneName"] == "zone-a" and row["storageProtocol"] == "protocol-a")
        self.assertEqual((group["total_capacity"], group["free_capacity"], group["used_capacity"]), (300, 60, 240))
        self.assertEqual(group["capacity_scope"], "按可用区和存储协议汇总")

    def test_same_group_multiple_pools_same_names_and_null_keys_are_not_lost_or_multiplied(self):
        plan = self.plan(); _, groups = self.query(plan, data()); all_details = []
        for row in groups:
            details = json.loads(row["pool_details"])
            expected = [pool for pool in data() if (pool["azoneName"], pool["storageProtocol"]) == (row["azoneName"], row["storageProtocol"])]
            self.assertEqual({detail["pool_id"] for detail in details}, {pool["id"] for pool in expected})
            self.assertEqual(len(details), len(expected))
            for detail in details:
                actual = next(pool for pool in expected if pool["id"] == detail["pool_id"])
                for field in ["name", "poolName", "nativeId", "totalCapacityGB", "freeCapacityGB", "provisionedCapacityGB"]:
                    self.assertEqual(detail[field], actual[field])
            all_details.extend(details)
        self.assertEqual(len(all_details), 4)
        self.assertEqual(len({detail["pool_id"] for detail in all_details}), 4)
        self.assertEqual(len({detail["name"] for detail in all_details}), 1)

    def test_disk_type_is_visible_null_and_protocol_is_not_mislabeled(self):
        plan = self.plan(); _, after = self.query(plan, data())
        self.assertEqual(plan["answer_completeness"], "partial")
        self.assertFalse(plan["runtime_default_enabled"])
        for row in after:
            self.assertIsNone(row["disk_type"])
            self.assertEqual(row["disk_type_availability"], "数据源未提供磁盘类型")
            self.assertEqual(row["storage_protocol_label"], "存储协议")
            self.assertEqual(row["capacity_unit"], "GB")
            self.assertEqual(row["over_subscription_ratio_unit"], "%")
            for detail in json.loads(row["pool_details"]):
                self.assertIsNone(detail["disk_type"])
                self.assertEqual(detail["storage_protocol"], row["storageProtocol"])
                self.assertEqual(detail["disk_type_availability"], "数据源未提供磁盘类型")

    def test_mixed_numeric_types_use_original_loader_and_reject_integer_SUM_overflow(self):
        plan = self.plan()
        records = [pool("mixed-"+str(i), "zone-a", "protocol-a", 1, 0, 0) for i in range(3)]
        for record, value in zip(records, [1, "1.0", 9223372036854775806]):
            record["totalCapacityGB"] = value
        with closing(p.executor.load_into_sqlite({p._TABLE: records})) as db:
            with self.assertRaisesRegex(sqlite3.OperationalError, "integer overflow"):
                db.execute(plan["base_sql"]).fetchall()
        result, lookup = self.validate(plan, records)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "storage_pool_capacity_sql_unproven")
        self.assertEqual(lookup.call_count, 1)

    def test_finite_mixed_numeric_types_remain_valid_with_original_loader(self):
        plan = self.plan()
        records = [pool("mixed-"+str(i), "zone-a", "protocol-a", 1, 0, 0) for i in range(3)]
        for record, value in zip(records, [100, "20.0", 30.0]):
            record["totalCapacityGB"] = value
        result, _ = self.validate(plan, records)
        self.assertTrue(result["valid"])
        with closing(p.executor.load_into_sqlite({p._TABLE: records})) as db:
            self.assertEqual(db.execute(plan["base_sql"]).fetchone()[2], 150)

    def test_only_exact_disk_type_attribute_span_is_available_for_coverage(self):
        plan = self.plan(); spans = plan["matched_attribute_spans"]
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(QUESTION[span["start"]:span["end"]], "磁盘类型")
        self.assertEqual(span["role"], "unavailable_storage_pool_attribute")
        self.assertEqual(plan["coverage_question"], QUESTION[:span["start"]] + " " * 4 + QUESTION[span["end"]:])
        self.assertIn("存储池名称", plan["coverage_question"])
        self.assertIn("物理容量总量", plan["coverage_question"])

    def test_positive_complete_grammar_allows_reordering_and_quoted_multiword_region(self):
        question = "请帮我统计区域'Team Alpha'下每个可用区的存储池的名称、物理容量总量、已用容量、空闲容量、超配比例及磁盘类型？"
        plan = self.plan(question=question)
        self.assertEqual(plan["scope_values"], {"logicalRegionName": "Team Alpha"})
        span = plan["matched_attribute_spans"][0]
        self.assertEqual(question[span["start"]:span["end"]], "磁盘类型")

    def test_unknown_or_additional_scope_resource_and_incomplete_requests_do_not_apply(self):
        questions = [QUESTION + "且租户owner", QUESTION + "且VDCowner", QUESTION + "且可用区zone-b",
                     QUESTION + "并列出云硬盘列表", QUESTION + "和云硬盘数量", QUESTION + "及挂载关系",
                     QUESTION.replace("磁盘类型", "磁盘数量"), QUESTION.replace("磁盘类型", "磁盘类型和云硬盘列表"),
                     QUESTION.replace("磁盘类型", "磁盘类型(HDD/SSD)"), QUESTION.replace("磁盘类型、", ""),
                     QUESTION.replace("存储池名称", "名称"), QUESTION.replace("region_demo", "region_demo other"),
                     QUESTION.replace("各可用区", "可用区zone-a"), QUESTION + "且name=pool-a",
                     QUESTION.replace("存储池名称", "存储池pool-a名称"), QUESTION.replace("可用量", "可用量和剩余IP数量")]
        for question in questions:
            with self.subTest(question=question): self.assertIsNone(p.plan_storage_pool_partial(question, source()))

    def test_no_question_entity_default_or_original_object_is_mutated(self):
        item = source(); before = copy.deepcopy(item); plan = self.plan(item)
        self.assertEqual(item, before)
        self.assertEqual(plan["item"], before)
        self.assertEqual(plan["scope_values"]["logicalRegionName"], "region_demo")
        self.assertNotEqual(plan["scope_values"]["logicalRegionName"], before["default_params"]["logicalRegionName"])

    def run_match(self, question=QUESTION, native_rows=None, proposal=None):
        item = {**source(), "id": "rb_fixture_pool", "name": "合成池属性", "resources": ["STORAGE_POOL"], "examples": []}
        before = copy.deepcopy(item)
        flags = {name: "0" for name in (
            "RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES", "RUNBOOK_COMPLETE_GROUPED_AGGREGATES",
            "RUNBOOK_COMPLETE_NETWORK_DETAILS", "RUNBOOK_COMPLETE_IDENTITY_PROJECTION",
            "RUNBOOK_COMPLETE_VPC_SUBNETS", "RUNBOOK_COMPLETE_TENANT_RESOURCES",
            "RUNBOOK_COMPLETE_VM_VOLUME_DETAILS", "RUNBOOK_COMPLETE_PARALLEL_LISTS",
            "RUNBOOK_COMPLETE_DETAIL_COUNT", "RUNBOOK_BIND_TENANT_VDC", "RUNBOOK_VALIDATE_API_DEPENDENCIES")}
        flags.update(RUNBOOK_PARTIAL_STORAGE_POOLS="1", RUNBOOK_RULE_ONLY_FILL="1",
                     RUNBOOK_PRESERVE_TEMPLATE_COLUMNS="1", RUNBOOK_PRESERVE_ROW_SEMANTICS="1",
                     RUNBOOK_REFINE_CONTRACT_PROMPT="1", RUNBOOK_GROUND_SQL_MEASURES="1")
        calls = []
        def ask(prompt, stage="unknown"):
            calls.append(stage)
            return "1" if stage == "select" else proposal or BASE_SQL
        diag = {}
        with patch.dict(os.environ, flags), patch.object(p.m, "llm_ask", side_effect=ask), \
                patch.object(p.m, "_get_table_schemas", return_value="合成池结构由本测试fixture提供"), \
                patch.object(p.m, "_execute_lookup_api", return_value=(
                    data() if native_rows is None else native_rows, p._TABLE)) as lookup:
            result = p.m.match_runbook(question, [item], SimpleNamespace(
                retrieve=lambda question: [SimpleNamespace(id=item["id"])]), diag)
        self.assertEqual(item, before)
        return result, diag, calls, lookup

    def test_full_match_only_waives_proven_missing_attribute_and_displays_partial_units(self):
        output, diag, calls, lookup = self.run_match()
        self.assertIsNotNone(output, diag)
        self.assertEqual(calls, ["select", "refine"])
        lookup.assert_called_once()
        self.assertEqual(diag["answer_completeness"], "partial")
        self.assertEqual(diag["unavailable_attributes"], ["disk_type"])
        self.assertEqual(diag["resource_coverage"]["unsupported"], [])
        span = diag["resource_coverage"]["unavailable_attribute_spans"][0]
        self.assertEqual(QUESTION[span["start"]:span["end"]], "磁盘类型")
        self.assertIn("NULL AS disk_type", output["sql"])
        self.assertIn("数据源未提供磁盘类型", output["sql"])
        self.assertIn("'GB' AS capacity_unit", output["sql"])

    def test_full_match_preserves_capacity_measure_if_refine_changes_it(self):
        proposal = BASE_SQL.replace("SUM(totalCapacityGB) AS total_capacity", "0 AS total_capacity")
        output, diag, calls, _ = self.run_match(proposal=proposal)
        self.assertIsNotNone(output, diag)
        self.assertEqual(calls, ["select", "refine"])
        self.assertEqual(diag["partial_storage_pool_base_fallback"], "changed_known_capacity_group_or_measure")
        self.assertIn("SUM(totalCapacityGB) AS total_capacity", output["sql"])

    def test_full_match_extra_volume_request_is_not_waived_and_empty_data_is_not_success(self):
        output, diag, calls, lookup = self.run_match(question=QUESTION + "和云硬盘列表")
        self.assertIsNone(output)
        self.assertEqual(diag["reason"], "resource_mismatch")
        self.assertEqual(calls, ["select"])
        lookup.assert_not_called()
        output, diag, calls, _ = self.run_match(native_rows=[])
        self.assertIsNone(output)
        self.assertEqual(diag["reason"], "invalid_partial_storage_pool_resources")
        self.assertEqual(calls, ["select"])

    def test_single_call_dict_or_list_and_original_scope_must_be_exact(self):
        self.plan(source(True))
        for change in ["other_ci", "extra_call", "extra_filter", "dependent", "or", "wrong_region", "method", "query_filter"]:
            item = source(); call = item["api_call"]
            if change == "other_ci": call["url"] = call["url"].replace("STORAGE_POOL", "VOLUME")
            elif change == "extra_call": item["api_call"] = [call, copy.deepcopy(call)]
            elif change == "extra_filter": call["condition"]["constraint"].append({"simple": {"name": "tenantName", "value": "owner"}})
            elif change == "dependent": call["condition"]["constraint"][0]["simple"]["value"] = "{{logicalRegionName from step 1}}"
            elif change == "or": call["condition"]["constraint"][0]["logOp"] = "or"
            elif change == "wrong_region": call["condition"]["constraint"][0]["simple"]["value"] = "other_region"
            elif change == "query_filter": call["url"] += "&condition=hidden"
            else: call["method"] = "POST"
            with self.subTest(change=change): self.assertIsNone(p.plan_storage_pool_partial(QUESTION, item))

    def test_simple_table_alias_is_supported_but_expression_alias_or_grain_changes_are_not(self):
        item = source()
        for field in ["azoneName", "storageProtocol", "totalCapacityGB", "freeCapacityGB", "provisionedCapacityGB"]:
            item["sql"] = re.sub(r"\b" + field + r"\b", "s." + field, item["sql"])
        item["sql"] = item["sql"].replace("FROM CLOUD_STORAGE_POOL", "FROM CLOUD_STORAGE_POOL AS s")
        plan = self.plan(item); self.assertIsNotNone(p.compose_storage_pool_partial(item["sql"], plan))
        for sql in [BASE_SQL.replace("AS total_capacity", "AS physical_capacity"), BASE_SQL.replace("* 100.0", "* 1.0"),
                    BASE_SQL + ",id", BASE_SQL.replace("GROUP BY azoneName, storageProtocol", "GROUP BY azoneName"),
                    BASE_SQL + " ORDER BY azoneName", BASE_SQL.replace("CLOUD_STORAGE_POOL", "CLOUD_VOLUME")]:
            changed = source(); changed["sql"] = sql
            with self.subTest(sql=sql): self.assertIsNone(p.plan_storage_pool_partial(QUESTION, changed))

    def test_schema_and_sqlite_json_support_are_required(self):
        for field in p._FIELDS:
            fields = [f for f in p._FIELDS if f != field]
            with self.subTest(field=field), patch.object(p.m, "_schema_columns", {"STORAGE_POOL": fields}):
                self.assertIsNone(p.plan_storage_pool_partial(QUESTION, source()))
        with patch.object(p.sqlite3, "connect", side_effect=sqlite3.OperationalError("JSON unavailable")):
            self.assertIsNone(p.plan_storage_pool_partial(QUESTION, source()))
        for columns in [None, [], p._FIELDS + ["diskType"], p._FIELDS + ["disk_media_type"]]:
            with self.subTest(columns=columns), patch.object(p.m, "_schema_columns", {"STORAGE_POOL": columns}):
                self.assertIsNone(p.plan_storage_pool_partial(QUESTION, source()))

    def test_native_validation_one_scoped_get_and_partial_diagnostics(self):
        for as_list in [False, True]:
            plan = self.plan(source(as_list)); result, lookup = self.validate(plan, data())
            self.assertTrue(result["valid"], result)
            lookup.assert_called_once_with(p._call(self.filled(plan)))
            self.assertEqual(result["answer_completeness"], "partial")
            self.assertEqual(result["scope_proof"]["unique_pool_ids"], 4)
            self.assertEqual(result["scope_proof"]["group_count"], 3)
            self.assertEqual(result["data_quality"]["null_group_key_rows"], 2)
            self.assertFalse(result["data_quality"]["is_complete_business_answer"])

    def test_missing_empty_or_duplicate_identity_scope_and_invalid_numerics_are_rejected(self):
        plan = self.plan()
        for change in ["empty", "missing", "empty_id", "duplicate_id", "name", "scope", "number", "nan", "infinity",
                       "negative", "free_over_total", "bool", "numeric_separator", "unicode_digit", "overflow", "underflow"]:
            rows = data()
            if change == "empty": rows = []
            elif change == "missing": rows[0].pop("poolName")
            elif change == "empty_id": rows[0]["id"] = ""
            elif change == "duplicate_id": rows[1]["id"] = rows[0]["id"]
            elif change == "name": rows[0]["name"] = None
            elif change == "scope": rows[0]["logicalRegionName"] = "different_region"
            elif change == "number": rows[0]["totalCapacityGB"] = "unknown"
            elif change == "nan": rows[0]["totalCapacityGB"] = "NaN"
            elif change == "infinity": rows[0]["totalCapacityGB"] = "Infinity"
            elif change == "negative": rows[0]["totalCapacityGB"] = "-1"
            elif change == "free_over_total": rows[0]["freeCapacityGB"] = "101"
            elif change == "bool": rows[0]["totalCapacityGB"] = True
            elif change == "numeric_separator": rows[0]["totalCapacityGB"] = "1_000"
            elif change == "unicode_digit": rows[0]["totalCapacityGB"] = "１００"
            elif change == "overflow": rows[0]["totalCapacityGB"] = "1e10000"
            else: rows[0]["totalCapacityGB"] = "1e-10000"
            with self.subTest(change=change): self.assertFalse(self.validate(plan, rows)[0]["valid"])

    def test_zero_capacity_is_preserved_with_null_oversubscription_not_defaulted(self):
        plan = self.plan(); rows = [pool("zero", "zone-a", "protocol-a", 0, 0, 0)]
        result, _ = self.validate(plan, rows); self.assertTrue(result["valid"], result)
        before, after = self.query(plan, rows)
        self.assertIsNone(before[0]["over_subscription_ratio"])
        self.assertIsNone(after[0]["over_subscription_ratio"])
        self.assertIsNone(after[0]["disk_type"])

    def test_individually_finite_capacities_cannot_overflow_original_group_sql(self):
        plan = self.plan()
        rows = [pool("large-a", "zone-a", "protocol-a", "1e308", "0", "1e308"),
                pool("large-b", "zone-a", "protocol-a", "1e308", "0", "1e308")]
        result, _ = self.validate(plan, rows)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "nonfinite_storage_pool_group_capacity")

    def test_changed_filled_scope_shape_or_missing_marker_is_rejected_before_get(self):
        plan = self.plan()
        for change in ["scope", "unresolved", "shape", "marker", "coverage"]:
            item, changed = self.filled(plan), copy.deepcopy(plan)
            if change == "scope": p._call(item)["condition"]["constraint"][0]["simple"]["value"] = "different_region"
            elif change == "unresolved": p._call(item)["condition"]["constraint"][0]["simple"]["value"] = "{{logicalRegionName}}"
            elif change == "shape": item["sql"] = item["sql"].replace("AS free_capacity", "AS free")
            elif change == "marker": changed["disk_type_availability"] = "available"
            else: changed["coverage_question"] = "all resources ignored"
            with self.subTest(change=change), patch.object(p.m, "_execute_lookup_api") as lookup:
                self.assertFalse(p.validate_storage_pool_partial(QUESTION, item, changed)["valid"])
                lookup.assert_not_called()
        changed = copy.deepcopy(plan); changed["disk_type_availability"] = "available"
        self.assertIsNone(p.compose_storage_pool_partial(BASE_SQL, changed))

    def test_native_page_completeness_and_encoded_url_bound_fail_closed(self):
        plan = self.plan()
        with patch.object(p.executor, "PAGE_SIZE", 4): result, _ = self.validate(plan, data())
        self.assertEqual(result["reason"], "native_storage_pool_completeness_unproven")
        self.assertFalse(result["pagination_proof"]["http_page_status_observed"])
        question = QUESTION.replace("region_demo", "'区域 %/Alpha'")
        quoted = self.plan(question=question); bound = p._uri_bound(p._call(self.filled(quoted)))
        self.assertGreater(bound["max_page_request_line_bytes"], bound["first_page_bytes"])
        with patch.object(p, "_MAX_URL_BYTES", bound["first_page_bytes"]), patch.object(p.m, "_execute_lookup_api") as lookup:
            result = p.validate_storage_pool_partial(question, self.filled(quoted), quoted)
        self.assertEqual(result["reason"], "storage_pool_native_uri_too_large")
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
