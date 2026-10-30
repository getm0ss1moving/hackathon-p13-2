# 最新版评分器：最初版加两处修改

**本文为73cf234时的历史别名版记录。用户随后明确要求同时修复ratio100.0→1.0，当前版本见[合并修订](EVALUATOR_COMBINED_REVISION_20261030.md)，不再使用本文的100.0阈值。历史测试与哈希保持原版本含义。**

用户于2026-10-30明确提供“以最初版implementation/evaluator.py为基线，仅修改两处”的最新版方案。本轮严格使用Git `d79c316` 原文件重建：

1. 完整替换_tuples_match，系统有额外值时按一对一消费匹配标准值，等宽时保留原顺序比较。
2. available_keys后、原列交集分支前，插入用户提供的别名/额外列值匹配兜底。

与最初版的diff恰为2个hunk，仅_tuples_match和_compare_answers两个函数的AST变化。其余函数逐一保持原样。

|版本|SHA256|数值函数|
|---|---|---|
|最初版d79c316|c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22|ratio阈值100.0|
|此前ratio1修订|d2a93903f068d77d84470dcd1e3eef8671571136c1d7cfb7e4f9b3307d3516c1|ratio阈值1.0|
|本次最新版|7b28151b8679124900c466dbe6f127c534c7a83867397934c8ba470f83b1df75|按“最初版，仅两处”保留100.0|

**未叠加此前ratio1补丁。** 因而本次不再包含原来的百倍数值错误修复；100倍数值仍按最初版规则比较。这一差异已在执行前说明，并在baseline_manifest授权记录和完整性检查中明确。不能把最新别名版称为“两处修改再加ratio1”。

官方executor、quick_eval、blackbox_eval仍逐字节匹配d79c316。新版evaluator的唯一接受哈希已同步至scripts/check_official_integrity.py和baseline_manifest.json；AGENTS.md也已更新。没有放宽为接受任意哈希。

## 实际验证

- 505项免费检查全部通过，0失败、0跳过、0真实网络。
- 合成正反例覆盖：别名不同、系统多列、缺值/错误值、少列、重复值不得复用、等宽原逻辑、行数不一致及重复行。
- 固定150题的标准答案与自身比较：最初版/新版均完全匹配，0差异。未读取封存50题或原200题逐题内容。
- 新版下F11三题真实小测15/15，9次请求0失败；没有新版完整150分数。
- 第一轮免费套件因历史original→ratio1回放测试误读当前新版而停止，原日志保留；该历史测试已固定到原冻结提交，未放宽历史回放门禁，最新别名版由独立控制验证。

本地证据为reports/evaluator_alias_v1/：原始版、此前ratio1版、新版源码、original_to_revised.patch、REVISION.json、integrity.json和unit_02/。历史训练计划、源码压缩包、日志及分数均未重写。

复核命令：

```bash
python -B scripts/check_official_integrity.py
python -B scripts/run_training_checks.py --output-dir reports/evaluator_alias_new_check --bounded
```

输出目录必须是新的。旧回放工具scripts/replay_compat.py仍用于它原先锁定的original→ratio1版本，不能据此给最新别名版记分；新训练使用scripts/train_live.py的当前来源校验。

本次依用户后续指令整合发布到main；授权记录、相对最初版的精确补丁和脱敏验证摘要在experiments/evaluator_alias_revision_20261030/，原始本地reports不发布。
