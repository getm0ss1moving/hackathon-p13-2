"""跨步条件不会被静默省略；保留原执行器与 SQL 精调。模型均为受控输出。"""

import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "implementation"))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system_module
from evaluator import evaluate_case
from runbook_items import RUNBOOK_ITEMS


def joined_lookup():
    return {"id": "dependency-fixture", "name": "宿主机虚拟机列表",
            "description": "按宿主机名称查询虚拟机与宿主机名称", "resources": ["HOST", "VM_NOVA"],
            "examples": ["查询宿主机上的虚拟机和宿主机名称"],
            "api_call": [
                {"method": "GET", "url": "/rest/hackthon/db/instances/HOST",
                 "condition": {"constraint": [{"simple": {"name": "name", "value": "{{name}}", "operator": "equal"}}]}},
                {"method": "GET", "url": "/rest/hackthon/db/instances/VM_NOVA",
                 "condition": {"constraint": [{"simple": {"name": "hostId", "value": "{{id from step 1}}", "operator": "equal"}}]}}],
            "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_HOST.name AS host_name "
                   "FROM CLOUD_VM_NOVA JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id"}


def filled_fixture():
    item = joined_lookup()
    assert matcher._fill_params(item, {"name": "host-alpha"})
    return item


class APIDependencyTests(unittest.TestCase):
    def setUp(self):
        context = patch.dict(os.environ, {"RUNBOOK_VALIDATE_API_DEPENDENCIES": "1"})
        context.start()
        self.addCleanup(context.stop)

    def test_disabled_candidate_keeps_existing_flow_without_dependency_reads(self):
        item = joined_lookup()
        retriever = Mock()
        retriever.retrieve.return_value = [SimpleNamespace(id=item["id"], tier="strong")]
        with patch.dict(os.environ, {"RUNBOOK_VALIDATE_API_DEPENDENCIES": "0"}), \
             patch.object(matcher, "_validate_api_dependencies", side_effect=AssertionError("关闭时不进入新分支")), \
             patch.object(matcher, "_get_table_schemas", return_value="fixture"), \
             patch.object(matcher, "_refine_sql", return_value=item["sql"]) as refine, \
             patch.object(matcher, "llm_ask", side_effect=["1", '{"name":"host-alpha"}']):
            details = {}
            self.assertIsNotNone(matcher.match_runbook('查询宿主机"host-alpha"上的虚拟机和宿主机名称', [item], retriever, details))
        self.assertNotIn("api_dependencies", details)
        refine.assert_called_once()

    def test_native_executor_omits_empty_dependency_but_guard_stops_before_target(self):
        item = filled_fixture()
        with patch.object(executor, "_query_server", return_value=[]) as query:
            executor._execute_api_call(item["api_call"])
            self.assertEqual(query.call_args_list[-1].args, ("VM_NOVA", []))
            query.reset_mock()
            outcome = matcher._validate_api_dependencies(item)
            self.assertFalse(outcome["valid"])
            self.assertEqual(outcome["reason"], "empty_dependency_source")
            self.assertEqual(query.call_count, 1)
            self.assertEqual(query.call_args.args[0], "HOST")

    def test_missing_empty_and_false_values_stop_before_refinement_with_sql_resources_present(self):
        item = joined_lookup()
        retriever = Mock()
        retriever.retrieve.return_value = [SimpleNamespace(id=item["id"], tier="strong")]
        for records in [[], [{"name": "host-alpha"}], [{"id": ""}], [{"id": None}], [{"id": 0}], [{"id": False}]]:
            with self.subTest(records=records), patch.object(matcher, "_execute_lookup_api", return_value=(records, "CLOUD_HOST")) as api, \
                 patch.object(matcher, "llm_ask", side_effect=["1", '{"name":"host-alpha"}']) as llm:
                details = {}
                self.assertIsNone(matcher.match_runbook('查询宿主机"host-alpha"上的虚拟机和宿主机名称', [item], retriever, details))
                self.assertEqual(details["reason"], "invalid_api_dependency")
                self.assertFalse(details["api_dependencies"]["valid"])
                self.assertEqual(llm.call_count, 2)
                self.assertEqual(api.call_count, 1)
                self.assertFalse(details["resource_coverage"]["missing_from_sql"])

    def test_three_step_chain_checks_actual_adjacent_results_and_does_not_read_last_target(self):
        item = filled_fixture()
        item["api_call"].append({"method": "GET", "url": "/rest/hackthon/db/instances/FLAVOR",
                                  "condition": {"constraint": [{"simple": {"name": "id", "value": "{{flavorId from step 2}}"}}]}})
        original = copy.deepcopy(item)
        hosts = [{"id": "opaque-host"}]
        vms = [{"flavorId": "opaque-flavor"}]
        for second_result, valid in [(vms, True), ([], False), ([{"name": "no-field"}], False)]:
            with self.subTest(valid=valid, second_result=second_result), \
                 patch.object(matcher, "_execute_lookup_api", side_effect=[(hosts, "CLOUD_HOST"), (second_result, "CLOUD_VM_NOVA")]) as api:
                outcome = matcher._validate_api_dependencies(item)
                self.assertEqual(outcome["valid"], valid)
                self.assertEqual(api.call_count, 2)
                self.assertIs(api.call_args_list[1].args[1], hosts)
                self.assertEqual(outcome["checks"][-1]["target_step"], 3)
                self.assertEqual(outcome["checks"][-1]["source_rows"], len(second_result))
                self.assertEqual(item, original)

    def test_unsupported_reference_syntax_and_step_are_rejected_before_any_api(self):
        for value in ["{{id from step 2}}", "{{id from step 0}}", "{{id FROM STEP 1}}", "{{id from step\n1}}",
                      "prefix {{id from step 1}}", ["{{id from step 1}}"]]:
            with self.subTest(value=value), patch.object(matcher, "_execute_lookup_api") as api:
                item = filled_fixture()
                item["api_call"][1]["condition"]["constraint"][0]["simple"]["value"] = value
                self.assertFalse(matcher._validate_api_dependencies(item)["valid"])
                api.assert_not_called()
        item = filled_fixture()
        item["api_call"].append(copy.deepcopy(item["api_call"][1]))  # 第三步仍写 step 1，原执行器只用第二步。
        with patch.object(matcher, "_execute_lookup_api") as api:
            self.assertEqual(matcher._validate_api_dependencies(item)["reason"], "nonadjacent_dependency_reference")
            api.assert_not_called()

    def test_first_step_and_noncondition_placeholders_cannot_bypass_preflight(self):
        for location in ["first_condition", "url"]:
            item = filled_fixture()
            if location == "first_condition":
                item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "{{id from step 1}}"
            else:
                item["api_call"][0]["url"] += "?cursor={{id from step 1}}"
            with self.subTest(location=location), patch.object(matcher, "_execute_lookup_api") as api:
                self.assertFalse(matcher._validate_api_dependencies(item)["valid"])
                api.assert_not_called()

    def test_each_dependency_field_needs_usable_values_but_some_null_records_do_not_erase_valid_values(self):
        item = filled_fixture()
        item["api_call"][1]["condition"]["constraint"].append({"simple": {"name": "name", "value": "{{name from step 1}}"}})
        for records, valid in [([{"id": "opaque", "name": "host-alpha"}, {"id": None}], True),
                               ([{"id": "opaque"}], False), ([{"id": ["opaque"], "name": "host-alpha"}], False),
                               ([{"id": {"nested": "opaque"}, "name": "host-alpha"}], False)]:
            with self.subTest(records=records), patch.object(matcher, "_execute_lookup_api", return_value=(records, "CLOUD_HOST")):
                self.assertEqual(matcher._validate_api_dependencies(item)["valid"], valid)

    def test_multiple_values_preserve_native_in_condition(self):
        item = filled_fixture()
        hosts = [{"id": "opaque-a"}, {"id": "opaque-b"}, {"id": None}]
        with patch.object(executor, "_query_server", side_effect=[hosts, []]) as query:
            executor._execute_api_call(item["api_call"])
        condition = query.call_args.args[1][0]
        self.assertEqual(condition["operator"], "in")
        self.assertEqual(set(condition["value"]), {"opaque-a", "opaque-b"})
        with patch.object(matcher, "_execute_lookup_api", return_value=(hosts, "CLOUD_HOST")):
            outcome = matcher._validate_api_dependencies(item)
        self.assertTrue(outcome["valid"])
        self.assertEqual(outcome["checks"][0]["usable_rows_by_field"], {"id": 2})

    def test_independent_calls_have_no_extra_reads_and_data_exceptions_propagate(self):
        for calls in [None, {}, {"url": "/instances/HOST"}, [{"url": "/instances/HOST"}, {"url": "/instances/VM_NOVA"}]]:
            with self.subTest(calls=calls), patch.object(matcher, "_execute_lookup_api") as api:
                self.assertIsNone(matcher._validate_api_dependencies({"api_call": calls}))
                api.assert_not_called()
        with patch.object(matcher, "_execute_lookup_api", side_effect=TimeoutError("local API")):
            with self.assertRaises(TimeoutError): matcher._validate_api_dependencies(filled_fixture())


