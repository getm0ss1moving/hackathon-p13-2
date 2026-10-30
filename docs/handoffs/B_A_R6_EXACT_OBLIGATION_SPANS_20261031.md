# A→B：r6原文义务跨度修正（默认关闭候选）

本候选默认关闭、尚未发布，不改已冻结的B `2c6ddfd532d5ee7990d6f642d577af1a18b8aa55` 或其全量测试。只修两端空白坐标，不改模板、region/default参数、prepare/schema、索引候选及B运行组件。

## 固定源码与范围

|版本|r5基底SHA-256|r6源码SHA-256|
|---|---|---|
|strict|`b5a1c943fcf4785aa40c39e4905fbbdba2719eed9d458b391c127657b348f3d6`|`a236235e98ebcceeb372577fe85fa3d3baa26d7a58edb0775c579d9e4fccca52`|
|enhanced|`b3294dcd7672d2ccf283bc79712b85509e877bf89527344830d3434ee9e7bd6e`|`76bbcd817d2f3ff4b8748061a8134a33f5693bc5d04ee6519d385cac1b6ba8b9`|

独立两版各50正控制通过、12本地严格验证器负控制拒绝。owner1148/49/54/978仅保留来源，不重跑或合并计数。R6最小运行仍需同版132v1受审数组；当前B compact132组合没有被本收据认证。私有数组/旧问法集/原生数据/历史逐题输出均不在发布材料内。

跨度为原始Python str码点，end排他。两端空白收缩后从原文重切text，保持内部空白、组合字符和补充平面字符，不进行Unicode归一化或全局find。重复相同文本仍保留各自有序位置；单原子query的retrieve_obligations=[]依旧正常。top_k=None才用于完整义务结论，预算不变。

## 与B临时修复的兼容

已只读核固定[B源码](https://github.com/getm0ss1moving/hackathon-p13-2/blob/2c6ddfd532d5ee7990d6f642d577af1a18b8aa55/implementation/runbook_system.py)和[运行配对清单](https://github.com/getm0ss1moving/hackathon-p13-2/blob/2c6ddfd532d5ee7990d6f642d577af1a18b8aa55/experiments/b_a132_r5_runtime_20261031/SOURCE_MANIFEST.json)。

- B的`_original_obligation_span`先检查`original == text`，r6精确区间直接返回原三元组，不会再次缩短。现有旧r5边缘空白兼容分支可留作回退；不需要覆盖或删除B修复，也不能将r6验收放宽成strip后相等。
- `_query_obligations`仍须检查原始顺序，分别调用每一段，保留同族多实体及profile证据。这里没有执行B模型选择、参数保留或SQL，因此这几层仍需B自己的隔离联调。
- B的R5测试目前对一个AND样例断言必须产生`obligation_span_normalization`。r6不需要修正时，日志可不存在；采用r6后应按版本/实际改动区分预期，不能为过旧测试伪造修正日志或再次改坐标。
- B当前来源清单固定`strict_r5`与r5模块哈希、compact数组哈希。直接替换root文件会破坏来源锁。需新增经核验的r6配对与清单，保留r5回退；不忽略哈希漂移、不覆盖matcher/system/issue3。

本次兼容检查仅为固定源码分析和隔离纯helper检查；不是当前B main已采用r6的证明。专门的2c6ddfd全量测试保持原冻结，不混入此增量，也不归入r6成绩。
