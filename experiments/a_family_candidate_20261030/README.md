# 180模板隔离候选包：交给B适配，生产仍198

本包已经冻结并可本地展开为180个唯一执行模板及400文档词袋索引。没有替换main的198条运行时；没有将旧R5补丁应用到B v18。

- [完整180定义清单](templates180.definitions.json)：174条固定Git源引用+6个完整新族；每条一个活动ID，不是180份隐藏旧查询。
- [六族新模板](family_candidates.json)、[24条当前ID→6族](canonical_to_family.json)、[参数/类型/输出映射](parameter_mapping.json)。
- [词袋索引元数据引用](index_metadata.references.json)：仅文字来源、顺序与重复次数，无API/SQL/默认值/答案；构建器本地展开正文。
- [R5精确旧基底增量](r5_matcher.patch)、[R5新增函数源](r5_family_additions.py)、[离线别名迁移](alias_migration.py)、[指纹](manifest.json)。
- [已实跑构建校验](BUILD_VALIDATION.json)、[完整中文B交接](../../docs/handoffs/B_A180_HANDOFF.md)。

从仓库根执行，输出必须是尚不存在的私有目录：

```bash
python3 scripts/build_a180_candidate.py --output /tmp/a180-candidate-new
```

构建器使用固定099b5bf的198模板与已验收检索器，实际生成candidate180/implementation/runbook_items.py、runbook_retriever.py及templates180.private.json，并自动完成180唯一ID、400文档、1600检索配对校验。源模板里的实体示例/默认值只在本地展开，生成文件不要直接上传；GitHub清单通过固定Git引用完整还原，避免重复发布敏感实体。

**B v18适配门禁**：R5原补丁针对2707ff9（同dfa61b5的旧matcher），不能直接应用最新099b5bf的v18 matcher，git apply --check已经失败。B应按新增函数+family分支增量移植并回归新helper，不复制旧完整matcher。构建器故意不复制或修改matcher/system，也不创建可误运行的未适配query入口。数据/索引就绪不等于180端到端就绪。

本次没有模型请求、服务测试或封存集评估；R5有限语义审查与离线fixture证据不代表真实模型理解或正式比赛成绩。不要把旧历史select/fill/refine回放当作新family_fill真实响应。
