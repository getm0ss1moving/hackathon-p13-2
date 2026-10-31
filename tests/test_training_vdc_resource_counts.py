import json
import sqlite3
from contextlib import closing
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
import runbook_vdc_counts as v
import runbook_matcher as m
import runbook_system as s

Q='查询区域region_lab下各VDC的ECS数量、云硬盘数量和GaussDB实例数量'
def fixture():
    return {'id':'synthetic','name':'synthetic counts','resources':list(v.TABLES),
        'api_call':[{'method':'GET','url':f'/rest/hackthon/db/instances/{ci}?pageNo=1&pageSize=10000'} for ci in v.TABLES],
        'sql':'SELECT vdcName, COUNT(*) AS volume_count FROM CLOUD_VOLUME GROUP BY vdcName'}

class CountsTests(unittest.TestCase):
    def execute(self,resources):
        with closing(sqlite3.connect(':memory:')) as db:
            db.row_factory=sqlite3.Row
            for ci,table in v.TABLES.items():
                db.execute('CREATE TABLE '+table+'(id TEXT,logicalRegionName TEXT,vdcName TEXT)')
                db.executemany('INSERT INTO '+table+' VALUES (?,?,?)',[(r['id'],r['logicalRegionName'],r.get('vdcName')) for r in resources.get(ci,[])])
            return [dict(r) for r in db.execute(v.SQL)]
    def row(self,id,label=None):return dict(id=id,logicalRegionName='region_lab',vdcName=label)
    def test_independent_populations_unknown_empty_and_extra_group_all_preserved(self):
        rows=self.execute({'VM_NOVA':[self.row('e1','extra'),self.row('e2','extra')],
            'VOLUME':[self.row('v1'),self.row('v2',''),self.row('v3','')],
            'GAUSSDB_INSTANCE':[self.row('g1','other')]})
        self.assertEqual([(r['vdcName'],r['volume_count']) for r in rows],[(None,1),('',2)])
        self.assertEqual(json.loads(rows[0]['ecs_groups_json']),[{'vdcName':'extra','count':2}])
        self.assertEqual(json.loads(rows[0]['gaussdb_groups_json']),[{'vdcName':'other','count':1}])
        self.assertIsNone(rows[1]['ecs_groups_json'])
    def test_zero_populations_and_volume_less_carrier_do_not_invent_a_volume_group(self):
        self.assertEqual(self.execute({}),[])
        r=self.execute({'VM_NOVA':[self.row('e1','owner')]})[0]
        self.assertEqual(r['row_kind'],'summary_only');self.assertIsNone(r['volume_count'])
        self.assertEqual(json.loads(r['ecs_groups_json'])[0]['count'],1)
    def test_scope_identity_label_checks_and_missing_label_normalization(self):
        raw={'id':'v','logicalRegionName':'region_lab'}
        self.assertIsNone(v.normalize('VOLUME',[raw],'region_lab')[0]['vdcName']);self.assertNotIn('vdcName',raw)
        for rows in [[self.row('a'),self.row('a')],[dict(raw,logicalRegionName='else')],[dict(raw,vdcName=[])]]:
            with self.assertRaises(ValueError):v.normalize('VOLUME',rows,'region_lab')
    def test_whole_question_and_real_schema_are_required(self):
        schema={ci:list(v.FIELDS) for ci in v.TABLES}
        self.assertIsNotNone(v.prepare(Q,fixture(),schema))
        self.assertIsNone(v.prepare(Q+'和管理员密码',fixture(),schema))
        schema['VOLUME'].remove('vdcName');self.assertIsNone(v.prepare(Q,fixture(),schema))
    def test_real_bounded_path_preserves_sparse_rows_and_scoped_requests(self):
        data={ci:[self.row(ci)] for ci in v.TABLES};del data['VOLUME'][0]['vdcName']
        class Session:
            def get(self,url,**kwargs):
                ci=url.split('?')[0].rsplit('/',1)[-1];return SimpleNamespace(status_code=200,json=lambda:{'objList':data[ci],'totalNum':1,'totalPageNo':1,'currentPage':1,'pageSize':10000})
        schema={ci:list(v.FIELDS) for ci in v.TABLES};item=v.prepare(Q,fixture(),schema);diag={}
        with patch.object(m,'_schema_columns',schema):r=s._execute_bounded_api(item,diag,session=Session(),request_line_limit=4096)
        self.assertEqual(r['result']['rows'][0]['volume_count'],1);self.assertTrue(diag['sql_executed']);self.assertEqual(diag['http_requests'],3)

if __name__=='__main__':unittest.main()
