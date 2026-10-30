# CMDB 智能查询系统 — Hackathon

2026-10-30 本地180适配快照：独立工作分支`codex/a180-train150`已完成B v18增量接入与默认导入核验，固定train150连续实测计时/质量均633.3/750，316请求、0失败。复现需按[接入与逐项修复记录](experiments/a180_runtime_port_20261030/README.md)在自己的独立快照展开安装候选库；展开库与原始响应只保留本地。50题保持封存，未验证其泛化表现。

B→A阶段反馈：[180本地接入、首轮训练与单例修复](docs/handoffs/B_TO_A_180_STATUS.md)。本链接为文档交接，未发布的180实现不随文档提交上传。

**180条隔离候选已交接，生产仍198：** [给B的适配与重测说明](docs/handoffs/B_A180_HANDOFF.md) · [候选定义/代码/构建包](experiments/a_family_candidate_20261030/README.md)。B v18需移植R5，旧补丁不可直贴；候选发布不表示上线或已有真实模型得分。

用户查询的未支持输出已统一：[空输出合同](docs/handoffs/EMPTY_OUTPUT_CONTRACT.md)。SDK结果为null、CLI不打印解释；成功零行保留原结果对象，内部诊断和原评分语义保留。

检索第一阶段已发布：[可选文本视图支持与独立验证](docs/handoffs/RETRIEVAL_STAGE1.md)。生产仍198条，180组合候选未启用；检索覆盖恢复不代表参数语义或模型得分通过。

模板参数化候选设计已单独归档：[27族逐族说明及200条映射](docs/template_family_design_20261030/README.md)。当前生产仍为198条；129/181/180均为待验证条件估计，首批实现等待对齐与独立审查，未应用候选补丁。

2026-10-30 严格等价去重：根 `implementation/` 现为 **198条**（054→052、087→086），保留原检索文本权重与旧编号映射；[变更说明与免费回归](experiments/a_strict_dedup_20261030/README.md)。B已统一根目录，与A/C共用这198条模板；下文既有200条记录与中文阅读表均保留原版本含义。没有新模型评分。

2026-10-30 模板阅读资料：新增独立的 [200条中文阅读表](reports/template_classification_20261030/模板分类阅读版.md)、[可筛选 Excel](reports/template_classification_20261030/模板分类阅读版.xlsx) 和 [CSV](reports/template_classification_20261030/模板分类阅读版.csv)。该表冻结在 `ad45ecc1` 的200条模板，区分查询用途、实际实现和未验证的合并候选；原 JSON、技术证据和业务代码保持原样。

基于 Runbook 的 CMDB 查询系统，通过 BM25 检索 + LLM 选择 + LLM 参数填充 + SQL 精调 + 通用执行器，将自然语言问题转化为 CMDB 查询结果。

## 当前目录与入口

开发脚本统一收在`scripts/`，根目录只保留项目说明、依赖/环境配置、安装入口和原始资料。

```text
implementation/       查询实现与评测入口
scripts/              训练、回放、分析、环境检查和交接工具
tests/                训练与语义回归
C/                    扩展诊断和报告工具
datasets/             固定训练划分
experiments/           历史来源与实验记录
docs/                 协作、训练、复现与A交接文档
output-server/        原数据服务
```

常用命令在仓库根目录执行：

```bash
./setup.sh
.venv/bin/python scripts/check_env.py
.venv/bin/python scripts/train_live.py --candidate-flags
.venv/bin/python scripts/train_replay.py --history-v2 --candidate-flags --output reports/new-replay.json
.venv/bin/python -B -W error::ResourceWarning -m unittest discover -s tests -p 'test_training_*.py' -v
```

训练入口默认只预检；真实模型调用仍需显式运行与匹配的新计划。脚本索引见[scripts/README.md](scripts/README.md)，分工见[docs/TEAM.md](docs/TEAM.md)。下文中“统一根目录”指共享项目与实现，开发脚本的实际路径以本节为准。


## 当前统一工作入口（2026-10-30）

B最新交付：固定提交`8a16793`在修订评分器下固定150题连续真实测试640/750，301请求、无时延扣分。main随后合并了远端检索视图/空输出更新，合并版尚无完整真实成绩。C请先读[复测协议](docs/training/C_RETEST_PROTOCOL_V18.md)，使用[无密钥v18配置](configs/train150_v18.env)；时间分析见[profile](docs/training/V18_TIME_PROFILE.md)；已做/可交付/需要A/C的内容见[B交接清单](docs/training/B_AC_HANDOFF_V18.md)。该成绩不是200题或正式比赛总分。

按用户要求，B独立项目已与根目录合并。A/B/C共同使用根目录的同一套模板、检索、匹配、执行与评测，不再进入B开发，也不再复制implementation或数据服务。

| 位置 | 当前用途 |
|---|---|
| `implementation/runbook_items.py`、`runbook_retriever.py` | A的当前198模板、BM25检索（严格去重映射见上方） |
| `implementation/runbook_matcher.py`、`runbook_system.py`、`runbook_aggregates.py` | B的最新选择、填参、SQL精调及默认关闭的聚合候选 |
| `implementation/quick_eval.py`、`blackbox_eval.py` | 主办方原评测入口，逐字节恢复后只读 |
| `C/quick_eval_diagnostics.py`、`C/blackbox_eval_diagnostics.py`、`implementation/eval_report.py` | 独立扩展诊断入口，原评分函数不变 |
| `output-server/` | 唯一的原数据服务和230个数据JSON |
| `scripts/train_live.py`、`scripts/train_replay.py`、`scripts/train_prompt_probe.py` | 固定150训练题的预检、真实诊断、免费回放和提示词探针 |
| `datasets/whitebox_150_50_v1/` | 原字节迁入的划分清单、150训练题与历史；不上传封存50题 |
| `tests/`、`C/tests/` | B的训练/语义测试与C的诊断/报告集成测试 |
| `experiments/`、`docs/training/` | 原实验来源和训练交接文档；历史哈希和旧目录含义保留 |
| `B/` | 仅迁移说明；本机忽略的旧环境、封存文件和历史报告不作为代码来源 |

