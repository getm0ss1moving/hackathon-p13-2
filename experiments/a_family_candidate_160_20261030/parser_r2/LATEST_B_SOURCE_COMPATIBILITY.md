# 新main来源复核：不混入已冻结160

核对远端提交`3057d64b47d4926d463eedfe0dfc3e683251e576`。本次只读GitHub文档和源码，在隔离目录保存并以Git blob算法核验四个文件，全部与远端一致；没有fetch/checkout/commit/push、没有向B源码应用补丁。

|来源|该提交的Git blob SHA|
|---|---|
|[B交接状态](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/docs/handoffs/B_TO_A_180_STATUS.md)|b47aa0c25d6ce436d45d6925e4842e0a3701b51a|
|[B170原生验证说明](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/experiments/a170_runtime_port_20261030/README.md)|a637c0e0fbe7566115f4167301c2bafcafd836d8|
|implementation/runbook_matcher.py|2397db01fd0db95d6a05d3b05d8bf447d27adfa1|
|implementation/runbook_family_views.py|8e95eb58e6f0d3f7fd77fd36b7e5c535ce39cc78|

## 来源一致与版本差异

- B170说明中的A170 JSON为`f77c75422faca71d32fcd8b9de357080a610fe1f0c5a9c4f3c6a1efd3c9c664c`，检索器为`befff58a0899be573ed1d0700f1ed14544c8a55a255bc0f438fe26f4d0ef4f24`，与本160链式构建的170起点一致。该一致性只确认来源，不替代160集成测试。
- 文档所述B原生运行冻结基底为fa9fe40，matcher SHA256为dced03e0…b96d9。实际3057提交中的implementation/runbook_matcher.py SHA256是`2668bf06805ecafd2a3d757787bb236b084feba401e3d783d7576fae173d0eb1`；implementation/runbook_family_views.py为`7915b297783e71fc6ac405c5d0f01184ae49299e6775b7446b7a62131c7dbba7`。这些不是旧运行快照，不混称同一文件。
- 当前代码位置在implementation/，根目录runbook_matcher.py查询返回404；随后已通过远端树确认并读取实际路径。这是路径修正，未遭权限审批拒绝。
- 当前matcher静态不含family_f10、family_f17_safe、family_next_n28、prepare_single_table_candidate或single_table_families引用。仓库树也无单表helper文件。故不能把当前main视为已经接入160；动态完整链路尚未验证。

## 兼容门禁与B最小接入要求

本包ascii_atom_only.patch仅针对独立single_table_families.py，基底必须为fc71c51f…6bb506，目标04098b71…ed6576。它不是matcher整文件补丁，也不负责把170变成160。应在当前B上增量接入所需族与helper，再做完整路径测试；禁止使用旧matcher整包覆盖当前B。

必须保留B已交接的F18 oneOf、F20结构bool到API枚举转换、VM/HOST状态归属、SUM/AVG DISTINCT粒度防线、EIP与170自然view/角色处理、现有日志/精调/组合逻辑。本次仅来源复核；没有据此独立认证每项B能力，也没有移植或测试其实现。实际3057的patch apply-check、模型/原生路径、完整160兼容测试均为NOT RUN。

原160数据SHA`477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182`、检索器以及51/70/41冻结验收输入/输出均不变。原解析/等价门禁PASS继续有效于该冻结快照，不扩张到新B版本。当前正式默认198，160未生产启用。

## COUNT业务门禁仍BLOCKED

B170原生说明记录：在170及180，API均0记录时原COUNT(*)得到一行total=1；聚合返回一行正常，但值1不正确。其执行器SHA为4febd1933699a4f17d36507dcb297250989ddfa1ce4900bafe191e12f37b4b92，根因是空表占位行，另有缺列被变为空结果。该结果属于B原生证据，不冒称我方重新执行；它与我方离线风险一致，不能因解析已修就改为业务PASS。

B/官方状态合同问题已交独立任务，本次不重复研究、不改固定SDK、不强制返回0。此门禁阻止宣称整体业务正确/生产就绪，但不否定已完成的解析修复和等价压缩。

本机命令通道曾短暂transport disconnected，后续读取已恢复；当前没有待批准操作或结果不明的Git写入。本轮没有模型/服务调用、读取封存题、修改官方文件或发布。
