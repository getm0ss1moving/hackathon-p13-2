# 给B的统一170模板与检索交接

**本包可发布为隔离候选材料；生产仍198，尚无170真实模型分数。** 显式/隐式纯语义与默认检索门禁已经通过。179只在history179中保留链式构建证据，不另行发布。建议仓库路径为 `experiments/a_family_candidate_170_20261030/`，docs/handoffs可加入口链接，不要移动本目录内相对文件。

## 版本和数量

|部分|冻结标识|状态|
|---|---|---|
|198原源码基底|099b5bfc…；已发布180包7b7271e3|通过固定Git引用重建，保留B/C变化|
|170语义数据（属性前）|804a1626669ae24bab860b282e465113241dceee09d567f6d12866bb37a09de0|11→2的F02/F19及此前7族，170唯一ID|
|最终170＋属性元数据|f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c|现有API/SQL/其他字段全部逐对象不变|
|检索器|befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24|原8fd12b75…＋独立字段BM25通道|
|自然语言原型|1f4bcb58757207122d6a607b401674a8ed480ff8acf2a0b12a5cf2b180bb9c8b|语义修复后未再改动|
|闭合batch3物化器|79815020db5c0f82ff3e5f0fb20c5b6f5d0ed69d43a363a6fe67b17228372ba7|未改|
|B候选适配补丁|e587d1b7fd9481ac5da39d07ef7a807211ba22381bbd49008c6377922e28969f|严格源matcher1e7cc2ff…902b63e，目标829a7e41…927fc5a|

完整200文字ID→170执行ID映射在170_ID_MAP；9族由前六族、F27及F02/F19构成。161个继承模板用固定Git引用保存，避免重复上传原题实体。400原文字文档＋11属性文档是索引表示，**不是411个执行模板**，也没有隐藏原执行条目。

|新增合并族|旧ID|闭合能力与参数|
|---|---|---|
|F02|006/009/029/037/038/039/042|ECS直接属性；创建时间、集群/可用区、IP/租户、列表等受控输出及完整等值筛选；042保留tenantName排序|
|F19|142/145/146/148|GaussDB直接属性；清单/版本、配置、数据VIP/高可用等受控输出与完整等值筛选|

其他族原ID和参数映射沿用已发布180包及history179材料。054→052、087→F14与全部原200文字归属保持。每项原合同的列序、排序和筛选组合可从OLD_TO_NEW与VIEW_CONTRACTS核对，不开放任意SQL、任意筛选/投影笛卡尔积或未经证明的关联。

## 本批到底修了什么

1. **语义增量**：9个view给普通自然问法提供原合同默认输出，实体仍必须来自原文。完整输出意图片段、自然状态/位置、角色和紧邻实例名按通用语法核对；不做旧ID、整句或实体查表。用户明确列/筛选/范围/排序不能被view覆盖。
2. **检索增量**：只给F02/F19增加retrieval_attributes（资源词、输出有序字段、合法筛选字段集合）。11张属性文字卡在独立BM25中检索，保留原strong门禁；主400文档、词袋顺序与全部TF/DF/IDF/tau/平均长度不变。
3. 字段通道只识别显式终末原生字段投影；引号值遮蔽，检查资源、投影顺序及完整筛选字段集合。它只产生候选，**不是整句可执行性判定**。一个意图冲突负例可以命中同族候选，但后续原文校验仍必须输出空。
4. 这8个显式缺口在原198按族检索中同样存在，是新增表达改善，不能称压缩损失恢复。我方另核得原198的精确旧合同覆盖37/46、按族38/46：一条改写只命中其他同族旧条目。两种指标不能混写为都38。

## 独立重跑结果

|检查|结果|能说明什么|
|---|---|---|
|同70语义控制|70/70；误空/误非空/错合同均0|含原隐式11、显式11、实体替换11、改写11、引号实体2、负例24；解析JSON由测试提供|
|真实170的46正例|默认38→46；top1 29→40，top5 36→44，top10 37→45|默认完整，**top5/top10仍非完整**|
|原179→属性前170|2148/2148归族全字段相同|复现原压缩检索不退化|
|属性修复→原170对照|2140/2148相同；另8次是两条显式合成问法×4种k的预期变化|不能称2148全相同；原525×4全部相同，未新增原目标损失|
|24原语义负例|全部空；原始候选非空前后均23/24，新增候选ID暴露0|候选存在不等于误答或正确拒绝|
|属性投影负控制|33/33不暴露属性候选|缺列、逆序、未知列；只是合同生成控制|
|别名与数量|170唯一ID、200原文字归属不变、400＋11文档|无新执行模板、无旧ID查询分流|
|公开可复制属性检查|11合法profile＋33非法投影通过|无需私有70输入；不是重跑完整70|

完整70和2148已曝光，是本轮回归，不称独立黑盒。语义160项、独立8例、937次完整matcher受控尝试保留并注明上游来源；**937使用受控模型响应/schema，不是937次模型或原生成功**。我方没有重新运行该完整mock套件，也未跑真实模型。

