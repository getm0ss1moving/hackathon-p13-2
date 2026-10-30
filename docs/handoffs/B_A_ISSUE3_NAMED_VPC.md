# A→B：具名 VPC 子网、EIP 独立计数候选

**独立默认关闭包；不改已交next、132、B或默认198，不关闭issue。** [候选主包](../../experiments/issue3_named_vpc_20261030/README.md)与[实际源码/合同闭包](../../experiments/issue3_named_vpc_20261030/SOURCE_CLOSURE.json)给出公开路径和哈希；本候选仅双计数，不含057或VM层级。

本包补齐“精确 VPC 名称，区域可选”的子网与 EIP 两个独立计数。它复用既有 network 的关系链和 network_hierarchy 的具名/无区域选择，不接管 VM 层级查询。该能力已有隔离实现，并经15项最小独立合成复验通过；允许默认关闭源码/合同交B，真实B接入和业务完整验收仍未完成。原 132 与运行时模板数未变；独立新增族预计 +1，若经统一族审查扩展原 network profile，则可为 0，本包不替 B 决定最终 N。

源码位于[独立候选candidate.py](../../experiments/issue3_named_vpc_20261030/candidate.py)，[CONTRACT.json](../../experiments/issue3_named_vpc_20261030/CONTRACT.json)保留受审原字节。公开MANIFEST绑定本次实际交付；原11项owner清单和SOURCE_LOCK仍在原归档，其指纹保存在SOURCE_PROVENANCE，不冒充本最小包。源码没有题号、问题原文、实体名称或答案路由，公开验证全部使用合成对象。

## 参数和变体

```json
{
  "profile": "named_vpc_subnet_eip_counts",
  "filters": {"name": "任意精确 VPC 名称"},
  "required_filters": ["name"],
  "same_name_policy": "all_matching_parent_ids"
}
```

四个顶层字段都必需，拒绝额外字段。`filters.name` 是非空、非全空白的 UTF-8 字符串，精确匹配，不修剪非空值，不支持子串匹配。可选的 `filters.logicalRegionName` 同样是精确字符串；若提供，`required_filters` 必须同时列出它，不能隐式丢弃作用域。`required_filters` 必须是无重复的完整过滤键列表。不存在默认区域。

`same_name_policy` 必须选择 `all_matching_parent_ids` 或 `reject_multiple_parent_ids`。前者逐 VPC.id 保留所有同名身份及其区域，后者遇到两个以上匹配身份即拒绝。单个身份正常返回，零身份返回真空列表。原题若没有消歧依据，B 应保留这个歧义，不能擅自选第一条或换实体。

## 输出与关联

每个匹配的 VPC.id 一行，列按下列顺序输出：

| 列 | 类型 | 含义 |
|---|---|---|
| vpc_id | string | ROUTER.id，输出身份 |
| vpc_name | string | 精确匹配的名称 |
| logical_region_name | string | 身份所属区域 |
| resolved_subnet_count | integer | 去重引用且可解析的子网 ID 数 |
| referenced_subnet_count | integer | 非空子网引用 ID 去重数 |
| unresolved_subnet_count | integer | 引用数减已解析数；不得当作已解析对象 |
| known_eip_count | integer | 已证父关系下的 EIP.id 去重数；未知归属另列诊断 |

子网链为同区域 `ROUTER.nativeId=PORT.devNativeId`，接 `PORT.id=R_PORT_IN_SUBNET.portId`，再按 `subnetId=SUBNET.id` 和父区域解析。完整父目录中 `(logicalRegionName,nativeId)` 必须唯一；跨区域相同 nativeId 可以存在，同区域重复则拒绝。EIP 链独立使用 `FLOATING_IPS.routerId=ROUTER.id` 和同区域；不能改成 nativeId。子网引用先按 `(VPC.id,subnetId)` 去重，EIP 先按父身份独立聚合，再 LEFT JOIN 父对象。两子集合没有直接 JOIN，子网数和 EIP 数不会互相乘倍。

