# A→B：管理 VM 隔离通用明细候选

**单独默认关闭，未修改bootable、132、默认198、B或官方组件，不关闭issue。** [候选主包](../../experiments/issue3_management_vm_20261030/README.md)和[实际源码/合同闭包](../../experiments/issue3_management_vm_20261030/SOURCE_CLOSURE.json)提供可访问路径及哈希；源码/合同保留原字节，完整业务和B接入尚未通过。

**已实现完整字段义务的候选与纯本地验证；未注册/启用，当前源仍不能保证原问题的完整业务答案。** 本轮仅写本新目录，未改已验 bootable-fix、共享 132、B 或官方组件；具名VPC双计数已另包交付，不混入本候选。

发布基线更新：保留B `b00e85a`已发布的132 strict＋r4根入口与实现；文中198为A冻结阶段历史默认，不回切、不覆盖。

## 先给证据与缺口

逐 SHA256 核对冻结文件，只聚合九个相关 CI 的字段类型、ID/外键匹配和覆盖，没有输出对象、名称、IP 或业务行，也未跑原生业务 SQL。原owner归档保留SOURCE_AUDIT.json及audit_source.py；本最小包只保留必要聚合来源指纹，不纳入原生文件或执行审计脚本。

- 2909 台 VM 的 management 全为 JSON bool，true 896、false 2013。**这是全局源统计，不是 B 所报告某区域 233 行的复测。** API 必须用 JSON bool true；不能换字符串来产生空结果。
- VM.flavorId→FLAVOR.id、挂载 vmId→VM.id、部署 node.vmId→VM.id 及后续部署服务链均有文档/原组件依据和实际键兼容路径。九 CI 的 id 当前均唯一。管理 VM 中 873 个规格可解析、23 个未解，738 台可沿部署链找到至少一个云服务。
- 896 台管理 VM 中 607 台缺 VDC ID/名称；privateIps 与 ipAddress 各有 3 个空值。ipAddress 有 115 个含分号的文本值，故不能默默取第一个地址，也不能把两个 IP 字段或部署 mgmtIp 互相补空。
- 管理 VM 的挂载记录有 1511 个卷目标未解析；全挂载集合则有 2007 条记录的 volumeId 未解析。两个口径人口不同，不能混加。125 条部署实例找不到节点；管理 VM 可达服务链有 25 条未解路径。未知关系不能被 INNER JOIN 丢掉后宣称完整。
- IP 的业务角色/多值编码、容量物理单位/换算、服务部署关联与更宽“所有权”的等价性仍未得到新权威定义。VDC 缺失不能借租户、服务或挂载卷推定。

据此实施的是**文档定义的部署关联、原生 IP/规格字段及挂载卷容量原值**。这些足以输出参数化已知完整字段与缺失诊断，不能补造源中缺失事实。full_answer_certified 固定 false；declared_values_complete 只表示所给完整投影快照中已请求字段及关系可解，不认证线上来源、单位或实际 B 采用。

## 候选合同

[candidate.py](../../experiments/issue3_management_vm_20261030/candidate.py)仅依赖标准库；[CONTRACT.json](../../experiments/issue3_management_vm_20261030/CONTRACT.json)含闭合参数schema、九CI必需schema、接入/失败政策和输出粒度。

```json
{"view":"management_vm_service_flavor_volume_rows","logicalRegionName":"Example-R","ip_role":"both_raw","capacity_mode":"per_volume_raw_and_numeric_summary"}
```

合成问句示例：查询区域“Example-R”下各VDC的管理虚拟机名称、IP、所属云服务、规格和挂载云硬盘容量。

- `prepare_candidate(full_question,item,params,diagnostics)` 核完整原文、选中 family、region 和名称/IP/云服务/规格/挂载容量五项义务；额外资源/动作、错区域/角色和缺字段拒绝。当前普通 IP 问法强制 both_raw；明确“私网IP”或“原生IP地址”才分别允许指定对应角色，避免模型猜选择。
- `build(params)` 生成九个 GET 与 SQL。只有 VM 请求带显式 region 和 management JSON bool true，服务链等取完整上下文；不为不存在 region 的服务 CI 拼条件。卷关系走 `/relations/`，其它走 `/instances/`。
- `prepare/preflight(params,receipts)` 校验 B 可信宿主绑定的请求、类型、schema、完整页、ID，再形成 **A_MANAGEMENT_VM_DETAILS** 投影。缺/失败/截断/重复身份/HTTP 矛盾拒绝；schema 已获证的稀疏可选字段可投影 NULL 并保留诊断。不能只以字段 union 推定每行有值。
- SQL **必须只执行在 prepare 输出表上**，不复制到原始 CI 表直接运行。派生 management=1 是此本地投影的显式编码；API 原生值仍是 bool，未改原生响应或官方装载器。
- 每 VM.id 一行，source VDC ID/名称、两种原生 IP、规格身份/原字段均保留。服务按 CloudService.id 去重成 services_json；卷按 (VM.id,volume引用) 去重成 mounted_volumes_json。相同名字不同 ID 保留；无 JSON SQL 函数依赖，也不做服务×卷展开。
- 已知容量按原字段数值精确整数刻度相加，支持非负普通十进制、最多 12 位小数和 64 字符；原值仍逐卷保留。未知/非法/过细精度不舍入或转 0，complete_size_sum_native_numbers 为 NULL；服务行数不会放大容量，也不用 SUM(DISTINCT size)。该数字不宣称 GB/GiB，更不是 VDC 独占容量。
- 缺 VDC、缺规格、未解卷与缺 IP 不丢父 VM。未解卷保留引用 ID；未知服务保留已知服务与不完整状态。没有已知服务不等于证明没有服务。未知部署节点归属/孤立实例使服务完整标志保守为 false；未知挂载 owner 使完整容量数字为 NULL。
- 同 VM 跨关系重复记录按业务 pair 去重；同 CI 重复 id 则拒绝。已解析规格/卷的 region 与父 VM 不符或未知则拒绝，不以名称或 IP 回退连接。

