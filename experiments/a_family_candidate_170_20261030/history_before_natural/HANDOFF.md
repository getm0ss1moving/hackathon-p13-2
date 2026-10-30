# 统一170条隔离候选：给B与发布负责人的增量交接

**统一交付170，不单独发布179。当前生产198不变。** 本目录包括已发布180库→历史179→170的完整构建资料；`history179/`只保存链式历史及F27/R5移植参考。本包不是已接通B的170生产系统，不能将170个容器直接交固定执行器。

## 本批实际变化

|族|替换旧ID|变化与保留合同|净减量|
|---|---|---|---|
|F02：ECS直接属性|006/009/029/037/038/039/042|受控projection、order和等值filters组合；保留创建时间、集群/可用区、IP/租户/状态等各自列顺序。042保留ORDER BY tenantName，不变成分组。|7→1，减6|
|F19：GaussDB直接属性|142/145/146/148|受控列表、版本/高可用/规格、名称/版本/VIP等各自列顺序；只直接字段，不补造关系。|4→1，减3|

以上11条与前24当前合同、F27及严格去重项无交集；基于179仅减少9，得到**170个唯一活跃ID**。剩余168条逐对象不变，包含全部前7族与旧别名。全200文字ID→170映射见 `170_ID_MAP.json`；新包定义为161条固定源码引用加9个参数族，见 `templates170.definitions.json`。

F02/F19均只允许filtered范围，参数固定为scope/projection/order/filters/required_filters。筛选值为非空原文字符串，全部语义必需条件必须存在；不回填实体默认值。projection顺序、筛选集合与order必须是已审组合，**不允许任意笛卡尔积、任意SQL、聚合、关系或投影**。具体11行合同见 `OLD_TO_NEW.json` 与两族 `parameter_contract`。

## 这次通过了什么

- 真实170库可初始化；保留200个text-only视图和400索引文档，含054/087历史别名与F27跨族锚点。原179文档顺序、token、TF/DF/IDF、tau和平均长度完全相同；没有额外执行模板藏进索引元数据。
- 525条既有已曝光输入＋12条合成单题/复合输入，共537条、4种k、**2148对**：179结果按11旧ID→2族映射、首出现去重后，170的ID顺序/tier/score/coverage差异0。不是原ID逐项相同，也不是模型答题或未见黑盒成绩。
- 11个旧源码API/SQL合同与新物化输出对齐；每合同空/正常/重复+NULL三组合成数据，共33组SQL/API对照通过。11条显式角色＋显式终末输出列的prepare正例通过；8种局部负控制返回空候选。
- 实际最大紧凑单条2690字节；容器深度最大7、含外层数组8。低于4KB只说明该序列化字节数，官方深度算法未确定，仍有提交风险。
- 延迟见 `OFFLINE_VALIDATION.json`：本机537个None-k样本，179 P95/P99约1.519/1.699ms，170约1.510/1.661ms；不含模型、API或SQL，不代表官方超时分。

## 不可隐藏的失败与未证明项

**原11条自然语言示例直接进当前helper，0/11返回普通item。** 10条先因缺显式完整终末投影失败，另1条先因排序证据不匹配失败。这个诊断不是模型抽参测试，也没有靠改问句去冒称能力保持。当前只能证明11个结构合同可恢复，**不能证明11个旧隐式问法已等价恢复**。因此本包可以统一交接，但暂不建议生产替换这11条。B不得把0/11解释为空结果正确。

- 038描述与历史默认条件冲突仍未解决；改成参数占位没有解决其业务含义。
- SQLite预先建立所有列，不能证明原SDK空结果建表缺列已修复。真实分页完整性、记录与唯一实例的关系、缺字段场景均未原生验证。
- COUNT/容量、存储池关联及093/186/193未证明能力没有纳入本批解决。F27的记录COUNT、NULL/重复与分页限制继续见 `history179/HANDOFF.md`。
- 复合检索仅保留召回；同族不同projection/view需B保留多项义务、分别物化执行，不能按族去重后丢义务。跨资源组合、部分不支持处理尚未验证。
- 没有170模型得分、完整端到端成绩或黑盒提升证据。净减9理论上只在其他得分不变时数量项+9；本批尚不能断言净总分增加。

