# 给C：B的v18成绩口径与复测方法

**B的640分是固定150训练题的640/750，不是200题总分、黑盒或正式比赛总分。** 这次发布交付已实际运行的B实现和配置；不能只比较“都在调用DeepSeek”。v18使用当时main `d912b48`上的未提交工作树，因此当时只pull该旧提交不会得到本轮全部实现。运行源码由冻结source_sha256精确标识，源码包也已逐项核对。新发布不引入尚未验证的外部候选。

## 一、实际测法和结果

| 条件 | v18实际值 |
| --- | --- |
| 输入集 | datasets/whitebox_150_50_v1/train.json，固定150题，seed20261030 |
| 运行 | 新进程，按固定train文件顺序，每题1次，150题连续完成 |
| 模板 | A2707ff9去重后的198条，保留检索alias；不是199候选 |
| 模型/地址 | deepseek-flash / https://api.deepseek.com |
| thinking | 显式disabled，301条请求全部记录一致 |
| 输出/重试 | 上限1024 token，SDK max_retries=0 |
| 业务开关 | configs/train150_v18.env，包含全部B候选/保护开关 |
| 原评分 | 用户通知的ratio100.0→1.0唯一修订，原evaluate_case直接评分 |
| 计时 | perf_counter覆盖完整system.query；含模型、校验、GET和SQLite |
| 缓存 | 初始化/schema预热不计单题，原executor缓存跨题共享；不预跑题目 |
| 结果 | 原计时640/750，无时延640/750；126题5分、4部分、6负分、14评分0 |
| 实际用量 | 301/450请求，0失败/型号不符，149余量关闭不复用 |
| 时延 | P50 1.66s，P95 2.58s，max3.81s；0时间罚分 |

真实入口没有使用题号/完整问题查答案，也没有把模型替换成历史回答。每题question交给RunbookQuerySystem，经BM25、模型选择/必要填参/SQL精调，再原API+SQL执行，完整结果交给修订evaluate_case。case_id只用于实验范围和记录。另有免费历史回放，但与真实v18记录分开，不拿回放冒充新模型成绩。

评分器SHA-256：`d2a93903f068d77d84470dcd1e3eef8671571136c1d7cfb7e4f9b3307d3516c1`。quick_eval.py、blackbox_eval.py和runbook_executor.py与原快照d79c316相同；诊断扩展另存C目录。原分5只表示原评分器给满分，不保证所有业务子问完整；合同矛盾见AC_BLOCKERS_20261030.md。

原200题与固定模板在划分前已经暴露，50题仅隔离后续调参，不宣称完全未见泛化。B后续不读取封存50或独立200逐题反馈。

## 二、先核对环境和配置，免费不调用模型

在本仓库根目录使用已配置的Python环境：

```bash
.venv/bin/python scripts/check_official_integrity.py
.venv/bin/python -B -m unittest discover -s tests -p 'test_training_*.py' -q
.venv/bin/python -B -m unittest discover -s C/tests -q
```

上述是合成/训练协议检查，不证明模型准确率。C报告单元测试使用合成题，不加载原全200。不要运行历史全量测试套件来替代本固定150协议。

本机设置自己的密钥，不提交。`scripts/train_live.py`读取根`.env.local`的密钥/模型/地址/SDK timeout；若其中model仍是deepseek-chat，它会覆盖shell export的模型。v18用的是deepseek-flash，必须从新计划实际字段确认。SDK timeout在历史v18计划未单独冻结；源码未设置时默认60秒。它与官方时间扣分阈值不同，不通过更改评分时限消除TLE。

普通C入口不会自动加载`.env.example`或`.env.local`。需要显式加载无密钥的v18环境：

```bash
set -a
. ./configs/train150_v18.env
set +a
```

此配置是150题配置，包含450请求上限。独立200评估使用自己的隔离范围、授权预算和记录，不把150分母或预算直接挪过去。加载配置本身不会发请求；训练CLI还会按参数重设业务开关，所以仅source环境文件仍不足以配置train_live，需下面完整flags。

## 三、固定150复测命令（Bash/macOS/WSL）

