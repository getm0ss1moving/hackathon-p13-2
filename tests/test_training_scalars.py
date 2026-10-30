"""独立标量补全的合成范围/形状/空资源反例；不读任何用例文件。"""

from contextlib import closing
import copy
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_matcher as m
import runbook_executor as executor


NETWORK_QUESTION = "查询VDCvdc_demo在区域region_demo中的VPC、子网、弹性IP和安全组数量"
VOLUME_QUESTION = "查询租户tenant_demo在区域region_demo中ECS的vCPU总核数、内存总量和云硬盘总容量"


def api(ci, owner="vdcName"):
    return {"method": "GET", "url": "/rest/hackthon/db/instances/"+ci+"?pageNo=1&pageSize=10000",
            "condition": {"constraint": [
                {"simple": {"name": owner, "operator": "equal", "value": "vdc_demo" if owner == "vdcName" else "tenant_demo"}},
                {"simple": {"name": "logicalRegionName", "operator": "equal", "value": "region_demo"}}]}}


def network_item():
    return {"resources": ["ROUTER", "SUBNET", "FLOATING_IPS", "SECURITY_GROUP"],
            "api_call": [api(ci) for ci in ["ROUTER", "SUBNET", "FLOATING_IPS", "SECURITY_GROUP"]],
            "sql": "SELECT COUNT(*) AS vpc_count FROM CLOUD_ROUTER"}


def volume_item():
    return {"resources": ["VM_NOVA", "FLAVOR", "VOLUME"],
            "api_call": [api("VM_NOVA", "tenantName"),
                         {"method": "GET", "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000"},
                         api("VOLUME", "tenantName")],
            "sql": "SELECT SUM(f.vcpuSize) AS total_vcpu, SUM(f.ramSize) AS total_ram "
                   "FROM CLOUD_VM_NOVA vm INNER JOIN CLOUD_FLAVOR f ON vm.flavorId=f.id"}


