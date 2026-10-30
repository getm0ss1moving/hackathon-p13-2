# B最新发布：A/C拉取与复现

本次用户明确要求上传B最新本地工作，沿现有main提交并同步远端A文档。发布matcher/system修复、训练/验证/尾段分析工具、测试和脱敏汇总；保留主办方评测/执行器的已接受字节，不上传密钥、环境、原始模型日志、封存题或私有展开库。

## 拉取后立即生效的行为

`RunbookQuerySystem.query`默认开启RUNBOOK_EMPTY_ANSWER_FALLBACK=1：正常答案原样返回，拒答及显式执行错误输出通用空SELECT结果，matched标识为empty_answer_fallback，诊断保留原始原因及answer_is_guess=true。它不声称业务数据真实为空，不额外发模型/HTTP请求；预算和未处理异常仍按原行为传播。

可显式配置：

```sh
export RUNBOOK_EMPTY_ANSWER_FALLBACK=1
export RUNBOOK_THINKING_MODE=disabled
```

要做旧行为对照时将猜空环境变量设0；自有训练入口用--no-empty-answer-fallback。官方quick/black脚本保持不变。C现有no_answer统计最终score==0，猜空若被API条件门槛判0也会落入该桶；报告须另统计diagnostics.empty_answer_fallback及原始rejection。

## 160复现

远端原库与BM25默认保留198；本地160展开库按既有构建约定不提交。使用普通git clone保留固定Git历史，在仓库根、已有Python环境中执行：

```sh
git pull --ff-only origin main
.venv/bin/python -B scripts/prepare_a160_candidate.py --output ../a160-private-b-latest --activate
```

输出目录必须为新的仓库外目录。该步骤离线重建固定A160，复核来源指纹并安装本地items/retriever；不调用模型或服务。若本地有未提交修改，先保存并按冲突文件处理，不覆盖同学的代码。A目前的新132仅交接原因，未在本发布启用。

两类已有真空恢复与猜空是不同路径。要复现B训练时的空结果处理，官方入口所在进程还须显式设置：

```sh
export RUNBOOK_TYPED_EMPTY_ROOT=1
export RUNBOOK_VERIFIED_EMPTY_ROOT=1
```

完整feature flags以本机新生成的plan.json为准；只设这三个空结果变量不等于复现全部B训练配置。本机.env.local沿用各自配置，切勿上传；普通官方入口读取进程环境，自有train_live会读取列出的本地模型配置。模型开发设置为deepseek-flash、thinking disabled、最大输出1024、SDK重试0。

## B本次其他增量

- 严格兼容单JSON代码块；明确脱敏IP、前置集群名及HOST虚拟化枚举接地。
- 根据候选能力排除不支持架构维度的view；在既有完整合同验证下恢复明确原文参数。
- 接入已证云服务区域名称→ID映射。稀疏NULL保护和部署节点区域绑定候选继续默认关闭，已知参考范围冲突保留。
- 固定50显式验证入口与来源冻结、训练失败子集工具、尾段按原序分析；默认训练仍读取150，50已曝光为验证集。

## 检查与成绩边界

本次发布入口相关检查命令：

```sh
.venv/bin/python scripts/run_training_checks.py \
  --output-dir reports/b-entry-check-new \
  --test-module test_training_subset \
  --test-module test_training_validation_scope \
  --test-module test_training_empty_answer_fallback
```

本机31项通过，0失败/错误/网络/模型请求；此前猜空与原结果守卫相关33项通过。脱敏发布摘要见experiments/b_publish_20261030/VALIDATION_SUMMARY.json，不混加成独立检查总数。未为本次上传重跑150/50/200，也未新增模型调用。

历史完整150为636.4/750，12未答；冻结后50为157/250，15未答。两轮代码不同，且早于猜空默认策略，不代表当前发布的新成绩。完整逐题日志只在本机，仓库文档和JSON汇总标明原始版本/哈希、失败和参考争议。尾部优先级与A/B职责见[B尾段归因](../training/B160_TAIL30_DIAGNOSIS_20261030.md)及[给A的优先级](B_TO_A_TAIL30_PRIORITY_20261030.md)。

若要自行生成新训练计划，启用160后执行：

```sh
.venv/bin/python -B scripts/run_saved_training.py --config configs/train150_a160_v34.json
```

这是预检，不调用模型；已有输出目录不会覆盖。默认不自动重跑全部题，后续先从失败题中选定范围再建新计划。冻结记录和API预算不因拉取代码自动复用。
