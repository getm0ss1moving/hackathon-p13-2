"""HOST范围与VM状态的合成正负例；原执行器仅接收内存数据，不读取题目。"""
import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_matcher as m
import runbook_executor as executor
from runbook_retriever import Candidate

QUESTION = "区域region_demo可用区az0.dc0中所有宿主机的名称、CPU架构和运行中虚拟机列表"
SQL = ("SELECT CLOUD_HOST.name AS host_name,SYS_X86Server.cpuArch AS cpu_arch,CLOUD_VM_NOVA.name AS vm_name "
       "FROM CLOUD_HOST INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId=SYS_X86Server.id "
       "INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id=CLOUD_VM_NOVA.hostId")
SCHEMA = {"HOST":["id","name","serverId","status","logicalRegionName","azoneName"],
          "VM_NOVA":["id","hostId","name","status","logicalRegionName","azoneName"], "S_X86Server":["id","cpuArch"]}


def source():
    scopes = [{"simple":{"name":name,"value":"{{"+name+"}}","operator":"equal"}}
              for name in ["logicalRegionName","azoneName"]]
    call = {"method":"GET","url":"/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
            "condition":{"constraint":scopes}}
    second = copy.deepcopy(call)
    second["condition"]["constraint"].append({"simple":{"name":"status","value":"{{status}}","operator":"equal"}})
    return {"id":"synthetic-host-details","name":"synthetic host VM details","resources":["HOST"],
            "examples":[],"api_call":[call,second],"sql":SQL}


