# bootable：原生小写字符串合同修正

**单独默认关闭的隔离增量；不修改132、默认198、B或官方组件，不注册或关闭issue。只处理`family_volume_rows`的`bootable_scoped_rows`输入→原生API字符串边界，不实施管理VM，也不改变其JSON bool合同。**

布尔值 `True/False`（JSON `true/false`）和大小写 `true/false` 字符串可作目标字段输入，prepare统一发原生字符串`"true"/"false"`。数字0/1、浮点、NULL、容器、yes/no、空白包裹及任意truthy对象拒绝。原生响应不改写；region/AZ大小写和角色、其他view、API/SQL资源/列序保持原规则，参考AZ争议仍由C裁定。

先读[中文B交接](../../docs/handoffs/B_A_ISSUE3_BOOTABLE_CONTRACT.md)及[B_INTEGRATION](B_INTEGRATION.md)。源码、合同、卡片test/replace提案、registry哈希提案、原模块和精确补丁保持受审字节，原公开闭包13项已核；本包选择7份必要原文件并补最小文档/复放，不冒称owner全归档。

|绑定|SHA-256|
|---|---|
|原模块|`bb6f0dace53f6ce6d47244c784a15265501a477da123892ffd86e353f23f4138`|
|新candidate|`56c6a58c9b8108cb7c0545e1c2da9e5ad00a35101d007f4b8415b703d05514d0`|
|卡片提案|`3e5f1cd67cd4332b70b0c930ab329f7a546261c175324efbe0f0b6cd69cfa547`|

## 最小复放

```sh
python3 -B scripts/verify_a_issue3_bootable_synthetic.py --output /tmp/a-bootable-check-new
```

从仓库根运行，输出须全新且在仓库外，只需标准库与内存SQLite。前11项沿独立收据的纯函数/合成检查；第12项核补丁内存精确重放、卡片/registry/schema联动提案及历史字段汇总一致性，**不重新读取原生记录**。这与原独立12项最后的原生字段复核范围不同，不能称再次完成原生扫描；owner71套件未运行或加总。公开实际摘要在[evidence/PUBLISH_VERIFICATION](evidence/PUBLISH_VERIFICATION.json)。

原独立收据12/12仅证明局部边界，曾核7份源6190个字段均为原生小写字符串。这里仅保留必要类型/枚举聚合和来源指纹，没有对象ID/名称、原生记录、展开模板、原题答案或凭据。无模型、服务、B运行、官方执行器或评分器调用。

B必须在自身隔离接入中同步模块、registry/受影响哈希、参数schema与卡片，并使用完整原文prepare；不能直接替换已有132数组或沿用旧绑定哈希。真实请求/schema/分页、typed-empty装载、失败传播和正式最终封装仍未验收，实际N变化0。
