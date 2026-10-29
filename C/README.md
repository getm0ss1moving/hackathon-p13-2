# C：完整实验与验收工具

C 的目标是交付可复现的基线、失败证据、版本对照和最终验收结论。完整合同见 [DESIGN.md](DESIGN.md)，当前数值、交接队列与剩余验收项见 [STATUS.md](STATUS.md)。实现都位于 C/，原评分器、执行器、数据与 A/B 代码保持原样。

## 已有功能

- 冻结原200题及189个组：开发166、回归34、代表性开发20；复用团队固定分组，不按结果重新选题。
- 独立泛化输入：12条已复核改写、4条已用参考查询重算答案的实体控制；另4条库外拒答控制单列。
- 读取 C 报告、B 的 JSONL 与根 round3 报告，核对完成数、唯一题号、总分与请求数；生成逐题CSV、失败交接队列和Markdown。
- 配对比较默认要求完整且合同一致；六题对200题须显式 --subset，只汇总这六题。模型/配置不一致时仅能显式 --descriptive 展示差值，不称受控提升。
- 审计原文件、模板数量/大小/容器深度、建索引与检索耗时。模型CPU与总内存未测时明确写未测。
- 实际运行入口支持冻结子集、独立轮次、派生题、真实HTTP请求上限、SDK重试计数、模型返回名/usage、最少匹配诊断、进程CPU/峰值内存和逐题检查点。
- 公式核算仅接收白盒200与黑盒100各两份独立完整记录；缺黑盒时拒绝计算，不补零。

本目录依赖完整仓库。不要把 C 的整个 implementation 覆盖根目录；根集成文件交由集成人明确交接后迁移。

## 无模型操作

在仓库根目录执行，以下命令不会调用模型：

```powershell
python -B -m unittest discover -s C/tests -v
python -B C/benchmark.py build --out C/reports/new-frozen
python -B C/benchmark.py analyze B/experiments/whitebox_20261029_full.jsonl --out C/reports/b-review
python -B C/benchmark.py analyze experiments/round3/model20.json --out C/reports/root-review
python -B C/benchmark.py compare B/experiments/whitebox_20261029_full.jsonl B/experiments/whitebox_20261029_projection_live.jsonl --subset --out C/reports/projection-pair.json
python -B C/benchmark.py audit --implementation-dir B/implementation --out C/reports/b-audit.json
```

工具已生成的冻结清单在 experiments/frozen-v1，现有证据分析在 experiments/assessment-v1。复现分析请选择新的输出目录；原始模型记录永不覆盖。源码/用例哈希变化时不能把旧模型记录认定为当前版本实测。

失败分类按证据处理：候选为空不证明库内无能力，资源门禁不证明一定误拒，SQL变化不证明一定退化。队列保留待复核项和责任人；模板频次只作描述。

## 真实模型运行

以下是后续执行方法，本轮没有执行。先确认模型、实际被测版本和当轮请求额度，并将密钥仅配置在运行进程的 DEEPSEEK_API_KEY 中。依赖沿用已有 openai/httpx/requests，不自动安装。

数据服务只启动一份：

```powershell
python -B output-server/data_server.py --host 127.0.0.1 --port 8080
```

将 $approvedRequestLimit 设置为本轮已明确批准的正整数后，在另一个终端运行：

```powershell
# 固定代表性20题；不是临时取前20题
python -B C/implementation/quick_eval.py --implementation-dir B/implementation --case-set C/experiments/frozen-v1/representative20.json --max-requests $approvedRequestLimit --report C/reports/b-representative.json

# 固定回归清单计划两轮：每轮单独进程和文件，两轮预算合计也需明确
python -B C/implementation/quick_eval.py --implementation-dir B/implementation --case-set C/experiments/frozen-v1/regression.json --round 1 --max-requests $approvedRequestLimit --report C/reports/b-regression-r1.json
python -B C/implementation/quick_eval.py --implementation-dir B/implementation --case-set C/experiments/frozen-v1/regression.json --round 2 --max-requests $approvedRequestLimit --report C/reports/b-regression-r2.json

# 已重算/复核的16题；与原白盒成绩分开
python -B C/implementation/quick_eval.py 16 --implementation-dir B/implementation --cases-file C/experiments/frozen-v1/generalization.json --max-requests $approvedRequestLimit --report C/reports/b-derived.json
```

--max-requests 按实际被允许进入传输的HTTP尝试计数，失败和SDK重试也占用。超额停止继承BaseException，穿透业务层异常回退，保存中止记录。该上限只约束当前进程；不代表token或账单上限，不代表其他轮次也获准。请求目标异常也会停止。无法核实模型客户端时不启动生成。

C 只观察请求中的模型/生成设置和响应usage，不修改选择、填参、提示词或SQL。响应钩子会读取响应体以保存usage，存在少量采集开销；不保存完整提示词、响应文本、认证头或密钥。root原实例未设置输出token上限时记录为provider default，不能猜成1024。

## 报告与验收

- JSON：提交/源码/数据/评分器哈希、模型请求与响应身份、配置、缓存、轮次、实际HTTP、阶段诊断、逐题得分、原reason、API/SQL、结果形状、CPU和进程峰值内存。
- failures.csv：已完成但得分未满5的题。UTF-8 BOM，可用Excel打开；答对超时仍保留正确类别和罚分。
- status=completed 只表示这一轮所请求题目完整执行。异常、中断、额度耗尽为aborted；已完成部分单列，不能把未完成题补0。
- 多轮清单通过 --round 分别执行，当前单个报告始终每题一次。正式公式由 aggregate 检查两轮后计算参考值；不是主办认证成绩。
- 同一JSON或配套CSV已存在时拒绝覆盖，保留前后版本。写盘时间不计入query，写盘失败停止后续生成。

C 评估进程的峰值RSS/Working Set不含单独的数据服务。Windows/Mac本机通过不证明正式环境合规。模板深度的具体官方定义待确认，不能自动给“提交合规”结论。

## 本轮交付验证

35项无模型测试通过，含真实已安装SDK配合内存HTTP传输验证重试计数、超额停止及usage采集。已有B200题、root20题、B候选6题证据均已离线核验并输出结果；本轮新增真实模型请求0。具体结果见 STATUS.md。

协作分支为 simple/official-starter。只提交C的设计、工具、冻结实验、分析与测试；C/reports下本机记录被忽略，不提交虚拟环境或密钥。
