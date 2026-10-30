# A→B：六族合同与状态/聚合争议回应（3057d64）

**本次为给B的脱敏文档回应，不修改实现。30个设计案例尚未执行，不能称已测；VM/HOST参考覆盖、聚合身份粒度及共同SDK业务问题仍待裁定。** 原A_REPLY.md SHA256为35d4efbdf4034b82a52558bda527669699193d7c85ae4020a63e0fc48f938281。发布版匿名化集群名，仅保留必要聚合和字段合同；原生逐对象明细、本机路径及密钥不上传。

本回应只提供合同与证据，不修改matcher、模板、检索、执行器、评分器或参考答案。固定来源为main `3057d64b47d4926d463eedfe0dfc3e683251e576`；13份仓库源码/文档和11份原生资源JSON的Git blob均逐一核对。详见[来源与必要聚合摘要](A_B_CONTRACT_REPLY_3057d64.sources.json)。没有读取50题或完整200题的逐题问题、答案、日志和反馈。

可直接确认三点：**旧044默认输出含type='ECS'；旧133的“各租户的弹性IP绑定状态”被源合同定义为租户×状态计数；F20结构层必须保持JSON bool，原生API层按NETWORK.shared的字符串枚举转换。** 兼容旧合同不要求用户额外念出源SQL中的标签/聚合词。当前提示或守卫与旧合同不一致处，应单列修复，不把新输出政策追认为旧合同。

## 1. 六族共同字段与边界

以下是已存在的结构合同，供B完善提示中的字段联动；不是新DSL或可直接执行的Schema。机器可读清单见[六族合同清单](A_B_CONTRACT_REPLY_3057d64.contracts.json)。

|字段|类型与规则|
|---|---|
|scope|string枚举global/filtered。global须原问题明确全局且filters为空，仅F01/F08可用；任何筛选存在时为filtered。|
|filters|object。只接受本族字段；未出现的可选字段省略。已明确条件全部保留，不能填null后丢条件。值必须来自当前问题，不用旧默认实体。|
|required_filters|唯一字符串数组，集合必须恰等于filters的键；不能漏项、重复或使用其他族字段。|
|布尔条件|shared、management必须type(value) is bool；false不是缺值。字符串“false”、数字0/1、null都不能代替结构bool。|
|其他筛选值|非空原文string；不接受null、空白或未填占位符。状态/网络类型的结构值是字符串，不据语法词表猜完整业务码表。|
|操作符|已有六族仅equal，多字段AND；OR、否定、包含、范围不属于这些闭合合同。|
|结构轴|group/metrics/view/count_alias/label/order均为**单个枚举字符串**，不能复制enum数组；required_filters才是数组。未知顶层键拒绝。|
|输出/执行|各输出列序、标签、公式、分组、筛选及排序均保留；B现有SQL精调阶段继续存在，不能用精调改变已审合同。最终仍为普通api_call+sql。|

