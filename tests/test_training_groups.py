"""网络资源按VDC分组组合；全部合成，不读训练/封存用例。"""

from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
import runbook_aggregates as g
import runbook_matcher as m


QUESTION = "查询区域region_demo下各VDC的VPC、子网、弹性IP和安全组数量汇总"
QUESTION_ELB = "查询区域region_demo下各VDC的VPC、子网、弹性IP、安全组和ELB数量汇总"
TABLES = {"ROUTER":"CLOUD_ROUTER","SUBNET":"CLOUD_SUBNET","FLOATING_IPS":"CLOUD_FLOATING_IPS",
          "SECURITY_GROUP":"CLOUD_SECURITY_GROUP","ELB":"CLOUD_ELB"}


def item(include_elb=False):
    cis = ["ROUTER","SUBNET","FLOATING_IPS","SECURITY_GROUP"]+(["ELB"] if include_elb else [])
    return {"api_call":[{"method":"GET","url":"/rest/hackthon/db/instances/"+ci+"?pageNo=1&pageSize=10000",
                         "condition":{"constraint":[{"simple":{"name":"logicalRegionName","value":"region_demo","operator":"equal"}}]}}
                        for ci in cis],
            "sql":"SELECT vdcName, COUNT(*) AS sg_count FROM CLOUD_SECURITY_GROUP GROUP BY vdcName"}


