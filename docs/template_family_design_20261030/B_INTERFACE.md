> 发布范围：这是源51f0aad、200条模板的设计快照，尚未通过生产接入验收。正文中的根/B双目录比较属于旧时点；当前main已统一根目录，严格去重后为198条（054→052、087→086）。本文不改生产。实体示例在本发布副本中用参数占位，完整机器接口/原始证据仍由本地实施与独立审查任务保留；本目录不提供可执行候选。

# 六族物化接口：实施者接入说明

接口版本v1.0；以[变更记录](INTERFACE_CHANGELOG.md)为准。只在实施任务独立目录开发，本任务没有修改根或B业务文件。

## 输入与输出

```python
from first_batch_reference import materialize

native = materialize('F01', {
    'scope': 'filtered',
    'group': 'azoneName',
    'metrics': 'count',
    'filters': {'logicalRegionName': 'Region-A'},
    'required_filters': ['logicalRegionName'],
})
assert native['sql'] == (
    'SELECT azoneName, COUNT(*) AS count '
    'FROM CLOUD_VM_NOVA GROUP BY azoneName'
)
assert native['api_call']['condition']['constraint'][0]['simple']['name'] == 'logicalRegionName'
```

上述Region-A只是明确提供给离线函数的合成输入，没有新增为任何模板默认实体。该函数不接收旧ID、题文或SQL文本；不运行网络/生产模块，只用于证明闭合参数空间能还原旧合同。不要把它作为新增适配层导入生产；实施者将必要的有限映射放入已认领matcher，并继续原有精调与执行。

|参数|含义|错误行为|
|---|---|---|
|family_id|已检索选择的六族之一|未知族拒绝|
|scope|global或filtered，来自问题/已证上下文|未知/缺失拒绝，不默认为global|
|filters|required_filters对应的已提及条件实际值|未知字段、缺值、错误类型拒绝|
|required_filters|从问题确定的筛选角色，必须完整提取|与启用条件不一致拒绝|
|结构参数|group、metrics、view、count_alias、label、order中的族白名单|任意SQL、未知字段、非法粒度组合拒绝|
|返回api_call/sql|普通原生执行合同|不要求固定executor解释任何新元数据|

F01、F08允许全局；F14/F18/F21要求region。F20必须明确shared，False是有效值。F18首批不允许engineName或tenant/VDC筛选。所有精确原配置见FIRST_BATCH.json的mappings；里面的old_id和source_{{name}}s_evidence_only只用于离线迁移，不供运行时路由/默认回填。

## 在B现有流程中接入

1. BM25索引保留原有有价值词面，选择器提示中明确族资源、允许分组/视图、范围与输出；现有`_format_runbook_list`不会自动展示新metadata，须显式加入必要摘要。
2. `_get_placeholders`目前只扫描原api_call/sql/params，不能自动发现group/metrics/view。由原填参步骤同步提取这些结构槽，严格限定枚举。不能只给API添optional值占位符就认为结构参数已生效。
3. 保留用户提及条件来源，在`_fill_params`之前物化已选结构；必要条件提取失败拒答。实体值只放API，不当SQL标识符。root matcher无占位符有早返回；B matcher没有这个早返回，但仍需主动识别结构槽。
4. 物化后再做资源覆盖、表集合/投影与粒度校验，继续原SQL精调；校验精调没有破坏已选分组、指标、列名、标签、排序。不能先拿固定基准SQL检验视图列后就拒绝本应允许的结构变化。
5. 首批只有单源API，没有新增from-step依赖。后续族复用B依赖校验必须确认实际路径：B matcher的`RUNBOOK_VALIDATE_API_DEPENDENCIES`开关默认不自动保证所有调用；B system的有界执行路径传`defer_api_validation=True`，由其runner在实际步骤前验证。不得单凭函数存在就声称已短路。
6. 原根matcher与B matcher差异显著，保留B train-only修改；本轮不要整文件用根旧实现覆盖B。严格重复模板由集成负责，六族实现只核对其实际删除后的映射。

## 证据及运行边界

完整无损复现代码与冻结输入保留在本地设计交接中，本次只发布阅读材料；未宣称本目录可独立复现实验。

三条命令只访问本目录快照/设计产物，使用标准库，无模型/服务/题库请求。`VALIDATION.json`证明25个原配置API条件等价（仅消除重复AND）和SQL除空白外相同；另有35个非法配置与10个类型/粒度控制。`STATIC_REVIEW.json`覆盖全200映射、27族98成员的轴一致性；其余73成员尚无物化等价证明。

27族原生基准候选都小于4KB，最大1,827字节；首批将真实启用条件和所选SQL放回候选后最大2,247字节、容器深度6（不含外数组）。新增metadata和API参数会改变最终容量，实施者仍须逐条重新量化。官方深度计数未明确，不能用基准F01无条件深度3宣称所有物化查询都深度合规。

原execute/API、模型抽取、训练150评分、封存50和官方黑盒均未运行；布尔API接受口径、索引/选择影响和正式提交深度仍待实施任务验证。
