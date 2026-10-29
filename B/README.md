# B：模板选择、参数填充与查询流程

本目录是 `hackathon-p13-2/B`，按仓库 `TEAM.md` 的 B 角色独立开发。负责人是本聊天的用户，由 Codex 协助。开发分支为 `simple/official-starter`。

已完成环境准备和两轮离线正确性修复：实体边界与必要条件、选择拒答和 SQL 精调校验。仍使用“BM25 → LLM 选择 → 参数填充 → SQL 精调 → 原执行器”，真实模型准确率、时延和提示词收益尚未测量。逐轮记录见 [PROGRESS.md](PROGRESS.md)。

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

- **官网没有指定 DeepSeek 型号或公网地址**，只要求“由赛题环境统一提供，模型不可更换”。下发基线默认使用 `deepseek-chat`、`https://api.deepseek.com`。正式接口尚待主办方确认；收到准确标识后配置 `DEEPSEEK_MODEL` 与 `DEEPSEEK_BASE_URL`，不自行挑选替代模型。
- 当前代码接收消息列表，调用 Base URL 下的 `POST /chat/completions`（Base URL 含 `/v1` 时路径为 `/v1/chat/completions`），使用 Bearer Key 鉴权。请求/响应合同已由内存 transport 验证；这不证明正式服务已可连接。
- TLS 证书与主机名校验开启，模型客户端尊重系统代理配置。自定义可信 CA 使用 `SSL_CERT_FILE`。
- `RUNBOOK_MAX_LLM_CALLS` 限制**整个进程**的模型请求数；`0` 或未设置表示不设本地次数上限。失败请求也计数，SDK 自动重试已关闭。
- `RUNBOOK_MAX_OUTPUT_TOKENS` 默认 1024，`RUNBOOK_LLM_TIMEOUT` 默认 60 秒。输出截断视为调用失败；SQL 精调失败仍走基线的原 SQL 回退逻辑。

仓库要求真实模型调用和费用先获得授权。首次建议只运行白盒前 3 题，最多 9 次请求；这是一轮小样本连通性诊断，不是全量基线成绩：

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

31 项测试覆盖模型请求合同、调用预算、实体替换、缺参保护、类型、枚举、拒答、SQL 校验和本地流水线。本地流水线使用真实数据 API、原执行器和原评分器，仅模型响应为测试夹具；还执行原 `quick_eval.py` 的前三题入口。该结果用于证明链路和逻辑约束，不能作为模型准确率或真实时延成绩。不设置 `RUNBOOK_TEST_LOCAL_API=1` 时会跳过两项数据服务测试。

## 本轮改动与后续整合

运行时改动集中在 B 的两个文件：

- 选择明确拒答或编号不合法时停止，不强制退回第一候选；不再将租户与 VDC 视为相同分组维度。
- 实体抽取采用有边界的 ASCII/引号解析；不回填示例默认实体，不删除缺失的必要 API 条件；保留 JSON 参数类型，字段枚举按 schema 样例校准。
- 区域、租户、可用区等显式条件须在 API 层体现；请求输出 IP 字段不会被当作按 IP 过滤。
- 保留 SQL 精调，合法 Top-N、输出别名和原模板 UNION 不再被无条件删除/改写；检查单条 SELECT、表集合、API 过滤约束和 schema 编译，精调失败回退原 SQL。
- 增加可解释诊断，保留 TLS 与调用预算。无占位符模板也经过共同校验与精调，可能增加请求数，需在真实模型阶段测量其得分和时延影响。

团队整合时比较并迁移 `B/implementation/runbook_matcher.py` 与 `B/implementation/runbook_system.py`。不要用 B 的整份 `implementation/` 覆盖主目录，否则会覆盖 A/C 后续工作。依赖锁定和本地测试可以一并交给 C。

同步 A 的新模板/检索器前先确认提交版本；更新 B 的对应快照并记录来源。哈希检查发现快照与初始版本不同是预期交接信号，应明确更新 manifest，不要直接绕过检查。

拿到 API 后先记录真实模型的小样本结果，再建立相同用例范围的前后对比。当前保守的实体依据检查可能增加拒答，需测量召回与得分；复合问题的多模板编排仍需与 A/C 确认原子模板和子结果格式。

## 检查记录

基线来源提交为 `d20af59`，精确哈希见 `baseline_manifest.json`。远端开发分支在本轮期间更新，已快进同步，并复制 C 已交接的评估脚本；原始数据、执行器、评分器、模板和检索器一致。

| 项目 | 实际结果 |
|---|---|
| 独立环境 | Python 3.13.12，锁定 20 个依赖包；含本机 SOCKS 代理所需的 socksio |
| 原始只读文件 | 240/240 个 SHA-256 校验通过 |
| 数据服务 | 63 类数据、186,152 条记录；本地 schema 可用 |
| 原请求示例 | 12 个请求完成：11 个 HTTP 200、1 个预期 HTTP 404 |
| 模型客户端配置 | 初始化成功，TLS 校验开启，自动重试为 0；该检查不发送请求 |
| 无外部模型测试 | 31 项全部通过，包含 2 项本地流水线/原评估入口联调，无跳过 |
| 同条件缺陷复现 | 对比 c068cd3：实体边界、缺参保护、明确拒答、Top-N 四项旧版失败、当前通过；不是模型成绩 |
| 原白盒入口联调 | 模拟模型 + 真实本地 API 下前三题输出 15/15，仅验证执行/评分衔接 |
| 真实模型小样本 | 用户明确本轮暂不调用模型，未运行、未产生模型调用费用 |
| 全量白盒 / 黑盒 / 正式成绩 | 未运行；黑盒文件缺失 |

目前没有查询算法收益结论。下一步获得模型调用授权后，以真实模型小样本确认账户、网络和完整执行链路，再扩大白盒范围。本轮临时数据服务在检查完成后关闭；继续工作时按上面的命令启动。