从仓库根目录准备环境（新机器安装依赖时使用）：

```bash
./setup.sh
.venv/bin/python scripts/check_env.py
.venv/bin/python output-server/data_server.py --host 127.0.0.1 --port 8080
```

另一个终端从同一根目录执行：

```bash
# 免费：只用合成用例/固定训练范围，不调用模型
.venv/bin/python -B -W error::ResourceWarning -m unittest discover -s tests -p 'test_training_*.py' -v
.venv/bin/python -B -W error::ResourceWarning -m unittest discover -s C/tests -v
.venv/bin/python scripts/train_live.py --candidate-flags
.venv/bin/python scripts/train_replay.py --history-v2 --candidate-flags --output reports/train-replay-new.json
```

`scripts/train_live.py`默认只预检，读取本机`.env.local`中列出的模型配置；真实运行需显式`--run`、匹配的新冻结计划与新结果路径。原`implementation/quick_eval.py`/`blackbox_eval.py`读取进程环境变量，已恢复主办方原件，不支持`--report`。C扩展报告功能移至`C/quick_eval_diagnostics.py`、`C/blackbox_eval_diagnostics.py`。模型、特性开关、数据范围和调用预算必须在运行前确定。

本次发布默认显式关闭thinking；旧提交`d912b48`仍是`provider_default`。复测该已提交版本时，普通入口设置`RUNBOOK_THINKING_MODE=disabled`，训练入口显式加`--thinking-mode disabled`（旧CLI会覆盖环境变量）。详见[思考模式复测说明](docs/training/THINKING_RETEST.md)。

开发继续遵守固定150/50隔离：只使用训练集，完整白盒和旧全200测试仅留作历史/明确授权后的最终评估入口，不能用其反馈指导当前调参。全200题和模板示例在划分前已公开，50题不是完全未见的泛化集。黑盒JSON仍缺失。

合并保留根A的稀疏服务器字段修复和C的报告接口；B新增诊断同时可经`query(question, diagnostics=...)`收集，并保留结果中的阶段诊断。旧实验计划不会因搬目录而改写，源哈希漂移时须重新预检，不能把旧成绩当成统一版本成绩。当前合并验证见[交付记录](experiments/unified_20261030/README.md)。训练详细协议与待办见[训练说明](docs/training/TRAINING.md)、[问题清单](docs/training/TRAINING_ISSUES.md)。

官方文件核验：`.venv/bin/python scripts/check_official_integrity.py`。该命令不运行模型或评测。`evaluator.py`采用用户提供的比值容差修订，仅将`100.0`改为`1.0`；`runbook_executor.py`保持官方原件。`quick_eval.py`、`blackbox_eval.py`曾加诊断，现已恢复`d79c316`原件。当前训练入口在运行前强制核验四个文件，失败即停。详见[原件核验与思考模式](docs/training/OFFICIAL_INTEGRITY.md)。

## 以下为既有交接和历史环境记录

下文包含当时的B独立目录、旧分支和旧测试结果；当前工作路径以上方统一入口为准。


当前协作分支为 `main`：按用户于 2026-10-30 的要求，已有协作分支的已提交历史统一合并，之后直接沿 `main` 工作，不为每次提交新建分支。本地B未提交成果继续等待用户明确提交指令；历史记录中的分支名称保留其原时间含义。

> 接手核验（2026-10-29）：本包缺少 `output-server/README.md` 和黑盒 JSON，实际有 200 条模板。原包评分说明存在差异，见文末“最小分支接手记录”。第二轮已构建本地环境，补 TLS 校验和评估入口检查；当前启动方法见“本地环境与第二轮开工”。

第三轮已完成原入口前20题模型基线（75.5/100，53次HTTP请求）及固定无费用实验；当前状态以[实验合同与结果](experiments/round3/README.md)和下方第三轮记录为准，不能将历史“未运行”记录当作当前状态。