一父多端口、多端口重复引用同一子网、多 EIP 均支持。不同关系对象 ID 指向同一个业务边可去重；同一个 CI 内重复对象 ID（即便行内容一致）不能去重掩盖缺失页，直接拒绝。所有对象 ID 必须是非全空白字符串；非空身份原值保留。空/空白/NULL 的可空外键归一为 NULL，保留未知诊断。

## 作用域、可信输入和 B 接入

`build(params)` 产生 5 个固定资源请求和一段 SQL。为保持父身份消歧，名称只在 SQL 选父，不用于缩小父目录 API。无区域时 5 个 API 都无区域谓词；有区域时 ROUTER/PORT/SUBNET/FLOATING_IPS 请求和父 SQL 使用该区域。关系表没有已证区域字段，始终用全局关系请求，再沿受校验的端口键传播区域。

输入资源及列：

- ROUTER：id、name、nativeId、logicalRegionName。
- PORT：id、devNativeId、logicalRegionName。
- R_PORT_IN_SUBNET：id、portId、subnetId。
- SUBNET：id、logicalRegionName。
- FLOATING_IPS：id、routerId、logicalRegionName。

逐资源 receipt 结构为 `{ok:true, request:build.api_call中的对应对象, schema:[列名], schema_verified:true, pages:[...]}`。逐页包含 `ok:true,pageNo,pageSize,totalNum,totalPageNo,objList`；页码从 1 连续、页大小和总数稳定、每页长度精确、完整页数正确。0 总量也需成功空页及已验证 schema，且 `totalPageNo` 可为 0 或 1。资源和页级的已声明 success/error/HTTP 状态不得与成功矛盾，HTTP 只接受非 bool 的整数 2xx。失败、缺页、缺 schema、重叠 ID、错区域、类型不符均拒绝，不能转为零。

schema 必须包含所有约定列；非空行必须包含它们，只有原生 EIP 可空 `routerId` 的逐行缺失允许投影为 NULL 并计入未知。资源目录中的未知区域拒绝。PORT devNativeId、关系 portId/subnetId、EIP routerId 的空值不伪造关系。原生其他多余列投影掉。

B 集成顺序：

1. 固定源码 SHA，校验结构化参数和必须保留的过滤条件，调用 `build`。复用旧 network 的 region+VDC schema 不能表达此 profile。
2. 在 B 的可信采集层获取当前完整目录；五路请求可独立完成，无跨步骤占位符。完整目录方案刻意避免把运行时依赖插入官方 executor。若 B 将其优化为跨步骤动态请求，须另行证明父目录消歧、每路覆盖、外部未知排除和当前执行命名空间绑定，不能直接声称等价。
3. 由可信采集层产生真实 receipt，调用 `prepare(params,receipts)`。不能让模型生成 `schema_verified` 或成功标志。标志、请求、哈希都是断言及本地一致性证据，本包不提供来源认证或原子快照证明。
4. 使用 prepare 返回的投影及 NULL 规范化，不能把原始 receipt 行直接塞进 SQL。纯本地复验可调用 `execute_prepared`，它会重新校验实际 receipt 证据并比较投影和诊断；修改版本标志或自报 verified 不能跳过检查。真实运行仍使用现有官方执行链，B 自己负责可信绑定及 typed-empty loader。
5. 保留结果与全部未知诊断。`known_local_graph_complete` 仅表示当前严格校验的已知本地关系图，没有认证现场数据或业务口径。部分图返回已知计数，但不能用它冒充完整总数。B 完成自身来源/覆盖/语义门禁后才可用于完整回答。
6. 检查展开后的传输长度及最终 B 请求边界；本包未修改 matcher/system、官方 executor/evaluator 或任何默认模板。

## 未知、真空与失败

零子对象的已知父对象保留，并返回四个数值 0。零匹配父对象返回空列表，诊断 `selected_parent_count=0`，没有占位 COUNT=1。

未知父名称影响名称选择完整性；未知父 nativeId 影响端口归属；未知端口归属、缺失端口的全局关系、选中端口上的未知子网、未解析子网、EIP 未知/未解析父都使 `known_local_graph_complete=false`。采用保守全目录门禁：一些未归属对象可能在选中父之外，但证据不足时不能自行排除。已解析的跨区域端口/子网或 EIP/父边直接拒绝，不能忽略后宣称完整。

