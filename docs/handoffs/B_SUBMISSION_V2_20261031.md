# B完整交付v2：源码、运行包和验证边界

本次在main提交，从`4abe75e`继续构建，不新建分支。完整开发源码、相关测试、诊断工具、配置和脱敏摘要随仓库交付；运行ZIP在提交完成后重新构建，确切提交和251个运行文件哈希写入包内`SUBMISSION_MANIFEST.json`。本次发布GitHub版本，不表示已经向赛事门户提交或在真实评测机通过。

下载：[v2 Release](https://github.com/getm0ss1moving/hackathon-p13-2/releases/tag/b132-r5-submission-v2-20261031)。附件包含`submission.zip`、`SHA256SUMS.txt`、`VERIFICATION_SUMMARY.json`与`SUBMISSION_README.md`。v1和先前本地候选ZIP保留，不覆盖旧验证记录；最终提交请使用v2 Release的包和对应校验文件。

## 默认运行内容

- 132 strict＋R5；入口为`implementation/runbook_system.py:RunbookQuerySystem.query`。完整`experiments/`来源闭包不可删除，不依赖Git历史或旧开发目录。
- 包含v1六项P0、CTE本地表处理、已验收hierarchy/VM-EIP/AZ及集群/CCE明细；新增OBS/GaussDB参数恢复和ECS/VDC默认类型标签。
- `RUNBOOK_JSON_COPY_MODE=fast`默认启用；`standard`可回退。原A文件及公开manifest不改；B显式绑定复制原语，canonical、prepare、recheck和完整明细守恒均保留。
- `RUNBOOK_ISSUE4_ADDRESS=0`。地址完整token管线已完成独立原生验收，仍是显式候选；未知地址、EIP所有权和原空参考未解决前不默认启用。
- thinking关闭，SDK重试0，输出上限1024token；外部密钥、API端点和模型显式配置优先。开发450次进程预算不带入直接评测入口。
- 官方四文件保持既有授权指纹，原数据和服务不改。evaluator只保留既有三处用户授权修订。包不含密钥、题集、答案、原始数据库、模型原始日志或本机环境。

## 已完成验证

OBS/GaussDB/标签修复：小集066/148/150/156/158各5分，15次Flash请求0失败；42项相关离线检查通过。修前066/148/158本次诊断也各5分，不能认定已复现此前控制台的具体失败根因。[逐题分流](B_829日志修复与剩余问题_20261031.txt)及[冻结证据](../../experiments/b_console829_repairs_20261031/VALIDATION_SUMMARY.json)保留。

复制优化：同冻结输入、独立新进程每组一次，161普通计时13.55→10.62秒，298为42.15→34.54秒；完整JSON输出及类型不变。均为离线测量，不能当HTTP端到端时延或新模型分数。298峰值仍有超过2GiB记录。[性能、261/192人口审计及归档生效版本](B_A_FEEDBACK_PROFILE_20261031.md)。

地址成员：50项地址/共享读取器离线控制通过。本轮完整原生捕获选中484 EIP、2830 VM上下文，433个不同token分别实际contain，总441次HTTP；输出567行，其中298行已知地址成员涉及215 EIP，869 VM地址未知。完整同轮收据、输出、source.zip留在本机reports，公开[脱敏摘要](../../experiments/b_address_membership_20261031/VALIDATION_SUMMARY.json)。不是567条已认证关联，不认证所有权；未执行模型或评分，已反馈[Issue #4](https://github.com/getm0ss1moving/hackathon-p13-2/issues/4#issuecomment-6537389222)。

最后入口/预算/恢复离线16项通过；与前述阶段不相加为业务覆盖，不回填旧200题成绩。本轮完整发布不重跑全200或额外模型测试。正式ZIP实际解压到无Git目录的离线与本地服务检查，精确结果随Release附件提供。

## A/C复现与剩余事项

直接拉main后按[运行说明](../SUBMISSION_README.md)安装；C必须使用相同入口和显式配置，不能将未加载配置的旧quick_eval运行视为等价。评测机需本地原版CMDB服务及`ps/lsof`可见，真实评测机尚未验收，服务容器/权限差异未认证。

A补权威物理CI区域字段、数据库专用卷/存储池及GaussDB/ELB部署AZ关系；已有192/253/260/261/262/287/300候选不重复造模板，未知和明细不得丢失。C核定租户、状态、AZ、区域、COUNT空集、排名未知人口与多义务输出口径。未解决项继续留在Issue #4，不通过删条件、改实体或伪造空集追分。

历史摘要中“本地未提交”和ZIP哈希描述各自测试时的状态，不改写；当前发布以v2 Release、其target提交和包内manifest为准。
