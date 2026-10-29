"""API 查找资源门禁：真实数据关系、空查找及不受支持结构的反例。"""

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
import runbook_matcher as m
import runbook_system as system_module
from evaluator import evaluate_case
from runbook_executor import execute, _query_server
from runbook_items import RUNBOOK_ITEMS


def lookup_item():
    return {"id": "lookup-fixture", "name": "宿主机下虚拟机数量", "examples": [],
            "resources": ["HOST", "VM_NOVA"],
            "api_call": [
                {"method": "GET", "url": "/rest/hackthon/db/instances/HOST",
                 "condition": {"constraint": [{"simple": {"name": "name", "value": "{{name}}", "operator": "equal"}}]}},
                {"method": "GET", "url": "/rest/hackthon/db/instances/VM_NOVA",
                 "condition": {"constraint": [
                     {"simple": {"name": "hostId", "value": "{{id from step 1}}", "operator": "equal"}},
                     {"simple": {"name": "status", "value": "{{status}}", "operator": "equal"}}]}}],
            "sql": "SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA"}


class ResourceLookupTests(unittest.TestCase):
    def setUp(self):
        for target, value in [
            ("_schema_columns", {"HOST": ["id", "name"], "VM_NOVA": ["hostId", "name", "status"]}),
            ("_schema_values", {"VM_NOVA": {"status": ["active"]}}),
        ]:
            context = patch.object(m, target, value)
            context.start()
            self.addCleanup(context.stop)
        self.retriever = Mock()
        self.retriever.retrieve.return_value = [SimpleNamespace(id="lookup-fixture", tier="strong")]
        context = patch.object(m, "_get_table_schemas", return_value="schema fixture")
        context.start()
        self.addCleanup(context.stop)

    def test_lookup_resource_is_covered_without_appearing_in_final_sql(self):
        coverage = m._resource_coverage("宿主机host-alpha上的虚拟机数量", lookup_item())
        self.assertEqual(coverage["covered_by_lookup"], ["HOST"])
        self.assertFalse(coverage["unsupported"])

    def test_unproven_dependencies_never_relax_the_gate(self):
        for mutation in ["constant", "wrong_step", "unknown_source_field", "unknown_target_field",
                         "unrelated_source_field", "unrelated_target_field",
                         "target_overwritten", "unfiltered_source", "unresolved_source", "unused_target"]:
            with self.subTest(mutation=mutation):
                item = lookup_item()
                child = item["api_call"][1]["condition"]["constraint"][0]["simple"]
                if mutation == "constant": child["value"] = "opaque-host-id"
                if mutation == "wrong_step": child["value"] = "{{id from step 2}}"
                if mutation == "unknown_source_field": child["value"] = "{{missingField from step 1}}"
                if mutation == "unknown_target_field": child["name"] = "missingField"
                if mutation == "unrelated_source_field": child["value"] = "{{name from step 1}}"
                if mutation == "unrelated_target_field": child["name"] = "status"
                if mutation == "target_overwritten": item["api_call"].append(copy.deepcopy(item["api_call"][1]))
                if mutation == "unfiltered_source": item["api_call"][0].pop("condition")
                if mutation == "unresolved_source": item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "{{id from step 0}}"
                if mutation == "unused_target": item["sql"] = "SELECT COUNT(*) FROM CLOUD_VOLUME"
                with patch.object(m, "llm_ask", return_value="1") as llm, patch.object(m, "_execute_lookup_api") as api:
                    details = {}
                    self.assertIsNone(m.match_runbook("宿主机host-alpha上的虚拟机数量", [item], self.retriever, details))
                    self.assertEqual(details["reason"], "resource_mismatch")
                    self.assertEqual(llm.call_count, 1)
                    api.assert_not_called()

    def test_empty_or_missing_dependency_refuses_before_refinement(self):
        for records in [[], [{"name": "host-alpha"}], [{"id": "", "name": "host-alpha"}]]:
            with self.subTest(records=records), patch.object(m, "_execute_lookup_api", return_value=(records, "CLOUD_HOST")), \
                 patch.object(m, "llm_ask", side_effect=["1", '{"name":"host-alpha","status":"active"}']) as llm:
                details = {}
                self.assertIsNone(m.match_runbook("宿主机host-alpha上ACTIVE状态的虚拟机数量", [lookup_item()], self.retriever, details))
                self.assertEqual(details["reason"], "invalid_resource_lookup")
                self.assertEqual(llm.call_count, 2)

    def test_replaced_entities_preserve_dependency_and_input_template(self):
        for entity in ["host-alpha", "host-beta-42"]:
            item = lookup_item()
            with self.subTest(entity=entity), patch.object(m, "_execute_lookup_api", return_value=([{"id": "opaque-id"}], "CLOUD_HOST")) as api, \
                 patch.object(m, "llm_ask", side_effect=["1", json.dumps({"name": entity, "status": "active"}), item["sql"]]):
                result = m.match_runbook(f"宿主机{entity}上ACTIVE状态的虚拟机数量", [item], self.retriever)
                self.assertIsNotNone(result)
                self.assertEqual(api.call_args.args[0]["condition"]["constraint"][0]["simple"]["value"], entity)
                self.assertEqual(result["api_call"][1]["condition"]["constraint"][0]["simple"]["value"], "{{id from step 1}}")
                self.assertEqual(item, lookup_item())

    def test_unresolved_lookup_never_queries_server(self):
        item = lookup_item()
        proof = m._direct_api_lookup(item)
        with patch.object(m, "_execute_lookup_api") as api:
            self.assertFalse(m._validate_resource_lookup(item, proof)["valid"])
            api.assert_not_called()

    def test_lookup_exceptions_propagate(self):
        item = lookup_item()
        proof = m._direct_api_lookup(item)
        item["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = "host-alpha"
        with patch.object(m, "_execute_lookup_api", side_effect=TimeoutError("local API")):
            with self.assertRaises(TimeoutError): m._validate_resource_lookup(item, proof)

    def test_metadata_and_mixed_case_ip_do_not_bypass_unsupported_resources(self):
        item = lookup_item()
        item["resources"].append("FLOATING_IPS")
        for word in ["弹性IP", "弹性ip", "EIP"]:
            with self.subTest(word=word):
                self.assertIn("FLOATING_IPS", m._resource_coverage(f"宿主机host-alpha上的虚拟机和{word}", item)["unsupported"])


@unittest.skipUnless(os.environ.get("RUNBOOK_TEST_LOCAL_API") == "1", "需启动本地数据服务")
class LocalResourceLookupTests(unittest.TestCase):
    def setUp(self):
        m._warm_schema_cache()
        self.item = next(i for i in RUNBOOK_ITEMS if i["id"] == "rb_023")
        self.case = next(c for c in json.loads((HERE / "CMDB用例集-白盒200.json").read_text())["cases"] if c["case_id"] == "CMDB-036")

    def query(self, question, name):
        candidates = system_module.RunbookRetriever(RUNBOOK_ITEMS).retrieve(question)
        index = next(i + 1 for i, candidate in enumerate(candidates) if candidate.id == self.item["id"])
        answers = [str(index), json.dumps({"name": name, "status": "active"}), self.item["sql"]]
        with patch.object(system_module, "get_llm"), patch.object(m, "llm_ask", side_effect=answers):
            return system_module.RunbookQuerySystem().query(question)

    def test_real_lookup_and_original_score_with_replaced_host(self):
        output = self.query(self.case["question"], "kvm-10")
        self.assertEqual(evaluate_case(self.case, output, 0)["score"], 5)
        self.assertTrue(output["diagnostics"]["matching"]["resource_lookup"]["valid"])
        hosts_with_active_vms = {v["hostId"] for v in _query_server("VM_NOVA") if v.get("status") == "active"}
        host = next(h for h in _query_server("HOST") if h.get("id") in hosts_with_active_vms and h.get("name") != "kvm-10")
        derived = copy.deepcopy(self.case)
        derived["question"] = f'宿主机"{host["name"]}"上ACTIVE状态的虚拟机有多少台'
        derived["api_call"][0]["condition"]["constraint"][0]["simple"]["value"] = host["name"]
        expected = execute({"api_call": derived["api_call"], "sql": derived["sql"]})
        self.assertIsNone(expected["error"])
        derived["answer"] = expected["result"]
        output = self.query(derived["question"], host["name"])
        self.assertEqual(evaluate_case(derived, output, 0)["score"], 5)

    def test_nonexistent_host_refuses_without_executing_unfiltered_vm_query(self):
        name = "nonexistent-host-resource-gate-probe"
        with patch.object(system_module, "execute") as execute_spy:
            output = self.query(f"宿主机{name}上ACTIVE状态的虚拟机数量", name)
            execute_spy.assert_not_called()
        self.assertIsNone(output["matched_runbook"])
        self.assertEqual(output["diagnostics"]["matching"]["reason"], "invalid_resource_lookup")


if __name__ == "__main__":
    unittest.main()
