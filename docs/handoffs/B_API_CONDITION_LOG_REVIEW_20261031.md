# B：API条件零分日志对照与当前复测（2026-10-31）

用户提供的两次全200控制台日志分别为766.4和796.4/1000，零分项25→19。它们没有源码提交、完整环境和原始query诊断，不能当作本轮冻结候选的完整200成绩；本轮没有再次全测。控制台avg=39.8%来自官方原脚本的既有公式；796.4/1000对应79.64%，本次没有改该脚本。

“系统无API条件”是评分器在最终输出层看到的现象。模型选择0、参数不合法、完整义务不足、原生schema/preflight拒绝、请求异常或预算耗尽，最后猜空/捕获异常时都可能api_call为空。不能仅凭这行判为实际全量查询，更不能把未执行条件补写为已执行来消除提示。

## 两次日志的变化

|题号|上次|此次|
|---|---:|---:|
|CMDB-012|0|5|
|CMDB-030|0|5|
|CMDB-086|0|5|
|CMDB-158|0|5|
|CMDB-163|0|5|
|CMDB-175|0|5|
|CMDB-187|0|5|
|CMDB-210|5|0|
|CMDB-236|5|0|
|CMDB-271|0|5|

## 本轮实际运行

只测训练236/291和已曝光验证194/210/289，分别10/10和15/15；共12次Flash请求，无失败、无猜空。thinking disabled，输出上限1024，SDK retries=0。各组独立冻结预算6/9，未复用余额。

210、236的控制台零分本轮未复现；缺旧逐题JSONL，不能宣称找到或彻底修好它们的历史根因。194、289、291在本地当前候选已接入通过；用户日志中仍0分的确切原因也不能从控制台追溯到代码或环境。

## 最新日志19个零分的逐项分流

|题号|当前判断|依据/下一步|
|---|---|---|
|CMDB-077|口径待核定|原题只说整个Region，未明确区域实体；参考指定region_guian4，不从参考补默认区域。|
|CMDB-105|A字段/关系证据|物理服务器CPU/内存资源统计所需证据仍待核验。|
|CMDB-139|A字段/关系证据|数据库专用盘到存储池关系仍缺权威依据。|
|CMDB-192|A新合同待B接入|远端a8d4fe1已交付具名VPC双计数，已快进合入但尚未接入/原生验收。|
|CMDB-194|当前小集5分|本轮A vdc_network执行通过，区域/VDC API条件均有真实执行账本。|
|CMDB-210|当前小集5分；日志失败未复现|本轮family_f26按区域统计通过；缺旧逐题JSONL，不能断言其先前失败根因。|
|CMDB-224|A字段/关系证据|GaussDB可用区namespace与题文量词仍有证据缺口。|
|CMDB-236|当前小集5分；日志失败未复现|本轮family_cce_children按具名集群查节点通过；缺旧逐题JSONL，不能断言先前失败根因。|
|CMDB-251|A模板/组合合同|按AZ分别统计ECS/卷/VPC完整三分支尚未接入支持。|
|CMDB-253|A原生合同阻塞|VOLUME行省略vdcName，被冻结preflight拒绝；已向A发原生证据。|
|CMDB-261|A原生合同阻塞|VM租户/IP字段存在行级省略和未知人口，被冻结preflight拒绝；已向A发原生证据。|
|CMDB-264|A模板/组合合同|按可用区的完整多资源查询尚需合同。|
|CMDB-287|A原生合同阻塞|完整区域ROUTER目录存在未知VDC，冻结preflight拒绝；已向A发原生证据。|
|CMDB-289|当前小集5分|本轮tenant_lists三资源清单保留完整输出通过。|
|CMDB-291|当前小集5分|本轮真实native namespace证明、三COUNT执行通过。|
|CMDB-297|A字段/关系证据|交换机/路由器/VFW统计的物理资源区域范围尚缺可信证明。|
|CMDB-298|A部分合同待核验|A新vm_eip_host仅已知EIP关联子集，尚不保证原题要求的完整EIP列表。|
|CMDB-299|A模板/组合合同|CCE集群清单与各集群节点/VM双计数完整义务尚未支持。|
|CMDB-300|范围/业务口径待核定|现有能力能执行，但区域、分组域及未知vCPU与参考冲突；未默认启用capacity。|

原生字段3项已发送A：[Issue 3原生证据反馈](https://github.com/getm0ss1moving/hackathon-p13-2/issues/3#issuecomment-6528797823)。已有9项模板和7项字段归因旧清单属于此前快照；其中192现已由A追加交付，不再重复称A没交。

## 拉取和诊断入口

在现有main拉取，避免再用旧160构建命令覆盖当前132。运行时库为26族+106固定项。A默认只启用已通过的namespace_counts、tenant_lists、vdc_network，其他合同保留隔离状态；先前终端显式设置RUNBOOK_ISSUE3_CONTRACTS=0时，直接官方入口仍尊重该值。B启动器会显式固定本轮启用项。

```bash
git pull --ff-only origin main
.venv/bin/python -B scripts/check_official_integrity.py
.venv/bin/python -B scripts/run_a132_eval.py --diagnostics --check
```

以上均不执行模型题目；最后一项只读取本地schema。需要下一轮真实运行时，先按已授权失败子集生成新计划，使用scripts/run_saved_training.py并保存新的输出目录；不要覆盖旧工件。

B自有启动器新增--diagnostics，复用C/quick_eval_diagnostics.py和既有EvaluationReport，将每题完整query输出及诊断保存为reports/a132_whiteboxN_时间戳.jsonl，同时保留控制台.log；C入口仍调用原evaluate_case，异常中止而不冒充完整基线。默认不加--diagnostics时依旧调用未修改的官方quick_eval.py。--check不验证完整query，也没有调用模型。

已授权另一次整批评估后，可由用户执行 `.venv/bin/python -B scripts/run_a132_eval.py 200 --diagnostics`。此启动器预算为最多450次模型请求，达到上限将终止诊断并保留已完成记录，不能把中止轮当完整200成绩。本轮未运行该命令，也未付费执行新增的C诊断路径。

本次本地原始工件位于reports/b_api_log_20261031/{train_probe2,validation_probe3}；不上传密钥、.env.local、.venv、封存数据或本地原始日志。可提交的脱敏摘要和实际执行API证据在experiments/b_api_log_review_20261031/VALIDATION_SUMMARY.json。

## A/C后续工作

A：优先处理253/261/287已发的稀疏字段、未知VDC父目录及未知租户人口合同；以新版本交付，不覆盖旧冻结包。C：核对116/270/300与旧15项C_REVIEW的具体参考/业务口径分歧。A新next与具名VPC包随远端main快进保留，尚未在B原生链路验收或默认开放。

旧16题阶段：10道曾在分段小集取得质量满分，3原生合同阻塞、3口径冲突。不能把所有最新逐题分数拼成单轮新全量分数。具体原题和修复见[B 16题处理说明](B_16问题处理结果与口径说明_20261031.txt)。