本机537个默认检索样本P95/P99约1.534/1.685ms，最大2.272ms；tracemalloc下建索引约8.29ms，存活Python分配约1.066MB、相对原库增量约40.8KB。均不是官方硬件全请求保证、容器RSS或端到端4s/6s成绩。单条紧凑JSON最大3179字节；容器深7、外数组8的官方口径风险仍未消除。

## B接入责任

- F02/F19解析JSON只给view、filters、required_filters，随后调用 `prepare_natural_candidate(question,item,parsed,frozen_prepare,diagnostics)`。成功得到普通API/SQL，失败None；内部区分不支持、异常与成功0行，对外沿用官方空结果出口，不输出“拒答”说明文字。
- 新B补丁只适配这两族；前六族与F27仍需B在当前代码统一移植、组合。不能据F02/F19受控通过把9个参数化容器未物化即交SDK。补丁是参考增量，**不直接覆盖最新B源码**；应用前核对精确源hash，漂移时按diff重基，保留B/C更新。
- 本次检查的固定B源使用retrieve(question)默认候选列表，没有显式top-k参数。保持候选返回顺序；若B截断top5只剩44/46，不能声称继承默认46/46。已有候选被提升时沿用原score字段，新增候选score来自属性规范查询，不是原整句分数/概率，不能混合按score重新排序来抵消该通道。
- retrieval_attributes是文字索引元数据，不是执行参数或答案。B提示/序列化若遍历整个item，需要只消费相关合同，避免把索引视图当API步骤。提示长度与真实模型选择质量本轮未测。
- 同族多view/输出义务要分别保留；列表＋计数不能只留一个family ID。跨资源或部分不支持组合不在本次纯路径通过声明中。
- 038按原问题租户填参的控制已通过，但原198默认值未修改、真实模型抽参仍未知；不得回填历史错误默认。093/186/193未知关系、原SDK空表缺列、分页、唯一资源证明及GaussDB“业务IP”歧义不假称解决。
- B适配后固定同一模型/B/C配置，对198回退、170正常/空/缺字段/组合与官方输出做原生验证；遵守150训练/50封存。不能用旧无family_fill回放替代新协议，不能读取封存逐题调参。

没有170白盒/黑盒真实分。数量项相对198理论+28，只在其他评分项完全不变时成立；本包不把它记作总分提升。

## 从发布资料生成完整170（全程离线、私有输出）

以下从仓库已有180资料和固定Git对象重建，不覆盖生产/B。每次使用全新输出目录。

```sh
python3 scripts/build_a180_candidate.py --repo . --output /tmp/a170-base180-new
python3 experiments/a_family_candidate_170_20261030/history179/build_179_candidate.py --base180 /tmp/a170-base180-new/templates180.private.json --f27 experiments/a_family_candidate_170_20261030/history179/F27_CANDIDATE.json --retriever /tmp/a170-base180-new/candidate180/implementation/runbook_retriever.py --output /tmp/a170-base179-new
python3 experiments/a_family_candidate_170_20261030/build_170_candidate.py --base179 /tmp/a170-base179-new/templates179.private.json --families experiments/a_family_candidate_170_20261030/CANDIDATES.json --retriever /tmp/a170-base179-new/candidate179/implementation/runbook_retriever.py --output /tmp/a170-semantic-new
python3 experiments/a_family_candidate_170_20261030/build_170_attributes.py --templates /tmp/a170-semantic-new/templates170.private.json --metadata experiments/a_family_candidate_170_20261030/attribute_index/ATTRIBUTE_METADATA.json --retriever /tmp/a170-semantic-new/candidate170/implementation/runbook_retriever.py --patch experiments/a_family_candidate_170_20261030/attribute_index/attribute_retriever.patch --output /tmp/a170-final-new
python3 experiments/a_family_candidate_170_20261030/verify_170_attributes_public.py --base170 /tmp/a170-semantic-new/templates170.private.json --attributes170 /tmp/a170-final-new/templates170.attributes.private.json --base-retriever /tmp/a170-semantic-new/candidate170/implementation/runbook_retriever.py --attribute-retriever /tmp/a170-final-new/candidate170/implementation/runbook_retriever.py
```

最后输出包含真正170条RUNBOOK_ITEMS和新检索器，仍是A侧隔离产物，不含已接通的B/system。完整70/537私有fixture不新上传，hash与引用验证代码在verification_reference；没有这些输入不能宣称异机复现完整70/2148。所有新代码/metadata/文档均无题目实体、密钥或本机绝对路径。保留旧A和全部失败证据，不应用历史cleanup。

## 发布、回滚与后续测试

A的本次候选资料门禁通过，可交唯一发布负责人普通提交main；提交前刷新main并核对B基底，不强推、不夹带stage2、不开模型/服务/比赛提交。资料发布不等于生产切换。若B未来切换，保留完整198与匹配B代码的回退快照，不能只回退A数据而遗留新协议。固定evaluator/runbook_executor/server/data本轮始终未动。
