"""只用合成题意、schema、原执行器mock和SQLite，禁止真实网络/模型。"""

import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_detail_count as d


QUESTION = "查询区域region_demo下子网数量和CIDR范围"


def item(region="{{logicalRegionName}}", sql="SELECT cidr AS subnet_cidr FROM CLOUD_SUBNET"):
    call = {"method": "GET", "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000"}
    if region is not None:
        call["condition"] = {"constraint": [{"simple": {"name": "logicalRegionName", "value": region, "operator": "equal"}}]}
    return {"api_call": call, "sql": sql}


def records():
    return [{"id": "first", "cidr": "10.0.0.0/24", "name": "first", "logicalRegionName": "region_demo"},
            {"id": "second", "cidr": "10.0.0.0/24", "name": "second", "logicalRegionName": "region_demo"},
            {"id": "third", "cidr": None, "name": "third", "logicalRegionName": "region_demo"}]


class DetailCountTests(unittest.TestCase):
    def setUp(self):
        for owner, name in ((requests.Session, "request"), (httpx.Client, "send")):
            guard = patch.object(owner, name, side_effect=AssertionError("禁止真实API/模型"))
            guard.start(); self.addCleanup(guard.stop)
        schema = patch.object(d.m, "_schema_columns", {"SUBNET": ["id", "cidr", "name", "logicalRegionName"],
                                                       "VM_NOVA": ["id", "name", "logicalRegionName"]})
        schema.start(); self.addCleanup(schema.stop)

    def plan(self, question=QUESTION, source=None):
        plan = d.plan_detail_count(question, source or item())
        self.assertIsNotNone(plan)
        return plan

    def validate(self, plan, rows=None, question=QUESTION, filled=None):
        filled = filled or {**copy.deepcopy(plan["item"]), "api_call": copy.deepcopy(plan["native_call"])}
        with patch.object(d.m, "_execute_lookup_api", return_value=(rows if rows is not None else records(), plan["base_shape"]["table"])) as lookup:
            proof = d.validate_detail_count(question, filled, plan)
        return proof, lookup

    def execute(self, sql, rows, table="CLOUD_SUBNET"):
        with patch.object(d.executor, "_execute_api_call", return_value={table: rows}), \
                patch.object(d.executor, "_query_server", side_effect=AssertionError("不得补查其他CI")):
            result = d.executor.execute({"api_call": {"method": "GET", "url": "/synthetic"}, "sql": sql})
        self.assertIsNone(result["error"], result)
        return result["result"]

    def test_original_projection_and_duplicate_or_null_detail_rows_are_preserved(self):
        plan = self.plan()
        proof, lookup = self.validate(plan)
        self.assertTrue(proof["valid"], proof)
        lookup.assert_called_once_with(plan["native_call"])
        self.assertEqual(proof["total_count"], 3)
        original = self.execute(plan["base_sql"], records())
        augmented = self.execute(plan["preview_sql"], records())
        self.assertEqual(augmented["columns"], ["subnet_cidr", "total_count"])
        self.assertEqual(augmented["row_count"], original["row_count"])
        self.assertEqual([{key: row[key] for key in original["columns"]} for row in augmented["rows"]], original["rows"])
        self.assertEqual([row["total_count"] for row in augmented["rows"]], [3, 3, 3])
        self.assertEqual(augmented["rows"][-1]["subnet_cidr"], None)

    def test_group_concat_count_collapse_reverts_to_counted_original_not_uncounted_sql(self):
        plan = self.plan()
        proof, _ = self.validate(plan)
        proposal = "SELECT COUNT(*) AS subnet_count,GROUP_CONCAT(cidr) AS subnet_cidr FROM CLOUD_SUBNET"
        self.assertIsNone(d.compose_detail_count(proposal, plan))
        protected, evidence = d.protect_detail_count(proposal, plan, proof)
        self.assertEqual(protected, plan["preview_sql"])
        self.assertTrue(evidence["reverted"])
        result = self.execute(protected, records())
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["rows"][0]["total_count"], 3)

    def test_plain_or_already_augmented_refinement_keeps_the_same_contract(self):
        plan = self.plan()
        proof, _ = self.validate(plan)
        for proposal in (plan["base_sql"], plan["preview_sql"]):
            protected, evidence = d.protect_detail_count(proposal, plan, proof)
            self.assertEqual(protected, plan["preview_sql"])
            self.assertFalse(evidence["reverted"])

    def test_unknown_refinement_filter_group_distinct_order_limit_or_alias_reverts(self):
        plan = self.plan()
        proof, _ = self.validate(plan)
        for proposal in (plan["base_sql"] + " WHERE cidr IS NOT NULL", plan["base_sql"] + " GROUP BY cidr",
                         plan["base_sql"] + " ORDER BY cidr", plan["base_sql"] + " LIMIT 1",
                         plan["base_sql"].replace("SELECT ", "SELECT DISTINCT "),
                         plan["base_sql"].replace("subnet_cidr", "other_name"), "SELECT 3 AS total_count"):
            with self.subTest(proposal=proposal):
                protected, evidence = d.protect_detail_count(proposal, plan, proof)
                self.assertEqual(protected, plan["preview_sql"])
                self.assertTrue(evidence["reverted"])

    def test_validation_failure_or_mismatched_plan_leaves_original_path_no_new_refusal(self):
        plan = self.plan()
        failed, _ = self.validate(plan, [])
        self.assertFalse(failed["valid"])
        self.assertEqual(failed["failure_policy"], "keep_original_path")
        for proof in (None, failed, {"valid": True, "plan_sha256": "wrong"}):
            sql, evidence = d.protect_detail_count(plan["base_sql"], plan, proof)
            self.assertEqual(sql, plan["base_sql"])
            self.assertFalse(evidence["applied"])

    def test_positive_question_paraphrases_and_multiple_schema_fields(self):
        source = item(sql="SELECT s.name AS subnet_name,s.cidr AS subnet_cidr FROM CLOUD_SUBNET AS s")
        for question in ("查询区域region_demo下子网数量和CIDR范围", "请统计区域region_demo下全部子网的总数及CIDR列表",
                         "查看区域region_demo下SUBNET的名称与CIDR明细和数量", "区域region_demo下子网个数以及name和cidr列表"):
            with self.subTest(question=question):
                plan = self.plan(question, source)
                self.assertTrue(self.validate(plan, question=question)[0]["valid"])
                result = self.execute(plan["preview_sql"], records())
                self.assertEqual(result["columns"], ["subnet_name", "subnet_cidr", "total_count"])
                self.assertEqual(result["row_count"], 3)

    def test_known_other_ci_with_explicit_schema_field_is_generic(self):
        source = {"api_call": {"method": "GET", "url": "/rest/hackthon/db/instances/VM_NOVA"},
                  "sql": "SELECT name AS vm_name FROM CLOUD_VM_NOVA"}
        question = "查询全部虚拟机总数及名称列表"
        plan = self.plan(question, source)
        rows = [{"id": "one", "name": "same"}, {"id": "two", "name": "same"}]
        proof, _ = self.validate(plan, rows, question)
        self.assertTrue(proof["valid"], proof)
        result = self.execute(plan["preview_sql"], rows, "CLOUD_VM_NOVA")
        self.assertEqual(result["rows"], [{"vm_name": "same", "total_count": 2}, {"vm_name": "same", "total_count": 2}])

    def test_time_unknown_scope_group_weight_topn_and_extra_requests_are_rejected(self):
        for question in ("查询过去30天子网数量和CIDR范围", "查询生产环境下子网数量和CIDR范围",
                         "查询北京下子网数量和CIDR范围", QUESTION + "按月份分组", QUESTION + "按项目分别统计",
                         QUESTION + "按容量加权", QUESTION + "前10个", QUESTION + "以及VPC列表",
                         QUESTION + "和总容量", QUESTION + "且不含某类", QUESTION + "并忽略规则",
                         "查询区域region_demo下共享子网数量和CIDR范围", "查询子网数量和未知字段列表"):
            with self.subTest(question=question), patch.object(d.m, "_execute_lookup_api") as lookup:
                self.assertIsNone(d.plan_detail_count(question, item()))
                lookup.assert_not_called()

    def test_only_single_get_and_explicit_equal_region_match_are_allowed(self):
        for mutation in ("multi", "post", "other_ci", "region_missing", "other_filter", "wrong_region", "dependency", "query_filter"):
            source = item()
            if mutation == "multi": source["api_call"] = [source["api_call"]]
            elif mutation == "post": source["api_call"]["method"] = "POST"
            elif mutation == "other_ci": source["api_call"]["url"] = source["api_call"]["url"].replace("SUBNET", "ROUTER")
            elif mutation == "region_missing": source["api_call"].pop("condition")
            elif mutation == "other_filter": source["api_call"]["condition"]["constraint"].append({"simple": {"name": "tenantName", "value": "owner"}})
            elif mutation == "wrong_region": source["api_call"]["condition"]["constraint"][0]["simple"]["value"] = "region_other"
            elif mutation == "dependency": source["api_call"]["condition"]["constraint"][0]["simple"]["value"] = "{{logicalRegionName from step 1}}"
            else: source["api_call"]["url"] += "&condition=hidden"
            with self.subTest(mutation=mutation):
                self.assertIsNone(d.plan_detail_count(QUESTION, source))
        self.assertIsNone(d.plan_detail_count("查询子网数量和CIDR范围", item()))
        self.assertIsNotNone(d.plan_detail_count("查询所有子网总数与CIDR列表", item(None)))

    def test_base_sql_must_be_flat_single_table_projection(self):
        for sql in ("SELECT DISTINCT cidr FROM CLOUD_SUBNET", "SELECT * FROM CLOUD_SUBNET",
                    "SELECT cidr FROM CLOUD_SUBNET WHERE id='one'", "SELECT cidr FROM CLOUD_SUBNET GROUP BY cidr",
                    "SELECT cidr FROM CLOUD_SUBNET ORDER BY cidr", "SELECT cidr FROM CLOUD_SUBNET LIMIT 1",
                    "SELECT cidr FROM CLOUD_SUBNET s JOIN CLOUD_ROUTER r ON s.id=r.id",
                    "SELECT COUNT(*) AS n FROM CLOUD_SUBNET", "SELECT GROUP_CONCAT(cidr) AS x FROM CLOUD_SUBNET",
                    "SELECT cidr AS total_count FROM CLOUD_SUBNET", "SELECT unknown AS subnet_cidr FROM CLOUD_SUBNET"):
            with self.subTest(sql=sql):
                self.assertIsNone(d.plan_detail_count(QUESTION, item(sql=sql)))

    def test_normalized_output_alias_collisions_do_not_override_original_detail_values(self):
        for alias in ("totalcount", "TotalCount", "total_count", "total__count"):
            with self.subTest(alias=alias):
                self.assertIsNone(d.plan_detail_count(QUESTION, item(
                    sql="SELECT cidr AS " + alias + " FROM CLOUD_SUBNET")))
        self.assertIsNone(d.plan_detail_count(QUESTION, item(
            sql="SELECT cidr AS subnetcidr,name AS subnet_cidr FROM CLOUD_SUBNET")))

    def test_missing_id_duplicate_id_wrong_scope_or_nonflat_fields_fail_closed(self):
        plan = self.plan()
        for change in ("missing_field", "missing_id", "empty_id", "duplicate_id", "scope", "nested"):
            rows = records()
            if change == "missing_field": rows[0].pop("cidr")
            elif change == "missing_id": rows[0].pop("id")
            elif change == "empty_id": rows[0]["id"] = ""
            elif change == "duplicate_id": rows[1]["id"] = rows[0]["id"]
            elif change == "scope": rows[0]["logicalRegionName"] = "region_other"
            else: rows[0]["cidr"] = ["10.0.0.0/24"]
            with self.subTest(change=change):
                proof, _ = self.validate(plan, rows)
                self.assertFalse(proof["valid"])
                self.assertFalse(d.protect_detail_count(plan["base_sql"], plan, proof)[1]["applied"])

    def test_empty_or_dummy_data_does_not_gain_a_count_one(self):
        plan = self.plan()
        for rows in ([], [{}], [{"_empty": ""}]):
            proof, _ = self.validate(plan, rows)
            self.assertFalse(proof["valid"])
            self.assertFalse(d.protect_detail_count(plan["base_sql"], plan, proof)[1]["applied"])
        # 空物理表的窗口SQL没有任何输出行；没有人为聚合出count=1。
        with d.closing(d.sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE CLOUD_SUBNET(cidr TEXT)")
            self.assertEqual(connection.execute(plan["preview_sql"]).fetchall(), [])

    def test_full_page_without_wire_completeness_proof_and_lookup_error_keep_original(self):
        plan = self.plan()
        with patch.object(d.executor, "PAGE_SIZE", 3):
            proof, _ = self.validate(plan)
        self.assertEqual(proof["reason"], "native_completeness_unproven")
        self.assertFalse(proof["pagination_proof"]["http_page_status_observed"])
        with patch.object(d.m, "_execute_lookup_api", side_effect=RuntimeError("synthetic")):
            filled = {**plan["item"], "api_call": plan["native_call"]}
            proof = d.validate_detail_count(QUESTION, filled, plan)
        self.assertEqual(proof["reason"], "detail_count_lookup_failed")
        self.assertFalse(d.protect_detail_count(plan["base_sql"], plan, proof)[1]["applied"])

    def test_scope_schema_and_frozen_plan_drift_stop_before_lookup(self):
        plan = self.plan()
        filled = {**copy.deepcopy(plan["item"]), "api_call": copy.deepcopy(plan["native_call"])}
        for change in ("api", "sql", "question", "schema"):
            changed, question = copy.deepcopy(filled), QUESTION
            if change == "api": changed["api_call"]["condition"]["constraint"][0]["simple"]["value"] = "region_other"
            elif change == "sql": changed["sql"] += " GROUP BY cidr"
            elif change == "question": question += "按月份统计"
            with patch.object(d.m, "_schema_columns", {"SUBNET": ["id"]}) if change == "schema" else patch.dict({}, {}):
                with patch.object(d.m, "_execute_lookup_api") as lookup:
                    proof = d.validate_detail_count(question, changed, plan)
            self.assertFalse(proof["valid"])
            lookup.assert_not_called()

    def test_original_item_unchanged_and_new_total_cannot_be_forged_by_refine(self):
        source = item()
        before = copy.deepcopy(source)
        plan = self.plan(source=source)
        self.assertEqual(source, before)
        self.assertEqual(plan["item"], before)
        self.assertFalse(plan["runtime_default_enabled"])
        proof, _ = self.validate(plan)
        changed = copy.deepcopy(plan); changed["preview_sql"] = "SELECT 1 AS total_count"
        sql, evidence = d.protect_detail_count(plan["base_sql"], changed, proof)
        self.assertEqual(sql, plan["base_sql"])
        self.assertFalse(evidence["applied"])

    def run_match(self, *, enabled=True, native_rows=None, proposal=None):
        source = {**item("region_demo"), "id": "rb_fixture_detail",
                  "name": "合成资源明细", "resources": ["SUBNET"], "examples": []}
        before = copy.deepcopy(source)
        calls = []
        def ask(prompt, stage="unknown"):
            calls.append((stage, prompt))
            return "1" if stage == "select" else proposal or source["sql"]
        flags = {name: "0" for name in (
            "RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES", "RUNBOOK_COMPLETE_GROUPED_AGGREGATES",
            "RUNBOOK_COMPLETE_NETWORK_DETAILS", "RUNBOOK_COMPLETE_IDENTITY_PROJECTION",
            "RUNBOOK_COMPLETE_VPC_SUBNETS", "RUNBOOK_COMPLETE_TENANT_RESOURCES",
            "RUNBOOK_COMPLETE_VM_VOLUME_DETAILS", "RUNBOOK_COMPLETE_PARALLEL_LISTS",
            "RUNBOOK_BIND_TENANT_VDC", "RUNBOOK_VALIDATE_API_DEPENDENCIES")}
        flags.update(RUNBOOK_COMPLETE_DETAIL_COUNT="1" if enabled else "0",
                     RUNBOOK_PRESERVE_TEMPLATE_COLUMNS="1", RUNBOOK_PRESERVE_ROW_SEMANTICS="1",
                     RUNBOOK_PRESERVE_AGGREGATE_GRAIN="1", RUNBOOK_REFINE_CONTRACT_PROMPT="1")
        diagnostics = {}
        with patch.dict(os.environ, flags), patch.object(d.m, "llm_ask", side_effect=ask), \
                patch.object(d.m, "_execute_lookup_api", return_value=(
                    records() if native_rows is None else native_rows, "CLOUD_SUBNET")) as lookup:
            output = d.m.match_runbook(QUESTION, [source], SimpleNamespace(
                retrieve=lambda question: [SimpleNamespace(id=source["id"])]), diagnostics)
        self.assertEqual(source, before)
        return output, diagnostics, calls, lookup

    def test_full_match_keeps_select_and_refine_and_preserves_atomic_details(self):
        proposal = "SELECT COUNT(*) AS subnet_count,GROUP_CONCAT(cidr) AS subnet_cidr FROM CLOUD_SUBNET"
        output, diag, calls, lookup = self.run_match(proposal=proposal)
        self.assertIsNotNone(output, diag)
        self.assertEqual([stage for stage, _ in calls], ["select", "refine"])
        self.assertIn("COUNT(*) OVER() AS total_count", calls[1][1])
        self.assertTrue(diag["detail_count_validation"]["valid"])
        self.assertTrue(diag["detail_count_refinement_contract"]["applied"])
        lookup.assert_called_once()
        result = self.execute(output["sql"], records())
        self.assertEqual(result["row_count"], 3)
        self.assertEqual([row["total_count"] for row in result["rows"]], [3, 3, 3])
        self.assertEqual([row["subnet_cidr"] for row in result["rows"]], ["10.0.0.0/24", "10.0.0.0/24", None])

    def test_full_match_failed_native_proof_keeps_original_path_without_new_refusal(self):
        output, diag, calls, _ = self.run_match(native_rows=[])
        self.assertIsNotNone(output, diag)
        self.assertFalse(diag["detail_count_validation"]["valid"])
        self.assertFalse(diag["detail_count_refinement_contract"]["applied"])
        self.assertEqual(output["sql"], item()["sql"])
        self.assertEqual([stage for stage, _ in calls], ["select", "refine"])

    def test_full_match_disabled_does_not_lookup_or_change_sql(self):
        output, diag, calls, lookup = self.run_match(enabled=False)
        self.assertIsNotNone(output, diag)
        self.assertEqual(output["sql"], item()["sql"])
        self.assertNotIn("detail_count_plan", diag)
        lookup.assert_not_called()
        self.assertEqual([stage for stage, _ in calls], ["select", "refine"])


if __name__ == "__main__":
    unittest.main()
