# 拒答猜空策略

用户在2026-10-30明确选择：无法作答时也提交空答案，接受答错扣分。此为答题策略，不代表已经补齐模板能力或查证数据为空。本轮在现有main工作区实现，尚未提交或推送。

## 计分依据

先按用户当前要求只看正确性、忽略时间扣分。若空答案正确的概率为p，正确+5、错误-1、拒答0，则猜空相对拒答的期望收益是`5p - (1-p) = 6p - 1`。当`p > 1/6`时有正期望；p=20%时每题期望+0.2。

p应是“当前准备兜底的题为空”的概率，不能直接取整个题库的空白比例。当前已观察的B训练150剩余未答以及后50验证未答的保存参考都非空，不能据此声称猜空一定提高这两批的分数。原评分器还有API条件硬门槛：没有实际API条件时，即便空值吻合也可能判0。原时间扣分照常生效，带时间扣分时上述阈值不能原样使用。

## 已实现行为

- 正常执行、类型化真空、COUNT=0及正常非空答案优先返回，不被空猜测覆盖。
- `_query`保留原检索、抽参、合同校验及执行流程；public `query`在出口对未命中/拒答返回值及显式error输出应用空答案策略。
- 通用固定SQL为`SELECT NULL AS value WHERE 0`，在本地SQLite执行，产生`columns=[value]`、`rows=[]`、`row_count=0`。不额外调用模型或数据服务。
- 输出标识为`matched_runbook=empty_answer_fallback`，明确表示兜底策略，不伪称选中了某个实际模板。诊断`empty_answer_fallback.answer_is_guess=true`、`source_result_verified=false`，保留原拒答、错误、SQL及原结果。
- 只保留原输出中已有的API信息。匹配阶段未执行请求、或部分请求无法证明完整计划已经执行时，API信息保持空；不从参考答案或未执行候选中伪造筛选条件来通过评分。
- 不根据题号、完整题文或参考答案决定是否猜空；运行时不读取题库。预算耗尽和其他未处理异常仍按原入口中止，不能通过兜底继续追加请求。

## 开关与复现

`RUNBOOK_EMPTY_ANSWER_FALLBACK`默认`1`。C直接运行官方入口时，不需要修改官方脚本；为显式对齐配置，可在启动Python的同一shell设置：

```sh
export RUNBOOK_EMPTY_ANSWER_FALLBACK=1
```

旧行为对照设为`0`。B训练入口默认显式写入`1`并冻结到`plan.json`，使用`--no-empty-answer-fallback`可显式写入`0`。新汇总字段`empty_answer_guesses`单列猜空次数；未作答数量减少不等于真实支持能力增长，不能仅看`runtime_abstentions`。

已有历史计划、模型结果和成绩不改写。160条模板数量不变，官方评分器和执行器不变。先前空结果类型化开关仍独立存在，真空恢复在猜空之前执行。

## 本轮验证

以下命令已在`hackathon-p13-2-160-20261030`根目录执行：

```sh
/Users/phyll1s0/contest/hackathon/hackathon-p13-2/.venv/bin/python scripts/run_training_checks.py \
  --output-dir reports/b160_empty_answer_fallback_20261030/checks_01 \
  --test-module test_training_empty_answer_fallback \
  --test-module test_training_blank_contract \
  --test-module test_training_execution_result_schema \
  --test-module test_training_a160_repairs.TypedResultRecoveryTests \
  --test-module test_training_empty_root_query
```

33项通过，0失败、0错误、0网络连接、0模型请求。包括默认开启/关闭对照、真空及COUNT零结果不覆盖、失败证据保留、无额外模型/执行器请求、原评分器空白+5/非空-1/API门槛0，以及预算异常不中断原错误传播。原核心结果守卫的对照测试显式关闭猜空，未删除原守卫。

另做单道既有未答077的配置预检，命令：

```sh
/Users/phyll1s0/contest/hackathon/hackathon-p13-2/.venv/bin/python scripts/run_saved_training.py \
  --config experiments/b160_empty_answer_fallback_20261030/preflight_one.json
```

预检成功，固定150内的单题、160模板、Flash关闭思考；新flag=1已进入冻结计划，计划的未来请求上限为3。本次没有加`--run`，实际模型请求0，未执行该题；计划和源码快照保存于`reports/b160_empty_answer_fallback_20261030/preflight_one`。不把预检称为模型验收或新成绩。

本轮未重跑150、50或200；未运行新的真实模型测试。后续继续只挑失败题，并同时报告原始拒答原因、猜空数量、API门槛0分和真实评分，优化真正的查询能力与计分策略分别记账。
