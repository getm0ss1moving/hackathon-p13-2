# B阅读待办：160候选与R2解析增量

**解析/等价压缩门禁PASS；COUNT总体业务仍BLOCKED。生产默认198不变，160未生产启用。**

先读[160主包](../../experiments/a_family_candidate_160_20261030/README.md)、[构建与公开复核](../../experiments/a_family_candidate_160_20261030/BUILD.md)、[R2完整交接](../../experiments/a_family_candidate_160_20261030/parser_r2/HANDOFF.md)及[最新B来源兼容说明](../../experiments/a_family_candidate_160_20261030/parser_r2/LATEST_B_SOURCE_COMPATIBILITY.md)。原51/70/batch4 41全部通过；九静态合同及27 SQL夹具仍保留2项历史错误，不能计作业务成功。当前结论不包含新B完整160兼容、真实模型或原生执行。

## B最小接入与业务协作

- 保留main3057d64及后续B的F18 oneOf、F20结构bool/API枚举、VM/HOST状态归属、SUM/AVG DISTINCT粒度守卫、EIP、170自然view、日志/精调/组合修复。先核最新源码，按diff增量移植；禁止旧matcher整包覆盖。
- 160包含15族，新增路径按batch4、single、count独立命名空间接入；单表入口prepare_single_table_candidate(question,item,parsed,diagnostics)必须走原文语义校验，成功才交普通API/SQL。R2补丁仅针对single_table_families.py，基底fc71c51f…6bb506，目标04098b71…ed6576，不负责完整B接入。
- 保留同族多view/范围/资源集义务、全部条件和预期列校验。B/官方需提供API成功、真空、失败/missing objList及分页完整性的可靠状态合同；单凭error=None/空行不能猜成功0。固定SDK空COUNT=1、缺列吞错/清UNION仍阻塞业务，不能改固定SDK或把SQL强置常量0。
- 两物理CI无非空原生证据、TopK并列身份、容量脏值、分页及深度口径继续保留限制。先做198回退、完整160导入与正常/空/缺字段/组合的合法原生验证，再按既定模型/B/C与150训练/50封存约定重测；本交付不启动模型/服务或扩展费用授权。

模板160固定SHA477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182，检索器befff58a…ef4f24，200文字归属和别名/400+11文档保持。B180历史成绩不归160；本次只有隔离资料可交付，COUNT业务及生产门禁并未放行。


## 同批补充：B问题的六族合同回应

请B阅读[3057d64固定源合同回应](A_B_CONTRACT_REPLY_3057d64.md)及其六族JSON清单。确认旧044的ECS标签、旧133隐式租户×状态计数、F18四种合法组合，以及F20严格结构bool/API枚举和111 total/112 count别名。30个设计案例未执行；VM/HOST参考与聚合身份粒度争议、共同SDK业务门禁继续待裁定。本补充只改文档，160候选及运行实现不变。
