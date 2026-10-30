# 160隔离候选：解析/等价通过，COUNT业务仍阻塞

**本次只交付可复现160候选与R2解析增量；生产默认198不变，stage2不启。** 原51/51、原70/70、batch4 41/41离线控制已通过；COUNT总体业务门禁仍BLOCKED，不能据此宣称160整体业务正确、生产就绪或总分提高。最新B完整160兼容、真实模型与原生执行尚未测试。

- **B先读：[160中文交接](../../docs/handoffs/B_A160_HANDOFF.md)** · [最新B来源兼容说明](parser_r2/LATEST_B_SOURCE_COMPATIBILITY.md) · [团队阅读待办](../../docs/TEAM.md)
- [构建与公开复核步骤](BUILD.md)、[变更及验证口径](CHANGELOG.md)、[当前分层状态](CURRENT_STATUS.json)、[发布复核](PUBLISHER_VALIDATION.json)
- [160定义引用](templates160.definitions.references.json)、[200文字→160映射](base160/ID_MAP160.json)、[源码清单](MANIFEST.json)
- [R2交接](parser_r2/HANDOFF.md)、[162项源控制摘要](parser_r2/SUMMARY160_PARSER_R2.json)、[四裸名修复](parser_r2/ORIGINAL4_TRANSITIONS.json)、[COUNT业务门禁](parser_r2/BUSINESS_GATE.json)
- [原27组SQL夹具证据](base160/evidence/SQL_COMPARISONS.json)：其中2项继承原SQL错误，保留失败，不能计为业务成功。

模板160 SHA256：`477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182`。检索器仍为`befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24`；R2单表解析器为`04098b713541a87681e0e916f84ccb4d82644ee218a68e424587c1cd3ced6576`。160唯一ID、15族、200原文字归属与054/087别名、400主文档+11属性文档保留。完整模板仅从已发布170资料和固定引用在新私有目录展开，不上传原实体、原始资产、51/70/537私有fixture或逐题结果。

**历史状态不能混用：** base160原样保留旧47/51、scope59和“不发布/HOLD”审阅记录；当前R2用同一原51标注修复通用ASCII原子边界，51/51通过，未以范围重分类抵消旧失败。当前解析/等价结论以parser_r2与本页为准；COUNT业务BLOCKED从未被解除。源文档Git_publication=false描述上游未发布时点，原证据不重写。

两阶段各原537×4=2148与新51×4=204按族对照差0属于源离线验收；本发布者仅重建166→164→160、核对固定hash、重放精确parser补丁与公开四条裸复杂名及负控制，不冒称重跑完整私有162/检索集。3179B、深7/含数组8仍不等于官方深度合规。

当前main已包含B新修复，不能用旧matcher整包覆盖。以3057d64来源核对为已读证据，B需在最新源码增量移植并完整回归；保留F18 oneOf、F20 bool/API枚举、状态归属、聚合粒度、EIP、170自然view及既有精调/日志/组合。B180的历史成绩不属于160。