class IndependentScalarTests(unittest.TestCase):
    def setUp(self):
        self.schemas = {ci: ["id", "vdcName", "tenantName", "logicalRegionName"] for ci in
                        ["ROUTER", "SUBNET", "FLOATING_IPS", "SECURITY_GROUP", "VM_NOVA", "FLAVOR", "VOLUME"]}
        self.schemas["VOLUME"].append("size")
        self.schemas["VM_NOVA"].append("flavorId")
        self.schemas["FLAVOR"] += ["vcpuSize", "ramSize"]
        context = patch.object(m, "_schema_columns", self.schemas)
        context.start()
        self.addCleanup(context.stop)

    def plan(self, question=NETWORK_QUESTION, item=None):
        result = m._independent_scalar_plan(question, item or network_item())
        self.assertIsNotNone(result)
        return result

    def lookup(self, call, previous=None):
        ci = call["url"].rsplit("/", 1)[-1].split("?", 1)[0]
        record = {name: 1 for name in self.schemas[ci]}
        record.update(id="fixture", flavorId="fixture", vdcName="vdc_demo", tenantName="tenant_demo",
                      logicalRegionName="region_demo")
        table = next(orig for orig, name in m._ORIG_TO_DESENS.items() if name == ci)
        return [record], table

    def test_full_matching_does_not_use_base_count_as_another_resource_count(self):
        item = network_item()
        item.update(id="synthetic_scalar_network", name="synthetic independent counts", examples=[])
        retriever = SimpleNamespace(retrieve=lambda question: [SimpleNamespace(id=item["id"])])
        proposal = "SELECT COUNT(*) AS vpc_count,COUNT(*) AS subnet_count FROM CLOUD_ROUTER"
        diagnostics = {}
        with patch.dict(os.environ, {"RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES": "1",
                "RUNBOOK_PRESERVE_ROW_SEMANTICS": "1", "RUNBOOK_PRESERVE_TEMPLATE_COLUMNS": "1"}), \
                patch.object(m, "llm_ask", side_effect=lambda prompt,stage="unknown": "1" if stage == "select" else proposal), \
                patch.object(m, "_execute_lookup_api", side_effect=self.lookup), \
                patch.object(m, "_get_table_schemas", return_value="synthetic schemas"):
            actual = m.match_runbook(NETWORK_QUESTION, [item], retriever, diagnostics)
        self.assertIsNotNone(actual)
        self.assertEqual(diagnostics["independent_scalar_base_fallback"], "refined_output_collides_with_independent_statistic")
        self.assertNotIn("COUNT(*) AS vpc_count,COUNT(*) AS subnet_count FROM CLOUD_ROUTER", actual["sql"])
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            for table,count in [("CLOUD_ROUTER",2),("CLOUD_SUBNET",3),("CLOUD_FLOATING_IPS",4),("CLOUD_SECURITY_GROUP",5)]:
                connection.execute("CREATE TABLE "+table+"(id TEXT)")
                connection.executemany("INSERT INTO "+table+" VALUES (?)",[(str(i),) for i in range(count)])
            self.assertEqual([dict(row) for row in connection.execute(actual["sql"])],
                             [{"vpc_count":2,"eip_count":4,"sg_count":5,"subnet_count":3}])

    def test_network_counts_are_independent_and_preserve_base_column(self):
        item = network_item()
        plan = self.plan(item=item)
        self.assertEqual(set(plan["base_tables"]), {"CLOUD_ROUTER"})
        self.assertEqual({part["table"] for part in plan["additions"]},
                         {"CLOUD_SUBNET", "CLOUD_FLOATING_IPS", "CLOUD_SECURITY_GROUP"})
        sql = m._compose_independent_scalars(item["sql"], plan)
        self.assertIsNotNone(sql)
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            for table, count in [("CLOUD_ROUTER", 2), ("CLOUD_SUBNET", 3),
                                 ("CLOUD_FLOATING_IPS", 4), ("CLOUD_SECURITY_GROUP", 5)]:
                connection.execute("CREATE TABLE "+table+"(id TEXT)")
                connection.executemany("INSERT INTO "+table+" VALUES (?)", [(str(i),) for i in range(count)])
            rows = [dict(row) for row in connection.execute(sql)]
        self.assertEqual(rows, [{"vpc_count": 2, "subnet_count": 3, "eip_count": 4, "sg_count": 5}])

    def test_volume_sum_does_not_multiply_vm_flavor_aggregates(self):
        item = volume_item()
        plan = self.plan(VOLUME_QUESTION, item)
        self.assertEqual([(p["ci"], p["aggregate"].upper(), p["field"]) for p in plan["additions"]],
                         [("VOLUME", "SUM", "size")])
        sql = m._compose_independent_scalars(item["sql"], plan)
        self.assertIsNotNone(sql)
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("CREATE TABLE CLOUD_VM_NOVA(id TEXT,flavorId TEXT)")
            connection.execute("CREATE TABLE CLOUD_FLAVOR(id TEXT,vcpuSize REAL,ramSize REAL)")
            connection.execute("CREATE TABLE CLOUD_VOLUME(id TEXT,size REAL)")
            connection.executemany("INSERT INTO CLOUD_VM_NOVA VALUES (?,?)", [("a", "f1"), ("b", "f2")])
            connection.executemany("INSERT INTO CLOUD_FLAVOR VALUES (?,?,?)", [("f1", 2, 4), ("f2", 4, 8)])
            connection.executemany("INSERT INTO CLOUD_VOLUME VALUES (?,?)", [("x", 10), ("y", 20), ("z", 30)])
            rows = [dict(row) for row in connection.execute(sql)]
        self.assertEqual(rows, [{"total_vcpu": 6, "total_ram": 12, "total_volume_size": 60}])

    def test_missing_or_conflicting_scope_is_not_independent(self):
        for change in ["missing", "conflict", "cross_field"]:
            with self.subTest(change=change):
                item = network_item()
                constraints = item["api_call"][1]["condition"]["constraint"]
                if change == "missing":
                    constraints.pop()
                elif change == "conflict":
                    constraints[-1]["simple"]["value"] = "region_other"
                else:
                    constraints[0]["simple"]["name"] = "tenantName"
                self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION, item))

    def test_duplicate_ci_or_non_get_cannot_be_composed(self):
        duplicate = network_item()
        duplicate["api_call"].append(copy.deepcopy(duplicate["api_call"][0]))
        self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION, duplicate))
        non_get = network_item()
        non_get["api_call"][1]["method"] = "POST"
        self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION, non_get))

    def test_unknown_schema_or_aggregate_field_is_rejected(self):
        with patch.dict(m._schema_columns, {}, clear=True):
            self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION, network_item()))
        without_size = copy.deepcopy(self.schemas)
        without_size["VOLUME"].remove("size")
        with patch.object(m, "_schema_columns", without_size):
            self.assertIsNone(m._independent_scalar_plan(VOLUME_QUESTION, volume_item()))

    def test_lists_relations_and_grouped_questions_are_not_scalar_intents(self):
        for suffix in ["列表", "分布", "对应的资源", "挂载的资源", "关联的资源", "各VDC汇总", "每个资源", "最大数量"]:
            with self.subTest(suffix=suffix):
                self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION+suffix, network_item()))

    def test_non_scalar_or_nested_base_is_rejected(self):
        for sql in ["SELECT id FROM CLOUD_ROUTER", "SELECT COUNT(*) AS n FROM CLOUD_ROUTER GROUP BY vdcName",
                    "SELECT COUNT(*) AS n FROM CLOUD_ROUTER HAVING COUNT(*)>1",
                    "SELECT COUNT(*) AS n FROM CLOUD_ROUTER ORDER BY n",
                    "SELECT COUNT(*) AS n FROM CLOUD_ROUTER LIMIT 1",
                    "SELECT COUNT(*) AS n FROM CLOUD_ROUTER WHERE id='x'",
                    "SELECT COUNT(*) AS n FROM (SELECT * FROM CLOUD_ROUTER)",
                    "SELECT COUNT(*) AS n FROM CLOUD_ROUTER UNION SELECT COUNT(*) FROM CLOUD_ROUTER"]:
            with self.subTest(sql=sql):
                item = network_item()
                item["sql"] = sql
                self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION, item))

    def test_alias_collision_and_non_scalar_refinement_are_rejected(self):
        plan = self.plan()
        self.assertIsNone(m._compose_independent_scalars("SELECT COUNT(*) AS subnet_count FROM CLOUD_ROUTER", plan))
        wrong_resource_alias = network_item()
        wrong_resource_alias["sql"] = "SELECT COUNT(*) AS subnet_count FROM CLOUD_ROUTER"
        self.assertIsNone(m._independent_scalar_plan(NETWORK_QUESTION, wrong_resource_alias))
        self.assertIsNone(m._compose_independent_scalars(
            "SELECT vdcName,COUNT(*) AS vpc_count FROM CLOUD_ROUTER GROUP BY vdcName", plan))

    def test_base_guard_rejects_changed_aggregate_even_with_same_alias(self):
        before = volume_item()["sql"]
        self.assertFalse(m._preserves_scalar_base(before, before.replace("SUM(f.vcpuSize)", "COUNT(f.vcpuSize)")))
        self.assertFalse(m._preserves_scalar_base(before, before.replace(", SUM(f.ramSize) AS total_ram", "")))

    def test_base_guard_accepts_equivalent_table_aliases(self):
        before = volume_item()["sql"]
        after = "SELECT SUM(spec.vcpuSize) AS total_vcpu, SUM(spec.ramSize) AS total_ram " \
                "FROM CLOUD_VM_NOVA AS instance INNER JOIN CLOUD_FLAVOR AS spec ON instance.flavorId=spec.id"
        self.assertTrue(m._preserves_scalar_base(before, after))

    def test_base_guard_accepts_original_aggregates_with_new_statistic(self):
        before = volume_item()["sql"]
        after = before.replace(" FROM ", ", COUNT(*) AS joined_vm_count FROM ", 1)
        self.assertTrue(m._preserves_scalar_base(before, after))

    def test_validate_reads_all_base_and_added_resources(self):
        item = network_item()
        plan = self.plan(item=item)
        with patch.object(m, "_execute_lookup_api", side_effect=self.lookup) as lookup:
            result = m._validate_independent_scalars(NETWORK_QUESTION, item, plan)
        self.assertTrue(result["valid"], result)
        self.assertEqual(lookup.call_count, 4)
        self.assertEqual({call.args[0]["url"].rsplit("/",1)[-1].split("?",1)[0] for call in lookup.call_args_list},
                         {"ROUTER", "SUBNET", "FLOATING_IPS", "SECURITY_GROUP"})

    def test_validation_does_not_read_unresolved_or_changed_scope(self):
        plan = self.plan()
        for change in ["unresolved", "changed"]:
            item = network_item()
            for call in item["api_call"]:
                for constraint in call["condition"]["constraint"]:
                    simple = constraint["simple"]
                    simple["value"] = "{{"+simple["name"]+"}}" if change == "unresolved" else "different_scope"
            with self.subTest(change=change), patch.object(m, "_execute_lookup_api", side_effect=self.lookup) as lookup:
                result = m._validate_independent_scalars(NETWORK_QUESTION, item, plan)
            self.assertFalse(result["valid"], result)
            lookup.assert_not_called()

    def test_empty_native_dummy_row_cannot_be_counted_as_a_resource(self):
        with closing(executor.load_into_sqlite({"CLOUD_SUBNET": []})) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM CLOUD_SUBNET").fetchone()[0], 1)
        item = network_item()
        plan = self.plan(item=item)
        for empty_ci in ["ROUTER", "SUBNET"]:
            def lookup(call, previous=None):
                records, table = self.lookup(call, previous)
                return ([], table) if "/"+empty_ci+"?" in call["url"] else (records, table)
            with self.subTest(empty_ci=empty_ci), patch.object(m, "_execute_lookup_api", side_effect=lookup):
                result = m._validate_independent_scalars(NETWORK_QUESTION, item, plan)
            self.assertFalse(result["valid"], result)
            self.assertEqual(result["reason"], "empty_scalar_resource")

    def test_nonempty_resource_with_missing_sum_field_is_rejected(self):
        item = volume_item()
        plan = self.plan(VOLUME_QUESTION, item)
        for missing_table,field in [("CLOUD_VOLUME", "size"), ("CLOUD_FLAVOR", "vcpuSize")]:
            def lookup(call, previous=None):
                records, table = self.lookup(call, previous)
                if table == missing_table:
                    records[0].pop(field)
                return records, table
            with self.subTest(table=missing_table,field=field), patch.object(m, "_execute_lookup_api", side_effect=lookup):
                result = m._validate_independent_scalars(VOLUME_QUESTION, item, plan)
            self.assertFalse(result["valid"], result)
            self.assertEqual(result["reason"], "missing_scalar_field")


if __name__ == "__main__":
    unittest.main()
