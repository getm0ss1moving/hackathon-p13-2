# CMDB 智能查询系统 — Hackathon

基于 Runbook 的 CMDB 查询系统，通过 BM25 检索 + LLM 选择 + LLM 参数填充 + SQL 精调 + 通用执行器，将自然语言问题转化为 CMDB 查询结果。

> 接手核验（2026-10-29）：本包缺少 `output-server/README.md` 和黑盒 JSON，实际有 200 条模板。原包评分说明存在差异，见文末“最小分支接手记录”。第二轮已构建本地环境，补 TLS 校验和评估入口检查；当前启动方法见“本地环境与第二轮开工”。

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

## 评分规则（原包说明，差异见文末）

以下保留原说明作对照，不代表当前 `evaluator.py` 的全部实际行为或正式计分流程。

评分规则定义在 `implementation/evaluator.py` 中，每题满分 5 分，每题测试 5 次取平均。

### 计分规则

| 情况 | 得分 | 说明 |
|------|------|------|
| 答案完全正确 | +5 | 行数匹配且所有行值匹配 |
| 部分正确 (≥50%) | round(5 × ratio, 1) | 按匹配比例得分 |
| 答案错误 (<50%) | -1 | 匹配率低于 50% |
| 不回答（弃权） | 0 | 系统未产出或未命中 runbook |
| 执行错误 | -1 | 运行时异常 |
| API 条件不合规 | -1 | 标准答案有条件但系统无条件 |

### 超时扣分（取最高档，不叠加）

| 响应时间 | 扣分 |
|----------|------|
| > 10 秒 | -3 |
| > 5 秒 | -2 |
| ≤ 5 秒 | 0 |

### 软检查

- **SQL 结构检查**：检查 GROUP BY / COUNT / SELECT 字段是否与标准答案一致，不覆盖答案分数，仅在 reason 中提示。
- **API 条件检查**：如果标准答案的 api_call 包含 condition，系统的 api_call 也必须包含 condition（不能全量 load + SQL 过滤），否则 -1 分。

### 模板数量约束

- 模板上限 60 条，每少 1 条加 1 分
- 超过 60 条封顶满分的 50%

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

- **SSL（更正）**：当前分支已在 `runbook_matcher.py:get_llm()` 开启证书和主机名校验，可通过 `SSL_CERT_FILE` 指定可信 CA；无效 CA 会在启动时失败。`main` 原实例中的 `verify=False` 保留于基线，当前分支已修正。执行器保持原文件不动，其数据服务地址为本地 HTTP。

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

目标仓库为 [hackathon-p13-2](https://github.com/getm0ss1moving/hackathon-p13-2)，首次检出为空仓库。仅从用户指定的本地 `hackathon` 出题者实例复制原文件，未读取旧 GitHub 仓库。244 个原文件逐文件 SHA-256 校验一致，保存为 `main` 基线提交 `d79c316`，再创建 `simple/official-starter`；不自动合回 `main`。首轮提交 `ef1745c` 仅新增 `AGENTS.md`、`TEAM.md` 并补充本 README；第二轮修改见文末。

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

首轮使用系统 Python 3.9.6，当时缺少 `openai`、`httpx`、`requests`，`DEEPSEEK_API_KEY` 未设置，未安装依赖或调用模型。第二轮已用 Python 3.11.16 构建 `.venv`，见文末；密钥仍未配置，模型 API 未调用。

从仓库根目录启动原数据服务（不需要模型）：

```bash
python3 output-server/data_server.py --host 127.0.0.1 --port 8080
```

另一个终端运行原请求示例：

```bash
python3 output-server/verify_server.py
```

完成后在服务终端按 Ctrl-C 关闭。本地 API 路径为 `/rest/hackthon/db/instances/{CI}`、`relations/{CI}` 和 `schema/{CI}`；注意原路径拼写为 `hackthon`。数据条件支持 equal/contain/in，数据服务支持 AND/OR；执行器会重新组装条件，多条件按 AND 发送。映射查执行器 `_pairs`，接口细节查原服务代码；不补造缺失的服务 README。

完整查询的准备顺序：创建虚拟环境并安装依赖、开启 TLS 校验、在本机配置密钥、确认调用范围及费用。前两项在第二轮已完成，模型调用尚未获准。密钥不能发送到聊天或写入仓库。激活 `.venv` 并获得调用授权后，从根目录运行：

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

模型调用尚未授权、密钥尚未配置。需要调用时，由用户在运行终端本机配置 `DEEPSEEK_API_KEY` 并确认模型与调用范围。可在已激活的终端用以下命令隐藏输入，不把密钥写入文件或命令历史：

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

真实模型白盒评分、黑盒评分和官方最终成绩均**未运行**。下一步等待本机密钥、模型接入与有限调用授权后建立真实白盒基线，再选一类实际失败优化。
