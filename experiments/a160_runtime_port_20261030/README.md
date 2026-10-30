# B160本地训练接入

固定A来源为main `e0f34ed42937203631eef0309964431c376cd179`；本次按用户要求直接整合发布到main，没有新建分支。原170/V32目录保留。本目录SOURCE_MANIFEST只锁定A数据、检索及纯函数来源；完整B代码及模型配置由每轮训练的plan.json/source.zip锁定。公开脱敏摘要见VALIDATION_SUMMARY.json，原始日志仍仅在B本地。

- 本地已物化160条、15族；A JSON SHA256为477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182。
- 检索仍为BM25，400主文字文档及11属性文档；没有运行时旧题号/问题/实体/答案查表。
- 六个新增族分别通过runbook_family_batch4、runbook_family_single（R2）、runbook_family_count接入模型抽参、完整原文校验、物化和SQL精调。给执行器的仍是普通api_call+sql。
- 继承并保留B170/V32修复，包括F01/F18联动、F21隐式双轴、布尔枚举、资源覆盖、测量/输出/粒度保护、分批及空依赖处理。
- 官方runbook_executor.py、quick_eval.py、blackbox_eval.py未修改。evaluator.py按用户最新方案单独修订，见评分版本文档；历史分数不改写。

详细结果和命令见 [A160_V33](../../docs/training/A160_V33.md)，协作事项见 [B→A/C交接](../../docs/handoffs/B_A160_V33_STATUS.md)，新评分器见 [最新版修订](../../docs/training/EVALUATOR_ALIAS_REVISION_20261030.md)。

本地展开库和reports保持私有、不发布。公开资料重建仍按 [A的BUILD](../a_family_candidate_160_20261030/BUILD.md)执行，B增量不能被A旧整份matcher覆盖。远端main默认198的历史说明与本地160训练候选须区分。

本次提供一条命令的复建入口（在仓库根运行，输出目录须全新）：

```bash
python -B scripts/prepare_a160_candidate.py --output ../a160-private-new --activate
python -B scripts/run_training_checks.py --output-dir reports/a160-check-new --bounded
python -B scripts/run_saved_training.py --config configs/train150_a160_v33.json
```

准备脚本逐步保存原始命令、构建日志和固定哈希，--activate只替换本地items/retriever；先在仓库外备份这两份文件，未知本地改动会停止。省略--activate只生成私有产物。不会调用模型、服务、改官方文件或自动提交Git。真实训练需要本机正确配置Flash密钥，并在计划冻结后显式使用--run。旧已存在的输出路径不能重跑覆盖。

整体COUNT业务、缺失原生字段、参考冲突及完整新版150验收尚未全部通过；本记录不代表生产就绪或正式比赛成绩。