整体任务清单、词汇/短语贡献实验、模板价值与精简、A/B/C 分工和验收标准见 [TEAM.md](docs/TEAM.md#整体任务清单)。实验从词、短语、同义词组和检索字段开始，不仅以完整模板为单位。

2026-10-30 集成交付：已同步远端 `aecdc09` 并保留协作提交，重放主 agent 的4个本地验收提交。原20题授权已有完成记录，本次无费用复算仍为 **75.5/100**，没有重新调用模型；该结果属于 `d534a08`，同步后的实现尚无本轮模型评分。当前原入口已支持 `--report 新路径.jsonl`。受保护236文件、当前语法、7个无网络CLI与报告写入检查通过，详情见[本次交付回执](experiments/integration_20261030/README.md)。200模板保留，完整白盒/黑盒与正式总分仍未运行。

## 目录结构

```
hackathon/
├── implementation/              # 最小实现（选手可修改的部分）
│   ├── runbook_system.py        # 主入口，RunbookQuerySystem 类
│   ├── runbook_retriever.py     # BM25 检索器（纯标准库）
│   ├── runbook_matcher.py       # LLM 选择 + 参数填充 + SQL 精调
│   ├── runbook_executor.py      # 通用执行器（选手不可修改）
│   ├── runbook_items.py          # Runbook 模板库
│   ├── evaluator.py             # 评估器（评分规则）
│   ├── blackbox_eval.py         # 黑盒评估脚本
│   └── quick_eval.py            # 白盒评估脚本
├── output-server/               # 数据库环境（模拟 CMDB API）
│   ├── data_server.py           # HTTP 服务（端口 8080）
│   ├── verify_server.py         # 服务验证脚本
│   ├── README.md                # 原清单列出，本包实际缺失
│   └── CI+md数据-脱敏-最终-0924/  # 数据目录（230 个 JSON 文件）
├── CMDB用例集-白盒200.json       # 白盒用例（200 题，含标准答案）
├── CMDB用例集-黑盒100.json       # 原清单列出，本包实际缺失
└── README.md                    # 本文件
```

## 系统架构

```
用户问题
  │
  ▼
┌─────────────────┐
│  BM25 检索器     │  runbook_retriever.py
│  (纯标准库)      │  从模板库检索 Top-K 候选
└────────┬────────┘
         │ 候选列表
         ▼
┌─────────────────┐
│  LLM 选择        │  runbook_matcher.py
│  (DeepSeek API)  │  从候选中选择最匹配的模板
└────────┬────────┘
         │ 选中的模板
         ▼
┌─────────────────┐
│  LLM 参数填充    │  runbook_matcher.py
│  (DeepSeek API)  │  从问题中提取参数值，填充 {{placeholder}}
└────────┬────────┘
         │ 填好参数的模板
         ▼
┌─────────────────┐
│  LLM SQL 精调    │  runbook_matcher.py
│  (DeepSeek API)  │  根据问题调整 SELECT/GROUP BY/JOIN 等
└────────┬────────┘
         │ 最终 api_call + sql
         ▼
┌─────────────────┐
│  通用执行器      │  runbook_executor.py（不可修改）
│  (API + SQLite)  │  调用 output-server API → 内存 SQLite → 执行 SQL
└────────┬────────┘
         │
         ▼
    查询结果
```

## 快速开始

### 1. 启动数据服务

```bash
cd output-server
python3 data_server.py --host 127.0.0.1 --port 8080
```

服务启动在 `http://127.0.0.1:8080`，提供 CMDB 数据查询 API。

### 2. 安装依赖

以下为原包依赖。本机已按用户授权安装到 `.venv`；新环境安装前仍需确认，第二轮记录中提供已验证版本和启动方法：

```bash
pip install openai httpx requests
```

### 3. 运行系统

**交互模式：**
```bash
cd implementation
python runbook_system.py
```

**单次查询：**
```bash
python runbook_system.py "查询region_guian4下所有ECS实例按状态的分布"
```

### 4. 运行评估

**白盒评估（前 N 题）：**
```bash
python quick_eval.py 20
```

**黑盒评估（前 N 题）：**

仅在评测环境具备实际黑盒文件时运行；当前包缺失该文件：
```bash
python blackbox_eval.py 100
```

**通过评估器直接运行：**

此入口同样固定读取黑盒文件，当前包无法进行该评估：
```bash
python evaluator.py 30
```

## 评分规则（当前本地 SDK）

本节按 `implementation/evaluator.py` 的实际实现核对（2026-10-30），评分器保持原样。根目录 `quick_eval.py` / `blackbox_eval.py` 每题运行 **1 次**；目前没有自动执行正式重复平均、黑白盒加权或模板数量计分。原包 README 的“5次平均、5秒/10秒扣分、API条件缺失−1、60模板上限”与当前实现不符，仅在文末差异表保留作历史对照。

### 计分规则

| 情况 | 得分 | 说明 |
|------|------|------|
| 答案完全正确 | +5 | 行数匹配且所有行值匹配 |
| 部分正确 (≥50%) | round(5 × ratio, 1) | 按匹配比例得分 |
| 答案错误 (<50%) | -1 | 匹配率低于 50% |
| 不回答（弃权） | 0 | 系统未产出或未命中 runbook |
| 执行错误 | -1 | 已命中模板的输出包含 error，之后仍应用超时扣分 |
| API 条件不合规 | 0 | 标准有有效条件字段，而系统没有有效API条件；提前返回 |

### 超时扣分（取最高档，不叠加）

| 响应时间 | 扣分 |
|----------|------|
| `t ≤ 4` 秒 | 0 |
| `4 < t ≤ 6` 秒 | -1 |
| `t > 6` 秒 | -3 |

代码先判断 `t > 6`，再判断 `t > 4`，只扣最高档。因此恰好4秒不扣分，恰好6秒扣1分；超过6秒扣3分，不是再叠加1分。答案正确时分别得5、4、2分；答案错误的−1分也会继续扣到−2或−4分，不保底为0。

例外：系统未产出、未命中模板，以及API条件不合规，评分器提前返回0分，不进入超时扣分。SQL结构检查仅作提示，不另外扣分。计时使用传入评分器的原始秒数，不能用控制台四舍五入后的显示值判断边界。

### 软检查

- **SQL 结构检查**：检查 GROUP BY / COUNT / SELECT 字段是否与标准答案一致，不覆盖答案分数，仅在 reason 中提示。
- **API 条件检查**：原实现检查有效条件字段是否存在；标准有而系统没有时按0分处理，不是−1分。它未完整核对条件字段和值是否与标准一致，开发时仍须保证实际查询语义正确。

### 本地分数与正式总分

本地输出为本轮逐题分数之和，得分率为 `总分 / (实际题数 × 5) × 100%`。它未包含数量分，也不是正式总分。已记录官网规则与原README的数量、重复次数和加权差异见文末“规则差异”；不能再按原说明的60条上限和50%封顶解释当前本地结果。

## 用例格式

用例 JSON 文件结构：

```json
{
  "cases": [
    {
      "case_id": "CMDB-001",
      "question": "当前所有ECS实例按状态的分布情况",
      "query_method": "查 CLOUD_VM_NOVA 全表，按 status 分组 COUNT(*)",
      "api_call": {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "region_guian4",
                "operator": "equal"
              }
            }
          ]
        }
      },
      "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY status",
      "answer": {
        "columns": ["status", "count"],
        "rows": [
          {"status": "active", "count": 1981},
          {"status": "unknown", "count": 861}
        ],
        "row_count": 5
      }
    }
  ]
}
```

## 数据服务 API

### 查询 Instance 数据

```
GET http://127.0.0.1:8080/rest/hackthon/db/instances/{CI_NAME}?pageNo=1&pageSize=10000
```

### 查询 Relation 数据

```
GET http://127.0.0.1:8080/rest/hackthon/db/relations/{CI_NAME}?pageNo=1&pageSize=10000
```

### 条件筛选

支持的 operator：`equal`（等于）、`contain`（包含）、`in`（在列表中）

```
&condition={"constraint":[{"simple":{"name":"logicalRegionName","value":"region_guian4","operator":"equal"}}]}
```

### Schema 查询

```
GET http://127.0.0.1:8080/rest/hackthon/db/schema/{CI_NAME}
```

### CI 名称映射

SQL 中使用 `CLOUD_` 前缀的原始表名（如 `CLOUD_VM_NOVA`），执行器内部自动映射到脱敏名（如 `VM_NOVA`）查询 API。本包缺少 `output-server/README.md`，实际映射见 `runbook_executor.py` 的 `_pairs`（只读）。

## LLM 配置

系统使用 DeepSeek API 进行模板选择、参数填充和 SQL 精调，运行前必须提供 API Key。

- **模型**：DeepSeek `deepseek-chat`
- **Base URL**：`https://api.deepseek.com`
- **API Key**：通过环境变量 `DEEPSEEK_API_KEY` 提供

```bash
# Linux / macOS
export DEEPSEEK_API_KEY="your-api-key-here"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="your-api-key-here"

# Windows CMD
set DEEPSEEK_API_KEY=your-api-key-here
```

- **SSL（更正）**：当前分支已在 `runbook_matcher.py:get_llm()` 开启证书和主机名校验，可通过 `SSL_CERT_FILE` 指定可信 CA；无效 CA 会在启动时失败。原始基线提交 `d79c316` 中的 `verify=False` 保留于历史，当前分支已修正。执行器保持原文件不动，其数据服务地址为本地 HTTP。

## 关键文件说明

| 文件 | 可修改 | 说明 |
|------|--------|------|
| `runbook_system.py` | 是 | 主入口，组装检索→匹配→执行流程 |
| `runbook_retriever.py` | 是 | BM25 检索器，纯标准库实现 |
| `runbook_matcher.py` | 是 | LLM 选择 + 参数填充 + SQL 精调 + 弃权策略 |
| `runbook_items.py` | 是 | 模板库定义（上限 60 条） |
| `runbook_executor.py` | **否** | 通用执行器，选手不可修改 |
| `evaluator.py` | **否** | 评估器，选手不可修改 |
| `blackbox_eval.py` | 是 | 黑盒评估脚本 |
| `quick_eval.py` | 是 | 白盒评估脚本 |

## 最小分支接手记录

### 来源、边界与实际文件

目标仓库为 [hackathon-p13-2](https://github.com/getm0ss1moving/hackathon-p13-2)，首次检出为空仓库。仅从用户指定的本地 `hackathon` 出题者实例复制原文件，未读取旧 GitHub 仓库。244 个原文件逐文件 SHA-256 校验一致，保存为原始基线提交 `d79c316`，再创建 `simple/official-starter`；首轮采用“不自动合回main”的历史约定，已被2026-10-30用户要求合并并沿main工作的指令更新。首轮提交 `ef1745c` 仅新增 `AGENTS.md`、`TEAM.md` 并补充本 README；第二轮修改见文末。

- 实际存在：8 个 implementation Python 文件、3 个 output-server Python 文件、白盒 200 题、230 个数据 JSON、`背景知识.md`。
- 实际缺失：`output-server/README.md`、`CMDB用例集-黑盒100.json`；没有依赖清单文件。`blackbox_eval.py` 存在不等于黑盒数据可用。
- 模板是 `runbook_items.py` 内的 Python 列表 `RUNBOOK_ITEMS`，实际 200 条、ID 唯一，包含 `id/name/description/resources/examples/api_call/sql`，180 条另有 `default_params`。
- 136 条模板含单个 API 对象，64 条含 API 列表，最多 5 步，19 条含 `from step` 占位符。已有题号式名称、具体实体示例和默认值保留作基线，后续不能据此新增题号路由或答案硬编码。
- 只改模板、检索、匹配、流程、两个评估入口及文档。执行器、评分器、数据服务、全部数据与测试用例保持原样；不新建框架、适配层、中间表示或审计系统。文件分工见 `TEAM.md`。

### 代码实际调用链

1. `RunbookQuerySystem.__init__()` 加载模板、构建 BM25 索引，并通过本地 schema API 预热字段缓存；该预热在各评估入口的单题计时之前。
2. `query()` 调用 `match_runbook()`：检索器按 examples/description 分词，BM25 排序、覆盖率门禁和 strong/weak 分层，最多返回 5 个 strong 加 10 个 weak 候选。
3. 匹配器调用 LLM 选择一个模板并深拷贝；返回 0/越界时可能退回 strong top1，资源/字段门禁也可能弃权。当前实例没有选择多模板并行组合的实现。
4. 有占位符时再调用 LLM 提取参数，进行规范化、自动补参及默认值回填，清理空条件，保留交给执行器处理的 `from step`。无占位符模板直接返回，跳过后续精调和清理。
5. 有参数且通过门禁的模板调用 LLM 精调 SQL，并校验 SELECT、WHERE、表集合等；可能弃权或保留原 SQL。原链路包含 SQL 精调，不应删除。通常每题为 1～3 次逻辑模型调用，异常重试可能增加请求。
6. 原 `execute()` 接收 `api_call + sql`，顺序调用单个/多步 API，解析上一步结果占位符、自动分页，补查 SQL 引用的表，载入内存 SQLite 后执行 SQL。进程内 API 缓存会影响后续题目的耗时。
7. `quick_eval.py` / `blackbox_eval.py` 对每题计时并调用原 `evaluate_case()`；`evaluator.run_evaluation()` 也只查询每题一次。评分按弃权、错误、API 条件、答案比对和时间扣分处理；多结果列表在本地被合并比较，并非逐子问题独立计分。

### 规则差异（核验日期：2026-10-29）

官方来源：[云运维场景智能问数查询优化](https://www.chaspark.com/#/races/competitions/1326646677767008256)，重点为 §3、§7、§8。网页说明评分细节以 SDK 评估器为准；本包评估入口没有实现完整正式聚合，仍须保留差异。

| 项目 | 官方赛题 | 原 README | 本包实际实现 |
|---|---|---|---|
| 每题重复 | 2 次平均 | 5 次平均 | 三个评估入口均每题 1 次 |
| 超时 | >4s 扣 1；>6s 扣 3，取最高档 | >5s 扣 2；>10s 扣 3 | 与官方摘要相同；弃权/API 条件失败提前返回，不扣时延分 |
| API 条件缺失 | 标准有条件、系统无条件得 0 | 得 −1 | 得 0；只检查系统是否存在非空有效条件字段，不核对字段/值与标准相同 |
| 模板数量 | 目标 150，数量分 `150−N` | 上限 60，少一条加 1，超量封顶 50% | 无数量计分、封顶或数量校验；当前 N=200，按网页公式数量分为 −50，此项未进入本地输出 |
| 最终总分 | 黑盒原始分×70%＋白盒原始分×30%＋数量分，不归一化 | 未说明 | 仅输出当前用例范围得分，无两次平均、黑白加权或数量调整 |
| 黑盒 | 100 题，选手不可见 | 列为本地文件 | 文件实际缺失；黑盒入口和 evaluator CLI 无法完成评估 |
| 模板提交 | JSON 数组；单条≤4KB，嵌套≤4层 | Python 模板库，仅写数量上限 | Python 列表；未导出提交 JSON、未做正式容量校验 |
| 模型/环境 | 模型统一提供、不可更换；CPU、内存≤2GB、索引≤60s、检索≤200ms；有禁网络/外部模型文件要求 | 外部 DeepSeek API | 默认外部 DeepSeek；隔离评测与统一模型的具体接入边界待确认 |

本地 SQL 结构检查仅提示，不覆盖答案分。`main` 原 `quick_eval.py` 的 `avg` 采用 `total_score/N*10`，满分只显示 50%；当前分支第二轮已将两个入口统一为 `pct=总分/(实际题数×5)×100`，只修展示，不修改评分函数。不得把本地输出叫正式成绩。

容量初查：按紧凑 UTF-8 JSON 序列化，单条最大 1604 字节；按“每个 dict/list 容器算一层”计，单条最大深度 7，含外层数组为 8。与官方深度≤4存在提交风险，具体深度算法和多步 API 表达需确认；本轮不改模板结构。官网 §3.4/§7 强调 BM25 限制，§8 另提决策树小模型；当前继续使用 BM25，不自行扩大技术范围。

### 首轮运行条件与检查记录

首轮使用系统 Python 3.9.6，当时缺少 `openai`、`httpx`、`requests`，`DEEPSEEK_API_KEY` 未设置，未安装依赖或调用模型。第二轮已用 Python 3.11.16 构建 `.venv`，见文末；后续已检测到本机密钥配置，API 连接有效性和真实模型评分尚未验证。

从仓库根目录启动原数据服务（不需要模型）：

```bash
python3 output-server/data_server.py --host 127.0.0.1 --port 8080
```

另一个终端运行原请求示例：

```bash
python3 output-server/verify_server.py
```

完成后在服务终端按 Ctrl-C 关闭。本地 API 路径为 `/rest/hackthon/db/instances/{CI}`、`relations/{CI}` 和 `schema/{CI}`；注意原路径拼写为 `hackthon`。数据条件支持 equal/contain/in，数据服务支持 AND/OR；执行器会重新组装条件，多条件按 AND 发送。映射查执行器 `_pairs`，接口细节查原服务代码；不补造缺失的服务 README。

完整查询的准备顺序：创建虚拟环境并安装依赖、开启 TLS 校验、在本机配置密钥、确认调用范围及费用。环境与 TLS 已完成，本机密钥配置已检测到；连接有效性和真实评分仍待实际运行。密钥不能发送到聊天或写入仓库。激活 `.venv` 并确认当轮调用范围后，从根目录运行：

```bash
python implementation/runbook_system.py "当前所有ECS实例按状态的分布情况"
python implementation/quick_eval.py 20
```

虚拟环境启用时使用其 `python`。`quick_eval.py N` 取白盒文件前 N 题，要求 1≤N≤实际题数（本包为 200），第二轮已增加范围检查。`blackbox_eval.py N` 与 `evaluator.py N` 都读取缺失的黑盒 JSON，当前不作为可执行评分命令推荐。

### 首轮实际检查与下一步

| 检查 | 实际结果 |
|---|---|
| 原文件复制完整性 | 复制时 244 个文件逐文件 SHA-256 相同；除 README 外的原文件与 main 无差异 |
| Python 语法 | 11 个文件通过 AST 解析；未生成测试文件或改业务代码 |
| 原数据服务 | 已运行；加载 63 张表、186,152 条记录；已关闭临时服务 |
| 原 verify_server | 已执行原 main 的 12 个请求，补充检查 HTTP 状态与分页字段；11 个 200、1 个预期 404；schema 请求 200 |
| BM25 检索 | 已执行 200 个白盒问题；索引约 2.41ms，单次中位数约 1.44ms，P95约1.94ms，最大约2.24ms；仅本机一次诊断，非正式性能结果；有候选不代表选择正确 |
| 原评分函数行为探针 | 6 个合成断言通过，验证 4s/6s 边界、缺 API 条件及弃权提前返回；不是答题成绩 |
| 白盒完整查询评分 | 未运行；尝试原 `quick_eval.py 1` 在导入阶段因缺少 httpx 退出，无模型请求、无用例评分 |
| 黑盒评分、官方两次平均及最终加权 | 未运行；黑盒文件缺失，正式环境未提供 |
| 正式资源/泛化验证 | 未运行；未验证总内存、统一模型、实体替换及正式模板深度校验 |

首轮之后先恢复可运行环境，再建立真实模型白盒基线；从实际错误中只选一类失败优化，沿用原评分函数比较得分、耗时和模板数量。A/B/C 已于第二轮认领，见 `TEAM.md`。

## 本地环境与第二轮开工（2026-10-29）

工作目录：`/Users/duanzeyu/Downloads/hackathon-p13-2`，分支 `simple/official-starter`。本机 `.venv` 已就绪，不进 Git。系统 Python 3.9.6 使用 LibreSSL 2.8.3，最终环境改用本机已有的 `/opt/homebrew/bin/python3.11`，未安装或替换系统 Python，证书校验一直开启。

已验证环境：Python **3.11.16**、OpenSSL **3.6.3**、`openai==2.48.0`、`httpx==0.28.1`、`requests==2.32.5`；`python -m pip check` 通过。相同 Python 环境下复建所需的最小命令为：

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install openai==2.48.0 httpx==0.28.1 requests==2.32.5
source .venv/bin/activate
```

已有环境只需执行最后一行。其他机器可用其带受支持 OpenSSL 的 Python 3.11；不复制 `.venv`。安装时仍按用户要求先确认，不使用关闭 TLS 校验的参数。

启动原数据服务：

```bash
cd /Users/duanzeyu/Downloads/hackathon-p13-2
source .venv/bin/activate
python output-server/data_server.py --host 127.0.0.1 --port 8080
```

另一个终端验证，无模型调用、无需密钥：

```bash
cd /Users/duanzeyu/Downloads/hackathon-p13-2
source .venv/bin/activate
python output-server/verify_server.py
python implementation/quick_eval.py --help
```

原样的 `evaluator.py` CLI 没有这些新入口检查，且读取缺失的黑盒文件，当前不用于启动评估。数据服务可在其终端按 Ctrl-C 关闭。

本机 `.env.local` 已检测到密钥配置，未显示其内容；该文件不入库，现有脚本不会自动加载它，运行时需安全读入进程环境。其他终端也可直接配置 `DEEPSEEK_API_KEY`，并确认模型与当轮调用范围。例如在已激活的终端隐藏输入，不把密钥写入命令历史：

```bash
read -s DEEPSEEK_API_KEY
export DEEPSEEK_API_KEY
```

企业 CA 可用 `SSL_CERT_FILE` 指向实际可信证书文件；密钥和 CA 配置不要提交。网页统一模型与此本地 DeepSeek 配置的正式接入差异仍待确认。

本轮只处理“基线无法可靠启动或报告”这一类问题：

| 分工 | 实际交付 |
|---|---|
| A | 只读模板/检索诊断，未修改模板或检索器。200 个白盒问题只有 198 个不同文本，全部出现在模板示例中；对应模板候选保留 200/200、top1 为 197/200，不能当答题正确率。168 个非官方实体替换变体候选保留 168/168，未验证填参或答案。发现两组执行结构重复模板，尚未合并 |
| B | 匹配器启用 TLS 证书/主机名校验，支持可信自定义 CA；系统初始化检查缺密钥，避免进入误记为弃权的评估；未改匹配算法或 SQL 精调 |
| C | 两个评估入口检查 N、数据文件、密钥、依赖及本地 schema 服务就绪；启动失败不发模型查询，未处理异常中止并报告已完成题数；普通业务 error 仍交原评分器。百分比按实际题数计算，仍为每题单次诊断 |

实际验证：

- B 在真实依赖环境中做 6 项零网络检查，覆盖 TLS 默认值/可信 CA/无效 CA、缺密钥、客户端复用及输出不泄露测试密钥。
- C 用真实未改评分器做 52 个无网络 mock 场景，包含 26 个数据服务失败场景；失败场景的模型查询均为 0。
- 集成执行 7 个实际 CLI 边界检查、11 个 Python 文件语法检查及依赖检查，全部通过。
- 原数据服务实际加载 63 张表、186,152 条记录；原验证脚本 12 个请求和 schema 检查通过。测试结束后临时服务已关闭。
- 使用固定 LLM 响应做流程冒烟测试：真实 API/执行器结果与一个公开用例一致；另用合成模板验证选择、填参、SQL 精调仍经过 3 次逻辑模型步骤。外部网络受阻断，模型请求数为 0；这不是模型准确率或答题基线。
- 执行器、评分器、服务、原数据和用例，以及本轮模板/检索器均与 `main` 无差异。未新增框架或测试文件。

截至第二轮，真实模型白盒评分、黑盒评分和官方最终成绩均未运行；第三轮的20题本地模型诊断已完成，见下文。


## 第三轮集成交付（2026-10-29）

本轮从交接 `b4deba0` 快进同步到 `d534a08`，保留新增C工作区，不审查或覆盖；根8个业务文件没有修改。主 agent 认领协作文档、根忽略规则和独立 `experiments/round3/`，交付完整输入哈希、冻结问题组、检索/能力复核脚本与实测报告。

用户最终批准先跑20题，硬上限为60次实际模型HTTP请求（包括重试）。使用根原 `quick_eval`、原执行器和原评分器，原文件前20题各一次，**75.5/100，53次请求，全部200**；P50为2.498s，P95为2.871s，>4s为0题。输入50,326 token，输出1,179 token。按分数为5分15题、部分正分1题、负分2题、弃权2题；其中1题虽得5分，原reason仍为“部分正确(100%)”，详见报告。没有继续调用剩余额度。

根代码请求 `deepseek-chat`，API响应全部报告 `deepseek-flash`；未主动更换请求模型。该接入未被确认为官方统一模型，不能称正式成绩。黑盒文件仍缺失，全白盒模型200题和正式重复/加权仍未运行。密钥仅从本机安全读取，TLS校验开启，认证配置未入库。

无费用部分完成189个固定问题组（开发166、回归34），222条输入×11条件共2,442次检索；12条改写只召回关联标签11/12、top1为5/12，资源词屏蔽进一步降至10/12。17组参考查询及固定模板能力复核答案均通过，4条实体替换预期全部由原执行器重新计算。片段使用多候选标签，结果不冒充完整题成绩。原文屏蔽计数词的top1增加没有支撑生产删词，本轮200条模板全部保留。

优先交B的失败类为SQL输出形状退化：`CMDB-020/022`固定实测API、只恢复原模板SQL后离线答案比较都恢复为5分；原模型基线仍保留75.5。两次弃权和异常状态映射另列待复核。后续由B处理其认领文件、C补阶段诊断/验证；主agent不并发覆盖。完整合同、结果字段、未验证项、原始JSON/CSV和无费用复现命令见[第三轮报告](experiments/round3/README.md)。执行器、评分器、原数据服务、数据与用例仍与原始提交一致。

本轮实验运行后，共享工作区中A认领的检索器出现新的未提交修改；主agent保留且未纳入本轮提交。实测代码以manifest哈希为准；无费用复现入口会先校验冻结输入，发现变化则停止保护旧结果。同期其他协作者的新提交均保留，本轮不合并其独立实验成绩。


## A 文档词频缓存独立验收（2026-10-29）

A 已交付生产提交 `1928514`，父提交 `1a72007`。主 agent 按本轮协调范围独立检验，只读取 A 冻结输入及交接报告；没有运行 A 的旧脚本或覆盖其目录。独立证据在 [result.json](experiments/a_cache_acceptance_20261029/result.json)，复现脚本为 [verify.py](experiments/a_cache_acceptance_20261029/verify.py)。本轮仅做本地交接，不推送远端、合并main或比赛提交。

**PASS**：`3b99aaf` 与 `1a72007` 的根检索器和模板逐字相同；`1928514` 相对父提交只改根检索器，将400篇索引文档的Counter移到构建期复用，没有问题缓存、词汇/权重/门禁或模板变化。固定1,075条输入（SHA-256 `37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0`）×top_k None/0/3/5/10/15，共6,450次逐字段比较，ID、顺序、tier、score、coverage全等；补空索引、无文本/空token文档、重复ID/并列小索引、空/标点/陌生词/数字/混合查询和非默认构造参数，共2,016次边界比较也全等。400个缓存Counter与各文档词频一致，查询前后索引文档和缓存指纹未变。

根调用点只构建索引和调用retrieve；其他根模块AST没有 `_docs`/`_doc_tfs`/`tokens` 属性引用，未发现运行期改写索引文档。此结论限于当前根Python代码，不保证未来通过反射或私有属性修改仍兼容。

3轮随机题序、配对交错次序、种子20261029，每版3,225次查询；单次计时只含retrieve，预热每版10条。独立本机测量：中位 1.085625→0.833458ms，P95 1.466458→1.217042ms，最大 1.926417→1.756209ms。索引增量分配中位 692062→901334字节，增加209272字节（约204.4KiB）。索引构建原始计时启用了tracemalloc，开销较大，见JSON原值；这些分配量不含已加载模板、LLM、服务或全系统RSS。毫秒级检索收益和输出全等不能称为官方得分提高，Mac测量不证明正式资源达标。

原始基线 `d79c316` 的236份固定文件（执行器/评分器、output-server原文件/数据、白盒）在本轮开始和结束均逐字节SHA-256一致。评分器为 `c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22`；执行器为 `4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92`。本轮未导入这两个模块，没有monkeypatch、重设BASE_URL、清空/注入执行器缓存或替换评分结果。

**NOT RUN**：真实模型选择/填参/SQL精调与端到端评分、官方黑盒及总分、词汇/别名/198模板合并的模型配对。生产仍200模板，P2/P3整体任务不勾完；旧20题75.5/100属于旧根代码基线，不能归给A新版本。A历史4题固定选择20/20仅保留历史诊断，不作为本轮严格验收证据；本轮未运行旧capability.py，也未使用剩余7次模型额度。

验收脚本首轮因Git中文路径转义把固定文件计成5份而失败，已改为NUL分隔读取后通过；初次完整失败记录保留于JSON的prior_attempts，不是生产检索失败。最终主检查失败数为0，全部候选原始输出、边界输出、配对时延和构建分配原值均保留于同一JSON。复现命令：

```bash
cd /Users/duanzeyu/Downloads/hackathon-p13-2
.venv/bin/python experiments/a_cache_acceptance_20261029/verify.py
```

脚本只加载Git内存快照和A本机未跟踪的冻结queries.json，需保留该输入；不会读取密钥、安装依赖、启动服务或进行网络调用。重跑会更新本轮独立JSON，不覆盖A或round3产物。下一步由C审阅独立证据和字段；词汇/合并方案仍按文件认领和明确预算另行做真实选择器/全链路配对，不把缓存验收扩成B/C业务改动。

## A 本轮最终交接与严格能力证据只读复核（2026-10-29）

本轮在 `9510f0a` 后只读审查 A 的29项完成矩阵、`strict_capability.py`、严格JSON/JSONL及HANDOFF必要字段，没有重跑检索、性能、模型、模板执行或评分。根业务代码、旧round3和9510f0a独立证据保持原样；本次只追加README/TEAM并做新本地提交，不推远端。

**PASS（限定范围）**：本轮词/token、字段与候选上限的免费诊断交付及保守决策可以关闭；唯一生产改动为 `1928514` 的文档词频缓存，已由 `9510f0a` 独立验收8,466次逐字段比较和本机配对资源记录；两对重复模板在4个原题上的新增严格固定选择能力检验可关闭。三项都不等于整个A或P2-A/P2-B/P3完成，29项矩阵仅用于对照，不自动勾完TEAM整体清单。

严格结果的只读复核：原始JSONL为11事件，其中8个worker的PID各异，stdout解析值与保存record逐项一致，返回码均0且stderr为空。每条输入的原模板/内存合并模板、核实参数及原参考用例与当前冻结原文件一致；填后完整API与参考条件一致，SQL保持原模板。原生输出与送评分器的结果字段未被替换，4组native_output逐项全等，行数分别2、2、47、47；其行值也与原标准答案逐行核对一致。日志分数按两版分别求和均为20/20，仅证明4题固定能力，不是实际模型选择、填参、精调或官方总分。

脚本源码/AST核对未发现对executor/evaluator全局的赋值、动态替换或_cache访问/清空；原模块从根路径自然导入，BASE_URL只读校验默认127.0.0.1:8080。服务记录显示仅关闭自启原服务，结束监听为空，本轮只读进程检查也未发现8080监听；没有新增API或服务请求。旧capability.py及旧4题20/20仍排除严格验收，新严格证据另列。原HANDOFF及其58项历史产物的现有哈希全部一致，没有覆盖、补造或重跑旧结果。

本机未跟踪严格证据：`.a-vocab-gt4hyfg2/strict_capability_raw.jsonl` SHA-256为 `69ef2a4ad0431af01e542a37b68b7c3b03f685f7aa08332c832981fc23d5c6d6`；`strict_capability_result.json`为 `4bf890f58b7e1a0f8b774b40d58b14616d81b446f461c1e6fe02416075b47bce`。236份原始保护文件开始/结束均与d79c316一致；按“相对路径→SHA-256、键排序、紧凑UTF-8 JSON”所得整体清单哈希前后均为 `28993ff1f813e7a1b20c274ee9e07bca09d9c6f84a07bb8114fd09da2962ebb2`。评分器仍为 `c7bc000d71a766f5dec3c2747fc84224fb85f30d513d7b89ade8ea881aa61f22`，执行器仍为 `4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92`。

**FAIL：本次证据/边界核对未发现不符。NOT RUN/待依赖**：真实选择器、填参、SQL精调、合并受影响题配对及完整评分均未获新调用范围；全模板参数/独有或替代能力、所有实体派生答案重建与未见验证未完成；官方统一模型、深度/提交格式、正式资源环境和缺失黑盒仍未解决。生产N=200，按已记录官网公式数量项150−N为−50，未有新版本正式WB/BB成绩，不能据缓存或4题等价推断总分增加；旧20题75.5/100仍归旧根代码基线，本轮未使用剩余7次额度。

另只读确认 `rb_130` 第3步声明 `id from step 1`，而原执行器仅传上一步记录；这是静态路径风险，尚未证明实际扣分，交B/C后续核验，不修改执行器。下一步按原文件认领、明确预算与受影响问题集开展选择器/完整链路验证。

归档限制：9510f0a的复现脚本依赖本机A未跟踪目录中的queries.json，当前可在本机复现；A严格证据及上述历史产物也尚未入远端。本轮不新增归档目录或修改冻结证据，转移环境前应保存冻结输入和A产物，不能假称远端已包含。本轮协调在此收束，后续新范围另行认领。

## 2026-10-30 同步与主 agent 交付

在指定根目录将远端 `1928514..aecdc09` 的17个协作提交正常同步，只重放4个主 agent 的未推送提交；得到 `c37442f`、`ee361d4`、`8bdd627`、`01f48f5`。这4个哈希分别替代旧本地 `9510f0a`、`5755b93`、`4b8b5e8`、`6c8f845`，历史结果中记录的旧哈希及原始内容不改写。没有覆盖他人目录、未跟踪文件、业务源码或原数据，没有强推或合并main。

本次只补主 agent 交付文件和有界复核，结果见[receipt.json](experiments/integration_20261030/receipt.json)。原保存20题的评分字典、顺序、53次HTTP记录和51,505 token重新核对一致；这是旧输出的评分复算，不是同步后版本的新模型成绩。报告入口以旧输出在临时目录检验，完整报告20题、中止报告只记已完成1题且不补零，已有文件不能覆盖；临时报告已移除。执行器、评分器和236份原始固定文件不变，本次没有服务、API、模型或安装操作。

为解除已知交付依赖，把缓存验收唯一必需的冻结 `queries.json` 副本放到 [queries.json](experiments/a_cache_acceptance_20261029/queries.json)，SHA-256仍为 `37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0`，1,075条。原A本机输入不动，未归档A其他未跟踪目录。自有 `verify.py` 只改输入位置、历史版本前置校验和新报告防覆盖；旧result.json、耗时和8,466次比较结论均原样保留，未重跑性能。当前模板已变化，该历史脚本应提前退出2；新报告默认 `result-rerun.json`，可用 `--output` 指定不存在的新路径。这不表示历史严格能力等其他未跟踪产物全部已归档。

最新根模板、B流程及C报告接入来自协作提交，已保留。本次不接管其优化，也不把历史词汇/模板诊断称作新版本得分。后续按TEAM认领推进B的选择/参数/SQL失败归因与C的配对回归；任何新模型运行另定范围和上限。全模型200题、缺失黑盒、官方模型接入/计时/模板深度与组合计分仍待解决，整体P1/P2/P3/P5不因本次交付而勾完。
