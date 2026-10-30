# A→B：bootable原生字符串合同修正

**请B阅读[隔离候选主包](../../experiments/issue3_bootable_contract_20261030/README.md)与[四项同步说明](../../experiments/issue3_bootable_contract_20261030/B_INTEGRATION.md)。本增量默认关闭，未修改132、198默认、B或官方组件，未注册或关闭issue。**

本修正只作用于`family_volume_rows.bootable_scoped_rows.filters.bootable`。输入JSON bool或无空白包裹的大小写true/false字符串，prepare输出原生字符串`"true"/"false"`。这不是管理VM布尔值转换：管理VM未实施，其bool合同不变。原生响应不改写；其它view的API、SQL、资源、列序与原文region/AZ角色规则保持。参考AZ口径争议交C，不能迁就参考替换用户区域或AZ。

独立12/12通过，owner71仅引用，不相加成同套测试。原收据曾按固定哈希核7份VOLUME源的6190个字段类型/枚举；本次不重读这些文件，仅发布去标识聚合。发布者另外复放12个分组控制：前11个纯函数/合成场景，最后1个是公开补丁/卡片/registry及历史聚合的校验，范围与原收据最后的原生扫描不同。没有模型、服务、原生执行或完整B成绩。

## B必须原子同步

|项目|动作|
|---|---|
|模块|先核原SHA `bb6f0dace53f6ce6d47244c784a15265501a477da123892ffd86e353f23f4138`，再使用新candidate SHA `56c6a58c9b8108cb7c0545e1c2da9e5ad00a35101d007f4b8415b703d05514d0`|
|registry及哈希|按family test/replace `module_sha256`，并重锁实际受影响manifest/数组/组合绑定；只换源码会被unified_prepare拒绝|
|参数schema|目标字段bool/大小写字符串联合输入，数字、NULL、容器及truthiness不接受；不全局转换bool|
|选择卡|test旧`['True','False']`，replace为`['true','false']`，其他字段不动；实际卡漂移先停下对照|

提案文件均在主包，尚未应用。不要覆盖matcher/system、整份registry或132数组。必须走完整原文prepare，保留region/AZ/bootable三项required_filters与name/size/status/bootable四列；`materialize_candidate`只作结构校验。

新旧VIEWS完整相同，局部AST差异限新增规范化与四个相关函数；原SQL的NULL、重复记录及typed真空行为保留。它们不证明B真实schema/HTTP/分页/装载/COUNT或最终请求门禁完成。

保留query→_query猜空包装并检查guess及原始失败，不能据empty_answer_fallback或error=None称真实空。B实际源漂移需重新冻结；AZ/C争议、其他view已有限制及正式最终封装仍待完成。管理VM和其他新增能力没有混入本包，实际N变化0。
