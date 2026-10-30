"""精调不能用相同ID别名掩盖字段/绑定改变；纯合成，无数据集/模型。"""

from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path.cwd()/"implementation"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runbook_identity_guard as guard
import runbook_projection_roles as roles
import runbook_matcher as m


LIBRARY = [{"sql":"SELECT w.name AS instance_name,w.nativeId AS instance_id FROM CLOUD_WIDGET w"}]
SOURCE = "SELECT node.name AS instance_name,parent.name AS parent_name FROM CLOUD_WIDGET node " \
         "LEFT JOIN CLOUD_OTHER parent ON node.parentId=parent.id"


class IdentityRefinementGuardTests(unittest.TestCase):
    def setUp(self):
        self.schemas = {"WIDGET":["id","name","nativeId","parentId","status"],"OTHER":["id","name","nativeId"]}
        for name,value in [("_ORIG_TO_DESENS",{"CLOUD_WIDGET":"WIDGET","CLOUD_OTHER":"OTHER"}),
                           ("_schema_columns",self.schemas)]:
            context = patch.object(m,name,value);context.start();self.addCleanup(context.stop)
        self.original,self.evidence = roles.complete_identity_projection("查询实例ID和名称",{"sql":SOURCE},LIBRARY)
        self.assertTrue(self.evidence)

    def check(self,candidate):
        return guard.validate_identity_refinement(self.original,candidate,self.evidence)

    def test_direct_native_id_survives_alias_rename_and_formatting(self):
        candidate = self.original.replace("node.","entity.").replace("CLOUD_WIDGET node","CLOUD_WIDGET AS entity") \
                                 .replace("parent.","owner.").replace("CLOUD_OTHER parent","CLOUD_OTHER AS owner")
        result = self.check(candidate)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["protected"][0]["field"],"nativeId")
        self.assertEqual(result["protected"][0]["binding_index"],0)
        self.assertTrue(self.check(self.original+"; -- retained comment")["valid"])

    def test_id_name_constant_and_computed_expression_cannot_reuse_id_label(self):
        for expression in ["node.id","node.name","'fixed'","NULL","COALESCE(node.nativeId,'')",
                           "CAST(node.nativeId AS TEXT)","node.nativeId || ''"]:
            candidate = self.original.replace("node.nativeId AS instance_id",expression+" AS instance_id")
            with self.subTest(expression=expression):
                result = self.check(candidate)
                self.assertFalse(result["valid"],result)
                self.assertEqual(result["reason"],"changed_proven_identity_field")

    def test_correct_field_from_wrong_ci_is_rejected(self):
        result = self.check(self.original.replace("node.nativeId AS instance_id","parent.nativeId AS instance_id"))
        self.assertFalse(result["valid"],result)
        self.assertEqual(result["reason"],"changed_proven_identity_binding")

    def test_same_ci_self_join_cannot_swap_entity_binding(self):
        source = SOURCE.replace("CLOUD_OTHER parent","CLOUD_WIDGET parent")
        original,evidence = roles.complete_identity_projection("列出实例ID",{"sql":source},LIBRARY)
        candidate = original.replace("node.nativeId AS instance_id","parent.nativeId AS instance_id")
        result = guard.validate_identity_refinement(original,candidate,evidence)
        self.assertFalse(result["valid"],result)
        self.assertEqual(result["reason"],"changed_proven_identity_binding")

    def test_display_name_anchor_cannot_be_replaced_by_another_binding(self):
        result = self.check(self.original.replace("node.name AS instance_name","parent.name AS instance_name"))
        self.assertFalse(result["valid"],result)
        self.assertEqual(result["reason"],"changed_proven_name_anchor")

    def test_join_type_predicate_or_extra_join_cannot_change_rows(self):
        for candidate in [self.original.replace("LEFT JOIN","INNER JOIN"),
                          self.original.replace("node.parentId=parent.id","node.id=parent.id"),
                          self.original+" INNER JOIN CLOUD_OTHER second ON node.id=second.id"]:
            with self.subTest(candidate=candidate):
                result = self.check(candidate)
                self.assertFalse(result["valid"],result)
                self.assertEqual(result["reason"],"identity_row_source_changed")

    def test_literal_predicates_are_compared_without_erasing_values(self):
        original = self.original+" WHERE node.status='up'"
        candidate = original.replace("'up'","'down'")
        result = guard.validate_identity_refinement(original,candidate,self.evidence)
        self.assertFalse(result["valid"],result)
        self.assertEqual(result["reason"],"identity_row_source_changed")

    def test_sort_only_change_does_not_change_identity_or_grain(self):
        self.assertTrue(self.check(self.original+" ORDER BY node.name")["valid"])

    def test_distinct_group_union_limit_subquery_and_wildcard_are_rejected(self):
        for candidate in [self.original.replace("SELECT ","SELECT DISTINCT ",1),
                          self.original+" GROUP BY node.name",self.original+" LIMIT 1",
                          self.original+" UNION ALL "+self.original,
                          self.original.replace("CLOUD_WIDGET node","(SELECT * FROM CLOUD_WIDGET) node"),
                          self.original.replace("node.nativeId AS instance_id","node.*")]:
            with self.subTest(candidate=candidate):self.assertFalse(self.check(candidate)["valid"])

    def test_missing_duplicate_or_unqualified_ambiguous_id_is_rejected(self):
        for candidate in [self.original.replace(", node.nativeId AS instance_id",""),
                          self.original.replace("node.nativeId AS instance_id","nativeId AS instance_id"),
                          self.original.replace("node.nativeId AS instance_id","node.nativeId AS instance_id,node.id AS instance__id")]:
            with self.subTest(candidate=candidate):self.assertFalse(self.check(candidate)["valid"])

    def test_single_ci_unqualified_id_has_one_proven_binding(self):
        original,evidence = roles.complete_identity_projection("返回实例ID",{
            "sql":"SELECT name AS instance_name FROM CLOUD_WIDGET"},LIBRARY)
        candidate = original.replace("CLOUD_WIDGET.nativeId","nativeId")
        result = guard.validate_identity_refinement(original,candidate,evidence)
        self.assertTrue(result["valid"],result)

    def test_ambiguous_row_source_and_stale_evidence_are_rejected(self):
        candidate = self.original.replace("LEFT JOIN CLOUD_OTHER parent ON node.parentId=parent.id",", CLOUD_OTHER parent")
        self.assertFalse(self.check(candidate)["valid"])
        bad = copy.deepcopy(self.evidence);bad[0]["ci"] = "OTHER"
        self.assertFalse(guard.validate_identity_refinement(self.original,self.original,bad)["valid"])
        with patch.object(m,"_schema_columns",{}):self.assertFalse(self.check(self.original)["valid"])

    def test_entity_list_evidence_also_protects_real_identity_field(self):
        original,evidence = roles.complete_identity_projection("查询组件实例列表",{"sql":SOURCE},LIBRARY)
        self.assertTrue(evidence)
        candidate = original.replace("node.nativeId AS instance_id","node.id AS instance_id")
        self.assertFalse(guard.validate_identity_refinement(original,candidate,evidence)["valid"])

    def test_caller_fallback_keeps_real_native_id_and_same_rows(self):
        original,evidence = roles.complete_identity_projection("输出实例ID",{
            "sql":"SELECT name AS instance_name FROM CLOUD_WIDGET"},LIBRARY)
        candidate = original.replace("CLOUD_WIDGET.nativeId","CLOUD_WIDGET.id")
        result = guard.validate_identity_refinement(original,candidate,evidence)
        safe = original if result["reject"] else candidate
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("CREATE TABLE CLOUD_WIDGET(id TEXT,name TEXT,nativeId TEXT)")
            connection.executemany("INSERT INTO CLOUD_WIDGET VALUES (?,?,?)",[
                ("internal-a","same","native-a"),("internal-b","same","native-b")])
            wrong = [dict(row) for row in connection.execute(candidate)]
            actual = [dict(row) for row in connection.execute(safe)]
        self.assertEqual(len(actual),len(wrong))
        self.assertEqual([row["instance_id"] for row in actual],["native-a","native-b"])
        self.assertEqual([row["instance_id"] for row in wrong],["internal-a","internal-b"])


if __name__ == "__main__":
    unittest.main()