class IndependentGroupTests(unittest.TestCase):
    def setUp(self):
        self.schemas = {ci:["id","name","vdcName","logicalRegionName"] for ci in TABLES}
        context = patch.object(m,"_schema_columns",self.schemas)
        context.start();self.addCleanup(context.stop)

    def plan(self,include_elb=False,source=None):
        value = g.plan_groups(QUESTION_ELB if include_elb else QUESTION,source or item(include_elb))
        self.assertIsNotNone(value)
        return value

    def lookup(self,call,previous=None):
        ci = call["url"].rsplit("/",1)[-1].split("?",1)[0]
        return [{"id":"one","vdcName":"shared"},{"id":"two","vdcName":None},{"id":"three","vdcName":""}],TABLES[ci]

    def execute(self,source,plan,include_elb=False):
        sql = g.compose_groups(source["sql"],plan)
        self.assertIsNotNone(sql)
        data = {"ROUTER":["only_router","shared","shared",None,""],
                "SUBNET":["shared","shared","shared",None,""],
                "FLOATING_IPS":["shared",None],
                "SECURITY_GROUP":["shared","shared",None,"","only_sg"]}
        if include_elb:data["ELB"] = ["only_elb","shared"]
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            for ci,keys in data.items():
                connection.execute("CREATE TABLE "+TABLES[ci]+"(id TEXT,vdcName TEXT)")
                connection.executemany("INSERT INTO "+TABLES[ci]+" VALUES (?,?)",[(str(i),key) for i,key in enumerate(keys)])
            return [dict(row) for row in connection.execute(sql)]

    def test_union_domain_keeps_resource_only_vdc_without_multiplication(self):
        source = item();plan = self.plan(source=source)
        rows = self.execute(source,plan)
        by_key = {row["vdcName"]:row for row in rows}
        self.assertEqual(len(rows),5)
        self.assertEqual(by_key["shared"],{"vdcName":"shared","sg_count":2,"vpc_count":2,"subnet_count":3,"eip_count":1})
        self.assertEqual(by_key["only_router"],{"vdcName":"only_router","sg_count":0,"vpc_count":1,"subnet_count":0,"eip_count":0})
        self.assertEqual(by_key["only_sg"]["sg_count"],1)
        self.assertEqual(sum(row["vpc_count"] for row in rows),5)
        self.assertEqual(sum(row["sg_count"] for row in rows),5)

    def test_null_and_empty_string_are_separate_correct_buckets(self):
        source = item();rows = self.execute(source,self.plan(source=source))
        by_key = {row["vdcName"]:row for row in rows}
        self.assertEqual(by_key[None],{"vdcName":None,"sg_count":1,"vpc_count":1,"subnet_count":1,"eip_count":1})
        self.assertEqual(by_key[""],{"vdcName":"","sg_count":1,"vpc_count":1,"subnet_count":1,"eip_count":0})

    def test_elb_only_key_is_added_to_full_domain(self):
        source = item(True);plan = self.plan(True,source)
        rows = self.execute(source,plan,True)
        by_key = {row["vdcName"]:row for row in rows}
        self.assertEqual(len(rows),6)
        self.assertEqual(by_key["only_elb"]["elb_count"],1)
        self.assertEqual(by_key["only_elb"]["sg_count"],0)
        self.assertEqual(by_key["shared"]["elb_count"],1)

    def test_base_key_and_count_output_aliases_are_preserved(self):
        source = item()
        source["sql"] = "SELECT vdcName AS owner_bucket,COUNT(*) AS security_total FROM CLOUD_SECURITY_GROUP GROUP BY vdcName"
        rows = self.execute(source,self.plan(source=source))
        self.assertEqual(set(rows[0]),{"owner_bucket","security_total","vpc_count","subnet_count","eip_count"})
        self.assertEqual(sum(row["security_total"] for row in rows),5)

    def test_refined_alias_changes_or_count_distinct_are_rejected(self):
        source = item();plan = self.plan(source=source)
        for sql in [source["sql"].replace("sg_count","new_count"),
                    source["sql"].replace("SELECT vdcName,","SELECT vdcName AS owner,"),
                    source["sql"].replace("COUNT(*)","COUNT(DISTINCT id)"),
                    source["sql"].replace("GROUP BY vdcName","GROUP BY name")]:
            with self.subTest(sql=sql):self.assertIsNone(g.compose_groups(sql,plan))
        equivalent = "SELECT s.vdcName, COUNT(*) AS sg_count FROM CLOUD_SECURITY_GROUP AS s GROUP BY s.vdcName"
        self.assertIsNotNone(g.compose_groups(equivalent,plan))

    def test_invalid_base_shape_and_alias_collision_are_rejected(self):
        base = item()["sql"]
        for sql in [base+" LIMIT 2",base+" ORDER BY vdcName",base+" HAVING COUNT(*)>1",
                    base.replace("GROUP BY vdcName","WHERE id='one' GROUP BY vdcName"),
                    base.replace("COUNT(*)","SUM(id)"),base+" UNION "+base,
                    base.replace("sg_count","from"),
                    base.replace("CLOUD_SECURITY_GROUP","(SELECT * FROM CLOUD_SECURITY_GROUP)"),
                    base.replace("sg_count","vpc_count")]:
            with self.subTest(sql=sql):
                source = item();source["sql"] = sql
                self.assertIsNone(g.plan_groups(QUESTION,source))

    def test_only_counted_network_enumeration_with_vdc_dimension_is_allowed(self):
        for question in [QUESTION+"列表",QUESTION.replace("各VDC","各租户"),
                         QUESTION.replace("弹性IP","GaussDB节点"),QUESTION.replace("弹性IP","交换机"),
                         QUESTION.replace("VPC","路由器"),QUESTION.replace("子网","对应子网"),
                         QUESTION.replace("数量汇总","总容量"),QUESTION.replace("子网","子网和OBS桶")]:
            with self.subTest(question=question):self.assertIsNone(g.plan_groups(question,item()))
        by = QUESTION.replace("各VDC的","按VDC统计")
        self.assertIsNotNone(g.plan_groups(by,item()))

    def test_scope_schema_duplicate_and_non_get_are_rejected(self):
        for change in ["missing","conflict","extra_filter","duplicate","post","dependency"]:
            source = item()
            constraints = source["api_call"][0]["condition"]["constraint"]
            if change == "missing":constraints.clear()
            elif change == "conflict":constraints[0]["simple"]["value"] = "region_other"
            elif change == "extra_filter":constraints.append({"simple":{"name":"vdcName","value":"owner","operator":"equal"}})
            elif change == "duplicate":source["api_call"].append(copy.deepcopy(source["api_call"][0]))
            elif change == "post":source["api_call"][0]["method"] = "POST"
            else:constraints[0]["simple"]["value"] = "{{logicalRegionName from step 1}}"
            with self.subTest(change=change):self.assertIsNone(g.plan_groups(QUESTION,source))
        for missing in ["vdcName","logicalRegionName"]:
            schemas = copy.deepcopy(self.schemas);schemas["SUBNET"].remove(missing)
            with self.subTest(missing=missing),patch.object(m,"_schema_columns",schemas):
                self.assertIsNone(g.plan_groups(QUESTION,item()))

    def test_validation_reads_all_resources_and_reports_key_quality(self):
        source = item();plan = self.plan(source=source)
        with patch.object(m,"_execute_lookup_api",side_effect=self.lookup) as lookup:
            result = g.validate_groups(QUESTION,source,plan)
        self.assertTrue(result["valid"],result)
        self.assertEqual(lookup.call_count,4)
        self.assertTrue(all(row["null_key_rows"] == row["empty_key_rows"] == 1 for row in result["tables"]))

    def test_validation_rejects_empty_or_missing_key_instead_of_dummy_group(self):
        source = item();plan = self.plan(source=source)
        for failure in ["empty_base","empty_added","missing_key"]:
            def lookup(call,previous=None):
                records,table = self.lookup(call,previous)
                if failure == "empty_base" and table == "CLOUD_SECURITY_GROUP":records = []
                elif failure == "empty_added" and table == "CLOUD_SUBNET":records = []
                elif failure == "missing_key" and table == "CLOUD_SUBNET":records[0].pop("vdcName")
                return records,table
            with self.subTest(failure=failure),patch.object(m,"_execute_lookup_api",side_effect=lookup):
                result = g.validate_groups(QUESTION,source,plan)
            self.assertFalse(result["valid"],result)
            self.assertEqual(result["reason"],"missing_group_field" if failure == "missing_key" else "empty_group_resource")

    def test_validation_does_not_read_unresolved_or_changed_scope(self):
        plan = self.plan()
        for value in ["{{logicalRegionName}}","region_other"]:
            source = item()
            for call in source["api_call"]:call["condition"]["constraint"][0]["simple"]["value"] = value
            with self.subTest(value=value),patch.object(m,"_execute_lookup_api",side_effect=self.lookup) as lookup:
                result = g.validate_groups(QUESTION,source,plan)
            self.assertFalse(result["valid"],result)
            lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
