"""同区域三资源按原生VDC标签独立计数，未知标签保留NULL，不猜所有权。"""
import copy
import re

TABLES={'VM_NOVA':'CLOUD_VM_NOVA','VOLUME':'CLOUD_VOLUME','GAUSSDB_INSTANCE':'CLOUD_GAUSSDB_INSTANCE'}
FIELDS={'id','logicalRegionName','vdcName'}


def prepare(question,item,schemas):
    match=re.fullmatch(r'\s*(?:查询|查看|统计)?\s*区域\s*(region_[A-Za-z0-9_\-]+)\s*(?:下|中|内)各\s*VDC的?(?:ECS|虚拟机)数量[、,，]云硬盘数量(?:和|及|与|[、,，])GaussDB实例数量\s*[。?？]?\s*',question,re.I)
    if not match or set(item.get('resources',[]))!=set(TABLES):return None
    if not re.fullmatch(r'\s*SELECT\s+vdcName\s*,\s*COUNT\(\*\)\s+AS\s+volume_count\s+FROM\s+CLOUD_VOLUME\s+GROUP\s+BY\s+vdcName\s*;?\s*',item.get('sql',''),re.I):return None
    if any(not FIELDS<=set(schemas.get(ci,[])) for ci in TABLES):return None
    calls=item.get('api_call');region=match[1]
    if not isinstance(calls,list) or len(calls)!=3:return None
    by_ci={}
    for call in calls:
        ci=next((ci for ci in TABLES if call.get('url')==f'/rest/hackthon/db/instances/{ci}?pageNo=1&pageSize=10000'),None)
        if ci is None or ci in by_ci or set(call)-{'url','method','condition','autoPagination'} or call.get('method','GET')!='GET' or call.get('autoPagination',True) is not True:return None
        condition=call.get('condition')
        if condition:
            if set(condition)!={'constraint'} or len(condition['constraint'])!=1:return None
            entry=condition['constraint'][0];simple=entry.get('simple',{})
            if (set(entry)-{'simple','logOp'} or entry.get('logOp','and')!='and' or set(simple)!={'name','value','operator'}
                or simple['name']!='logicalRegionName' or simple['operator']!='equal' or simple['value'] not in {region,'{{logicalRegionName}}'}):return None
        by_ci[ci]={'method':'GET','url':call['url'],'condition':{'constraint':[{'simple':{'name':'logicalRegionName','value':region,'operator':'equal'}}]}}
    ordinary=copy.deepcopy(item);ordinary.update(api_call=[by_ci[ci] for ci in TABLES],sql=SQL,
        _vdc_resource_counts={'region':region,'group_policy':'exact native label; NULL and empty are separate unknown buckets'})
    return ordinary


_GROUPS={ci:'SELECT vdcName,COUNT(*) AS count FROM '+table+' GROUP BY vdcName' for ci,table in TABLES.items()}
_ANCHOR=("SELECT vdcName,COUNT(*) AS volume_count,0 AS carrier FROM CLOUD_VOLUME GROUP BY vdcName UNION ALL "
         "SELECT NULL,NULL,1 WHERE NOT EXISTS(SELECT 1 FROM CLOUD_VOLUME) AND "
         "(EXISTS(SELECT 1 FROM CLOUD_VM_NOVA) OR EXISTS(SELECT 1 FROM CLOUD_GAUSSDB_INSTANCE))")
_FIRST="a.carrier=1 OR a.vdcName IS (SELECT vdcName FROM CLOUD_VOLUME GROUP BY vdcName ORDER BY vdcName LIMIT 1)"
SQL=("SELECT a.vdcName,a.volume_count, CASE WHEN "+_FIRST+" THEN "
     "(SELECT json_group_array(json_object('vdcName',vdcName,'count',count)) FROM ("+_GROUPS['VM_NOVA']+")) END AS ecs_groups_json, "
     "CASE WHEN "+_FIRST+" THEN (SELECT json_group_array(json_object('vdcName',vdcName,'count',count)) FROM ("+_GROUPS['GAUSSDB_INSTANCE']+")) END AS gaussdb_groups_json, "
     "CASE WHEN a.carrier=1 THEN 'summary_only' ELSE 'volume_group' END AS row_kind FROM ("+_ANCHOR+") a ORDER BY a.vdcName")


def normalize(ci,rows,region):
    seen=set();result=[]
    for row in rows:
        identity=row.get('id')
        if not isinstance(identity,str) or not identity.strip() or identity in seen:raise ValueError('vdc_counts_missing_or_duplicate_id')
        seen.add(identity)
        if row.get('logicalRegionName')!=region:raise ValueError('vdc_counts_wrong_scope')
        if row.get('vdcName') is not None and not isinstance(row['vdcName'],str):raise ValueError('vdc_counts_invalid_label')
        result.append(dict(row,vdcName=row.get('vdcName')))
    return result
