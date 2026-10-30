# 隐式输出view独立建议交接

本目录与冻结batch3平行，**没有修改首批R5、batch2或batch3**。最新状态见ADAPTATION_STATUS：同一70例已全过，独立目录中的完整matcher增量也已测试；真实170检索仍有8个显式问法缺召回，发布门禁保持暂停。共享B源码和生产未改，当前运行库变化0。

已给出B可采用的最小三键参数：view、filters、required_filters。9个view仅展开原11条的既有输出列/顺序和排序；所有筛选值仍须由原文提供。普通“创建时间”“列表”“配置信息”等可以触发明确view的默认输出，不要求用户逐列说。业务IP不擅自当dataVip，明确列限制不能被默认列覆盖。

|产物|内容|
|---|---|
|docs/B_INTERFACE_AND_PROMPT.md|B最小JSON、view表、family_fill提示词和接入门禁|
|VIEW_CONTRACTS.json|机器可读原列序、排序及合法筛选集合；旧ID只作离线来源证据|
|scripts/natural_view_candidate.py|纯离线参考原型；识别完整输出意图片段和明确实例名，其余原文交冻结校验器|
|NEW_CASES.json、docs/NEW_CASES.md|独立编写40例，18正22反；已用于修正通用问句结构，现为暴露回归|
|VALIDATION.json|160项受控原型检查，含原11隐式/显式/同义/倒序及明确列负例|
|acceptance70_r4/SUMMARY70.json|同协议/同案例hash的70/70复制回归；原验收目录不改|
|patches/latest_main_F02_F19_view_adaptation.patch|针对7b7271e3 matcher源hash1e7cc2ff…902b63e的最小接入方案，不能覆盖B最新代码|
|MATCHER_ADAPTATION.json、B_LEGACY_AST_PRESERVATION.json|源/候选/patch指纹；所有旧函数与除新dispatch外原主流程AST不变|
|FULL_MATCHER_VALIDATION.json|实际match_runbook的937受控尝试通过；真实170正例38/46，整体门禁明确失败|
|RETRIEVAL_BLOCKERS_SUMMARY.json|8个显式缺召回定位；原模板/索引未改|
|INDEPENDENT_R4_SMALL.json|最终1f4原型新增独立8例全过；非真实模型成绩|
|source/REVIEW_SUMMARY.json、reviewer_probes.*|原审查公开证据快照，仅作已暴露回归|
|SOURCE_MANIFEST.json|首批8、batch2全67、batch3全31份冻结文件hash|
|INTEGRATION_HANDOFF.json、DELIVERY_MANIFEST.json|接口、当前指纹、验证范围与未完成项|

原审查19例显式语法回归保持通过；两条隐式控制中创建时间现可用，业务IP因语义冲突保持为空。新40例首轮只发生普通问句词和意图位置的误空，改为完整片段所有权后通过；不通过实体/题号/整句查表。代码不含任何测试实体或旧题号。

```bash
python3 tests/validate_candidate.py
python3 scripts/build_handoff.py
```

原型测试复用冻结batch3纯prepare/materialize，比较最终普通API/SQL和完整filters。新增完整matcher候选保留真实select/family_fill/refine调用结构，但模型响应和schema受控，未启动服务/执行器，也不代表真实模型抽参、SDK空表、分页或官方出口。已暴露70/160/48回归不能叫新独立模型成绩；新增独立8例单列。

B完整入口复现（默认会因尚未通过的真实170召回门禁返回非零，不能当成已可发布）：

```bash
python3 scripts/build_matcher_candidate.py
python3 tests/validate_full_matcher.py
```

当前原型hash为1f4bcb58757207122d6a607b401674a8ed480ff8acf2a0b12a5cf2b180bb9c8b，候选matcher为829a7e41…927fc5a，新增纯业务函数模块为55d732ab…6ed065e。若B源文件hash已漂移，须由B/主协调重基，不能整文件替换。补丁未应用到共享仓库。

本目录包含本地private合成案例和170副本。**禁止整目录上传**；发布清单排除.private.json与private_170。上传还须先解决A检索8项、根独立组合验收及用户门禁，当前publication_ready=false。

建议B先评审输出意图所有权与原文保留机制，再在独立候选中接最小view参数。原问题、拥有的片段、规范化问题和展开合同均保留内部审计；额外条件或明确列限制不能消失。之后由A验证真实整库竞争，B按原授权固定训练范围配对重测，主协调决定候选发布。没有为本建议重新计算N收益或直接发布生产。
