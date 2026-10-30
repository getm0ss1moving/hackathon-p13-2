# 给B的最小view参数与提示词建议

本文件只提出新目录中的独立候选接口，不改已审batch3。两个family容器保持F02/F19；view是容器内受控输出合同，不是新增模板或旧ID路由。170仍是候选计划，当前没有新的N收益。

## 最小模型响应

```json
{
  "view": "ecs_creation_time",
  "filters": {"name": "<问题中实际实例名称>"},
  "required_filters": ["name"]
}
```

只给这三个键。view确定原合同的列、列序、filtered范围和既有排序；模型不用输出projection、SQL或order。实体filters必须保留原文，status只可按有证据的受控自然状态谓词规范化；提取失败用null，不能删键、回填默认实体或扩大范围。required_filters与全部filters键一致。无法表达的请求输出JSON null，交现有None→官方空结果路径，不输出说明文字。

## 受控view与默认合同

|view|默认列及顺序|完整合法筛选|
|---|---|---|
|ecs_creation_time|name, createdAt|name|
|ecs_cluster_zone|name, clusterName, azoneName|name|
|ecs_ip_tenant|name, privateIps, tenantName|azoneName+status 或 logicalRegionName+azoneName|
|ecs_filtered_list|name, privateIps, status|tenantName+logicalRegionName，可再含azoneName|
|ecs_tenant_ordered_ip|tenantName, name, privateIps；原ORDER BY tenantName|vdcName+logicalRegionName+azoneName|
|db_region_inventory|name, engineName, engineVersion, haMode, flavorCode|logicalRegionName|
|db_named_config|engineVersion, haMode, flavorCode|name|
|db_region_version_vip|name, engineVersion, dataVip|logicalRegionName|
|db_named_ha_vip|haMode, dataVip|name|

默认的只是**输出合同**，从不默认实体或删掉条件。原009问创建时间但返回name/createdAt，原145配置是三列，原148是haMode/dataVip；不要强迫用户把这些原合同的每列都再说一次。反过来，用户明确“只返回createdAt”、新增公网IP、要求其他排序等，不能以默认view覆盖其要求；不在闭合合同内则空。

“业务IP”在原合同中有dataVip/eip冲突，不能自动当dataVip；明确数据VIP的请求才能选择对应VIP view。名称相同可能多条记录，原SQL没有DISTINCT，不能承诺唯一实际实例。原pageSize=10000及SDK空数据行为保持原状，本候选不解决分页或空表列缺失问题。

## 可直接改写到family_fill的提示词

```text
你为已选中的F02或F19提取受控参数，只输出JSON对象或JSON null。
合法对象仅包含view、filters、required_filters；禁止输出SQL、旧ID、题号、projection、order或默认实体。
view必须来自本family的闭合view表（附上上述表中相应family的行）。

先判断用户需要哪种输出合同，再提取所有实际筛选。
普通“创建时间”“集群和可用区”“IP和租户归属”“实例列表/清单”“配置信息”
以及明确的配置属性/数据VIP请求，可选择对应原合同view；用户无需逐列列出默认列。
同名查询只表示name equal，并不保证唯一记录。

filters使用问题原文字符串，name/logicalRegionName/tenantName/vdcName/azoneName/status角色不能互换。
ECS[实例]<名称>或GaussDB[实例]<名称>中的紧邻名称可以提取为name，但必须匹配完整原文，不能改变实体大小写。
VDC等紧邻的角色和值可按明确角色绑定；不按实体拼写推断角色。
ecs_ip_tenant下，实际状态谓词加单一裸位置的唯一已审合同是AZ/status；明确区域绝不能转成AZ。
正在跑/正在运行/运行中可规范化active，已停止/停机可规范化stopped；无该谓词时不能默认状态。
全部明确筛选必须进入filters和required_filters。未提取到的必要值保留null，不能丢弃。
禁止用模板默认实体。列表view不能授权global，也不能删去状态、名称、租户等额外要求。

若请求包含非法筛选组合、名称包含/前缀、否定、OR、容量、COUNT、关系、多资源、
额外输出列/别名/排序，或含义不明确的业务IP，则输出null。
用户明确缩减/增加列时，不能用view默认列冒充满足；输出null。
不要把资源/状态/或等字出现在引号实体内部当成额外请求。
```

可以继续使用原family_fill阶段，无需增加一次模型请求。现有预算、截断/传输异常、schema/SQL精调由B保留；模型选view不能代替原文校验。

当前已生成真实matcher增量方案：`patches/latest_main_F02_F19_view_adaptation.patch`，基于main 7b7271e3及matcher源hash 1e7cc2ff…902b63e，只在选择后对F02/F19接入view路径，并新增一个纯业务函数模块。未修改B共享文件；应用前必须核对源hash，不可用候选快照覆盖B的新修改。完整入口937次受控调用通过，但真实170索引仍有8项显式问法缺召回，尚不能上传。

## 原文校验与接入顺序

建议B将view展开为上述固定参数，先核对合法profile；再验证原文输出意图与view一致，名称/区域等实际实体确有角色证据。新原型只拥有完整输出意图片段和明确资源+实例+名称片段，其他原词保留，交冻结batch3校验全部筛选和未知语义。审计记录原文、变换片段及展开参数，不能只保留规范化问题而失去删除条件的证据。

用户明确输出列时走原显式合同检查，不因失败而回退默认列。SQL精调保留调用，漂移时保留已审SQL。成功交普通API/SQL，失败None；内部原因不进业务输出。完整matcher、检索竞争、模型提示词和官方出口仍由B/A/主协调单独接入与验收。
