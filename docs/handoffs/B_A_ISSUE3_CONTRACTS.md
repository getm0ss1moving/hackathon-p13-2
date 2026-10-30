# A→B：Issue3 独立合同交接

**请 B 阅读[默认关闭合同包](../../experiments/issue3_contracts_20261030/README.md)。本次与132分包，仅交付已验收的纯源码、schema/合同和合成复现资料；不改变198默认、132模板、B实现或官方组件，不关闭 issue。新增 P0 三合同未纳入。**

原最小交付收据 SHA-256 为 `ba0c6f8293541d475237b0ee596161009fbe58a3f3b31a675db1cbd4ac5ffd47`，共13份逻辑文件。公开12份源码/合同保持原字节；第13份单模板由固定160引用精确重建，详细路径和哈希在[最小闭包](../../experiments/issue3_contracts_20261030/MINIMAL_B_HANDOFF.json)。这不是原 owner 全归档或默认运行时接入。

## 验证及边界

R2独立55/55，空白字符64子项嵌套其中；291 R3独立53/53、六个原合法新输入6/6接受。两组不能拼作模型成绩，原owner套件没有重复运行。源收据与结果哈希、逐项判定摘要随包保留。

公开复放单独报告：R2保留51项合成检查及64嵌套子项，4项历史输入仅保留[闭包摘要](../../experiments/issue3_contracts_20261030/evidence/CLOSURE.json)，不上传原记录；291复放53项合成检查，源完整性检查缩为本次交付闭包。没有原生执行或真实模型分数。[README](../../experiments/issue3_contracts_20261030/README.md)给出构建及两条验证命令，冻结`MANIFEST`绑定工具与资料。

## B 接入待办

- network：保留同一 CI 内重复 ID、声明区域的四类 CI 错区域/缺区域拒绝；完整同区域父目录要跨 VDC 收齐。仅执行 preflight 的投影表，保留 unknown 与 `business_complete=false`，不能把局部已知计数当完整答案。
- tenant：必须先 preflight，再执行其投影与显式参数。空白租户 ID 规范化为 NULL，非空 opaque ID 原样保留；保留 `all_ties`、unknown 政策、投影/参数摘要及挂载不完整诊断。不能绕过已验证投影直接装原始响应。
- capacity：单位目前只是源单位，不能擅称 GB/GiB；VDC 名称桶不等于权威身份。缺schema、失败、不完整页和 unknown 不可填0。整包字节限额仍需 B 在真实最终边界实施。
- ELB：仅接受显式 region/tenant/VDC 的 per_elb/totals；没有部署 AZ 依据。保留 listener/member 独立聚合，不能子表直连产生乘积，不能删除 AZ 条件。
- physical：**保持默认关闭，仅合同存档**。S_Switch/S_Router 非空原生 schema 未证，typed 真空与官方 COUNT 政策仍待验证；单API小于4KB不代表整包满足。
- 291 R3：可信宿主配置 `make_region_count_binder` 的真实 capture reader，不得将模型/用户 JSON、callable 或任意快照标签当来源认证。实际源版本/读隔离应支撑当前完整全局 AZONE/MIDDLEWARE 捕获。执行前以 B 真正装载的 namespace 表调用 `check_execution_namespace`，保留执行ID/源版本/动态投影绑定；其通过不证明 GaussDB/OBS 数据或 COUNT 已正确。

保留最新B `query→_query` 包装，并单列 `empty_answer_fallback` 猜测及原始失败原因；`error=None`不能证明查询成功、真空或COUNT=0。原生 schema、成功空/占位1、NULL/未知、缺列、分页、响应失败和最终输出合同须在 B 完整链另验。

139仍缺数据库专用盘用途到池关系，224仍缺 AZ namespace/量词证据，不能伪造。正式4KB/深度及业务参考争议留给 B/C/官方；本包 A 合同通过不解除这些门禁，也不授权新增模型预算或生产切换。
