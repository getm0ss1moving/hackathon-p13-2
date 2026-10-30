# A → B：180模板候选与适配重测交接

## 当前交付与状态

**候选包已发布；生产仍198。** 当前main保留B v18与A检索第一阶段/空输出，不为发布候选替换matcher、system或生产模板。候选的完整180定义、索引元数据和生成代码见[候选包](../../experiments/a_family_candidate_20261030/README.md)。本交接不等待stage2、batch2，也不把文档发布当作180已上线。

|对象|精确版本/状态|
|---|---|
|当前同步基底|099b5bfc5545d98f81e46a4a7b6244623c29ef8c，包含B v18和A两项提交|
|B真实已测版本|8a167936caede9f96e2e1318c82f8f98e7d5ec68；其640/750仅固定train150一次，不归给合并main或180|
|生产198模板SHA256|9799b9fd6007e80f08610aa3d62d8495b3e85efe4924328477343c967a158465|
|检索第一阶段|484e44a；最终检索器8fd12b7556bdcf89a10f9d408d9c8473e04a48bcd4bd3bd89bc06c8aaec856cc|
|空输出|dfa61b5；SDK result=None/null、matched=None、error=None，CLI未支持回答stdout为空|
|R5新增源|3c91b3d479d86116d6cf550eec8af243d296361831180f8b7c6cb144489efa5f|
|R5旧补丁|2d84d724209806457b92b2ec96485d30e88b9ee20eb0a02ac998aca26257c397；基底2707ff9，旧matcher0e6f3e6f…|
|当前B v18 matcher|1e7cc2ffa968e04e7cb4da8116b5da14bcd39d7b7d583b6b87fa5ed0f902b63e；旧R5补丁不能直贴|

R5有限语义审查按声明范围通过：既有及53回归、新30有限组合21正常/9未支持；这是冻结旧B基底的合成证据，不是v18适配通过。R5代码与旧基底补丁均已交付供B移植。B v18现有新helper全部保留，不能用旧完整候选覆盖。第二批F27不在本包，不能再减数量。

## 180如何得到及如何复现

198中替换24个活动条目，加入6族，174条原合同保留，实际180唯一ID。087早已属于086别名，不能再当一条活动模板或重复计算收益；054仍归052，087迁到family_f14。全部[逐项映射](../../experiments/a_family_candidate_20261030/parameter_mapping.json)只用于离线迁移，不进入运行时按题号/旧ID查SQL。

|族|当前成员（rb_省略）|参数/输出边界|
|---|---|---|
|F01|001/002/003/004/005/007/017/044/074/184|global/filtered；group=none/status/AZ/management/tenant/VDC；count、VDC total_active、AZ status_counts；别名、ECS标签、排序受闭集约束，一维不能换成二维|
|F08|048/049/053|global或显式region；hypervisorType/AZ/status单维count|
|F14|086/102（087为别名）|region必需、固定VDC；count_sum或avg_max，不能再给group|
|F18|105/106/143/144|region必需；flavorCode/engineVersion/haMode的count或VDC count_storage；不含150、engineName及tenant/VDC扩展|
|F20|110/111/112|shared必须JSON bool；显式region/providerNetworkType可选；rows固定三列，count必须count/total别名|
|F21|113/133|region必需；VDC一维或tenantName+status明确二维|

从仓库根执行以下已实跑的无费用构建；路径必须是新目录：

```bash
python3 scripts/build_a180_candidate.py --output /tmp/a180-candidate-new
```

输出中的BUILD_MANIFEST.json给出精确hash：180唯一ID、200文字profile、400索引文档；400源措辞×4 top-k共1600配对，归族后差异0。生成的candidate180只含A模板/检索器，不含未适配B入口；不要直接把它复制到main。完整本地模板含继承实体例句/默认值，保留私有，不当成新上传载荷。GitHub的180定义采用固定源码引用，六个新族完整可读，由构建器还原全部真实数据，不是删减版候选。

## 检索差距与采用阈值

