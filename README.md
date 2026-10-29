# CMDB 智能查询系统 — Hackathon

基于 Runbook 的 CMDB 查询系统，通过 BM25 检索 + LLM 选择 + LLM 参数填充 + SQL 精调 + 通用执行器，将自然语言问题转化为 CMDB 查询结果。

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
│   ├── README.md                # API 接口文档
│   └── CI+md数据-脱敏-最终-0924/  # 数据目录（230 个 JSON 文件）
├── CMDB用例集-白盒200.json       # 白盒用例（200 题，含标准答案）
├── CMDB用例集-黑盒100.json       # 黑盒用例（100 题，含标准答案）
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
python data_server.py
```

服务启动在 `http://127.0.0.1:8080`，提供 CMDB 数据查询 API。

### 2. 安装依赖

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
```bash
python blackbox_eval.py 100
```

**通过评估器直接运行：**
```bash
python evaluator.py 30
```

## 评分规则

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

SQL 中使用 `CLOUD_` 前缀的原始表名（如 `CLOUD_VM_NOVA`），执行器内部自动映射到脱敏名（如 `VM_NOVA`）查询 API。完整映射表见 `output-server/README.md`。

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

- **SSL**：因企业代理拦截，httpx 客户端需设 `verify=False, trust_env=False`

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
