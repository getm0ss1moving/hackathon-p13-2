"""同族view、单资源范围与原计划重执行的合成正反控制。"""
import copy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runbook_matcher as matcher
import runbook_system as system
from runbook_items import RUNBOOK_ITEMS
from a160_fixtures import family_item


class ClosedViewRepairTests(unittest.TestCase):
    def setUp(self):
        self.item = family_item("F02")
        self.question = "租户tenant_alpha在区域region_alpha可用区zone_alpha中的ECS IP列表"
        self.parsed = {"view": "ecs_ip_tenant", "filters": {"tenantName": "tenant_alpha",
                        "logicalRegionName": "region_alpha", "azoneName": "zone_alpha"},
                       "required_filters": ["tenantName", "logicalRegionName", "azoneName"]}

    def match(self, question, parameters):
        detail = {}
        with patch.object(matcher, "llm_ask", return_value=json.dumps(parameters)), \
                patch.object(matcher, "_get_table_schemas", return_value="synthetic"), \
                patch.object(matcher, "_refine_sql", side_effect=lambda q, sql, *a, **k: sql):
            result = matcher._match_closed_view_candidate(question, self.item, detail)
        return result, detail

    def test_wrong_view_is_corrected_only_after_unique_full_question_validation(self):
        result, detail = self.match(self.question, self.parsed)
        self.assertIsNotNone(result, detail)
        self.assertEqual(result["sql"], "SELECT name, privateIps, status FROM CLOUD_VM_NOVA")
        self.assertEqual(detail["view_repair"]["from"], "ecs_ip_tenant")
        self.assertEqual(detail["view_repair"]["to"], "ecs_filtered_list")
        actual = {x["simple"]["name"]: x["simple"]["value"] for x in result["api_call"]["condition"]["constraint"]}
        self.assertEqual(actual, self.parsed["filters"])

    def test_explicit_projection_extra_filter_and_wrong_entity_cannot_be_repaired(self):
        questions = [self.question + "，只输出name、privateIps、tenantName",
                     self.question + "，并且状态active", self.question.replace("region_alpha", "region_other")]
        for question in questions:
            with self.subTest(question=question):
                result, detail = self.match(question, self.parsed)
                self.assertIsNone(result)
                self.assertNotIn("view_repair", detail)


class SingleScopeCompletionTests(unittest.TestCase):
    def setUp(self):
        schema = patch.dict(matcher._schema_columns, {"GAUSSDB_INSTANCE": ["name", "logicalRegionName", "azoneName", "vdcName"]})
        schema.start()
        self.addCleanup(schema.stop)
        self.item = {"sql": "SELECT name FROM CLOUD_GAUSSDB_INSTANCE",
                     "api_call": {"method": "GET", "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
                                  "condition": {"constraint": [{"simple": {"name": "vdcName", "value": "vdc_alpha", "operator": "equal"}}]}}}

    def test_adds_only_proven_native_scope_and_preserves_existing_filter(self):
        original = copy.deepcopy(self.item["api_call"]["condition"]["constraint"][0])
        added = matcher._complete_single_ci_scope(self.item, {"azoneName": "zone_alpha", "vdcName": "different", "privateFake": "x"})
        self.assertEqual(added, ["azoneName"])
        constraints = self.item["api_call"]["condition"]["constraint"]
        self.assertEqual(constraints[0], original)
        self.assertEqual(constraints[1]["simple"], {"name": "azoneName", "value": "zone_alpha", "operator": "equal"})

    def test_does_not_guess_scope_transfer_across_other_tables_or_calls(self):
        for mutation in ["join", "two_calls", "unknown_field"]:
            with self.subTest(mutation=mutation):
                item = copy.deepcopy(self.item)
                requested = {"azoneName": "zone_alpha"}
                if mutation == "join":
                    item["sql"] += " JOIN CLOUD_HOST ON CLOUD_HOST.id=CLOUD_GAUSSDB_INSTANCE.hostId"
                elif mutation == "two_calls":
                    item["api_call"] = [item["api_call"], copy.deepcopy(item["api_call"])]
                else:
                    requested = {"tenantName": "tenant_alpha"}
                self.assertEqual(matcher._complete_single_ci_scope(item, requested), [])


class TypedResultRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.query = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        self.query.items, self.query.retriever = [], None
        self.item = {"name": "synthetic_original", "sql": "SELECT a.name FROM CLOUD_HOST a JOIN CLOUD_VM_NOVA b ON a.id=b.hostId",
                     "api_call": [{"method": "GET", "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000"}]}

    def run_query(self, recovered):
        empty = {"sql": self.item["sql"], "result": {"columns": [], "rows": [], "row_count": 0}, "error": None}
        flags = {"RUNBOOK_TYPED_EMPTY_ROOT": "1", "RUNBOOK_BOUNDED_API": "0", "RUNBOOK_SG_RULE_SEMIJOIN": "0", "RUNBOOK_VERIFIED_EMPTY_ROOT": "0", "RUNBOOK_EMPTY_ANSWER_FALLBACK": "0"}
        def repeat(item, evidence, **options):
            self.assertEqual(item, self.item)
            if isinstance(recovered, Exception):
                raise recovered
            return recovered
        with patch.dict(os.environ, flags), patch.object(system, "match_runbook", return_value=self.item), \
                patch.object(system, "get_llm_events", return_value=[]), patch.object(system, "execute", return_value=empty), \
                patch.object(system, "_execute_bounded_api", side_effect=repeat):
            return self.query.query("合成HOST与VM关系查询")

    def test_preserves_original_sql_and_verified_zero_row_columns(self):
        expected = {"columns": ["name"], "rows": [], "row_count": 0}
        answer = self.run_query({"sql": self.item["sql"], "result": expected, "error": None})
        self.assertEqual(answer["result"], expected)
        self.assertEqual(answer["sql"], self.item["sql"])
        self.assertEqual(answer["diagnostics"]["typed_result_recovery"]["status"], "verified_original_plan_reexecuted")

    def test_transport_failure_never_becomes_a_zero_row_answer(self):
        answer = self.run_query(RuntimeError("synthetic failed response"))
        self.assertIsNone(answer["matched_runbook"])
        self.assertIsNone(answer["result"])
        self.assertEqual(answer["diagnostics"]["typed_result_recovery"]["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
