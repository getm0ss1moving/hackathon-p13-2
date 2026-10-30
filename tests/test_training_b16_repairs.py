"""失败队列第二批：角色错配、漏过滤和规则/端口独立输出；仅合成数据。"""
import copy
import json
import os
import sqlite3
import unittest
from unittest.mock import patch

import runbook_matcher as m
from runbook_items import RUNBOOK_ITEMS
import test_training_a132_intake as intake


class B16Repairs(unittest.TestCase):
    def setUp(self):
        self.by_id={i['id']:i for i in RUNBOOK_ITEMS}
        p=patch.dict(os.environ,{'RUNBOOK_A132_CANDIDATE':'1'});p.start();self.addCleanup(p.stop)

    def fill(self,*args):return intake.A132IntakeTests.fill(self,*args)

    def test_f02_wrong_role_keeps_literal_but_recovers_actual_az(self):
        raw={'view':'ecs_filtered_list','filters':{'logicalRegionName':'az0.dc0','status':'active'},
             'required_filters':['logicalRegionName','status']}
        result,d,_=self.fill('family_f02','az0.dc0里正在跑的ECS有哪些IP，分别属于哪个租户',raw)
        self.assertIsNotNone(result,d)
        self.assertEqual(d['parameters']['effective']['filters'],{'azoneName':'az0.dc0','status':'active'})
        raw['filters']['logicalRegionName']='unrelated_region'
        result,_,_=self.fill('family_f02','az0.dc0里正在跑的ECS有哪些IP，分别属于哪个租户',raw)
        self.assertIsNone(result)

    def test_f01_missing_explicit_filter_recovered_from_evidence_not_metric_words(self):
        raw={'scope':'filtered','group':'azoneName','metrics':'status_counts','count_alias':'count',
             'label':'none','order':'none','filters':{'logicalRegionName':'region_demo'},
             'required_filters':['logicalRegionName']}
        q='查询VDCdemo_vdc在区域region_demo中各可用区的ECS运行中数量、停止数量和异常数量'
        d={}
        with patch.object(m,'llm_ask',return_value=json.dumps(raw)),patch.object(m,'_get_table_schemas',return_value=''), \
                patch.object(m,'_refine_sql',side_effect=lambda q,s,*a,**kw:s):
            item=m._match_family_candidate(q,self.by_id['family_f01'],d)
        self.assertIsNotNone(item,d)
        constraints=item['api_call']['condition']['constraint']
        self.assertEqual({c['simple']['name']:c['simple']['value'] for c in constraints},
                         {'logicalRegionName':'region_demo','vdcName':'demo_vdc'})

    def make_rule_plan(self):
        root={'method':'GET','url':'/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000',
              'condition':{'constraint':[{'simple':{'name':'name','value':'demo_group','operator':'equal'}}]}}
        rule={'method':'GET','url':'/rest/hackthon/db/instances/SECURITY_GROUP_RULE?pageNo=1&pageSize=10000',
              'condition':{'constraint':[{'simple':{'name':'securityGroupId','value':'{{id from step 1}}','operator':'equal'}},
                                         {'simple':{'name':'direction','value':'ingress','operator':'equal'}}]}}
        return {'api_call':[root,rule,copy.deepcopy(root)],'sql':'SELECT COUNT(*) AS port_count FROM CLOUD_SECURITY_GROUP INNER JOIN R_PORT_USE_SECURITY_GROUP ON CLOUD_SECURITY_GROUP.id = R_PORT_USE_SECURITY_GROUP.sgId INNER JOIN CLOUD_PORT ON R_PORT_USE_SECURITY_GROUP.portId = CLOUD_PORT.id'}

    def test_rule_details_do_not_multiply_original_port_count(self):
        item=self.make_rule_plan();original=copy.deepcopy(item)
        with patch.dict(m._schema_columns,{'SECURITY_GROUP_RULE':['id','securityGroupId','direction']}):
            plan=m._complete_ingress_rule_details('安全组demo_group中哪些规则允许了外部访问，关联了多少个端口',item)
        self.assertIsNotNone(plan);self.assertEqual(item,original)
        with sqlite3.connect(':memory:') as c:
            c.executescript("CREATE TABLE CLOUD_SECURITY_GROUP(id TEXT);INSERT INTO CLOUD_SECURITY_GROUP VALUES('sg');CREATE TABLE R_PORT_USE_SECURITY_GROUP(sgId TEXT,portId TEXT);INSERT INTO R_PORT_USE_SECURITY_GROUP VALUES('sg','p1'),('sg','p2');CREATE TABLE CLOUD_PORT(id TEXT);INSERT INTO CLOUD_PORT VALUES('p1'),('p2');CREATE TABLE CLOUD_SECURITY_GROUP_RULE(id TEXT,securityGroupId TEXT,direction TEXT);INSERT INTO CLOUD_SECURITY_GROUP_RULE VALUES('r1','sg','ingress'),('r2','sg','ingress'),('r3','sg','ingress');")
            row=c.execute(plan['sql']).fetchone()
        self.assertEqual(row[0],2);self.assertEqual(len(json.loads(row[1])),3)

    def test_rule_scope_extra_or_changed_root_is_not_completed(self):
        q='安全组demo_group中哪些规则允许了外部访问，关联了多少个端口'
        with patch.dict(m._schema_columns,{'SECURITY_GROUP_RULE':['id','securityGroupId','direction']}):
            self.assertIsNone(m._complete_ingress_rule_details(q+'，排除r1',self.make_rule_plan()))
            item=self.make_rule_plan();item['api_call'][1]['condition']['constraint'][1]['simple']['value']='egress'
            self.assertIsNone(m._complete_ingress_rule_details(q,item))


if __name__=='__main__':unittest.main()
