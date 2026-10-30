# 统一170发布源（语义R4冻结，检索未通过，暂缓上传）

**当前publication_ready=false。** 本目录是本地待发布副本，不是已上传或已启用版本。生产仍为198，179不单独发布。原包与失败证据保留，`history_before_natural/`是语言修复前的合同/门禁历史；以本说明及CURRENT_STATUS为最新状态。

## 已冻结内容

- A170完整数据/索引生成链：已发布180→history179→170。170唯一ID、161条固定源码引用＋9个族；200文字视图、400索引文档。实际私有展开SHA256：`804a1626669ae24bab860b282e465113241dceee09d567f6d12866bb37a09de0`。继承资产文字只在本地展开，不重复上传。
- 相对179的F02/F19合并11→2、净减9，其余168条逐对象不变，旧别名及锚点完整。合同、字段/输出变化与构建信息见OLD_TO_NEW、170_ID_MAP、BUILD_VALIDATION和history_before_natural/HANDOFF。
- 语义原型R4：`1f4bcb58757207122d6a607b401674a8ed480ff8acf2a0b12a5cf2b180bb9c8b`；批次3闭合物化器`79815020…8372ba7`未改。
- B最小增量补丁：`e587d1b7fd9481ac5da39d07ef7a807211ba22381bbd49008c6377922e28969f`；严格基底B matcher`1e7cc2ff…902b63e`（7b7271e3），目标matcher`829a7e41…927fc5a`、新增模块`55d732ab…6ed065e`。仅私有重放与编译通过，没有应用到共享B。

## 当前验收

|层次|结果|界限|
|---|---|---|
|170数据/索引/原合同|2148对相对179归族检索差异0；11合同/33合成SQLAPI通过|保留原基线不代表所有问法召回|
|我方固定70显式/隐式|70/70；原11、显式11、实体替换11、自然改写11、引号实体2、负例24全通过|给定正确族与解析JSON的纯准备/物化，不是实际模型选择|
|实现方受控回归|160项；937个match_runbook受控尝试|模型响应与schema为mock；不是真实API/SDK或得分|
|独立小审|最终原型8例通过|单列上游审查证据，非我方重新运行|
|真实170 BM25（同70中的46正例）|默认38/46，top5=36/46；8个显式字段问法缺所需族|**FAIL，阻塞上传**|
|B真实选择/抽参/精调/组合及原生SDK|未测|不继承其他版本历史模型分|

语义增量接口和9个view见 `natural_language/INTEGRATION_NOTES.md`、VIEW_CONTRACTS与SOURCE_B_INTERFACE_AND_PROMPT.md。新输出合同允许普通隐式问法，不能覆盖用户显式列、筛选或范围；不支持返回None，内部诊断不对外显示。

## B与集成仍需完成

1. 先修真实170检索缺失8项，使用通用字段/意图表示，不能按用例ID/实体分流。固定70及源hash不变再验，后续独立泛化另列。
2. B补丁仅F02/F19；其他七族的移植、组合与同族多义务仍需B统一适配。拿未适配族容器直接执行可能丢条件，禁止据本包直接替生产。
3. 最新B源码若已漂移，重新核对hash并保留B变化；旧补丁不能强套。937mock不替代B真实模型测试与原生空结果序列化。
4. 038原默认值冲突、SDK空表缺列、分页与唯一资源证明、093/186/193未知关系仍不在本轮完成范围内。按问题原文填参的70源038通过，不等于历史default_params已修改。
5. 单条最大2690字节；容器深7/整体8，官方深度算法未明。不能据字节数称正式合规或据减9称总分已增加。

## 数据/索引离线复现

建议最终路径 `experiments/a_family_candidate_170_20261030/`。每步新建私有输出；不改生产或B。

```sh
python3 scripts/build_a180_candidate.py --repo . --output /tmp/a170-chain180-new
python3 experiments/a_family_candidate_170_20261030/history179/build_179_candidate.py --base180 /tmp/a170-chain180-new/templates180.private.json --f27 experiments/a_family_candidate_170_20261030/history179/F27_CANDIDATE.json --retriever /tmp/a170-chain180-new/candidate180/implementation/runbook_retriever.py --output /tmp/a170-chain179-new
python3 experiments/a_family_candidate_170_20261030/build_170_candidate.py --base179 /tmp/a170-chain179-new/templates179.private.json --families experiments/a_family_candidate_170_20261030/CANDIDATES.json --retriever /tmp/a170-chain179-new/candidate179/implementation/runbook_retriever.py --output /tmp/a170-final-new
python3 experiments/a_family_candidate_170_20261030/verify_170_offline.py --base179 /tmp/a170-chain179-new/templates179.private.json --candidate170 /tmp/a170-final-new/templates170.private.json --retriever /tmp/a170-final-new/candidate170/implementation/runbook_retriever.py --helper experiments/a_family_candidate_170_20261030/family_batch3_additions.py --mapping experiments/a_family_candidate_170_20261030/OLD_TO_NEW.json --output /tmp/a170-contract-check-new
```

最后命令是原闭合合同回归；其中原隐式会失败的诊断是历史基线，不是当前R4结果。当前R4的70通过汇总和真实检索失败汇总在natural_language/OWN_*。完整70需本地私有fixture，不附原题/资产/原始日志。

## 发布与回滚状态

本轮没有Git stage/commit/push、网络、模型、服务或用户200/封存测试，也没改固定评估器/执行器。仅私有目录中应用补丁核验指纹。唯一发布负责人须等最新PUBLICATION_GATE解除再发布；不要将本地待发布目录视为已获上传通过。生产未切换，停止隔离候选即可，无需回退生产。此后合并前刷新main，保留其他合作者改动。
