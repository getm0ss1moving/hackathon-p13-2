# Issue3：默认关闭的 A 合同交付

**A 侧已验收合同可供 B 接入评审；B 原生运行与官方业务门禁仍未解除。本包默认关闭，不注册能力、不混入132数组，生产默认198不变。physical 仅作阻塞合同存档，不得启用。**

先读 [B 中文交接](../../docs/handoffs/B_A_ISSUE3_CONTRACTS.md)、[13 文件逻辑闭包](MINIMAL_B_HANDOFF.json)和 [SOURCE_PROVENANCE](SOURCE_PROVENANCE.json)。本包没有运行时总量缩减，也不关闭 issue；新增 P0 合同仍独立审查，未纳入此包。

|模块|交付状态|B/官方仍需完成|
|---|---|---|
|network R2|重复 ID 与跨区域输入先于 SQL 拒绝；可条件交接|完整受信分页、投影表、局部图不完整状态、实际最终请求|
|tenant R2|两个排名视图的已验证投影可交接|明确 unknown/all_ties 政策，使用投影而非原始响应，保留动态摘要|
|capacity|沿用已有条件合同|单位/列政策、typed empty、分页与最终字节边界|
|ELB|仅 region/tenant/VDC 通用视图|没有 ELB 部署 AZ 证据，不得删掉 AZ 条件后作答|
|physical|原生 schema 阻塞，仅存档|S_Switch/S_Router 非空权威 schema、COUNT 与分页政策|
|291 R3|A 输入边界通过，去除历史数据白名单|真实可信 capture/源一致性、实际 SQL 输入绑定及 typed COUNT|

原独立 R2 检查55/55、嵌套空白字符64子项不另加；291 R3独立53/53，不能相加成模型题成绩。capacity/ELB/physical 在 R2 的范围主要是源码哈希与字节/深度核对，不把此前 owner 的套件重复计数。本包提供 R2 的51项公开合成复放，另4项历史输入只保留闭包摘要和哈希；291提供53项合成复放。公开脚本的源完整性检查只覆盖本次交付闭包，不冒称完整 owner 归档复验。

## 重建与复放

从仓库根执行，使用 Python 标准库和 SQLite。先按 [160 构建说明](../a_family_candidate_160_20261030/BUILD.md)生成固定160，SHA-256 必须为 `477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182`。以下输出目录必须全新、在仓库外。

```sh
python3 -B scripts/build_a_issue3_contracts.py --base160 /tmp/a160-stages-new/templates160.private.json --output /tmp/a-issue3-private-new
python3 -B scripts/verify_a_issue3_r2_synthetic.py --output /tmp/a-issue3-r2-check-new
python3 -B scripts/verify_a_issue3_291_r3_synthetic.py --private-template /tmp/a-issue3-private-new/rb_196.after.json --output /tmp/a-issue3-r3-check-new
```

原最小闭包是13份逻辑文件：公开保留12份原字节源码/合同；第13份 `rb_196.after.json` 含继承示例，改由 `rb196.references.json` 重建，目标 SHA-256 为 `f2c25f8f5b7902b47eeedde370cfdd8ee91c059bd471f7d13f4dd0fe953e48b7`。旧 ID 引用仅用于离线构建，不是路由或答案数据。物化源码不读取历史实体白名单。

合成 capture 仅测试纯函数，不能认证生产 provider。无模型、服务、B运行流程、官方执行器或评分器调用，不读取原生记录、封存或全200逐题反馈。未认证最终请求4KB/深度、COUNT业务或整体官方合规。