分组维度不是null筛选条件；状态分组也不是状态筛选。筛选属于哪个CI由原问题角色和schema决定。静态可物化不等于整条问句可执行，更不等于所有组合均已有真实模型/原生验证。[R5合同源码](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/experiments/a_family_candidate_20261030/r5_family_additions.py#L31)、[当前B抽参Schema](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_matcher.py#L1880)。

## 2. 按族联动清单

### F01：ECS数量与固定状态指标

筛选字段：logicalRegionName、tenantName、vdcName、azoneName、status为string；management为bool。group、metrics必需；其余轴可省略，代码默认count_alias=count、label=none、order=none。**代码默认不代表旧view的默认输出政策。**

|metrics|group|count_alias / label / order联动|固定输出|
|---|---|---|---|
|count|none|必须显式total；label省略/none；order省略/none|total|
|count|status、azoneName、management、tenantName、vdcName|别名省略/count；只有vdcName允许label=ECS；count_desc仅分组时允许|group,count；带ECS标签时为type,vdcName,count|
|total_active|仅vdcName|count_alias只能省略/count，label省略/none，order省略/none|vdcName,total,active_count|
|status_counts|仅azoneName|同上|azoneName,running_count,stopped_count,error_count|

total_active的结构count_alias=total会被拒绝，虽然输出中确实有一列total；该轴不是让模型任意指定所有指标列名。status_counts的旧error_count公式为status NOT IN('active','stopped','building')，NULL不计，building也不计；不能称它完整覆盖“所有其他状态”或主办方定义的“异常”。group=none配count_alias=count、非VDC配ECS标签、非count指标配排序/标签都是非法组合。[物化分支](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/experiments/a_family_candidate_20261030/r5_family_additions.py#L79)。

**F01标签答复：**旧rb_044问题仅问“某区域下各VDC的ECS数量”，原SQL就输出`'ECS' AS type, vdcName, COUNT(*) AS count`；离线迁移映射也明确label=ECS。故兼容这一旧意图时，应保留该标签，不能要求问题显式说type=ECS才添加。当前B提示“label默认为none，只有明确要求常量列时为ECS”与该旧合同不等价。

这不是说问题里任何“ECS”资源名都授权加标签，而是该已证view的输出形状包含标签。若用户明确只要vdcName,count，代码可表达label=none；应将它标明为显式输出请求/新view，不能未经确认把“无标签默认”替换旧默认。本回应未裁定主办方如何给新形状判分，未实现政策变更。[旧044原合同](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_items.py#L1675)、[离线迁移映射](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/experiments/a_family_candidate_20261030/parameter_mapping.json)、[当前B提示政策](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_matcher.py#L1920)。

### 其余五族

|族|必需轴、枚举与筛选|合法输出联动|应拒绝的例子|
|---|---|---|---|
|F08 HOST|group=hypervisorType/azoneName/status；只接受region筛选。global可空filters，filtered须region。|固定group,COUNT(*) AS count；无metrics/view/alias。|把“正常宿主机”当可用status筛选；加metrics或count_alias。|
|F14 VOLUME|metrics=count_sum/avg_max；region必需。group固定vdcName，顶层不提交group。|count_sum→vdcName,count,total_size；avg_max→vdcName,avg_size,max_size。|group=status，或任意添加sum_free、别名、标签。|
|F18 GAUSSDB|group、metrics必需，region必需。|flavorCode/engineVersion/haMode只配count→group,count；vdcName只配count_storage→vdcName,instance_count,total_storage。|flavorCode/count_storage或vdcName/count；数组group、metric单数、其他筛选。|
|F20 NETWORK|view=rows/count；shared bool必需；region、providerNetworkType为可选原文条件。始终filtered。|rows无count_alias，输出name,providerNetworkType,providerPhysicalNetworkSegId；count须显式total/count别名。|rows附count_alias；count不填别名；shared字符串/null；没有shared仍强套此族。|
|F21 FLOATING_IPS|group=vdcName/tenantName_status；region必需且唯一允许筛选。无metrics/view/alias/label轴。|vdcName→vdcName,count；tenantName_status→tenantName,status,count。|group数组；status=ACTIVE或指定tenantName筛选被丢弃；只按tenantName分组。|

F18恰4个合法group×metrics组合，独立枚举的8组合中另外4个须排除；B现oneOf与此吻合，文字Schema不等于提供方强制输出。[F18组合说明](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/docs/training/F18_SCHEMA_COMBINATIONS_20261030.md)。

F20还存在旧别名联动：旧111的shared+providerNetworkType计数用total，旧112的region+shared计数用count；模型未听到用户念别名，仍须继承对应旧输出。当前提示“未指定别名用total”不能作为两旧view都等价的证明。region与providerNetworkType同时出现等新组合，没有由这两条旧合同自动决定的默认别名；应单列新合同/显式输出政策。[旧110/111/112](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_items.py#L3757)。

## 3. F21隐式二维数量意图

旧rb_133原问题就是“某区域下各租户的弹性IP绑定状态”，没有额外“数量/分布”字样；SQL明确GROUP BY tenantName,status并COUNT(*)。因此**在旧合同兼容语义中，这一完整意图足以选择tenantName_status计数view**，不应额外要求用户补数量词。[旧133](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_items.py#L4657)。

这不表示“绑定状态”任意出现都等于二维数量。该view须同时保留：明确区域、各租户、弹性IP、全部绑定状态分布，且无额外明细/比例/状态值筛选。绑定状态沿原status值分桶；不自动压成“已绑定/未绑定”两桶，不推断error、binding、unknown或NULL的二分类。

当前守卫静态分析中，“各租户”只形成tenantName维度，末尾“绑定状态”未必形成status维度，可能与expected={tenantName,status}不符。这是旧意图接地缺口，不能只靠放开所有维度检查处理。建议B在既有语义逻辑内识别该通用旧view意图，并继续保护状态筛选、缺区域和额外输出义务；本回应没有修改代码或宣布该建议已验证。[当前维度守卫](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_matcher.py#L1380)。

|合成文字示例（未跑匹配器）|合同判定|
|---|---|
|区域region_contract_C下各租户的弹性IP绑定状态|旧133兼容意图：tenantName_status，不强加数量词。|
|区域region_contract_C下按租户和状态统计弹性IP数量|显式二维计数。|
|区域region_contract_C下各VDC的弹性IP数量|另一合法view：vdcName。|
|区域region_contract_C下各租户已绑定的弹性IP数量|状态筛选，不是全部状态分布；F21没有status过滤能力，不能丢条件。|
|区域region_contract_C下按租户和状态分组，但只看ACTIVE|仍有明确状态筛选，本族不支持。|
|租户tenant_contract_C的弹性IP绑定状态明细|具名租户/明细且缺区域，不能冒充旧133。|
|区域region_contract_C下各租户弹性IP绑定状态及占比|多了比例义务，不可只返回计数。|

## 4. F20：结构bool与API枚举

结构true/false先通过严格类型与原文接地，之后在**NETWORK.shared的API边界**根据已证明schema枚举规范化。官方背景将shared列为string枚举true/false；本固定数据3806条中3804条为字符串false，2条为字符串true。当前B物化器调用_canonical_enum处理bool；其schema样本匹配会返回原枚举表示。A原R5构建输入直接传bool与B边界转换有差别，不应让B回退。[官方字段](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/背景知识.md#L151)、[当前转换函数](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_matcher.py#L444)、[B API边界](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_matcher.py#L1327)。

|结构输入|边界/合同预期|
|---|---|
|shared:true且原文共享|结构保持bool，原生NETWORK筛选值使用已证字符串true。|
|shared:false且原文非共享|false有效，不作为缺失；原生值使用字符串false。|
|shared:"false"、0、1、null|结构阶段拒绝，不做truthiness转换，不靠API阶段补救。|
|未提region/providerNetworkType|省略该可选字段；不填null，不制造范围。|
|未提shared或只问一般网络数量|不能选择一个未说明的true/false；此族必需条件未满足。|
|schema不可得或枚举表示缺证|不把函数返回值当已证明转换；需B诊断和明确失败/回退合同，不能猜字符串或把错空当正常。|

该转换须按CI/字段完成；VM.management在官方说明中是boolean，不应把所有CI布尔字段全局转换为字符串。providerNetworkType的原数据还出现local，故vlan/vxlan/flat的词面识别列表不是完整业务枚举；不得据此无证缩小其原文字符串值域。全部真值控制为合同示例，本轮没有调用服务验证。

## 5. VM/HOST状态谓词：确认角色，不裁定参考

官方字段定义VM_NOVA.status的active=运行中、stopped=已停止；HOST.status的normal=正常。关系为VM_NOVA.hostId→HOST.id，HOST→VM是一对多。两套状态不是可互换枚举。[VM定义](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/背景知识.md#L94)、[HOST定义](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/背景知识.md#L340)、[关系](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/背景知识.md#L495)。

- “运行中的虚拟机清单”→VM侧active；不能以HOST.normal代替。
- “正常宿主机上的虚拟机”→HOST侧normal；没有额外VM运行条件时，不能自动删stopped VM。
- “正常宿主机上的运行中虚拟机”有两个谓词，需分别保留；不能因修VM角色丢HOST条件或region/AZ范围。
- “运行中宿主机”是否等同normal未由上述字典给出，不能仅因两种状态常一起出现就扩大映射。

旧060的两个API都查HOST，第二次同表覆盖并筛normal；SQL又JOIN VM。按该原公开合同scope对原生JSON做只读关系审计，复现1335个不同VM，其中1287 active、48 stopped；在VM侧增加active及相同region/AZ范围后为1287个。证据见[必要聚合摘要](A_B_CONTRACT_REPLY_3057d64.sources.json)。本轮没有读取保存答案，因此只确认与B描述的计数一致，**没有独立确认“逐行等于参考答案”**，不修改参考或追求原分。

B的_correct_host_vm_status_role只在可证两表、固定JOIN、相同占位范围和闭合文字条件下纠正第二步CI；本回应不扩大该修复。它不能通用于否定/OR、具名额外实体或含HOST独立状态条件的所有问句。[旧060](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_items.py#L2239)、[B限定修复](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_matcher.py#L1993)。

## 6. JOIN聚合：对象去重与数值去重不同

旧034按CLUSTER→HOST→VM做INNER JOIN后，COUNT(DISTINCT HOST.id)与SUM(HOST.totalVcpuCores)的粒度不一致；后者按每个VM关联行重复累加HOST值。SUM(DISTINCT totalVcpuCores)只去掉相同数值，不能按HOST身份去重。两台不同HOST各8核、另一台16核，应按身份合计32；按数值去重只有24。[旧034](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/implementation/runbook_items.py#L1228)。

同一原公开region/AZ范围的原生JSON关系审计结果：

|分组|不同HOST数|JOIN行数|按JOIN行SUM|SUM(DISTINCT数值)|按HOST身份各算一次|
|---|---:|---:|---:|---:|---:|
|集群A（匿名）|2|14|2436|174|348|
|集群B（匿名）|8|492|132840|270|2160|
|集群C（匿名）|11|829|268596|324|3564|
|合计|21|1335|403872|768|6072|

这一scope内三集群ID各唯一，21个HOST引用均解析、vCPU非缺失且均有VM，因此6072是该固定域中按HOST身份各一次的小计。该证据不授权将6072写成参考答案，也不能自动确定其他范围的零VM宿主、悬空引用、未知容量或同名集群政策。

兼容原合同：B防止SQL精调擅改原SUM/AVG的DISTINCT方式是保护旧形状，不能将该保护表述为认证原JOIN总量正确。提议新业务合同：若输出定义是“每个集群的HOST vCPU总量”，应在HOST身份粒度独立聚合，再与VM数量聚合组合；先明确父对象保留、身份键、零VM、缺值和关联范围政策。此处仅建议，不新增实现、指标或评估器变更。

## 7. 给B与协调者的执行边界

1. 可直接拿本清单核对六族提示联动，保留B已有helper、布尔边界、SQL精调、角色和输出保护；不要覆盖旧完整patch。任何代码变更由B唯一owner接入。
2. 已证旧兼容要求是044带标签、133隐式二维计数、111/112不同别名。若改成新默认，需单列新view/版本、输出政策和回退边界；本回应未将其认作已经批准的新合同。
3. 需要C/主办方裁定：VM运行中题文与含stopped参考的覆盖冲突；HOST身份总量与旧JOIN重复总量；新默认标签/列变化的判分政策；EIP状态二分类及未知桶政策若拟新增。
4. 共同SDK空表占位COUNT=1、缺列返回空及失败/部分响应歧义继续阻塞业务正确性；不统一SQL改0、不吞错、不改执行器来凑数量或分数。

版本说明：本固定提交当前matcher SHA256为`2668bf06805ecafd2a3d757787bb236b084feba401e3d783d7576fae173d0eb1`，静态含F27分支；前六族spec与R5逐对象相同。B交接中180实测冻结matcher是`dced03e08a68670a7c4899060b6c2ac1fee57c680bf91de53322928f7a7b96d9`，两者不能混写。源码含某分支也不证明当前实例加载了170或180。[170隔离README](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/experiments/a170_runtime_port_20261030/README.md)的免费/原生检查不等于真实模型成绩，且明确共同空表门禁未通过。

B的180历史评估只属于其冻结版本，不归本回应或160。本任务未查看50或完整200逐题反馈、未据留出汇总调参、未重跑模型或评分，也不将不同版本成绩拼接。[B原交接](https://github.com/getm0ss1moving/hackathon-p13-2/blob/3057d64b47d4926d463eedfe0dfc3e683251e576/docs/handoffs/B_TO_A_180_STATUS.md)。
