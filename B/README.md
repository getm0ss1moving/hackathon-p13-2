# B：模板选择、参数填充与查询流程

本目录是 `hackathon-p13-2/B`，按仓库 `TEAM.md` 的 B 角色独立开发。负责人是本聊天的用户，由 Codex 协助。开发分支为 `simple/official-starter`。

已完成环境、本地回归和一次真实模型全量白盒测试：**448.9/1000，116 题完全正确、20 题部分正确、23 题错误、41 题拒答**。仍使用“BM25 → LLM 选择 → 参数填充 → SQL 精调 → 原执行器”。这是 deepseek-flash 开发结果，尚无完整版本对照或正式成绩。完整证据见 [全量报告](experiments/whitebox_20261029_summary.md)，最新一轮为 [API 查找资源门禁修复](experiments/resource_gate_20261029_summary.md)，逐轮交接见 [PROGRESS.md](PROGRESS.md)。

## 文件与职责

```text
B/
├── implementation/
│   ├── runbook_matcher.py     # B 主改：选择、填参、精调、模型客户端
│   ├── runbook_system.py      # B 主改：主流程与阶段诊断
│   ├── runbook_items.py       # A 的基线快照，B 不修改
│   ├── runbook_retriever.py   # A 的基线快照，B 不修改
│   ├── quick_eval.py          # C 已交接的评估入口，B 不修改
│   ├── blackbox_eval.py       # C 已交接的评估入口，当前无黑盒文件
│   ├── runbook_executor.py   # 官方原文件，只读
│   └── evaluator.py           # 官方原文件，只读
├── output-server/             # 原数据服务与本地数据副本
├── CMDB用例集-白盒200.json     # 本地数据副本，不重复提交到 Git
├── requirements.in            # 直接依赖
├── requirements.txt           # 本轮锁定的完整依赖版本
├── setup.sh                   # 建环境、装依赖、准备数据、环境检查
├── prepare_data.py            # 仅复制缺失的数据，不覆盖已有文件
├── check_env.py               # 无模型调用的环境与原文件校验
├── baseline_manifest.json     # 来源提交和原文件 SHA-256
├── tests/                     # 无外部模型调用的回归与本地联调
├── run_whitebox.py             # 原评分入口上的单轮 JSONL 记录，默认仅预检
├── analyze_whitebox.py         # 免费重算统计、完整性检查与失败清单
├── replay_sql.py               # 免费冻结模型输出回放，需本地数据服务
├── experiments/               # 已完成实验记录、报告及固定候选诊断计划
└── reports/                   # 本机运行记录，忽略生成文件
```

代码和依赖自成一组，克隆后运行 `setup.sh` 从同一仓库根目录复制数据即可。数据准备完成后，可以整体复制 B 目录独立运行；换机器时重新创建虚拟环境。Git 中不重复保存约 250MB 数据，不提交虚拟环境和密钥。

## 环境准备

本机使用 Python 3.13.12。macOS/Linux 从仓库根目录执行：

```bash
cd B
./setup.sh
source .venv/bin/activate
```

优先使用已安装的 `uv`，没有 `uv` 时使用 `python3 -m venv` 和 pip。可通过 `B_PYTHON` 指定解释器；`uv` 路径默认选择 Python 3.13。Windows 可用以下等价命令：

```powershell
cd B
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python prepare_data.py
.venv\Scripts\python check_env.py
```

单独取得 B 代码时，用 `python prepare_data.py --source /path/to/hackathon-p13-2` 指向同版本仓库。`check_env.py` 应通过 240 个只读文件的哈希校验。未启动服务时会提示“未就绪”，不影响依赖与数据检查。

## 启动数据服务

终端一，在 B 目录：

```bash
.venv/bin/python output-server/data_server.py --host 127.0.0.1 --port 8080
```

终端二，仍在 B 目录：

```bash
.venv/bin/python check_env.py --require-server
.venv/bin/python output-server/verify_server.py
```

原执行器固定连接 `127.0.0.1:8080`，此轮不修改该接口。不要同时启动两份占用 8080 的数据服务。服务加载 63 类数据、186,152 条记录。

## 模型配置与真实查询

程序读取进程环境变量，不自动加载 `.env`。本机配置 `DEEPSEEK_API_KEY`；不要将密钥贴进聊天、脚本、日志或 Git。`.env.example` 只给变量说明。

本机已将获授权的开发配置保存在 `.env.local`（Git 忽略、权限 0600）。需要运行时，在 B 目录加载到当前终端：

```bash
set -a
source .env.local
set +a
```

其中 `deepseek-flash` 仅为用户批准的开发自测模型；正式模型仍待主办方确认。每次运行都会重新计算进程内调用上限，扩大测试前需另行确认预算。

