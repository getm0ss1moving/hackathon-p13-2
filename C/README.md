# C 的职责和使用方法

C 负责把根目录集成后的系统跑完原评测，保存执行证据，统计得分与耗时，整理失分题，并在 A/B 修复后比较前后结果。

实际代码是根目录 `implementation/quick_eval.py`、`blackbox_eval.py`、共用的 `eval_report.py`，以及 `C/analyze_results.py`。查询系统仍使用根目录 A/B 的实现，评分仍调用原 `evaluator.evaluate_case()`。无需把 C 的文件合并进查询模块，也无需另建 C 查询系统。A/B 的候选版本应先交接到根目录，再评测该集成版本。

这些评测、分析文件应提交团队 Git 仓库，方便复测；它们属于开发验证工具，不进入 `RunbookQuerySystem.query()` 的答题链路。最终比赛提交包的内容按主办要求核对，不能把 C 的日志分析工具当作参赛算法。旧版重复评估器、冻结套件和复杂审计工具已移除。

## 1. 准备

以下命令适用于 WSL 的 bash、macOS 的 bash/zsh，均在仓库根目录执行。WSL 下本工作区对应：

```bash
cd /mnt/d/huwwei/hackathon-p13-2
```

macOS 下进入你实际保存的 `hackathon-p13-2` 目录即可。若已有该环境创建的 `.venv`，在两个终端各执行 `source .venv/bin/activate`。WSL、macOS 和 Windows 不共用虚拟环境。

使用 Python 3.11 或以上，在实际测试环境检查依赖：

```bash
python3 -c "import openai, httpx, requests; print('依赖可用')"
```

分析脚本只依赖 Python 标准库。依赖缺失时先补齐当前环境，不使用 Windows 的依赖检查结果代替 WSL/macOS 的检查。

在运行评测的终端隐藏输入密钥，不要将密钥发到聊天、写进代码或提交到仓库：

```bash
export DEEPSEEK_API_KEY="$(python3 -c 'import getpass; print(getpass.getpass("DeepSeek API Key: "))')"
export PYTHONIOENCODING=utf-8
```

现有查询代码从这个环境变量读取密钥，不自动加载 `.env` 文件。配置密钥后，运行评测会发起真实模型调用并可能计费；N 是题数，不是模型请求数，一题可能调用模型多次。

## 2. 启动原数据服务

在第一个终端运行并保持开启；已有同一数据服务时不用重复启动。数据服务和评测使用同一 WSL 发行版或同一台 Mac：

```bash
python3 -B output-server/data_server.py --host 127.0.0.1 --port 8080
```

## 3. 运行原评测，再分析

在第二个已配置密钥的终端运行。下面取白盒文件前20题，每题一次：

```bash
run_stamp="$(date +%Y%m%d-%H%M%S)-$$"
result_path="C/reports/whitebox-${run_stamp}.jsonl"
git rev-parse HEAD
python3 -B -u implementation/quick_eval.py 20 --report "$result_path"
eval_exit_code=$?
python3 -B C/analyze_results.py "$result_path" --expected 20 --exit-code "$eval_exit_code"
```

全白盒200题：将上述两个 `20` 都改为 `200`。只有确认本轮调用范围后再执行。`--report` 可省略，原评测用法仍有效；省略后只打印原控制台结果，不生成详细证据。

`--report` 每完成一题立即写入 JSONL，保留问题、精确 query 耗时、原评分及完整原因、选中模板、实际 API/SQL、执行结果和错误。记录开始时保存用例和实现文件哈希。写盘在原 query 计时与原评分之后，原评分器和原执行器不变。已有报告拒绝覆盖，换一个文件名即可。

查询异常或 Ctrl+C 中止会保留已完成记录；分析器将其标为 incomplete，不把未运行题补0或算作完整成绩。密钥缺失、依赖/服务未就绪等启动错误时先按控制台提示修复，再用新文件名重跑。

黑盒入口已支持相同的 `--report`，但当前缺少官方 `CMDB用例集-黑盒100.json`，不能运行黑盒，不用自造题替代。

## 4. 查看报告和前后比较

分析目录默认位于原文件旁，如 `C/reports/whitebox-时间-analysis/`：

- `REPORT.md`：完成状态、总分、得分/原因分布、平均/P50/P95耗时、超时与失分概况。
- `cases.csv`：全部逐题结果，UTF-8 BOM，可用 Excel 打开。
- `failures.csv`：未满5分的题，附实际模板、API、SQL、错误和建议排查方向，交给 A/B 复核。
- `results.json`：完整汇总和原始执行证据，包含运行来源和实现哈希。

修复后运行新一轮，再与上一轮比较：

```bash
python3 -B C/analyze_results.py C/reports/新一轮.jsonl --baseline C/reports/上一轮.jsonl
```

额外生成 `comparison.csv`：逐题新旧分数、分差和耗时；报告列出增分、退分题数。要求两轮完整且题号/问题一致；模型、配置、环境是否一致仍需人工核对。已分析过的文件用 `--output-dir C/reports/新的分析目录`，避免覆盖旧结论。

只有得分不能证明召回、选择或 SQL 精调哪一步出错。C 提供证据和排查方向，A/B 结合各自代码确认原因；发现缺少必要中间信息时再补少量诊断。当前不采集 token、模型请求数、CPU/内存，不冒充已测；这些不是启动本轮答题回归的前置条件。

## 当前完成范围

已实现原入口运行与结果采集、完整性检查、统计分析、失败交接表和版本结果对照。删除了 C 的重复查询入口和实验框架。上述代码使用跨平台 Python 标准库，没有固定 Windows 路径。WSL/macOS 上的真实模型评测尚未在本轮运行；下一步是在实际环境配置 API，并明确题数后执行第3步，依据真实结果处理失败题。