成功且数据为空、查询选择为空、已知父无子对象、输入失败、已知部分图是不同状态，B 需分开处理。即便本地关系图完整，`full_business_acceptance` 与最终 B 请求验证仍未通过。

## 长度与深度

`build` 按 compact、sorted keys、`ensure_ascii=False` UTF-8 JSON 测量展开后的 `api_call+sql`；候选阈值 4096 字节，超过时标 `blocked_core_length`，保留原参数和 SQL 供诊断，禁止发送超限 core 或截断。更长的合法标识符并未被宣告业务无效，B 可验证新的参数绑定/紧凑表示。元数据、prepare 的原始当前证据、最终 B envelope 不包含在该 core 测量内；若进入模型请求，B 必须重新测量全部实际内容。

`LENGTH_BOUNDARIES.json` 分别记录静态占位骨架、普通展开示例、长合法示例、整个 build 返回值的长度；深度分字典层数和包含列表的容器层数，根字典为 1。正式 4KB 或深度算法尚未确认，不把候选测量当作官方门禁通过。

## 验证与剩余门禁

原owner归档的`VALIDATION.json`记录owner合成测试，本最小包未纳入其27项套件，也未重跑或计数。公开复放命令为`python3 -B scripts/verify_a_issue3_named_vpc_synthetic.py --output /tmp/a-named-vpc-check-new`，从仓库根运行，输出须全新且在仓库外；仅依赖标准库与内存SQLite。它复放15项合成场景和26嵌套状态子项，源完整性仅核本次交付闭包，不冒称完整owner归档复验，不与独立验收相加。

已覆盖独立计数、防扇出、跨区域同名身份、显式消歧、精确实体替换、SQL 引号、同业务边幂等、未知归属、未知外键、跨区冲突、重复 ID、缺键/空白/NULL、HTTP503+okTrue、分页失败、typed-empty、prepared 证据重校验、超长合法名称不截断。

现场完整 PORT 快照已知存在两个重复 ID 键，本候选沿用严格拒绝规则，没有按实际 ID 放行或改原数据。EIP routerId 空缺等现场数据仍需真实采集诊断。本包未运行原生 SQL、模型、业务 API、官方评估、全 200 或封存反馈。057 多值地址 token 匹配和全量 EIP→VM 能力不在本包；298 冻结包保持不变。

## 独立最小复验收据

本轮15/15独立场景通过，26个HTTP/缺schema/缺页状态子例未叠加，owner27方法未执行或计入。已核ZIP、checkpoint、11个manifest条目，12个文件与实际仓库源一致，源未改。

重点已独立验证：无默认region、同名all/reject政策、两源独立聚合防扇出、零子项父/零匹配父/真空、错scope与跨region边、EIP routerId角色、未知/未解析诊断、重复PORT拒绝、prepared实际证据重验和新引号实体。

本profile无跨步骤依赖，五路完整目录是当前可审方案；B若改成按上步ID动态拉子资源，要另证父目录唯一性、覆盖、全局未知排除及当前执行绑定，不能称本收据已覆盖。单region请求配global关系表可能因目录外关系无法归属而保守partial，这不是完整计数通过证据。

PORT canonical源路径、EIP未知归属、可信实际回执/schema/pages、typed-empty/验证投影、完整原文义务、最终B外壳/正式深度和业务权威门禁均保留。057 token匹配与完整EIP→VM不在此包。此交付单独保存，不修改已交next包；实际运行N变化0，无默认启用。历史checkpoint的额度停止阈值已被用户后续取消，本收据不继承它。

## 本次交付与B状态提醒

前一next包记录“192双count未含”属于当时冻结范围，本独立增量现交付其A侧双计数合同；B现场与完整业务仍未完成，旧next文件不改写，057仍未纳入。保留B的query→_query猜空包装并检查guess/原始失败原因，不能把empty_answer_fallback或error=None当真实空、COUNT成功或业务门禁通过。