本批是保留基线，不是声称提升：原profile独立经过BM25/覆盖门禁/top-k，最后才归族、去重、不补位。没有隐藏API/SQL/参数/答案，算法仍为词袋。两组原alias保留且不重复索引。新增首视图锚点校验拒绝缺失/自循环；原BM25常数、分词和查询评分未变。

- 本地517条、每条4种top-k：198原路径2068次逐字段不变；180共2068次严格等于198按族归并的编号/顺序/tier/分数/coverage。50/50合并源措辞、350/350其他源措辞、25/25已见正控均保留。这些不是业务答案标签或模型分数。
- 新候选生成器另实际跑400源文档、1600配对，归族差异0；该生成序列化略有不同，当前包最大单条为2562B，不混用早期压缩快照2450B。
- 独立审查反馈32新句×4 top-k=128次也与198归族全等。这里只接收聚合结果，不把其未见问题提供给调参者。
- 独立组合仅2/4全目标覆盖、原子7/9；正常模板外8/8仍有候选、纯OOD3/4有weak候选。候选暴露不是最终误答，也不是空输出已通过；B必须实测选择、范围、参数、组合与空出口。
- 本机交错每版1551次retrieve：198新路径P95/P99约1.090/1.209ms，隔离180约1.093/1.230ms、max1.597ms；索引约15ms、增量Python分配约0.81MB。非端到端、非总RSS、非正式环境认证。

当前明确检索门槛：同冻结400文档下归族后的候选ID/顺序/分数/覆盖率差异必须0；任一已覆盖能力丢失或无依据误空阻止采用。换词面/启用stage2后必须另冻协议，不能沿用这一0差异结论；需报告正例损失、负例暴露、组合全覆盖与尾延迟，不能只报平均召回。检索分数不是校准概率，不据此单独设全局空回答阈值。

## B负责的适配与验证

1. 在当前v18 matcher中以增量接入R5新增函数和唯一family分支，保留全部现有helper、flags、预算、诊断及标量/分组/网络补全。旧patch在099b5bf已git apply --check失败；这是明确适配门禁，不能强贴/整文件覆盖。A本包没有替B修改matcher/system。
2. 选择仍返回新候选列表序号，不返回旧ID；模板文字视图只为召回。family_fill是新的结构填参stage，必须同时提取scope、group/metrics/view、输出别名/标签/排序和filters/required_filters。禁止任意SQL或字段拼接；闭集之外/显式条件缺值/角色绑定错误/实体外OR/否定/不支持筛选均不能删条件继续执行。
3. global须明确且无筛选，filtered至少一项且required_filters与filters完整一致；shared/management为JSON bool，false有效，数字0不是通用缺失值但不能冒充文本/bool。所有实体源于原文/已证上下文，不回填旧默认实体。
4. 先物化普通api_call+sql，再走原精调和执行。R5保留精调调用，但若建议改动已验证输出合同则保留物化SQL。family分支提前返回，不会自动继承B后续独立聚合；多资源/复合请求不能答一部分。B须单独设计完整2–4原子覆盖与编排，未支持时走None→空结果，不取消R5守卫凑覆盖。
5. 旧train_replay的fake_model仅处理select/fill/refine，缺family_fill；旧API无法还原结构参数。旧回放只能作条件合同证据，不能冒称真实抽参；新真实运行应完整保存family_fill响应与预算记录。新指纹需新计划，不能删freeze断言或伪造旧hash。
6. SDK None沿原封装为matched/sql/result/error的null；成功0行保留columns/rows=[]/row_count=0对象。内部diagnostics保留，用户界面只呈result，不能把内部原因整包展示；真实异常继续抛出/记录，不能吞作未支持。详见[空输出合同](EMPTY_OUTPUT_CONTRACT.md)。

## 重测顺序、开关和回滚

先验证B适配后的真实导入路径、180数量/唯一ID/6个family、索引400文档、元数据容量、参数类型/角色与正负控制；之后原SDK/本机服务正常/空/缺字段/多键与B旧聚合回归。当前包尚未完成B v18 family端到端或原生CMDB服务验证，不把250 fixture/50 mock/语义审查算真实成绩。

