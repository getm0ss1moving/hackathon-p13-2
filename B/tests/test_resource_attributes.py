"""分类属性与真实资源请求分开；只屏蔽 schema + SQL 投影已证明的分类短语。"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m


class ResourceAttributeTests(unittest.TestCase):
    def setUp(self):
        schema = patch.object(m, "_schema_columns", {"S_DeployNode": ["id", "name", "hostClass"]})
        schema.start()
        self.addCleanup(schema.stop)
        self.item = {"sql": "SELECT name AS node_name,hostClass AS host_class FROM SYS_DeployNode"}

    def coverage(self, question, enabled="1", item=None):
        with patch.dict(os.environ, {"RUNBOOK_RESOURCE_ATTRIBUTE_ROLES": enabled}):
            return m._resource_coverage(question, self.item if item is None else item)

    def test_classification_only_requires_the_projected_class_field(self):
        for question in ["查询部署节点，节点类型是虚拟机还是物理机", "列出节点的类型是虚拟机还是物理服务器",
                         "查询主机类型分类（虚拟机、物理机）", "查询hostClass(VM/PM)分布"]:
            with self.subTest(question=question):
                result = self.coverage(question)
                self.assertEqual(result["unsupported"], [])
                self.assertTrue(result["attribute_evidence"])

    def test_default_flag_preserves_the_old_resource_gate(self):
        question = "查询节点类型是虚拟机还是物理机"
        self.assertIn("VM_NOVA", self.coverage(question, "0")["unsupported"])

    def test_schema_and_projection_are_both_required(self):
        question = "查询节点类型是虚拟机还是物理机"
        for sql in ["SELECT name FROM SYS_DeployNode", "SELECT COUNT(*) AS n FROM SYS_DeployNode",
                    "SELECT name FROM SYS_DeployNode ORDER BY hostClass", "SELECT 'hostClass' AS host_class FROM SYS_DeployNode"]:
            with self.subTest(sql=sql):
                self.assertIn("VM_NOVA", self.coverage(question, item={"sql": sql})["unsupported"])
        with patch.object(m, "_schema_columns", {}):
            self.assertIn("VM_NOVA", self.coverage(question)["unsupported"])

    def test_actual_vm_request_outside_the_classification_still_requires_vm_resource(self):
        for question in ["节点类型是虚拟机还是物理机，同时列出虚拟机IP", "查询节点关联的虚拟机名称",
                         "节点类型是物理机或虚拟机，虚拟机有多少台"]:
            with self.subTest(question=question):
                self.assertIn("VM_NOVA", self.coverage(question)["unsupported"])

    def test_type_filter_is_not_misread_as_classification_output(self):
        for question in ["查询节点类型为虚拟机", "查询类型为虚拟机或物理机的节点", "查询节点类型为虚拟机或物理机"]:
            with self.subTest(question=question):
                self.assertIn("VM_NOVA", self.coverage(question)["unsupported"])

    def test_field_literal_and_storage_protocol_cannot_fake_disk_type(self):
        item = {"sql": "SELECT storageProtocol FROM CLOUD_STORAGE_POOL"}
        result = self.coverage("查询存储池磁盘类型以及容量", item=item)
        self.assertIn("VOLUME", result["unsupported"])
        self.assertNotIn("attribute_evidence", result)

    def test_alias_projection_is_supported_but_complex_output_is_not_guessed(self):
        sql = "SELECT d.name AS node_name,d.hostClass AS host_class FROM SYS_DeployNode d"
        self.assertEqual(self.coverage("节点类型是虚拟机还是物理机", item={"sql": sql})["unsupported"], [])
        nested = "SELECT host_class FROM (SELECT hostClass AS host_class FROM SYS_DeployNode)"
        self.assertIn("VM_NOVA", self.coverage("节点类型是虚拟机还是物理机", item={"sql": nested})["unsupported"])


if __name__ == "__main__":
    unittest.main()