@unittest.skipUnless(os.environ.get("RUNBOOK_TEST_LOCAL_API") == "1", "需启动本地数据服务")
class LocalAPIDependencyTests(unittest.TestCase):
    def setUp(self):
        context = patch.dict(os.environ, {"RUNBOOK_VALIDATE_API_DEPENDENCIES": "1"})
        context.start()
        self.addCleanup(context.stop)

    def query(self, item, question, parameters):
        answers = ["1", json.dumps(parameters), item["sql"]]
        retriever = Mock()
        retriever.retrieve.return_value = [SimpleNamespace(id=item["id"], tier="strong")]
        with patch.object(system_module, "RUNBOOK_ITEMS", [item]), patch.object(system_module, "get_llm"), \
             patch.object(system_module, "RunbookRetriever", return_value=retriever), \
             patch.object(matcher, "llm_ask", side_effect=answers) as llm:
            output = system_module.RunbookQuerySystem().query(question)
        return output, [call.kwargs["stage"] for call in llm.call_args_list]

    def test_real_empty_first_step_stops_target_and_executor(self):
        item = next(i for i in RUNBOOK_ITEMS if i["id"] == "rb_021")
        case = next(c for c in json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"] if c["case_id"] == "CMDB-033")
        value = case["api_call"][0]["condition"]["constraint"][0]["simple"]["value"]
        with patch.object(matcher, "_execute_lookup_api", wraps=executor._execute_single_api_call) as api, \
             patch.object(system_module, "execute") as execute:
            output, stages = self.query(item, case["question"], {"fixedIpAddress": value})
        self.assertIsNone(output["matched_runbook"])
        self.assertEqual(output["diagnostics"]["matching"]["api_dependencies"]["reason"], "empty_dependency_source")
        self.assertEqual(stages, ["select", "fill"])
        self.assertEqual(api.call_count, 1)
        execute.assert_not_called()

    def test_real_positive_preserves_refinement_answer_and_does_not_repeat_source_http(self):
        vms = executor._query_server("VM_NOVA")
        host_ids = {row.get("hostId") for row in vms}
        host = next(row for row in executor._query_server("HOST") if row.get("id") in host_ids and row.get("name"))
        item = joined_lookup()
        reference = copy.deepcopy(item)
        self.assertTrue(matcher._fill_params(reference, {"name": host["name"]}))
        with patch.dict(executor._cache, {}, clear=True):
            expected = executor.execute(reference)
        self.assertIsNone(expected["error"])
        self.assertGreater(expected["result"]["row_count"], 0)
        with patch.dict(executor._cache, {}, clear=True), patch.object(executor.requests, "get", wraps=executor.requests.get) as request:
            output, stages = self.query(item, f'查询宿主机"{host["name"]}"上的虚拟机和宿主机名称', {"name": host["name"]})
        self.assertEqual(stages, ["select", "fill", "refine"])
        self.assertEqual(output["result"], expected["result"])
        case = {"case_id": "DEV-DEPENDENCY-CONTROL", "question": output["question"], "api_call": reference["api_call"],
                "sql": reference["sql"], "answer": expected["result"]}
        self.assertEqual(evaluate_case(case, output, 0)["score"], 5)
        urls = [call.args[0] for call in request.call_args_list]
        self.assertEqual(sum("/instances/HOST?" in url for url in urls), 1)
        self.assertEqual(sum("/instances/VM_NOVA?" in url for url in urls), 1)
        self.assertTrue(output["diagnostics"]["matching"]["api_dependencies"]["valid"])


if __name__ == "__main__":
    unittest.main()
