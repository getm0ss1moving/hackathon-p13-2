# A 五项交接与根因修复（2026-10-29）

本次完成 A 范围内有证据的参数筛选修复、19 模板参数合同、原生失败复现及历史 199 候选生成方法。五项业务能力尚未全部修好，以下逐项列出限制和 B 待办。结构化结果见 [A_VALIDATION_SUMMARY.json](A_VALIDATION_SUMMARY.json) 的 `current_handoff`；`historical_handoff` 保留早期统计，不能当作当前状态。

发布基底 `e063f6a90a3dd895f767d06f9efdd876c894097d`；A 模板修复提交 `e9d76e456c17215525300869f198c61657a559a9`。生产保持 **200 模板、400 索引文档**，沿用已验收词频缓存检索器。199 精简及描述索引实验未替换生产。本次没有新增 B 运行时改动，没有改评分器、执行器、服务、数据或用例。

## 本轮新增：rb_071 稀疏字段 SQL 修复

后续代码提交 `3c6e1227f5f3e92e3158d156b6deed13a66d6495` 只改 rb_071.sql，其他 199 条模板、API 条件与检索器不变。当前模板 SHA256：`34ac7400c905c9da3657038f9f7bc40a80f07e6ba43ef70eca6e4ca3197d1a35`。

原始 d79 实现也使用相同旧 SQL。未筛选的 45 条记录列并集掩盖了缺列；筛选后的 6 条记录完全缺 hostName/hostIpAddress，原执行器将列错误吞成空结果。以下纯 SQL 保留原字段及三列输出合同，真正缺值为 NULL，空输入不产生假资源行：

```sql
SELECT x.hostName AS name, x.hostIpAddress AS ip_address, x.hostType AS type
FROM (SELECT *, NULL AS hostName, NULL AS hostIpAddress,
             NULL AS hostType, NULL AS _empty FROM SYS_X86Server) AS x
WHERE x._empty IS NULL
```

正常字段优先保留，NULL 别名仅提供缺列结构；_empty 是原加载器的保留空表占位列。没有生成业务资源或恢复未知数据，没有依赖双引号字符串回退、PRAGMA、额外 API 或运行时改写。资源 name 与 hostName、BMC ipAddress 与 hostIpAddress 在重叠样本均不相等，所以没有互相替代。

开发离线 14/14，独立离线 10/10，原 execute + 原服务独立 5/5：两区域返回 6/39 行，空范围 0 行，实际 ID 单键/多键 1/2 行；HTTP 均 200、过滤准确，独立直跑 SQL 无被吞列错。缺失单元仍为真实 NULL。模板保持 200 条。此结果修复假空 SQL 行为，不代表已知缺失的主机名/IP 已补出。

复现使用已有依赖环境，报告保存在仓库外且路径尚不存在：

```sh
python3 -B experiments/a_sparse_projection_check.py --repo . --offline-only --report ../a-local-evidence/sparse-offline.json
python3 -B experiments/a_sparse_projection_check.py --repo . --server-log ../a-local-evidence/service.log --report ../a-local-evidence/sparse-native.json
```