## B 最小接入与限制

最小源码/合同：candidate.py、CONTRACT.json、此 HANDOFF 与固定 MANIFEST。候选可在隔离适配器接入 build → 原文 prepare_candidate → 真实 fetch → preflight → typed prepared table → SQL。`execute_local` 仅是合成验证器，不是官方 executor 替代上线授权。

B 必须验证真实请求 provenance、完整分页/schema 和实际投影加载，不能让模型填写 receipt。当前候选的 receipt 字段是宿主断言，不是认证器；跨 CI 版本一致性/原子快照仍属 B 的来源门禁。

正常合成参数的 compact API+SQL core 为 **1757 字节**；完整本地 metadata 和最终 B 外壳是不同边界。长实体会输出 blocked_core_length，不能截断实体/SQL 或把局部字节检查当正式 4KB/深度通过。新 family 的 registry/卡/选择参数与 unified_prepare 适配尚未做，不能直接覆盖默认 132；若将来扩原族净增可能为 0，独立注册可能为 1，本轮实际增量 0。

字段组合已实现，但以下事项仍阻止宣布原题完全解决：现场 VDC/规格/服务/卷缺失；IP/容量单位和服务角色的业务核定；B 的真实来源、最终外壳和独立接入验收。当前未在原生记录上执行本候选，未声称得到 B 参考结果。

## 验证

原owner归档的test_candidate.py报告**92/92 owner局部合成检查通过**，本最小包未纳入或重跑该套件，不是本轮独立验收或新业务分数。公开命令为`python3 -B scripts/verify_a_issue3_management_vm_synthetic.py --output /tmp/a-management-vm-check-new`，从仓库根运行，输出须全新且在仓库外，仅需标准库与内存SQLite。覆盖两卷×三服务不放大、同容量不同卷、共享卷、同名异 ID、0.1+0.2 精确和、原生布尔与 typed request 绑定、错 scope/角色、额外义务、无父/全空、稀疏 schema、缺关系、未知引用、异常容量、HTTP 六类别名矛盾、分页/重复/UTF-8、SQL 引号及长实体。

原owner归档的MATERIALIZED_SYNTHETIC.json和VALIDATION.json分别保留物化合成图及检查明细；本最小交付不冒称含该全归档，公开脚本自建合成fixture，结果写仓库外。源审计不加入合成通过数，未跑原生业务 SQL、服务/模型、200/旧 50 答案或官方评分。本profile现已通过17项最小独立合成复验，owner92未运行或计入；默认关闭源码可交B，真实接入及完整业务仍未通过。额度阈值取消按最新指令执行，本目录不设置额度停止条件。

## 最小独立交接补充

独立17/17通过，HTTP/缺schema/缺载荷矩阵20子例未叠加，bootable没有导入或重测。服务×卷不扇出、同容量不同卷、共享卷、NULL/缺引用、原生bool类型、region/角色、完整原文义务、新合法实体等控制已验证。部署FK按官方模型字段核对，不把实际键兼容统计升级成所有权或全量覆盖证明。

当前闭集只按显式region筛管理VM，VDC字段用于来源身份/展示；没有命名VDC过滤或VDC总容量汇总参数。SQL只消费typed A_MANAGEMENT_VM_DETAILS，management=1是准备编码，API仍bool true。native raw IP字符串不是已定义codec后的IP对象列表，未取第一个、未用其他字段补空。

最小源码/合同为candidate.py与CONTRACT.json；本文档可另存docs/handoffs/B_A_ISSUE3_MANAGEMENT_VM.md。本reviewed子集清单不替换原MANIFEST：原清单列9文件，如交原manifest必须带全文件。当前源码交接不切默认，不自动注册family，不修改132；B来源/typed-empty/投影/最终封装、IP/单位/服务角色政策以及现场缺失全部保留。

## 本次公开复放与B状态提醒

发布者仅复放同一17项纯合成场景（20健康/schema子项嵌套），地址改用文档网段、正常长度样例用合成Example-R。源码审计缩为实际公开闭包，不重跑owner92、bootable、原生统计或B链，不与原独立17相加。保留B的query→_query包装和guess/原始失败证据，不能将empty_answer_fallback或error=None当真实空、完整服务/容量或业务成功。
