# 根目录与B合并交付（2026-10-30）

此前根目录保留A模板/检索和C报告，而B有独立源码、服务与训练入口；从根入口评测不会使用B最新改动。本次按用户要求，将当前B实现接入根目录，移除重复源码/服务副本，所有协作者使用同一套`implementation/`。

## 最终布局和取舍

- 保留根A模板、BM25检索及C的quick/blackbox/eval_report；接入B的最新matcher、system及runbook_aggregates。
- 根A模板含`3c6e122`稀疏服务器投影修复，B旧快照没有；本次保留根A版本。其差异与来源显式写入根`baseline_manifest.json`，固定划分manifest不改。回放只接受这项已交接模板差异，其他知识库/保护内容漂移仍停止。
- `query(question)`继续可用；增加C已使用的`diagnostics`参数，同时保留B结果中的matching、阶段时间、请求事件。候选/选择、参数来源、精调原提案/回退和执行结果进入C同一报告。
- 训练脚本、测试和固定训练数据移至根目录；协作文档在`docs/training/`。历史已跟踪的实验和数据记录按原字节移动；不改写历史计划或来源哈希。
- 本机旧环境、原数据副本、封存50题、未跟踪的旧全200逐题材料/未应用补丁保留在本机忽略路径或仓库外备份，不随这次提交新增上传。已在Git历史中的材料仅搬路径。
- 模型/规则候选开关沿用B默认值，未为了目录合并额外启用新算法。独立/分组聚合和thinking功能含最新合成测试，但不把这些测试当成新模型质量结果。

## 验证

- 训练专项114项、合成语义/客户端75项、C诊断和报告9项，共198项通过；模型通信使用替身，未读取封存集。
- 固定150训练题v2历史（原147+补3）使用真实本地数据、原执行器/评分器，经统一query免费回放：历史585/750、当前585/750；117完全正确、2部分、5错误、26评分零分，0改善/0退化。
- 上述是无时延诊断分与固定历史模型输出；不合并历史分段计时，不声称新模型准确率、正式总分或700目标已完成。
- 240个当前只读快照全部通过；根236个原评分器/执行器/服务/数据/用例与操作前完全一致。训练dataset/manifest/history与历史实验文件原字节迁移。
- 额外在无B源码、无本机配置的干净暂存副本中复跑198项，全部通过；旧补测入口已允许不存在`.env.local`，来源/型号/计划门禁继续保留。
- 根训练入口免费预检、80文件交接ZIP生成校验通过；完整白盒/黑盒、付费模型和最终留出评估本轮未运行。

复查命令（仓库根目录）：

```bash
.venv/bin/python -B check_env.py --require-server
.venv/bin/python -B -W error::ResourceWarning -m unittest discover -s tests -p 'test_training_*.py' -v
PYTHONPATH=tests .venv/bin/python -B -W error::ResourceWarning -m unittest test_llm_runtime test_matching_sql test_params test_projection_contract test_bounded_api test_resource_attributes test_row_semantics -v
.venv/bin/python -B -W error::ResourceWarning -m unittest discover -s C/tests -v
.venv/bin/python -B train_live.py --candidate-flags
.venv/bin/python -B train_replay.py --history-v2 --candidate-flags --output reports/new-replay.json
```

## 来源

同步起点`ad45ecc`，B已提交基础`51f0aad`。`B-uncommitted.patch.gz`（gzip解压后为原始Git补丁）保存合并前B相对该提交的3个本地文件差异；新增聚合模块的原字节即根`implementation/runbook_aggregates.py`。它们共同保留本次接入的未提交来源，历史补丁中B路径只表示当时位置。运行代码只在根目录维护。

本机完整操作前备份在仓库外`b-local-evidence/unify-20261030-114637`，不会进入GitHub；精确源码、检查摘要和文件哈希见`validation.json`。
