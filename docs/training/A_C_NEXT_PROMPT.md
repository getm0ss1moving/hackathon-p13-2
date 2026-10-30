# A/C下一轮协作提示词（v18）

最新交接以[B_AC_HANDOFF_V18.md](B_AC_HANDOFF_V18.md)、[C复测协议](C_RETEST_PROTOCOL_V18.md)及[阻塞证据](AC_BLOCKERS_20261030.md)为准；下段可直接复制：

```text
请基于现有main协作，不新建分支。先读AGENTS.md、docs/TEAM.md及docs/training/B_AC_HANDOFF_V18.md、C_RETEST_PROTOCOL_V18.md、AC_BLOCKERS_20261030.md。同一文件一轮一人；A拥有模板与BM25检索，B拥有matcher/system及训练工具，C拥有扩展诊断与分析。未经用户当次明确要求不自动提交/推送。

B当前真实基线：A2707ff9的198模板，固定train150连续一轮640/750，126满分、4部分、6负分、14评分0（13真实拒答）；301请求、0失败、0时延罚分。deepseek-flash显式thinking disabled、1024输出上限、SDK重试0，完整开关见configs/train150_v18.env。当前不是700，也不是200题或正式成绩。免费回放与真实结果分开，不拼多轮最佳。

quick_eval.py、blackbox_eval.py、runbook_executor.py保持d79c316原件；evaluator.py仅采用用户通知的ratio100.0改1.0修订。用scripts/check_official_integrity.py核验。C扩展入口在C/目录，不写回官方文件；保留BM25、真实模型选择/填参/精调与api_call+sql链路，不改数据/用例，不按题号/原题/实体/答案路由。

开发只使用固定train150和仅训练范围证据，不读sealed50、原全200或旧全200逐题反馈，不重抽划分。固定模板和原200在划分前已暴露，不能声称完全未见泛化。199候选不接生产，当前198是两条等价合同去重。

A请按B_AC_HANDOFF列的优先级提供字段/参数/范围/主外键/输出粒度和缺失政策的可执行合同、原生证据与反例，尤其状态/tenant-VDC、数据库专用盘、AZ/region、287父键和261/300未知桶。不猜关系，不把宿主非启动卷当专用数据盘。

C请先按C_RETEST_PROTOCOL_V18生成新计划，核对同提交/数据/hash/flags/model/thinking/评分/缓存/计时后再测。给计划+聚合summary及训练范围差异，不只给总分；审计112/252/256/274/300参考覆盖冲突及189门禁、127/270子问，不删正确对象凑分，不自行改官方评分器。独立200或封存评估反馈不回传B调参。

B会先修204明细+计数退化及做原已过题回归，不等待全部合同。外部候选不等于已发布实现。新付费实验冻结独立范围和预算、与其他运行协调，不复用旧余额，不发密钥。稳定后完整train150连续验收700/750，未达不称完成。
```