先检查自己的`.env.local`或进程环境提供了正确模型与地址、自己的密钥。下列第一条train_live命令只预检：

```bash
set -euo pipefail
v18_flags=(
  --candidate-flags
  --refine-contract-prompt
  --independent-aggregates
  --grouped-aggregates
  --network-details
  --identity-projection
  --vpc-subnets
  --tenant-resources
  --vm-volume-details
  --tenant-vdc-binding
  --parallel-resource-lists
  --thinking-mode disabled
)
v18_retest_stamp="$(date +%Y%m%d_%H%M%S)-$$"
v18_retest_plan="experiments/c_v18_${v18_retest_stamp}_plan.json"
v18_retest_live="experiments/c_v18_${v18_retest_stamp}_live.jsonl"
.venv/bin/python scripts/train_live.py "${v18_flags[@]}" > "$v18_retest_plan"
```

预检应为150题、train_only、full_training、198模板、deepseek-flash、thinking disabled、450/1024/retry0。feature_flags须与`experiments/train150_v18_full_plan.json`完全一致。新计划source_sha256也应与该历史计划一致；提交后code_base改变是正常的，必须使用**新生成的计划**，不能把旧expected-plan的code_base改成新值或绕过freeze。

确认该次复测有自己的模型预算、资源窗口后，以下命令才会实际调用模型；本次GitHub交付没有替C执行它：

```bash
.venv/bin/python scripts/train_live.py "${v18_flags[@]}" \
  --expected-plan "$v18_retest_plan" --run --output "$v18_retest_live"
```

如果因源/数据/开关/hash不同停止，应先解释版本差异、重新预检，不能关掉门禁。模型服务的随机性/队列/后端更新仍可能导致同配置结果不同，640不是对下一轮的保证。未设置temperature/seed为确定性；记录response model和fingerprint再比较。

## 四、怎样确认是可比较的完整结果

1. summary必须complete，completed_cases=planned_cases=150，成员及顺序与固定train一致；中断/补测不能拼成连续一轮。
2. total_score是传真实elapsed的原计时总分；untimed_score只是额外诊断，不用它代替total_score。
3. request事件与每题llm_calls要闭合，模型响应身份一致，thinking_mode=disabled，SDK重试0，预算不超限；余量关闭。
4. 比较source_sha256、training_sha256、feature_flags、scoring_revision和缓存/计时方式，不能仅比较branch或脚本文件名。
5. 逐题差异仅限固定150训练范围归因：API条件、SQL精调前后、原评分原因及stage耗时。独立200/封存的逐题表现不带回本优化任务。

最常见的差异是：旧GitHub缺8个新helper；默认业务flags为0；示例模型deepseek-chat而实际v18是Flash；小预算例只有9请求；旧train_live默认provider_default覆盖export；普通入口未加载环境；旧评分器；使用不同题集或缓存方式。先核条件，不先认定任何同学测错。

## 五、时间profile与证据入口

150题query共259.49秒，DeepSeek客户端请求区间240.75秒（92.78%）：精调127.80、选择102.96、填参9.99秒；本地execute13.27秒。请求计时包括网络/SDK和部分来源核验，不是纯服务器GPU时间；计时嵌套不能叠加。最慢181的execute占约一半，是局部例外。当前已关thinking、无时间罚分，后续prompt优化需验证正确性及真实提速，不会自动补上640到700的分差。

- 完整计划/真实请求/预算：experiments/train150_v18_full_{plan.json,live.jsonl,budget.json}。
- 冻结核验：experiments/train150_v18_freeze.json（source23项/源码ZIP均已核对）。
- 新A来源：experiments/a_2707ff9_training_handoff.json。
- 详细profile：V18_TIME_PROFILE.md；数据与可复算脚本在experiments/train150_v18_time_profile和scripts/profile_training_time.py。

本次同步仅发布v18已测试实现及复现资料。CIDR+count、严格布尔比例、网卡收窄/单ID修复、存储池缺失属性部分回答和新prompt草案仍是外部候选，未接生产，不混入640的解释。700目标继续进行；上传不是比赛提交，也不表示已完成700。
