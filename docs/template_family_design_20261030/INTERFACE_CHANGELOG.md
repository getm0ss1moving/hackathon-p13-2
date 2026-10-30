> 发布范围：这是源51f0aad、200条模板的设计快照，尚未通过生产接入验收。正文中的根/B双目录比较属于旧时点；当前main已统一根目录，严格去重后为198条（054→052、087→086）。本文不改生产。实体示例在本发布副本中用参数占位，完整机器接口/原始证据仍由本地实施与独立审查任务保留；本目录不提供可执行候选。

# 首批接口版本记录

## v1.0（实现线程开工后明确发布）

`FIRST_BATCH.md`保持六族、25原ID及19条条件减少；原生接口不变。正式机器入口为 `FIRST_BATCH.json`；`first_batch_reference.py:materialize(family_id, configuration)`是独立离线物化参考，只产出普通`api_call`与`sql`，不是生产改动或SDK扩展。

- **F18首批边界明确收紧**：只包含105/106/143/144；`group=flavorCode/vdcName/engineVersion/haMode`，`filters`只允许logicalRegionName。`engineName`、tenantName/vdcName筛选与150仅在全量设计待核，不能因全量F18参数轴出现它们而加入首批。机器首批JSON已独立过滤这部分。
- **F01别名组合明确**：标量`group=none, metrics=count`必须`count_alias=total`；分组COUNT为`count`；`total_active`输出total/active_count；`status_counts`输出running_count/stopped_count/error_count。`label=ECS`只允许VDC/count。
- **公共必需条件**：传入`scope`、`filters`、`required_filters`。`required_filters`记录从用户/已证上下文明确识别的过滤维度，必须与当前启用条件一致。filtered至少有一个条件，global禁止携带过滤条件；required缺值不允许退化global。False/0的缺失判定不用真值法，但字符串字段收到0/False仍应按类型拒绝。
- **布尔值**：参考物化保持False/True的原类型；旧模板中的字符串True/False原样对照。数据服务对布尔/字符串接受口径未在本任务实测，不称已验证。
- **元数据处理位置**：结构参数在既有参数填充/SQL精调前物化，不能等待executor解释。根旧matcher无占位符会提前返回，B matcher没有这个早返回，但其 `_get_placeholders` 仍只看原字段，不自动识别新增结构元数据。两处都须显式接入。
- **验证结果**：25条原合同API语义等价（只消除重复AND条件），SQL除空白外逐字相同；35个非法配置拒绝；10个语义/类型控制通过。没有原服务、executor/evaluator、模型或题库访问。
- **冻结输入**：集成者开始修改共享模板后，重建脚本因哈希变化主动停止（未继续分析变化中的输入）。已改为只读取本任务之前复制且SHA256一致的`source/runbook_items_native_51f0aad.py`。该修正不改变任何配置或测试结论；当前生产N不在本设计任务中断言。

严格重复052/054、086/087由原集成任务独立扫描、去重、回归与提交。本设计不重复实现，不预先声明其生产数量。以200为基准的六族N=181包含086/087去重收益；若两组严格重复都已先删除，再做剩余首批合并，额外收益18条，联合条件N=180，不得把19与2直接相加。

## 文件状态

设计及参考代码只在`a-family-design`；共享生产文件无修改。`FULL_MAPPING`中非首批配置是明确的语义参数映射，尚无物化实现验证；不能把首批25通过外推为全27族通过。