## B需要适配什么

1. 在最新B matcher/helper中接入受控projection/order/filter结构及语义证据，而不是覆盖matcher/system。源码 `family_batch3_additions.py` 是已复审纯函数，只有copy/re依赖；它不选择模板、不调用模型、不提供新执行器，也不读取旧ID映射。
2. 成功调用 `_prepare_batch3_candidate(question, selected_item, parameters, diagnostics)` 得普通api_call+sql；不支持为None，最终按当前B官方空结果出口序列化。内部区分不支持、异常与成功0行，诊断不要作为对外“拒答”文字。
3. **先解决旧隐式问法的语义适配与独立回归**，不能要求用户为通过检查主动补列，也不能随意把模型补写文字当原用户证据。可提出受控意图→输出合同推导方案，经审查后再启用。
4. 保留现有模型预算、异常处理、schema和SQL精调约束；精调不得悄改投影、列序、筛选或排序。前R5/F27旧matcher补丁仍不能直接打B v18，移植门禁沿用历史资料。
5. 固定同一B/C、模型和配置，对198回退与候选做原生接口/正常空值/缺列/组合验证，再按已批准150训练/50封存界限测试。不读取封存逐题调参，不把旧不含family_fill回放当完整新协议。

本地没有B完整matcher补丁，B端接入仍是**未完成**，不阻塞隔离资料交接，但阻塞正式启用。当前生产、固定评估器/执行器、服务和数据没有改动。

## 可复制的离线构建与验证

发布建议目录 `experiments/a_family_candidate_170_20261030/`，保留已发布180包和其固定Git对象。每次选全新私有输出目录，以下不会改生产或B：

```sh
python3 scripts/build_a180_candidate.py --repo . --output /tmp/a170-chain180-new
python3 experiments/a_family_candidate_170_20261030/history179/build_179_candidate.py --base180 /tmp/a170-chain180-new/templates180.private.json --f27 experiments/a_family_candidate_170_20261030/history179/F27_CANDIDATE.json --retriever /tmp/a170-chain180-new/candidate180/implementation/runbook_retriever.py --output /tmp/a170-chain179-new
python3 experiments/a_family_candidate_170_20261030/build_170_candidate.py --base179 /tmp/a170-chain179-new/templates179.private.json --families experiments/a_family_candidate_170_20261030/CANDIDATES.json --retriever /tmp/a170-chain179-new/candidate179/implementation/runbook_retriever.py --output /tmp/a170-final-new
python3 experiments/a_family_candidate_170_20261030/verify_170_offline.py --base179 /tmp/a170-chain179-new/templates179.private.json --candidate170 /tmp/a170-final-new/templates170.private.json --retriever /tmp/a170-final-new/candidate170/implementation/runbook_retriever.py --helper experiments/a_family_candidate_170_20261030/family_batch3_additions.py --mapping experiments/a_family_candidate_170_20261030/OLD_TO_NEW.json --output /tmp/a170-public-check-new
```

公开验证默认只用12条合成检索问句×4个k、33组SQL/API、11显式正例及8负例；完整537输入留本地，hash见MANIFEST。展开的完整模板继承源实体示例/默认值，保留私有输出，不附加上传原始JSON、问题或日志。索引元数据公开文件只给固定源码引用及顺序，不重复敏感原文。

回滚无需改生产：停止使用隔离目录，保持198。若后续B切换，先保留其198整套快照与开关；不能仅把A数据改回却留下不匹配B协议。本轮未切换，所以没有执行生产回滚、Git提交/推送、付费模型、共享服务、200题评估或封存输入读取。