class StatusRoleTests(unittest.TestCase):
    def setUp(self):
        for context in [patch.object(m,"_schema_columns",copy.deepcopy(SCHEMA)),
                        patch.object(m,"_schema_values",{"HOST":{"status":["normal","fault"]},"VM_NOVA":{"status":["active","stopped"]}})]:
            context.start()
            self.addCleanup(context.stop)

    def repaired(self):
        result=m._correct_host_vm_status_role(QUESTION,source())
        self.assertIsNotNone(result)
        return result

    def test_wrong_owner_explains_missing_value(self):
        self.assertEqual(m._param_resource(source(),"status"),"HOST")
        values={}
        m._auto_fill_params(QUESTION,values,["status"],source())
        self.assertNotIn("status",values)
        result=self.repaired()
        m._auto_fill_params(QUESTION,values,["status"],result)
        self.assertEqual(values["status"],"active")

    def test_scope_and_sql_are_preserved_without_mutating_source(self):
        original=source();before=copy.deepcopy(original)
        result=m._correct_host_vm_status_role(QUESTION,original)
        self.assertEqual(original,before)
        self.assertEqual(result["api_call"][0],original["api_call"][0])
        self.assertEqual(result["sql"],SQL)
        self.assertIn("/VM_NOVA?",result["api_call"][1]["url"])
        self.assertEqual(result["api_call"][1]["condition"],original["api_call"][1]["condition"])

    def test_unproven_schema_or_join_does_not_change_calls(self):
        for field in ["hostId","status","logicalRegionName","azoneName"]:
            changed=copy.deepcopy(SCHEMA);changed["VM_NOVA"].remove(field)
            with patch.object(m,"_schema_columns",changed):
                self.assertIsNone(m._correct_host_vm_status_role(QUESTION,source()))
        item=source();item["sql"]=SQL.replace("CLOUD_VM_NOVA.hostId","CLOUD_VM_NOVA.id")
        self.assertIsNone(m._correct_host_vm_status_role(QUESTION,item))

    def test_extra_or_conflicting_conditions_are_not_deleted(self):
        for action in ["extra","or","different_scope","host_status","literal_scope"]:
            item=source();first,second=item["api_call"]
            if action=="extra":second["condition"]["constraint"].append({"simple":{"name":"name","value":"vm-x"}})
            if action=="or":second["condition"]["constraint"][-1]["logOp"]="or"
            if action=="different_scope":second["condition"]["constraint"][0]["simple"]["value"]="other-region"
            if action=="host_status":first["condition"]["constraint"].append({"simple":{"name":"status","value":"normal"}})
            if action=="literal_scope":
                first["condition"]["constraint"][0]["simple"]["value"]="fixed-default"
                second["condition"]["constraint"][0]["simple"]["value"]="fixed-default"
            with self.subTest(action=action):self.assertIsNone(m._correct_host_vm_status_role(QUESTION,item))

    def test_negation_disjunction_extra_metrics_and_named_entities_refuse_repair(self):
        for question in [QUESTION.replace("运行中","非运行中"),QUESTION.replace("运行中","运行中或已停止"),
                         QUESTION+"且vCPU大于8",QUESTION+"及内存容量",QUESTION+"，宿主机host_demo",QUESTION+"，虚拟机vm_demo",
                         "正常宿主机及运行中虚拟机列表","运行中宿主机列表"]:
            with self.subTest(question=question):self.assertIsNone(m._correct_host_vm_status_role(question,source()))

    def test_entity_perturbations_keep_status_attached_to_vm(self):
        for region in ["region_other","region_2027","region_cpu"]:
            result=m._correct_host_vm_status_role(QUESTION.replace("region_demo",region),source())
            self.assertIsNotNone(result)
            values={};m._auto_fill_params(QUESTION.replace("region_demo",region),values,m._get_placeholders(result),result)
            self.assertEqual(values["logicalRegionName"],region)
            self.assertEqual(values["status"],"active")

    def test_pipeline_fills_using_the_corrected_native_role(self):
        item=source();details={}
        retriever=SimpleNamespace(retrieve=lambda *a,**k:[Candidate(id=item["id"],tier="strong",score=1,coverage=1)])
        with patch.dict(os.environ,{"RUNBOOK_RULE_ONLY_FILL":"1"},clear=True), \
                patch.object(m,"llm_ask",return_value="1") as ask, \
                patch.object(m,"_get_table_schemas",return_value=""),patch.object(m,"_refine_sql",side_effect=lambda q,sql,*a:sql):
            result=m.match_runbook(QUESTION,[item],retriever,details)
        self.assertIsNotNone(result,details)
        self.assertEqual(details["parameters"]["final"]["status"],"active")
        self.assertEqual(details["api_role_correction"]["to_ci"],"VM_NOVA")
        self.assertEqual(ask.call_count,1)

    def native_fixture(self,empty=False):
        rows={"HOST":[{"id":"h-a","name":"host-a","serverId":"s-a","logicalRegionName":"region_demo","azoneName":"az0.dc0","status":"normal"},
                      {"id":"h-b","name":"host-b","serverId":"s-b","logicalRegionName":"region_other","azoneName":"az0.dc0","status":"normal"}],
              "VM_NOVA":[{"id":"v-a","name":"vm-active","hostId":"h-a","status":"active","logicalRegionName":"region_demo","azoneName":"az0.dc0"},
                         {"id":"v-s","name":"vm-stopped","hostId":"h-a","status":"stopped","logicalRegionName":"region_demo","azoneName":"az0.dc0"},
                         {"id":"v-b","name":"vm-other-region","hostId":"h-b","status":"active","logicalRegionName":"region_other","azoneName":"az0.dc0"},
                         {"id":"v-cross","name":"vm-cross-namespace","hostId":"h-a","status":"active","logicalRegionName":"region_other","azoneName":"az0.dc0"}],
              "S_X86Server":[{"id":"s-a","cpuArch":"arch-a"},{"id":"s-b","cpuArch":"arch-b"}]}
        def query(ci,conditions=None):
            if ci=="HOST" and empty:return []
            result=copy.deepcopy(rows[ci])
            for c in conditions or []:
                self.assertEqual(c["operator"],"equal")
                result=[r for r in result if r.get(c["key"])==c["value"]]
            return result
        return query

    def test_original_executor_preserves_root_scope_and_zero_rows(self):
        for empty in [False,True]:
            item=self.repaired();values={};m._auto_fill_params(QUESTION,values,m._get_placeholders(item),item)
            self.assertTrue(m._fill_params(item,values,QUESTION))
            with patch.object(executor,"_query_server",side_effect=self.native_fixture(empty)):
                result=executor.execute(item)
            self.assertIsNone(result["error"])
            if empty:self.assertEqual(result["result"]["row_count"],0)
            else:self.assertEqual(result["result"]["rows"],[{"host_name":"host-a","cpu_arch":"arch-a","vm_name":"vm-active"}])


if __name__=="__main__":unittest.main()
