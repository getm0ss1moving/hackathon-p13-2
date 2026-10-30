"""额外资源、绑定维度和聚合指标的合成边界，无模型或数据服务。"""
import copy
import unittest
import runbook_matcher as m


class EasyGuardTests(unittest.TestCase):
    def test_obs_is_an_extra_resource_but_scope_and_column_values_are_not(self):
        item = {"sql": "SELECT vdcName,COUNT(*) FROM CLOUD_VM_NOVA GROUP BY vdcName", "api_call": {}}
        for word in ["OBS桶", "OBS存储桶", "对象存储桶", "OBS_BUCKET", "“OBS_BUCKET”"]:
            with self.subTest(word=word):
                self.assertIn("OBS_BUCKET", m._resource_coverage("区域region_demo下各VDC的ECS和"+word+"数量", item)["unsupported"])
        for question in ['区域OBS_BUCKET下各VDC的ECS数量', 'tenantName=OBS_BUCKET的ECS数量',
                         'ECS名称OBS_BUCKET', 'ECS名称“OBS桶”', '显示字段OBS_BUCKET',
                         '查询ops-OBS_BUCKET的ECS数量', '查询OBS_BUCKET_backup的ECS数量']:
            with self.subTest(question=question):
                self.assertFalse(m._mentions_obs_resource(question))

    def test_obs_coverage_requires_actual_table_not_an_output_literal_or_alias(self):
        for sql in ['SELECT name FROM CLOUD_OBS_BUCKET', 'SELECT b.name FROM "CLOUD_OBS_BUCKET" b']:
            self.assertTrue(m._obs_sql_table_covered(sql))
        for sql in ["SELECT 'CLOUD_OBS_BUCKET' FROM CLOUD_VM_NOVA", 'SELECT name AS CLOUD_OBS_BUCKET FROM CLOUD_VM_NOVA',
                    'SELECT name FROM CLOUD_VM_NOVA /* FROM CLOUD_OBS_BUCKET */',
                    'WITH CLOUD_OBS_BUCKET AS (SELECT name FROM CLOUD_VM_NOVA) SELECT * FROM CLOUD_OBS_BUCKET']:
            self.assertFalse(m._obs_sql_table_covered(sql))

    def test_f21_tenant_binding_is_two_output_axes(self):
        p = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"},
             "required_filters": ["logicalRegionName"], "group": "tenantName_status"}
        for question in ['查询区域region_demo下各租户的弹性IP绑定状态',
                         '区域region_demo下按租户和绑定状态统计EIP数量']:
            m._ground_family_parameters(question, "F21", copy.deepcopy(p))
            result = m._materialize_family({"family_id": "F21"}, p)
            self.assertIn("GROUP BY tenantName, status", result["sql"])

    def test_f21_does_not_invent_axes_from_the_model_or_drop_predicates(self):
        p = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"},
             "required_filters": ["logicalRegionName"], "group": "tenantName_status"}
        for question in ['区域region_demo下按绑定状态统计EIP数量',
                         '查询区域region_demo下各租户已绑定的弹性IP数量',
                         '查询区域region_demo下各租户的弹性IP绑定状态且status=down']:
            with self.subTest(question=question), self.assertRaises(ValueError):
                m._ground_family_parameters(question, "F21", p)

    def test_f18_cannot_silently_drop_storage_or_change_max_into_sum(self):
        for question,group,metric in [('区域region_demo下按引擎版本统计GaussDB实例数量和总存储容量', 'engineVersion', 'count'),
                                      ('区域region_demo下各VDC的GaussDB实例数量和最大存储容量', 'vdcName', 'count_storage')]:
            p = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"},
                 "required_filters": ["logicalRegionName"], "group": group, "metrics": metric}
            with self.subTest(question=question), self.assertRaisesRegex(ValueError, "unsupported_requested_aggregate_metric"):
                m._ground_family_parameters(question, "F18", p)

    def test_f14_cannot_drop_avg_max_or_extra_count(self):
        for question,metric in [('区域region_demo下各VDC云硬盘平均和最大容量', 'count_sum'),
                                ('区域region_demo下各VDC云硬盘数量及平均和最大容量', 'avg_max')]:
            p = {"scope": "filtered", "filters": {"logicalRegionName": "region_demo"},
                 "required_filters": ["logicalRegionName"], "metrics": metric}
            with self.subTest(question=question), self.assertRaisesRegex(ValueError, "unsupported_requested_aggregate_metric"):
                m._ground_family_parameters(question, "F14", p)


if __name__ == "__main__":
    unittest.main()