- **官网没有指定 DeepSeek 型号或公网地址**，只要求“由赛题环境统一提供，模型不可更换”。下发基线默认使用 `deepseek-chat`、`https://api.deepseek.com`。正式接口尚待主办方确认；收到准确标识后配置 `DEEPSEEK_MODEL` 与 `DEEPSEEK_BASE_URL`，不自行挑选替代模型。
- 当前代码接收消息列表，调用 Base URL 下的 `POST /chat/completions`（Base URL 含 `/v1` 时路径为 `/v1/chat/completions`），使用 Bearer Key 鉴权。请求/响应合同已由内存 transport 验证；这不证明正式服务已可连接。
- TLS 证书与主机名校验开启，模型客户端尊重系统代理配置。自定义可信 CA 使用 `SSL_CERT_FILE`。
- `RUNBOOK_MAX_LLM_CALLS` 限制**整个进程**的模型请求数；`0` 或未设置表示不设本地次数上限。失败请求也计数，SDK 自动重试已关闭。
- `RUNBOOK_MAX_OUTPUT_TOKENS` 默认 1024，`RUNBOOK_LLM_TIMEOUT` 默认 60 秒。输出截断视为调用失败；SQL 精调失败仍走基线的原 SQL 回退逻辑。
- 选择/填参遇到截断或空输出时当前题拒答，后续题继续；网络、认证、预算等基础设施异常仍中止评估。`RUNBOOK_PRESERVE_TEMPLATE_COLUMNS=1` 启用实验性的输出列保护，默认关闭；详见实验报告，不能将开启候选的运行称作已测全量基线。

仓库要求真实模型调用和费用先获得授权。以下是首次前三题连通性检查示例，运行会消耗模型额度；历史已完成不代表可以无预算重复：

```bash
RUNBOOK_MAX_LLM_CALLS=9 RUNBOOK_MAX_OUTPUT_TOKENS=1024 \
  .venv/bin/python implementation/quick_eval.py 3
```

单次查询：

```bash
RUNBOOK_MAX_LLM_CALLS=3 .venv/bin/python implementation/runbook_system.py \
  "查询区域region_guian4下所有ECS实例按状态的分布情况"
```

主入口保留原输出字段，并额外返回 `diagnostics`：匹配/执行耗时、各次模型调用阶段/耗时/token 数，以及候选模板 ID、拒答原因和已填字段名。诊断中不保存密钥、提示词或模型原文。运行 `quick_eval.py` 时仍使用原官方评分函数；已同步 C 在 `d20af59` 交接的启动检查、范围校验和百分比修复。查询异常会中止评估，不把基础设施故障记成拒答。

## 不消耗模型额度的验证

```bash
.venv/bin/python -m unittest discover -s tests -v
# 先启动本地数据服务，再执行完整本地联调：
RUNBOOK_TEST_LOCAL_API=1 .venv/bin/python -m unittest discover -s tests -v
```

49 项测试覆盖模型请求合同、调用预算、实体替换、缺参保护、类型、枚举、拒答、截断处理、SQL 校验、候选开关、API 查找依赖和本地流水线。本地流水线使用真实数据 API、原执行器和原评分器，仅模型响应为测试夹具；还执行原 `quick_eval.py` 的前三题入口。该结果用于证明链路和逻辑约束，不能作为模型准确率或真实时延成绩。不设置 `RUNBOOK_TEST_LOCAL_API=1` 时会跳过四项数据服务测试。

## 整体白盒测试入口

`run_whitebox.py` 在原 `quick_eval.main()` 上记录单份 JSONL，继续调用原 `evaluate_case()`。默认只预检文件、模型配置、只读哈希与运行范围，不发起模型请求：

```bash
.venv/bin/python run_whitebox.py --limit 200 --max-requests 600 --max-output-tokens 1024
```

获得当轮预算授权并启动数据服务后，执行一次完整白盒：

```bash
.venv/bin/python run_whitebox.py --run --limit 200 --max-requests 600 \
  --max-output-tokens 1024 --output experiments/whitebox_next_authorized_run.jsonl
```

该入口加载本机 `.env.local`，不需要在命令中填写密钥。每题最多选择、填参和精调三次请求，无 SDK 自动重试；原文件顺序、单轮、全量 200 题，黑盒缺失不运行。输出文件以独占方式创建，不能覆盖已有实验。

JSONL 包含配置和代码/数据哈希、初始化、每次模型请求、逐题得分/耗时/候选/参数来源/API/精调前后 SQL/结果预览，以及完整性和资源汇总。模型、网络或预算异常中止时标为 incomplete，不把未完成题补 0。记录的进程峰值内存只包含评估进程，数据服务需单独记录；不据本机单次测试宣称正式资源合规。

全量已测版本为实验时提交 `f3ca455`，正常协作 rebase 后对应 `0b1d032`，六个核心模块哈希一致，详见 JSONL 首行。当前另有默认关闭的输出列候选；每轮只选择一个主要因素做对照。

重新计算已经完成的结果不消耗模型额度：

```bash
.venv/bin/python analyze_whitebox.py experiments/whitebox_20261029_full.jsonl \
  --output reports/recomputed_analysis.json
# 需已启动本地数据服务，模型请求仍为 0：
.venv/bin/python replay_sql.py experiments/whitebox_20261029_full.jsonl \
  --output reports/recomputed_sql_replay.jsonl
```

上述工具拒绝覆盖已有输出。真实全量测试的完整记录、首次中断记录、预算和分数解释都保留在 experiments，不将中断与重跑结果拼接。

