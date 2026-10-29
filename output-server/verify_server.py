#!/usr/bin/env python
"""Data Query Service - 请求示例

用法:
  1. 启动服务:  python data_server.py --port 8080
  2. 发起请求:  python verify_server.py
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
import sys

BASE_URL = "http://127.0.0.1:8080"


def get(path, params=None):
    url = BASE_URL + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    start = time.time()
    try:
        with urllib.request.urlopen(url) as resp:
            status = resp.status
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode('utf-8')
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {'raw': body}
    elapsed = (time.time() - start) * 1000
    return status, data, elapsed


def cond(constraint_list):
    return json.dumps({"constraint": constraint_list}, separators=(',', ':'))


def show(title, status, data, ms, show_items=3):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"  Status: {status}  |  Time: {ms:.0f}ms")
    meta_keys = ['totalNum', 'pageSize', 'totalPageNo', 'currentPage']
    meta = {k: data.get(k) for k in meta_keys if k in data}
    if meta:
        print(f"  Meta: {json.dumps(meta, ensure_ascii=False)}")
    obj_list = data.get('objList', [])
    if obj_list:
        print(f"  objList: {len(obj_list)} items (showing first {min(show_items, len(obj_list))})")
        for i, obj in enumerate(obj_list[:show_items]):
            preview = {k: obj[k] for k in list(obj)[:6]}
            print(f"    [{i}] {json.dumps(preview, ensure_ascii=False)}")
    elif 'error' in data:
        print(f"  Error: {data['error']}")
    print(f"{'─'*60}")


def main():
    print("=" * 60)
    print("  Data Query Service - 请求示例")
    print("=" * 60)

    # === 1. 查询Instance数据（自定义pageSize） ===
    status, data, ms = get('/rest/hackthon/db/instances/VM_NOVA', {'pageNo': '1', 'pageSize': '2'})
    show("1. GET /instances/VM_NOVA?pageNo=1&pageSize=2  — 自定义每页数量", status, data, ms)
    vm_id = data['objList'][0]['id'] if data.get('objList') else ''
    vm_id2 = data['objList'][1]['id'] if len(data.get('objList', [])) > 1 else ''

    # === 2. 查询Relation数据 ===
    status, data, ms = get('/rest/hackthon/db/relations/R_PORT_IN_SUBNET', {'pageNo': '1', 'pageSize': '2'})
    show("2. GET /relations/R_PORT_IN_SUBNET?pageNo=1&pageSize=2  — Relation接口", status, data, ms)

    # === 3. 条件查询: equal ===
    c = cond([{"simple": {"name": "id", "value": vm_id, "operator": "equal"}}])
    status, data, ms = get('/rest/hackthon/db/instances/VM_NOVA', {'pageNo': '1', 'pageSize': '10', 'condition': c})
    show(f"3. GET /instances/VM_NOVA  condition: id equal '{vm_id}'", status, data, ms)

    # === 4. 条件查询: contain ===
    c = cond([{"simple": {"name": "modelIndexName", "value": "kafka", "operator": "contain"}}])
    status, data, ms = get('/rest/hackthon/db/instances/S_DeployComponent', {'pageNo': '1', 'pageSize': '5', 'condition': c})
    show("4. GET /instances/S_DeployComponent  condition: modelIndexName contain 'kafka'", status, data, ms)

    # === 5. 条件查询: in ===
    c = cond([{"simple": {"name": "id", "value": [vm_id, vm_id2], "operator": "in"}, "logOp": "and"}])
    status, data, ms = get('/rest/hackthon/db/instances/VM_NOVA', {'pageNo': '1', 'pageSize': '10', 'condition': c})
    show(f"5. GET /instances/VM_NOVA  condition: id in ['{vm_id[:12]}...', '{vm_id2[:12]}...']", status, data, ms)

    # === 6. 多条件: AND ===
    c = cond([
        {"simple": {"name": "osType", "value": "linux", "operator": "equal"}},
        {"simple": {"name": "status", "value": "active", "operator": "equal"}, "logOp": "and"}
    ])
    status, data, ms = get('/rest/hackthon/db/instances/VM_NOVA', {'pageNo': '1', 'pageSize': '3', 'condition': c})
    show("6. GET /instances/VM_NOVA  condition: osType=linux AND status=active", status, data, ms)

    # === 7. 多条件: OR ===
    c = cond([
        {"simple": {"name": "name", "value": ["ecs-quasar-1", "ecs-quasar-2"], "operator": "in"}},
        {"simple": {"name": "modelIndexName", "value": "kafka", "operator": "contain"}, "logOp": "or"}
    ])
    status, data, ms = get('/rest/hackthon/db/instances/S_DeployComponent', {'pageNo': '1', 'pageSize': '100', 'condition': c})
    show("7. GET /instances/S_DeployComponent  condition: name in [...] OR modelIndexName contain 'kafka'", status, data, ms)

    # === 8. pageNo超出范围 ===
    status, data, ms = get('/rest/hackthon/db/instances/VM_NOVA', {'pageNo': '99999', 'pageSize': '10'})
    show("8. GET /instances/VM_NOVA?pageNo=99999  — 超出范围返回空objList", status, data, ms)

    # === 9. 不存在的CI ===
    status, data, ms = get('/rest/hackthon/db/instances/NON_EXISTENT', {'pageNo': '1'})
    show("9. GET /instances/NON_EXISTENT  — 不存在的CI返回404", status, data, ms)

    # === 10. Relation + 条件查询 ===
    c = cond([{"simple": {"name": "relation_Name", "value": "R_PORT_IN_SUBNET", "operator": "equal"}}])
    status, data, ms = get('/rest/hackthon/db/relations/R_PORT_IN_SUBNET', {'pageNo': '1', 'pageSize': '5', 'condition': c})
    show("10. GET /relations/R_PORT_IN_SUBNET  condition: relation_Name equal 'R_PORT_IN_SUBNET'", status, data, ms)

    # === 11. Relation + contain ===
    c = cond([{"simple": {"name": "ipAddress", "value": "64", "operator": "contain"}}])
    status, data, ms = get('/rest/hackthon/db/relations/R_PORT_IN_SUBNET', {'pageNo': '1', 'pageSize': '5', 'condition': c})
    show("11. GET /relations/R_PORT_IN_SUBNET  condition: ipAddress contain '64'", status, data, ms)

    # === 12. 条件查询 + 分页（第2页） ===
    c = cond([{"simple": {"name": "modelIndexName", "value": "kafka", "operator": "contain"}}])
    status, data, ms = get('/rest/hackthon/db/instances/S_DeployComponent', {'pageNo': '2', 'pageSize': '5', 'condition': c})
    show("12. GET /instances/S_DeployComponent  condition: contain 'kafka', pageNo=2, pageSize=5", status, data, ms)

    print(f"\n{'='*60}")
    print("  全部请求完成")
    print(f"{'='*60}")


if __name__ == '__main__':
    try:
        main()
    except urllib.error.URLError as e:
        print(f"\n无法连接 {BASE_URL}，请先启动服务:")
        print("  python data_server.py --port 8080")
        print(f"  错误: {e}")
        sys.exit(1)