第二条须原本机 8080 服务和独占日志窗口。均无模型调用；各 native 用例采用新解释器的自然冷缓存。A 静态 SQL 仍无法区分已被底层吞掉的 HTTP 失败与真正空响应；B 的模型 SQL 精调也可能改掉该投影，完整模型流程尚未验证。[SQLite SELECT 文档](https://www.sqlite.org/lang_select.html) 说明投影、子查询和 NULL 结果的基础语义；此写法的缺列及占位行行为另有上述可执行回归。

## 本轮新增：关系缺证的根因与替代方案

对照原始实现后确认，rb_093 不是单纯漏了一个 JOIN：原模板已把不存在的 storagePoolId 用作后步依赖，SQL 又只给常量 N/A，并按 VDC 分组却选择单个实例名，不能证明实例级池归属。原参考与模板的一致性不构成业务正确证明。

本轮检查 63 类数据、存储相关字段及 74,366 个可解析 JSON 编码字段，没有发现数据库专用卷关系。186 条宿主挂载路径含 24 个启动卷、162 个非启动卷；每个可达节点仍有 6 或 7 个非启动卷，bootable=false 不等于数据库数据盘。12 个可达实例的宿主卷虽落在同一个规范池，也不能据此猜剩余 2 个实例。6 个缺失宿主的规范 ID 和原生 ID 仅在对应节点中出现；VM_NOVA、VM、S_VM、空 BMS 及挂载关系均无补齐记录。

可执行的替代方法分两种，均不静默替换现有能力：

1. **宿主挂载卷清单**：实例→节点→VM→挂载关系→卷→池，保留 instance/node/volume/pool 粒度和缺失项，已证静态覆盖 12/14。它回答宿主卷池清单，不回答专用数据库盘。B 必须先防止空依赖扩大请求，才能集成该六步候选。
2. **数据库专用卷查询**：需要权威 instance/node→volume_id 关系、system/data/log/temp 等用途及有效期，再以 VOLUME.id、attachBackendId 精确连接。若通过来宾机，需目录/挂载点→块设备→规范卷 ID；容量、类型、卷名和挂载设备号不能替代归属关系。

当前未改 rb_093 的业务含义，也未把未知标成无池或本地盘。重新开放完整修复所需的最小材料：一组明确标注启动盘和多个非启动用途的实例；一个非数据库的非启动卷反例；多卷/多池输出规范；一个缺失宿主的实际记录或权威不适用规则。详细已排除路径及候选 SQL 见 JSON `root_cause_followup.rb093`。这是明确的数据事实阻塞，不是待猜一个字段名。

## 本轮新增：五项映射的具体可行路径

| 模板 | 新证据／方法 | 当前采用边界 |
|---|---|---|
| rb_078 | AZONE 按 logicalRegionName 查唯一 logicalRegionId，再过滤 S_CloudService.logicalRegionId | 本机原生两组分别 110/34 行，集合与多重性匹配；B 须接入解析和失败停止，生产模板未改 |
| rb_079 | 同样按规范区域 ID 过滤 S_DeployNode | 本机原生 928/152 行匹配，覆盖 1080/1086；6 条缺区域 ID，另有 21 条区域/AZ 冲突，不自动猜归属 |
| rb_151 | 区域上下文 + AZONE.nativeId/deviceName → NODE.azCode → NODE.ref_instanceId → INSTANCE.id | 离线 30/30 节点、14/14 实例；24 个有 VM 的节点 AZ ID 一致。仍需确认名称命名空间、多 AZ 的任一/全部/主节点语义，并保留 VDC/区域过滤 |
| rb_186 / rb_193 | listener/pool/member 关系可达；后端 VM AZ 仅覆盖 73/728 ELB，VIP 端口缺 AZ | 后端 AZ 不能冒充 ELB 部署 AZ，无合法完整替代路径，保持阻塞 |

区域接口实验实际 7 次原服务 HTTP，全部 200、无无条件请求。两组正常解析后才访问目标 CI；合成未知区域首阶段返回空，第二阶段 **0 请求**。这证明建议接口的本机可行性；它是隔离实验的显式停止，**没有把这份逻辑接入 B 或修好生产运行时**。

AZ 名称有重要歧义：AZONE.name 与用户常见 azoneName 不总相同；本机 HOST/VM 的 azoneName 与对应 AZONE.deviceName/nativeId 一致，全局标签又跨逻辑区域重名。必须携带区域上下文并确认别名规范，不能以同名字段直接替换。最小文档未明确所有这些外键和命名空间，数据一致性证据不等于全局规范保证。

B 的最小接口为：`resolve_location(kind, source_value, logical_region_context)`，返回 `resolved/unknown/ambiguous/incomplete/error`、规范 ID、字段命名空间和覆盖限制；仅验证后的 resolved 进入目标请求，其余停止并澄清。还需每一后步的空依赖、类型及 HTTP/SQL 结果校验。固定执行器只看紧邻前步且不会自动短路，故不能直接把候选多步 API 拼进生产模板。

接口复现脚本只针对当前冻结数据做有界实验，不是生产适配层；先保持原服务及独占日志窗口：

```sh
python3 -B experiments/a_location_resolution_probe.py --repo . --server-log ../a-local-evidence/service.log --report ../a-local-evidence/location-probe.json
```

不调用模型、最多 10 次 HTTP，当前实际 7 次。未知域停止也必须看真实请求数，而非只看空输出。源码未硬编码具体区域名称/ID，原始值只在本机内存；生成报告仅聚合。详细覆盖及已排除路径见 JSON `root_cause_followup.mappings`。

## 1. 参数合同与缺失绑定

**A 已完成并验证：**19 模板共 30 个语义参数槽，按已审计意图判定 27 个必需、3 个未知，未确认可任意省略的业务参数。“必需”仅针对该筛选意图，不代表所有未来问题必须提供同样条件。API 允许不传 condition，不代表用户要求的过滤条件可以删除。字段级合同和占位符见 JSON `parameter_contracts`。

| 模板 | 已审计意图中的必需参数 | 未知或限制 |
|---|---|---|
| rb_038 | tenantName、logicalRegionName、azoneName | tenantName 来源与参考值冲突，未擅自选值 |
| rb_041 | logicalRegionName | status 需上下文确认 |
| rb_052 | — | logicalRegionName 需上下文确认 |
| rb_062 | logicalRegionName、management | 绑定已存在，值仍需正确提取 |
| rb_071 | logicalRegionName | 新增同名字段绑定；另有稀疏输出失败 |
| rb_078 | logicalRegionName | S_CloudService 无该名称字段，映射未证明 |
| rb_079 | logicalRegionName | S_DeployNode 无该名称字段，映射未证明 |
| rb_084 | bootable | 绑定已存在，不能删除合法 false |
| rb_085 | logicalRegionName、azoneName、bootable | 绑定已存在 |
| rb_110 | shared | 绑定已存在 |
| rb_111 | shared、providerNetworkType | 绑定已存在 |
| rb_112 | logicalRegionName、shared | 绑定已存在 |
| rb_128 | — | name 所指对象需上下文确认 |
| rb_151 | vdcName、logicalRegionName、azoneName | GAUSSDB_INSTANCE 无 azoneName，映射未证明 |
| rb_175 | logicalRegionName、management | 绑定已存在 |
| rb_177 | logicalRegionName | VOLUME、STORAGE_POOL 两步新增绑定 |
| rb_183 | logicalRegionName | VOLUME 新增绑定 |
| rb_186 | azoneName | ELB 无该字段，关联映射未证明 |
| rb_193 | azoneName | 同上，相关资源也未证明替代关系 |

前轮 8 个缺失绑定中，**修复 3 个语义槽、4 条 API 条件**：rb_071 的 S_X86Server、rb_177 的 VOLUME 和 STORAGE_POOL、rb_183 的 VOLUME，均绑定 `{{logicalRegionName}}`。当时其余 197 条、原 SQL、示例、默认值、资源和 ID 顺序未变。本轮仅额外修 rb_071.sql，未新增实体默认值。

前一轮 826525a 的独立原生验证 6 次，在两组原数据范围下确认筛选字段、值和操作符，实际实例 HTTP 请求 8 次、均为 200：**筛选绑定 6/6 PASS**。当时固定 SQL 输出可验证 5/6；rb_071 另一范围的 6 条源记录缺 `SYS_X86Server.hostName`，原执行器吞列错后返回空，因此当时该输出能力 **FAIL**；本轮 SQL 修复及新回归见上节，原失败证据保留。不能用两份空输出相等冒充通过。两组范围可能是别名或克隆数据，不构成未知地区泛化证据。rb_177 原 SQL 未输出池明细、rb_183 原 SQL 未限定最多租户，这两条仍只修筛选，不宣称整体题意已修好。

**限制：**前轮未证的 5 个缺绑定，本轮已有上节所列候选路径；尚未作为生产绑定采用。rb_078/079 的 logicalRegionId、regionId 不能直接填名称；rb_151/186/193 不能以业务区或逻辑区冒充可用区。三个未知槽、rb_038 值冲突及 API 正式 nullable/required 定义仍待澄清。

**B 需要做：**按用户语义及上下文校验来源；缺键、None、空串不能静默删除必需条件，字符串 `"null"` 也不等于空值。合法布尔 false、数值 0 按类型保留，名称字段中的 False/0 则应拒绝。当前纯填参回归中缺键、None、空串、False、0 都会被清条件，说明绑定本身不替代运行时校验。还需检查必要输出列及被吞的 SQL 错误；未知关系先澄清或安全拒答，不能猜字段。

**验收：**缺键/null/空串/合法 False/0 与正常值分别测试；检查真实 HTTP 条件，分开报告筛选正确、SQL 输出正确和模型得分。安全拒答不能算业务能力完整修复。

## 2. rb_021 / rb_041 空前步

**A 已完成并验证：**新解释器、自然冷缓存、原服务及原 execute 下，合成不存在条件使首步各返回 0 条；之后仍各发 **1 次无条件 VM_NOVA 请求并读取 2,909 条**。目标为后续请求 0 次，当前 **FAIL：复现完成，运行时未修复**。error 为空不代表安全。

**限制：**固定执行器省略空依赖条件，静态模板没有已证实的原生短路表达。B 目录默认关闭的依赖验证候选不代表根生产路径已保护。

**B 需要做：**在官方允许的编排边界中，发送后步前检查空前步、缺连接键和请求失败。可以明确拒答，但不能伪称完整 SQL 已执行；区分合法空结果与依赖不明。不得修改固定执行器或注入结果。

**验收：**空前步、缺键和 HTTP 失败时后续真实请求均为 0；正常单键、多键不退化；拒答与空结果评分单列。复现命令见后文。

## 3. rb_093 数据库存储池关联

**A 已完成并验证：**14 条 GAUSSDB_INSTANCE 均没有 storagePoolId。实际部分链为：

```text
GAUSSDB_INSTANCE.id = GAUSSDB_NODE.ref_instanceId
GAUSSDB_NODE.ref_vmbmsId = VM_NOVA.id
VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId
R_VOLUME_MOUNTON_VM.volumeId = VOLUME.id
VOLUME.attachBackendId = STORAGE_POOL.id
```

覆盖 12/14 实例，形成 186 条完整挂载路径；6 个节点的 VM 引用不匹配，BMS 数据为空。所用主键在检查数据中唯一，但跨表有缺失和一对多。resourcePoolId 直接匹配 STORAGE_POOL.id 无命中；共享 resourcePoolId 又可命中 3 个池，不能当唯一键。

**尚未解决：**该链包含系统盘，只证明宿主 VM 的挂载卷，**不证明数据库专用数据盘归属**。没有可靠依据把 rb_093 改成完整正确的数据库池查询，本次未猜造关系。历史固定选择 5 分不证明关联正确。

**B 需要做：**得到权威“数据库实例／节点→数据卷”关系及缺失节点语义前，禁止按不存在字段或猜测键执行；明确反馈信息缺口。取得关系后与 A 对齐 API/SQL，C 再回归。

**验收：**检查业务含义、唯一性、一对多、缺失及系统盘/数据盘区分。12/14 宿主卷可达不能写成 14/14 数据库数据盘完整支持。

## 4. 历史 199 模板候选

**A 已完成并验证：**历史基底 `5755b93435270a01d0df96c9faf777da60217a40` 的模板字节，与公开初始提交 `d79c3166ef81ed0c809f8233ce1b1ebd40c9e0ea` 相同。[生成脚本](experiments/a_199_candidate.py) 显式读取 Git 对象，只删除 rb_087、保留 rb_086，验证其余 199 项字段和顺序不变，不回退到当前工作区内容。

- 基底模板 SHA256：`cbd114635009d7a621b997810d12b874bcc1a672409908c497086b833a8e499b`
- 199 JSON SHA256：`7aa441b426f3d5e1ae3160cb347285b70be4240337231fc662d12ce73f2a55a8`
- 实际索引文档 **398**；旧聚合中的 400 误沿用基线元数据，原记录保留并标明纠正。

**限制：**旧检索运行没有锁定输入 JSON 哈希。现可复现候选产物，不等于认证旧整轮实验完全复现。本次参数修复后模板与该历史基底不同，脚本故意读取旧 Git 对象。生成 JSON 含本地模板数据，应留仓库外，不上传。

**B 需要做：**继续使用 200 模板。199 未获完整真实模型配对验收，不能按数量收益自动采用，也不按原题 ID 硬路由。

**验收／命令：**仓库根目录用已有 Python 运行，无网络和模型调用；输出必须在仓库外且尚不存在。

```sh
python3 -B experiments/a_199_candidate.py --repo . --base-commit d79c3166ef81ed0c809f8233ce1b1ebd40c9e0ea --output ../a-local-evidence/candidate199.json
```

本次退出码 0：200→199、仅删 rb_087、199 项不变、398 文档及上述 SHA256 均一致。

## 5. rb_126 超长 GET / HTTP 414

**A 已完成并验证：**首步产生 1,814 个 ID；第二步 securityGroupId IN 和 direction equal 两个条件，经原方式编码产生 **80,249 字节绝对 URL**、80,228 字节请求目标、80,243 字节请求行，超过服务标准库 65,536 字节限制，真实返回 **414**。

环境为 Python 3.11.16、requests 2.32.5、原本机 8080 HTTP 服务，无生效代理，未改 TLS 设置。完整原 execute 观察到 `[200,414,200,200,200,200,200,200]`，error 仍为空；固定 SDK 可给 5 分，因为请求/JSON 错误被吞且原 SQL 没消费 SECURITY_GROUP_RULE。高分不能证明步骤成功或规则维度语义正确。历史调用走过真实执行器，但未记逐步线上 HTTP 状态，不能补称当时全部 200。

**尚未解决：**没有已验收分批组合器。A 不能为绕过错误删除业务所需步骤，也不能无依据将 GET 改 POST、改服务上限或固定执行器。

**B 需要做：**先确认规则维度目标 SQL，再按官方允许多次完整 API 设计有界分批：保留每批所有筛选、检查状态、并集合并、按稳定键去重，再关联和聚合，并计总耗时。不能直接相加独立 COUNT。

**验收：**所有批次 HTTP 成功，无遗漏重复，关联聚合一致；与可处理的单批输入原生对照，跨批键和时间上限另测。当前 **FAIL：已复现，运行时未修复**。

## 原生复现命令及保护边界

[原生探针](experiments/a_native_boundary_probes.py) 不调用模型，不修改源码或缓存；每条命令在新解释器运行。先用已有依赖环境启动原 `output-server/data_server.py --host 127.0.0.1 --port 8080`，将 stdout/stderr 重定向至仓库外 `../a-local-evidence/service.log`，保持独占日志窗口。报告仅输出聚合，不保存 URL、实体值或原结果；本地参数可用 `--params-json` 提供，该文件不得提交。

```sh
python3 -B experiments/a_native_boundary_probes.py --repo . --mode empty-step --template-id rb_021 --empty-param fixedIpAddress --server-log ../a-local-evidence/service.log --report ../a-local-evidence/empty021.json
python3 -B experiments/a_native_boundary_probes.py --repo . --mode empty-step --template-id rb_041 --empty-param logicalRegionName --server-log ../a-local-evidence/service.log --report ../a-local-evidence/empty041.json
python3 -B experiments/a_native_boundary_probes.py --repo . --mode long-url --template-id rb_126 --server-log ../a-local-evidence/service.log --report ../a-local-evidence/long126.json
python3 -B experiments/a_native_boundary_probes.py --repo . --mode native --template-id rb_126 --server-log ../a-local-evidence/service.log --report ../a-local-evidence/native126.json
```

探针退出码 0 表示“成功记录复现”，不表示缺陷修好。模型选择、填参和 SQL 精调不在固定参数原生探针范围内。

上一轮模板 SHA256 `8f795734400eac0217ccde86c9bcd9bb38d9682b22fe833739d9695a54c32cd1`；本轮以顶部 34ac7400… 为准。检索器 SHA256 `1f00b14b1c7c24104a2695f1f33e94d223f59d0cd0277b766c2bb6d8a3135705`。236 个保护文件在原项目和交付副本均与基线一致；评分器 c7bc000d…、执行器 4febd193… 原样保留。

## 已有评分、实验材料和下一步

以下为不同冻结版本的原 SDK 本地诊断，不能归给本次参数修复，也不能混成完整配对。

| 版本 | 实际运行 | 原始白盒分 |
|---|---|---|
| 已交付缓存 A，d154d77275142544d2ae96391455f77dcac583e6 | Flash 非思考，200 题各两次 | 553.9 / 557.9；均 **555.9/1000**；180 开发组均 490.95/900，20 留出组 64.95/100 |
| 描述索引实验，4949f6d41e8f62259d06236365b92be20798ba6a | 同配置完整一遍 200 题 | **548.7/1000**；第二遍未运行，未采用 |
| 前轮参数修复 e9d76e4 / 模板 8f795734… | 免费定向原生回归 | 未跑全量模型，不提供白盒总分 |
| 稀疏投影修复 3c6e122 / 模板 34ac7400… | 5 项原生、10 项独立离线均通过 | 未跑全量模型，不提供白盒总分 |

旧版 400 题次的 4s/6s 时延扣分审计与 SDK 一致；仍是本地环境，不是赛题方正式评测。172 题旧模型及 72 题早期候选均为不完整运行，单列且不混入。全 200 题此前已曝光，固定留出只隔离调优，不能称真正未见黑盒。无真实黑盒成绩，不能给官方总分或声称黑盒提升。

描述索引实验仅以 [补丁](experiments/a_description_index_candidate.patch) 保留，可用 `git apply --check experiments/a_description_index_candidate.patch` 核验；本交付不应用。开发排名改善不足以抵消负对照风险和单遍分数下降，暂不采用。缓存的历史等值/速度数据保留在 JSON 历史部分，不能代替模板效果证据。

下一步由 B 落实参数、依赖、错误可见性及请求规划合同，C 按原执行器和评分器验证；A 待权威关系明确再补余下模板。B 修改后作为联合新版本评分，不能与固定旧 B 的结果冒称 A 单变量对照。本轮不新增付费调用，不自动启动新 A 第二遍。

上传只含 A 代码、复现脚本、实验补丁及脱敏聚合。原题、实体值、凭据、路径、进程信息及逐题/访问日志留本地；摘要不足以异机全量复现实验。原含数据的四个本地提交不进入本次推送历史，B/C 提交保留，不自动合并 main。
