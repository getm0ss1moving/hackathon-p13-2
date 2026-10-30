# 统一170隔离候选：离线门禁通过，生产仍198

**显式/隐式语义70/70、默认真实检索46/46已独立通过；本次统一交付170。** top5仅44/46，top10仅45/46；B真实模型选择、填参、组合与原生执行仍待验证。生产保持198，stage2不启，不能把离线门禁或数量减少记成正式总分提升。179只在history179中保留构建链，不单独发布；[已发布180包](../a_family_candidate_20261030/README.md)继续保留。

- **B先读：[完整统一交接和五步构建命令](B_A170_HANDOFF.md)**；[团队B阅读待办](../../docs/TEAM.md)
- [本次变更说明](CHANGELOG.md)、[当前源状态](CURRENT_STATUS.json)、[本次发布复核](PUBLISHER_VALIDATION.json)
- [完整组合验证](COMBINED_VALIDATION.json)、[70项语义摘要](natural_language/OWN_SUMMARY70.json)、[46项检索明细](REAL46_DETAILS.json)、[8次预期差异](DIFF2148.json)
- [170定义引用](templates170.definitions.json)、[ID映射](170_ID_MAP.json)、[原文字索引引用](index_metadata.references.json)、[11张属性元数据](attribute_index/ATTRIBUTE_METADATA.json)
- [78文件源指纹](MANIFEST.json)、[闭合合同](OLD_TO_NEW.json)、[自然view合同](natural_language/VIEW_CONTRACTS.json)、[B补丁及精确源要求](natural_language/MATCHER_ADAPTATION.json)

最终模板JSON SHA256为`f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c`，最终检索器SHA256为`befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24`。170唯一执行ID、161条继承模板+9族；200原文字归属和054/087别名保留，400主文档+11属性文档不是411个执行模板。完整模板只在新的私有目录展开，不上传继承实体例句、默认值、70/537私有fixture或逐题输出。

**源清单历史字段说明：** MANIFEST原样保存上游指纹及演进字段，其中`publication_ready=false`、`upload_allowed=false`、38/46、旧804a…运行时hash和“8缺口”等来自此前held状态；它们由同一清单末尾的`candidate_publication_ready=true`、默认46/46及最终f77c…hash，以及CURRENT_STATUS/COMBINED_VALIDATION覆盖。history_before_*目录保留原失败证据，历史Git_publication=false描述上游未发布时点。当前发布门禁以本页、CURRENT_STATUS和PUBLISHER_VALIDATION为准；原源文件不被重写。

2148次属性前后对照为2140次完全相同，另两条显式合成问法×4种k共8次预期变化；原525×4全同。24项语义负例为空，33属性投影负例不暴露属性候选。新属性分数不等同原整句分数或校准概率，B不能按score重新混排，也不能截断top5后声称默认46/46完整。

最大单条紧凑JSON3179B、容器深7/含外数组8，官方深度口径仍未明确。B补丁是精确基底参考，前六族和F27仍需统一移植，不能直接覆盖最新B。真实模型/SDK、空表缺列、分页、唯一资源及部分关系能力仍未证；仅停止隔离目录即可保持生产198，不reset或强推。
