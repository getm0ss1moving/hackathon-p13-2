# A→B：132v2 compact＋r4 最终联调候选

**请 B 先阅读本交接和[候选主包](../../experiments/a_family_candidate_132_v2_r4_20261030/README.md)。r4 离线独立验收已通过；本候选默认关闭，B 端到端与官方整包合规尚未验收。生产默认 198、最新 B `fea24c5aed33a3e857651bf3260d3ec3e5c18b73` 的实现和已有猜空策略均保留。**

132 唯一项由 26 族与 106 固定项构成。包内显式启用后默认 strict（11 属性卡），enhanced（22 卡）可选，没有真实模型分数证明胜者。完整原始源封包 58 文件的 manifest SHA-256 为 `30075daecabe811616ac2fe780036845eccaf303f449d91f93a823f31ebcb885`。公开交付将 17 份含继承实体示例的数组/族定义/Python 导出改为固定 160 引用及精确重建，其余源码与合同保留原字节；[SOURCE_CLOSURE](../../experiments/a_family_candidate_132_v2_r4_20261030/SOURCE_CLOSURE.json)覆盖原 57 项源文件。[LOAD](../../experiments/a_family_candidate_132_v2_r4_20261030/LOAD.md)给出可复现命令。

|配对|模板数组 SHA-256|r4 引擎 SHA-256|
|---|---|---|
|strict|`a3f6a0d3ea12be6555025e37e4a0189f259a2da6766124160f90b94fcce88ef3`|`99d15b6995aa8a731354b02811c3613fc4c92c4a9c1d3a900f8ae393d7814802`|
|enhanced|`897798c3ee26bfc6fba2b625b6e7e820146ac49db7d2fb299b68a5d15701466b`|`dbaf4381493907a8f3b19d14344700884f8b9c1d9703f573c4385b216d4fcedc`|

## 已验范围

独立收据随包交付：每版 1166 离线控制中，1016 支持例误空 0，内含 161 个复合完整性例；150 负例三入口均为空。compact 数组另有检索实例状态等价证明，未冒称重新运行全部私有控制。普通原 132 的 603×4 排名向量 2412 全同；历史 200 模板实现为 2368/2412 相同、44 属性通道差异，不是 200 题端到端成绩。

发布构建器另外实际核验精确数组/导出/族 JSON 重建、132 唯一 ID、400 主文档、11/22 属性卡、12 prepare 模块哈希和 F03 恢复 7 示例/6 view 参数合同。没有模型、服务、评分器或原生执行调用。

## B 接入待办

- 新增独立 132 manifest/预检与 flags/source 冻结，禁止放宽旧 160/170/180 哈希或复制旧 matcher 覆盖新 main。
- 选择提示和填参提示两处调用 `prompt_metadata.prompt_item`。F03 compact 的恢复仅引用同对象文字/schema；未接 adapter 时没有示例，不能称提示无损。
- 保留 r4 的 `profile_ids`/`obligation_spans` 及原文 Unicode 字符跨度。完整义务需 `top_k=None`；同族多 view、多实体及范围各自抽参/prepare，不能只按 family ID 去重。
- `handles_item=True` 才走 12 变更族的完整原文 prepare；False 继续旧路由（14 旧族＋106 固定项）。保留精调、精确列序、JOIN/DISTINCT/排序/API 约束和依赖，不把 materialize 当完整原文 prepare。
- **保留最新 B 的 `query→_query` 包装。** 默认拒答/显式错误可能变为 `empty_answer_fallback` 且 `error=None`。读取猜测标记和原始原因，将猜空单列，不能据此认定真实空、COUNT=0 或执行成功。
- 原三处“仅依次输出”、礼貌包装、F02 natural_views 选择卡、schema/view/dispatch、多义务组合与 SDK/分页/缺列状态须由 B 集成验证。既有非检索补丁没有自动采用。

## 保留限制

F03 紧凑 UTF-8 strict3549B/enhanced3986B；这不证明 ASCII/默认空格等序列化也小于 4KB。深7/外层数组8及官方计算口径、COUNT业务空占位与参考、原生执行/分页完整性仍未决。本轮未切生产、未启 stage2、未混 Issue3、未修改评估器，不能把旧 180/160 成绩归入132。B 的新模型联调须另锁源码、配置、数据范围和预算。
