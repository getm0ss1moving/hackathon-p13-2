"""ID输出角色来自SQL库结构；仅合成字段/数据，无训练或封存文件读取。"""

from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path.cwd()/"implementation"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runbook_projection_roles as roles
import runbook_matcher as m


LIBRARY_SQL = "SELECT w.name AS instance_name,w.nativeId AS instance_id FROM CLOUD_WIDGET AS w"
SELECTED_SQL = "SELECT w.name AS instance_name,w.status AS state FROM CLOUD_WIDGET AS w"


class SqlOnly(dict):
    def get(self,key,default=None):
        if key != "sql":
            raise AssertionError("候选不能读取模板ID、题文、示例、默认值或API")
        return super().get(key,default)


class IdentityProjectionRolesTests(unittest.TestCase):
    def setUp(self):
        self.schemas = {"WIDGET":["id","name","nativeId","status","parentId","instance_id"],
                        "OTHER":["id","name","nativeId"]}
        for target,name,value in [(m,"_schema_columns",self.schemas),
                                  (m,"_ORIG_TO_DESENS",{"CLOUD_WIDGET":"WIDGET","CLOUD_OTHER":"OTHER"})]:
            context = patch.object(target,name,value);context.start();self.addCleanup(context.stop)

    def complete(self,sql=SELECTED_SQL,library=None,question="列出实例名称、实例ID和状态"):
        return roles.complete_identity_projection(question,{"sql":sql},library or [{"sql":LIBRARY_SQL}])

    def test_library_role_adds_native_id_without_collapsing_duplicate_names(self):
        sql,evidence = self.complete()
        self.assertIn("w.nativeId AS instance_id",sql)
        self.assertEqual(len(evidence),1)
        self.assertEqual((evidence[0]["ci"],evidence[0]["field"],evidence[0]["id_alias"]),
                         ("WIDGET","nativeId","instance_id"))
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("CREATE TABLE CLOUD_WIDGET(id TEXT,name TEXT,nativeId TEXT,status TEXT)")
            connection.executemany("INSERT INTO CLOUD_WIDGET VALUES (?,?,?,?)",[
                ("internal-one","same","native-one","up"),("internal-two","same","native-two","up")])
            before = [dict(row) for row in connection.execute(SELECTED_SQL)]
            after = [dict(row) for row in connection.execute(sql)]
        self.assertEqual(len(after),2)
        self.assertEqual([{key:row[key] for key in before[0]} for row in after],before)
        self.assertEqual([row["instance_id"] for row in after],["native-one","native-two"])

    def test_same_question_on_another_ci_cannot_reuse_role(self):
        sql = "SELECT name AS instance_name FROM CLOUD_OTHER"
        self.assertEqual(self.complete(sql),(sql,[]))

    def test_current_table_alias_and_join_are_preserved(self):
        sql = "SELECT node.name AS instance_name,parent.name AS parent_name FROM CLOUD_WIDGET node " \
              "LEFT JOIN CLOUD_OTHER parent ON node.parentId=parent.id"
        completed,evidence = self.complete(sql)
        self.assertIn("node.nativeId AS instance_id",completed)
        self.assertEqual(completed[completed.index(" FROM "):],sql[sql.index(" FROM "):])
        self.assertEqual(evidence[0]["reference"],"node")

    def test_unqualified_single_ci_and_prefix_normalization_are_supported(self):
        sql = "SELECT name AS service__instance_name FROM CLOUD_WIDGET current_node"
        library = [{"sql":"SELECT name AS service_instance_name,nativeId AS ServiceInstance_id FROM CLOUD_WIDGET"}]
        completed,evidence = self.complete(sql,library)
        self.assertIn("current_node.nativeId AS ServiceInstance_id",completed)
        self.assertEqual(evidence[0]["role_prefix"],"serviceinstance")

    def test_existing_id_alias_is_not_replaced_or_duplicated(self):
        for expression in ["w.id AS instance_id","w.nativeId AS instance_id","w.nativeId AS existing_native_id"]:
            sql = "SELECT w.name AS instance_name,"+expression+" FROM CLOUD_WIDGET w"
            with self.subTest(expression=expression):self.assertEqual(self.complete(sql),(sql,[]))

    def test_no_explicit_id_intent_leaves_sql_unchanged(self):
        self.assertEqual(self.complete(question="列出实例名称及状态"),(SELECTED_SQL,[]))
        self.assertNotEqual(self.complete(question="列出实例编号")[0],SELECTED_SQL)
        self.assertNotEqual(self.complete(question="返回nativeId字段")[0],SELECTED_SQL)

    def test_explicitly_excluded_identity_is_not_added(self):
        for question in ["列出实例名称，不要实例ID", "无需输出实例的ID", "不返回nativeId"]:
            self.assertEqual(self.complete(question=question),(SELECTED_SQL,[]))
        self.assertNotEqual(self.complete(question="返回实例的ID和名称")[0],SELECTED_SQL)

    def test_entity_list_gets_proven_identity_without_changing_display_only_request(self):
        completed,evidence = self.complete(question="查询应用下组件实例列表")
        self.assertIn("w.nativeId AS instance_id",completed)
        self.assertEqual(evidence[0]["intent"],"entity_list_identity")
        self.assertEqual(self.complete(question="组件实例列表只返回名称"),(SELECTED_SQL,[]))
        self.assertEqual(self.complete(question="组件实例列表，不需要实例ID"),(SELECTED_SQL,[]))

    def test_non_detail_shapes_are_rejected(self):
        base = "SELECT w.name AS instance_name FROM CLOUD_WIDGET w"
        for sql in [base.replace("SELECT ","SELECT DISTINCT ",1),base+" GROUP BY w.name",
                    base+" LIMIT 1",base+" UNION ALL "+base,
                    "SELECT name AS instance_name FROM (SELECT name FROM CLOUD_WIDGET)",
                    "SELECT w.name AS instance_name,COUNT(*) AS n FROM CLOUD_WIDGET w",
                    "SELECT w.* FROM CLOUD_WIDGET w"]:
            with self.subTest(sql=sql):self.assertEqual(self.complete(sql),(sql,[]))

    def test_conflicting_id_field_role_in_library_is_rejected(self):
        library = [{"sql":LIBRARY_SQL},{"sql":LIBRARY_SQL.replace("w.nativeId","w.id")}]
        self.assertEqual(self.complete(library=library),(SELECTED_SQL,[]))
        library = [{"sql":LIBRARY_SQL},{"sql":LIBRARY_SQL.replace("w.name AS instance_name","w.status AS instance_name")}]
        self.assertEqual(self.complete(library=library),(SELECTED_SQL,[]))

    def test_roles_cannot_be_paired_across_different_ci_or_self_join_bindings(self):
        for source in ["SELECT a.name AS instance_name,b.nativeId AS instance_id FROM CLOUD_WIDGET a "
                       "INNER JOIN CLOUD_OTHER b ON a.parentId=b.id",
                       "SELECT a.name AS instance_name,b.nativeId AS instance_id FROM CLOUD_WIDGET a "
                       "INNER JOIN CLOUD_WIDGET b ON a.parentId=b.id"]:
            with self.subTest(source=source):
                self.assertEqual(self.complete(library=[{"sql":source}]),(SELECTED_SQL,[]))

    def test_competing_ci_output_labels_and_unqualified_multi_ci_are_rejected(self):
        library = [{"sql":LIBRARY_SQL},{"sql":LIBRARY_SQL.replace("CLOUD_WIDGET","CLOUD_OTHER")}]
        sql = "SELECT a.name AS instance_name,b.name AS instance__name FROM CLOUD_WIDGET a " \
              "INNER JOIN CLOUD_OTHER b ON a.parentId=b.id"
        self.assertEqual(self.complete(sql,library),(sql,[]))
        sql = "SELECT name AS instance_name FROM CLOUD_WIDGET a INNER JOIN CLOUD_OTHER b ON a.parentId=b.id"
        self.assertEqual(self.complete(sql,library),(sql,[]))

    def test_unknown_schema_or_unproven_prefix_is_rejected(self):
        for schema in [{}, {"WIDGET":["id","name","status"]}]:
            with self.subTest(schema=schema),patch.object(m,"_schema_columns",schema):
                self.assertEqual(self.complete(),(SELECTED_SQL,[]))
        sql = SELECTED_SQL.replace("instance_name","component_name")
        self.assertEqual(self.complete(sql),(sql,[]))

    def test_existing_sort_resolution_cannot_be_changed_by_new_alias(self):
        sql = SELECTED_SQL+" ORDER BY instance_id"
        self.assertEqual(self.complete(sql),(sql,[]))

    def test_only_sql_structure_is_read_and_inputs_are_not_modified(self):
        selected = SqlOnly(sql=SELECTED_SQL,examples=object(),default_params=object(),id=object())
        library = [SqlOnly(sql=LIBRARY_SQL,examples=object(),default_params=object(),id=object())]
        original_selected = dict(selected);original_library = [dict(row) for row in library]
        completed,evidence = roles.complete_identity_projection("输出实例ID",selected,library)
        self.assertNotEqual(completed,SELECTED_SQL)
        self.assertEqual(dict(selected),original_selected)
        self.assertEqual([dict(row) for row in library],original_library)
        self.assertEqual(len(evidence[0]["supporting_sql_sha256"][0]),64)


if __name__ == "__main__":
    unittest.main()
