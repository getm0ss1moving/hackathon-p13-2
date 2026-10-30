# 官方原件与开发工具核验

> **最新评分基线修订（2026-10-30）**：按用户提供的修订通知，`implementation/evaluator.py`仅将`abs(ratio - 100.0) < 0.1`改为`abs(ratio - 1.0) < 0.1`。新SHA-256为`d2a93903f068d77d84470dcd1e3eef8671571136c1d7cfb7e4f9b3307d3516c1`。核验工具与manifest已采用该修订版；其余3个官方文件仍与`d79c316`逐字节一致。修订来源显式记录，不再宣称当前评分器与未修订原件相同。下文原件核验表为修订前历史记录；历史分数、日志和冻结计划不重写，未重新评估的旧成绩不能称为修订后成绩。本轮只做合成数值回归，不读取封存题、不调用模型，也未重跑通知中的100个用例。

用户于2026-10-30明确要求官方测试脚本完全保持下发原件。此前不能笼统声称“所有测试脚本从未改过”：评分器和执行器未改，但两个入口曾加入环境检查、诊断和报告功能。本次已将两个入口恢复为原始字节，增强版另存C目录，没有改评分规则。

## 当前官方原件

以Git原始快照`d79c316`和仓库外下发文件`../implementation/`双重比较，以下4个文件均完全一致：

| 文件 | SHA-256 |
| --- | --- |
| implementation/evaluator.py | c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22 |
| implementation/runbook_executor.py | 4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92 |
| implementation/quick_eval.py | 41c28aa77be441451c440e3ab8f7b4bfbb6172cb5d87dc016a68c0f23fca7324 |
| implementation/blackbox_eval.py | 4f20375597dad1927fa12a0c72d14c31021bbcd3bc4d059629804b9d9469198c |

执行`.venv/bin/python scripts/check_official_integrity.py`可重复核验。该命令只读字节，不导入或执行官方脚本，不打开题目语义，不发模型请求。独立固定哈希门禁不依赖manifest中的哈希；`scripts/train_live.py`与`scripts/train_replay.py`在运行前调用门禁，失败即停。全部240个受保护文件也核验一致。详细结果见`experiments/official_integrity_20261030.json`。

官方脚本中的原展示行为一并保留，不再修改其百分比、CLI、异常处理或报告格式。旧增强版保存在`C/quick_eval_diagnostics.py`、`C/blackbox_eval_diagnostics.py`，它们是开发诊断入口，不冒称主办方原件。官方入口读取完整题库，当前150/50隔离开发不运行它们；只使用固定训练工具，不读取或评估封存50题。

## DeepSeek思考模式

修改位于参赛查询系统的`implementation/runbook_matcher.py`中`llm_ask()`。当环境变量`RUNBOOK_THINKING_MODE=disabled`时，模型请求增加：

```python
extra_body={"thinking": {"type": "disabled"}}
```

当前本地默认`disabled`，显式发送关闭思考参数；选择`provider_default`时不发送该参数。训练入口默认也为`disabled`，可显式用`--thinking-mode provider_default`恢复服务默认；模式记录在冻结计划与请求中，参数与计划不一致时发送前停止。该模型调用设置不修改官方脚本、答案、API条件合规检查或时延扣分规则。开发模型仍为已授权的`deepseek-flash`。旧提交`d912b48`默认仍为`provider_default`，本次发布包含默认关闭修复，复测步骤见[思考模式复测说明](THINKING_RETEST.md)。

`scripts/train_live.py`是我们新增的固定150题开发工具：真实`system.query()`整段计时，直接调用原`evaluate_case(case,output,elapsed)`记录原分，并额外调用同一函数传`0`记录单列的无时延质量分。后者不能当成原计时分。历史固定响应回放不称新模型成绩。

## 文件链接迁移

用户另一次授权已把B内容合并到根目录，`B/implementation/runbook_matcher.py`、`B/GOAL.md`已不存在。当前相应文件为`implementation/runbook_matcher.py`、`docs/training/GOAL.md`。旧聊天链接不会随移动自动更新，因此旧路径会打不开。后续使用仓库根目录绝对路径；未得到具体报错目标前，不能断言其他“couldn’t open the file”也都来自同一原因。

## 后续共享目录变更

目录整理已把开发脚本迁到scripts/，当前核验入口为scripts/check_official_integrity.py。v14在15/150时因源码旧路径消失停止，不能算完整成绩。随后A的2707ff9把等价模板200→198并增加检索canonical alias；当前四个官方文件仍相同，但baseline_manifest中的A两组件哈希尚未重新交接，新预检停止、模型请求0。此前240文件一致是恢复时点核验，不代表后续A提交没有源码变化。原件和新组件分别验证，不能改哈希直接放行。