## 本轮改动与后续整合

运行时改动集中在 B 的两个文件：

- 选择明确拒答或编号不合法时停止，不强制退回第一候选；不再将租户与 VDC 视为相同分组维度。
- 实体抽取采用有边界的 ASCII/引号解析；不回填示例默认实体，不删除缺失的必要 API 条件；保留 JSON 参数类型，字段枚举按 schema 样例校准。
- 区域、租户、可用区等显式条件须在 API 层体现；请求输出 IP 字段不会被当作按 IP 过滤。
- 保留 SQL 精调，合法 Top-N、输出别名和原模板 UNION 不再被无条件删除/改写；检查单条 SELECT、表集合、API 过滤约束和 schema 编译，精调失败回退原 SQL。
- 增加可解释诊断，保留 TLS 与调用预算。无占位符模板也经过共同校验与精调，可能增加请求数，需在真实模型阶段测量其得分和时延影响。
- 资源门禁补充首步过滤 API → 下一步 SQL 表的明确依赖证明；填参后使用原执行器核验查找记录，空查找拒答，防止依赖条件被省略。仅在固定选择审计中改变 CMDB-036，其他 199 题门禁判断不变；尚不能据此声称新全量成绩。

团队整合时比较并迁移 `B/implementation/runbook_matcher.py` 与 `B/implementation/runbook_system.py`。不要用 B 的整份 `implementation/` 覆盖主目录，否则会覆盖 A/C 后续工作。依赖锁定和本地测试可以一并交给 C。

同步 A 的新模板/检索器前先确认提交版本；更新 B 的对应快照并记录来源。哈希检查发现快照与初始版本不同是预期交接信号，应明确更新 manifest，不要直接绕过检查。

下一步按真实失败逐类改进：先验证 SQL 输出列候选，再检查资源门禁、参数/API 条件与模型串行时延。当前 41 题拒答需区分合理弃权和误拒；复合问题的多模板编排仍需与 A/C 确认原子模板和子结果格式。

## 检查记录

基线来源提交为 `d20af59`，精确哈希见 `baseline_manifest.json`。远端开发分支在本轮期间更新，已快进同步，并复制 C 已交接的评估脚本；原始数据、执行器、评分器、模板和检索器一致。

| 项目 | 实际结果 |
|---|---|
| 独立环境 | Python 3.13.12，锁定 20 个依赖包；含本机 SOCKS 代理所需的 socksio |
| 原始只读文件 | 240/240 个 SHA-256 校验通过 |
| 数据服务 | 63 类数据、186,152 条记录；本地 schema 可用 |
| 原请求示例 | 12 个请求完成：11 个 HTTP 200、1 个预期 HTTP 404 |
| 模型客户端配置 | 初始化成功，TLS 校验开启，自动重试为 0；该检查不发送请求 |
| 无外部模型测试 | 49 项全部通过，包含 4 项本地流水线/原评估入口/查找依赖联调，无跳过 |
| 同条件缺陷复现 | 对比 c068cd3：实体边界、缺参保护、明确拒答、Top-N 四项旧版失败、当前通过；不是模型成绩 |
| 原白盒入口联调 | 模拟模型 + 真实本地 API 下前三题输出 15/15，仅验证执行/评分衔接 |
| 真实模型小样本 | 用户已批准 deepseek-flash：前三题全部答对，单次本地得分 14/15，8 次请求；一题因 >4 秒扣 1 分 |
| 全量白盒 | 200/200 完成；原评分 448.9/1000；完全正确 116/200；P50 3.89s、P95 9.02s |
| 预算与资源 | 含首次中断及获准的 6 题复测共 594/600 请求；完整单轮评估进程峰值 501.69 MiB，不含数据服务 |
| 冻结 SQL 回放 | 49 题原得分全部重现；默认关闭候选改善 25 题、退化 0 题，诊断分 +80.4；无模型请求 |
| 候选 6 题真实复测 | 原评分 14.5 → 21/30；三道丢列题实际触发保护且恢复正确，控制组答案质量保持；不是全量回归 |
| API 资源查找修复 | 07cc224＋5b677ef；受控模型＋真实本地链路下原题与实体替换恢复正确，空查找仍拒答；真实模型结果单独记录 |
| 黑盒 / 正式成绩 | 未运行；黑盒文件缺失，正式模型身份与完整正式聚合未验证 |

真实开发自测记录见 [experiments/20261029_flash_smoke.json](experiments/20261029_flash_smoke.json) 与 [PROGRESS.md](PROGRESS.md)。输入 token 7480、生成 token 650，均按服务返回口径统计；没有请求错误或自动重试。每题耗时分别为 2.81、4.24、3.31 秒。这里只运行前三题一次，不构成完整基线，也没有前后版本对照，不能据此宣称算法收益。

全量结果同时暴露精调丢列和时延损失，因此先固定一个 SQL 质量因素，不同时改变填参调用策略。完整单轮输入 token 464883、输出 token 89221；加上中断尝试后的预算、失败事件和有效性限制见实验报告。候选 6 题真实复测另行记录，不能混入 200 题基线。
