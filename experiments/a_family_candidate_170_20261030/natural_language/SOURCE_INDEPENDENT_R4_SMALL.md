# R4 裸位置机制独立小审

结论：**新增8/8通过，3正例、5反例，0错放、0误空。** 未发现本次新增机制的阻塞项。只新增本轮脚本、INDEPENDENT_R4_SMALL.json和本说明，未改原型、旧结果或以前目录。

原型SHA256为`1f4bcb58757207122d6a607b401674a8ed480ff8acf2a0b12a5cf2b180bb9c8b`，冻结batch3 helper为`79815020db5c0f82ff3e5f0fb20c5b6f5d0ed69d43a363a6fe67b17228372ba7`；执行前后稳定。新案例commitment SHA256：`1bf0e982cb46dae561883bf5db004b0e6311725215abd40cf3b361cf583a3518`。

本轮只验ecs_ip_tenant的唯一AZ/status profile与真实裸位置空间附件。正例使用不具AZ字形的ASCII位置、裸中文位置、含“区域/故障/或/HOST”词的引号位置，分别配实际active或stopped证据。返回原name/privateIps/tenantName列，API等值筛选完整保留。

反例确认：明确“区域”不能被转成AZ；没有状态不能默认active；模型改写位置大小写不能接受；完整实体中的子串不能当位置值；输出意图后面的真实名称包含条件不能被丢掉。均返回None，内部保留原因。

未读private70或已有案例，未自行重跑/认证根的70、160项结果。当前8例已暴露，后续运行属于回归。可从本目录用新输出路径复现：

```bash
python3 scripts/independent_r4_small.py --output independent_r4_small_new.json
```

脚本拒绝覆盖已有证据或测试非指定原型hash。运行只经过纯原型和冻结prepare，parsed JSON由审查控制，无完整B链路、检索或模型能力证明；无模型/服务请求、费用或生产修改。
