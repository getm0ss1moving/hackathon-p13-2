# B：模板选择、参数填充与查询流程

本目录为团队B独立项目，当前工作分支`main`，按用户要求不再为每次提交新建分支。旧协作分支的已提交历史已汇入main；本次用户已另行授权提交B最新代码与训练交接证据。当前只用固定150题训练，另外50题封存且不上传；模板库仍200条，199候选未接入。原执行器、评分器、服务、数据及用例不改。

持续目标：[固定150题原计时评分达到700/750](GOAL.md)。先小范围优化未通过题，再回归原来通过题；A/C可直接使用[下一轮协作提示词](A_C_NEXT_PROMPT.md)。当前尚未达到目标。

v3新增默认关闭的SQL合同提示词候选：固定16训练题、32次真实精调配对已完整结束，原提示11/16满质量、无时延57/80，新提示13/16、69/80，2改善0退化；合同拒绝7→1、截断1→0。仅提示词实验，不能外推150题准确率或当作700目标验收。[协议与结果](experiments/train150_v3_prompt_notes.md)。68项训练专项通过，240受保护文件哈希一致。

**最新真实训练覆盖：117/150完全正确（78.0%），上一轮113；5项质量改善、0退化。** 原运行147题后接口超时，经单独授权补3题，不能称完整连续单轮。累计293/450请求，157余量结束不复用。程序实际拒答25条，原评分0分26条，全部问题尚未解决。[真实报告](experiments/train150_v2_live_summary.md)。

已实现聚合粒度、类型标签、无消费者查找裁剪和枚举语义4类通用候选，默认关闭；45项专项检查通过（候选42+补测门禁3）。不按题号、完整问题或答案做运行时路由。训练协议和仅150题的入口见[TRAINING.md](TRAINING.md)，开发时不再运行旧全200脚本。

给团队的材料：[A/C交接说明](TEAM_TRAINING_HANDOFF.md)、[37项逐题清单](TRAINING_ISSUES.md)、[A要求](A_REQUESTS_TRAINING.md)、[C要求](C_REQUESTS_TRAINING.md)。A补字段/关系及完整模板合同，C复核参考覆盖与隐藏条件，B提供代码、回放和字段证据；没有自动向其他聊天发消息。

所有本轮代码和结果在B，本次用户已明确授权提交推送；后续新增成果按用户后续提交指令交付。密钥仅存被Git忽略、权限0600的.env.local，不放进交接包。用户已持续授权后续问题自行决定，有界训练实验先冻结具体范围与来源、记录独立账目，不再逐轮询问，不伪称逐轮人工批准。

历史全200产物留在原本地历史归档，不随本次训练交接上传，也不能用于当前调参或推算封存集；历史文档中的旧路径仅表示当时记录。此前已看过全部200题和公开模板示例，50题仅隔离未来调参，未证明完全未见泛化。


## 环境与启动

本机已验证Python 3.13.12。从同版本仓库根目录进入B：

```bash
cd B
./setup.sh
.venv/bin/python output-server/data_server.py --host 127.0.0.1 --port 8080
```

setup仅从同仓库复制缺失数据、安装锁定依赖并校验哈希，不覆盖已有数据。Git不重复保存约250MB原数据副本；单独取得B代码时先运行`python prepare_data.py --source /path/to/hackathon-p13-2`。数据服务只启动一份，占用127.0.0.1:8080。官方执行器、评分器及服务保持原字节。

另开终端，在B目录做免费复查：

```bash
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -p 'test_training_*.py' -v
.venv/bin/python train_live.py --candidate-flags
.venv/bin/python train_replay.py --latest-live --candidate-flags --output reports/train-replay-new.json
```

前两条不调用模型；回放需已启动本地数据服务，使用固定历史模型输出。输出路径须尚不存在。历史全套测试、quick_eval、run_whitebox和旧全200回放入口保留为原来工具，划分后不要用于开发，以免读取封存题。

## 模型与真实训练

本机密钥仅存在忽略的`.env.local`、权限0600。训练入口加载其中的DEEPSEEK_API_KEY、DEEPSEEK_MODEL、DEEPSEEK_BASE_URL及RUNBOOK_LLM_TIMEOUT，不把密钥输出或提交。新机器按`.env.example`配置；deepseek-flash是开发模型，正式比赛模型仍待主办方确认。

`train_live.py`固定150题，没有其他集合入口；默认只打印预检计划。要真实执行，先将预检输出存为新计划，再以匹配的`--expected-plan`、新的`--output`和`--run`执行。`--candidate-flags`启用v2四个候选，`--refine-contract-prompt`独立启用v3提示词；开关、范围、来源和预算全部写入计划并逐请求核对。新候选不能套用旧计划或复用旧余额。

每轮最多450生成请求、1024输出token、SDK重试0，失败请求计数；优先失败小集少次复测。基础设施异常停止，截断不使用不完整回答。当前`train_prompt_probe.py`只支持本轮固定16题的新旧精调配对，默认预检；不是任意抽题入口，也不是完整query成绩。

## 代码和证据

- `implementation/runbook_matcher.py`：模型选择、参数/API条件和SQL精调；保留BM25、原api_call+sql及验证合同。
- `implementation/runbook_system.py`：原流程、阶段诊断及默认关闭的有界依赖实验。
- `implementation/runbook_items.py`、`runbook_retriever.py`：固定A交接快照，200模板，B不盲目覆盖根A/C的新代码。
- `training_data.py`、`train_live.py`、`train_replay.py`：固定训练加载、真实入口和免费回放。
- `train_prompt_probe.py`、`analyze_prompt_probe.py`：固定输入的SQL精调配对与分析。
- `datasets/whitebox_150_50_v1/`：只交manifest、train.json、train_history.jsonl；封存题留在原本机，不上传，不重抽划分。
- `experiments/train150_v1*`、`train150_v2*`、`train150_v3*`：训练范围的来源、计划、独立账目、真实trace和分析；v2是147+3分段，v3是16题探针。
- `GOAL.md`、`TRAINING.md`、`TRAINING_ISSUES.md`：700目标、实验协议及37项问题账本。
- `A_C_NEXT_PROMPT.md`、`A_REQUESTS_TRAINING.md`、`C_REQUESTS_TRAINING.md`：下一轮分工与合同要求。

以main中的B目录为最新交接，不用旧ZIP代替。业务迁移只交接具体差异，不能整份B/implementation覆盖根目录。同轮同文件只有一个修改人；A补字段/关系/模板合同，C复核参考覆盖和原评分验收，B接入匹配与流程修复。未知合同明确标未证明，不删除筛选或加虚假条件凑分。