现有scripts/train_live.py会从其项目根implementation导入；仅设置PYTHONPATH不能保证切到候选。B应在独立受控候选快照接入两份A文件与已移植matcher，或明确增加实现目录选项并验证__file__，不污染当前198运行和数据服务。训练工具仍属B；本包没有擅加不存在的CLI参数。

B按现有[C复测协议](../training/C_RETEST_PROTOCOL_V18.md)和configs/train150_v18.env固定Flash、显式thinking disabled、完整flags、1024上限、SDK重试0、同评分器/缓存/计时。仅train150，sealed50继续封存，不重抽，也不读全200/旧全200逐题反馈；此前全模板暴露不能叫完全未见泛化。先新预检计划，再受影响训练范围+已过项回归，预算允许才完整150。必须保存新代码/模型/数据/模板N/hash、实际请求/token/费用和错误分类。旧640/750仅固定B8a16793的一次150；main合并版与180都未真实复测。

本交付不启动模型、不新增费用授权；后续调用仍计本轮累计50元，先统一账本和未决预留，保留实际额度15%，不沿用旧计划余额、不重复进程、不充值。

生产切换门禁：B v18增量适配、有限语义正负/组合、原SDK服务、B旧能力回归及新真实重测证据齐备后，才能建议采用180。当前不满足；候选已就绪不等于正式上线。回滚只移除本候选应用，回到固定198 A模板与对应检索版本，保留B v18和后续他人提交；不reset整个分支、不强推。

## 固定组件与来源口径

本轮未改官方执行器、评分器、数据、服务或官方入口。B v18远端把官方入口恢复并声明采用数值ratio修订，当前evaluator SHA256为d2a93903f068d77d84470dcd1e3eef8671571136c1d7cfb7e4f9b3307d3516c1。该修订来源仅由B交接声明；A本轮不自行改动或背书为官网修订。B/C应统一已确认口径；旧评分器与新评分器、150与200、单次与双次结果不得混比。

完整库按dict/list计深最大7、含外数组8，198也如此；不是仅首批6族的深6。官方深度算法未确认。静态最大2562B仅当前冻结值，真实长实体/物化参数会变，4KB须在实际提交前重查。关联缺证、NULL桶、稀疏字段等原业务缺口不因合并自动修复，黑盒未测，不给虚构总分。

## 已读取B请求及后续分工（来源099b5bf）

来源：[B_AC_HANDOFF_V18](../training/B_AC_HANDOFF_V18.md)、[A_C_NEXT_PROMPT](../training/A_C_NEXT_PROMPT.md)、[AC_BLOCKERS](../training/AC_BLOCKERS_20261030.md)。接受同文件一人、train150/sealed50隔离、可执行合同、同配置重测、不猜关系；文档旧的逐轮push限制不阻止用户已明确批准本轮main发布。700/750是阶段训练目标，不替代比赛总分。

|责任|下一项可执行工作|证据/边界|
|---|---|---|
|A合同|状态全集、异常/报废、tenant与VDC范围角色；给字段/操作符/类型/空值与正负例|不按题号硬编码，不猜状态映射；参考冲突交C/主办核查|
|A关系|数据库专用盘→池、部署region/AZ、磁盘类型与协议、物理网络归属|无键/覆盖证据就标未知，宿主非启动卷不能冒充数据库盘|
|A合同+C|ROUTER.id→EIP.routerId、逐VPC粒度；NULL租户排名与未知CPU政策|核唯一性/缺失/覆盖；不删正确对象凑参考分|
|检索|阶段2的重要信息/子意图、多样覆盖，继续分族精简|另冻结协议和负控制，阶段1只保留基线；不夹带batch2|
|B|v18移植R5、family_fill日志/回放、完整组合/空输出适配和重测|不覆盖新helper；旧回放缺结构响应不能算新抽参|
|C|同版本原SDK复现、范围/参考覆盖冲突、业务完整性与原分分列|不改评分器；封存评估不回流调参|
|集成|版本/hash、容量、保护文件、门禁/回滚与main发布|本次只发布隔离候选与交接，生产198不动|
