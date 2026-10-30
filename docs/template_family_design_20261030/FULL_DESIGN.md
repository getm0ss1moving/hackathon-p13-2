> 发布范围：这是源51f0aad、200条模板的设计快照，尚未通过生产接入验收。正文中的根/B双目录比较属于旧时点；当前main已统一根目录，严格去重后为198条（054→052、087→086）。本文不改生产。实体示例在本发布副本中用参数占位，完整机器接口/原始证据仍由本地实施与独立审查任务保留；本目录不提供可执行候选。

# 全200条模板族参数化设计（独立复核）

以51f0aad固定的200条公共模板为输入，没有读取原白盒、训练题或封存50题。设计与原执行合同分开；没有生产修改或推送。

固定设计源N=200；当前生产N由独立集成任务负责，以其实际提交为准。本设计得到27个互不重叠的合并族，覆盖98个旧模板；102个保留单例。若全部合同与B/模型验证通过，源200上的算术N为129，减少71。这个数不包含能力修复，不是已达到结果。

首批六族25条→6条，条件N=181；可以先由实现任务并行接入。其余族有明确先决条件，不能以总量估计替代验收。

旧草案200→147按图连通把重叠候选归并；本版按可编译参数轴重新划分，补入ECS完整数量/直接属性、宿主物理配置、卷容量多指标等族，拒绝仅因相同残缺SQL合并子网/OBS容量/多资源题。两版N不可当成绩比较。

## 接口与证据约束

FAMILIES.json为设计审计文件，source_contracts保留每个旧API/SQL。正式新模板不能内嵌所有旧查询当万能分发表；应把公共取数骨架、闭合字段/指标映射和合法组合直接放入原matcher的小段逻辑。FULL_MAPPING的oldID仅供离线迁移，运行时根据自然语言语义选择结构参数，禁止按oldID或完整题文查SQL。

FIRST_BATCH.json的25行是可精确物化的闭合枚举配置，其余映射是输出/筛选/依赖→语义轴的完整审计接口，仍需B实现相应族的物化函数。后者明确不能直接拿作运行时自由SQL参数。

物化必须发生在无占位符提前返回和SQL精调之前。根matcher与B matcher不同：根仍禁止UNION/删除LIMIT，B已支持受控精调、TopK、紧邻空依赖校验。集成方不得用根旧版整文件覆盖B train-only代码。

global/未提及过滤和filtered/已提及但缺值分开。False/0是值；None/空字符串不是有效必需条件；明确条件缺值失败关闭。所有实体源自用户/已证上下文，源默认值仅是离线旧合同证据。

固定SDK只直接传紧邻前步，同表后步覆盖前表，空前步/缺键可退化无条件查询，空表可能创建占位行，缺列可被吞为空。B现有依赖检查只在其真正调用路径生效；stop_on_empty元数据本身无效。不改SDK，不发明可回溯任意step的DSL。

官方页面本次web文本读取超时，结构规则沿用原交接的独立核验转述：允许调整模板结构，单条4KB/深度4，N按数组条目计，150不是上限。官方深度算法未知，下面按dict/list容器计层仅为风险检查。

## 族清单

|族|能力|旧ID|条件减少|风险|候选紧凑字节/深度|
|---|---|---|---:|---|---|
|F01|ECS单源数量与分布|001/002/003/004/005/007/017/044/074/184|9|medium|1827/3|
|F02|ECS直接属性明细|006/009/029/037/038/039/040/042/075/182|9|medium-high|1757/6|
|F03|ECS规格关联明细|008/010/016/043|3|medium-high|1603/7|
|F04|ECS规格分布与TopK|011/012/015|2|high|1448/7|
|F05|VM到宿主及物理服务器归属|018/020/027/028|3|medium-high|1585/6|
|F06|弹性IP绑定VM关系|021/041|1|high|1335/7|
|F07|指定宿主VM计数|023/026|1|medium-high|1024/7|
|F08|宿主机单源分布|048/049/053|2|low-medium|743/3|
|F09|宿主物理配置查询|031/050/051/058|3|medium-high|1252/6|
|F10|宿主资源排名|056/057|1|medium-high|1045/6|
|F11|物理服务器单源分布|052/054/063/065/066/072|5|high|1350/6|
|F12|设备类别分布|068/073|1|high|817/6|
|F13|云服务部署节点明细|076/077|1|medium-high|1390/6|
|F14|卷按VDC容量统计|086/087/102|2|low-medium|895/6|
|F15|VM与卷挂载明细|089/090/091/094|3|medium-high|1515/6|
|F16|单池容量与使用率明细|095/097|1|medium|1278/6|
|F17|存储池分组容量汇总|096/098/104/189|3|medium-high|1623/6|
|F18|GaussDB单源数量分布|105/106/143/144/150|4|medium|1161/6|
|F19|GaussDB基本属性明细|142/145/146/148/155|4|medium-high|1252/6|
|F20|共享网络清单与计数|110/111/112|2|low-medium|1019/6|
|F21|弹性IP数量分布|113/133|1|low-medium|818/6|
|F22|ELB监听器明细与协议分布|115/116/117/119|3|medium-high|1359/6|
|F23|VM网卡及子网属性明细|121/123|1|medium-high|1297/6|
|F24|应用模块与组件实例清单|165/166/167/180|3|high|1245/6|
|F25|中间件集群及成员查询|152/153|1|medium-high|961/3|
|F26|虚拟防火墙查询|140/141|1|medium|700/6|
|F27|OBS桶清单与租户分布|099/101|1|medium|825/6|

## F01 ECS单源数量与分布

旧ID：rb_001、rb_002、rb_003、rb_004、rb_005、rb_007、rb_017、rb_044、rb_074、rb_184。条件减少N=9。

**参数轴**：{"scope":["global","filtered"],"group":["none","status","azoneName","management","tenantName","vdcName"],"metrics":["count","total_active","status_counts"],"count_alias":["count","total"],"label":["none","ECS"],"order":["none","count_desc"],"filters":["logicalRegionName","tenantName","vdcName","azoneName","status","management"]}

**合法组合**：count允许单个所列group或none；total_active仅vdcName；status_counts仅azoneName；label=ECS仅vdcName/count；count_desc仅count且有group；global无筛选；filtered有至少一个已提及条件且全部required_filters取值成功。

**不合法组合**：group=[status,azoneName]不等于任一原一维合同；total_active+tenantName不在当前审核闭集；scope=global但明确用户区域缺值；任意SQL表达式或未知分组字段。

**输出合同**：count:所选分组列+count；标量total；VDC活跃统计:vdcName/total/active_count；AZ状态统计:azoneName/running_count/stopped_count/error_count。标签型多type列；只在指定时排序。

**B配合**：在无占位符提前返回前提取结构参数；物化普通API条件与闭合SQL；保持每个group一维；固定status集合表达式不随精调改写；异常语义另核实；保护ECS常量标签和count/total别名。

**验证**：逐10原配置比较API条件/SQL/列名；全局、区域、租户+区域+AZ、VDC+区域；False/0和缺值；构造AZ与状态交叉数据，证明一维不会退化二维。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_001|status,count|status||none / None|
|rb_002|status,count|status|VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_003|azoneName,count|azoneName|VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_004|total|明细/标量|VM_NOVA.tenantName equal {{tenantName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.azoneName equal {{azoneName}}|none / None|
|rb_005|management,count|management|VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_007|tenantName,count|tenantName|VM_NOVA.logicalRegionName equal {{logicalRegionName}}|count DESC / None|
|rb_017|vdcName,total,active_count|vdcName|VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_044|type,vdcName,count|vdcName|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_074|tenantName,count|tenantName|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_184|azoneName,running_count,stopped_count,error_count|azoneName|VM_NOVA.vdcName equal {{vdcName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|

## F02 ECS直接属性明细

旧ID：rb_006、rb_009、rb_029、rb_037、rb_038、rb_039、rb_040、rb_042、rb_075、rb_182。条件减少N=9。

**参数轴**：{"projection":["name","privateIps","status","tenantName","vdcName","azoneName","clusterName","createdAt","nativeId"],"alias_style":["native","semantic"],"order":["none","tenantName"],"filters":["name","tenantName","vdcName","logicalRegionName","azoneName","status"]}

**合法组合**：查询粒度始终每条VM记录；只投影已审查字段，别名随输出合同；只有排序不是分组。

**不合法组合**：把tenantName与vdcName互换；把IP输出当IP筛选；因未填租户/状态而删条件；保留182无消费者FLAVOR请求却称关联能力；或不经证明自动删查找。

**输出合同**：各旧投影原列与顺序分别保留；不统一返回所有列。009创建时间、029归属字段仍是VM直接属性。

**B配合**：新增受控投影清单及别名策略，先物化再精调；075租户→VDC语义冲突待公共合同；182无消费者FLAVOR须按B已实现的可证明裁剪路径验证；不能整文件覆盖B。

**验证**：每个投影的原列名和行粒度；中文紧邻实体、错误区域、同名不同ID、缺属性与真实NULL。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_006|name,privateIps,tenantName|明细/标量|VM_NOVA.azoneName equal {{azoneName}}; VM_NOVA.status equal {{status}}|none / None|
|rb_009|name,createdAt|明细/标量|VM_NOVA.name equal {{name}}|none / None|
|rb_029|name,clusterName,azoneName|明细/标量|VM_NOVA.name equal {{name}}|none / None|
|rb_037|name,privateIps,status|明细/标量|VM_NOVA.tenantName equal {{tenantName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_038|name,privateIps,status|明细/标量|VM_NOVA.tenantName equal {{tenantName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.azoneName equal {{azoneName}}|none / None|
|rb_039|name,privateIps,tenantName|明细/标量|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.azoneName equal {{azoneName}}|none / None|
|rb_040|tenant_name,azone_name,vm_name,private_ips|明细/标量|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_042|tenantName,name,privateIps|明细/标量|VM_NOVA.vdcName equal {{vdcName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.azoneName equal {{azoneName}}|tenantName / None|
|rb_075|name,status,nativeId|明细/标量|VM_NOVA.vdcName equal {{vdcName}}|none / None|
|rb_182|vm_name,tenant_name|明细/标量|VM_NOVA.logicalRegionName equal {{logicalRegionName}}|none / None|

**沿用源问题，不视为修复**：rb_075 模板以vdcName筛租户，租户/VDC角色待核；rb_182 无消费者FLAVOR步骤，不代表具备规格关联输出。

## F03 ECS规格关联明细

旧ID：rb_008、rb_010、rb_016、rb_043。条件减少N=3。

**参数轴**：{"projection":["vm_name","status","flavor_name","vcpuSize","ramSize","diskSize","azoneName","private_ips"],"join_policy":["inner","keep_unmatched_vm"],"order":["none","azoneName"],"filters":["name","tenantName","logicalRegionName","status"]}

**合法组合**：仅VM.flavorId=FLAVOR.id关系；keep_unmatched_vm对应LEFT JOIN；按所需列组合投影。

**不合法组合**：统一INNER JOIN丢43缺规格的VM；把FLAVOR.name与VM.name作为一个无角色name槽；VM为空或flavorId缺失仍无条件查FLAVOR。

**输出合同**：VM粒度；008不额外加规格名称；010含规格配置；016有AZ和排序；043有IP并保留未关联VM。

**B配合**：复用B紧邻步骤依赖校验，验证source非空且依赖键非空；物化后再做SQL表集合保护，不能要求所有视图固定同表之前就拒绝；LEFT/INNER语义与输出粒度保护。

**验证**：有效/无规格/重复flavorID/空首步/缺键，观察下一步HTTP数；4个旧投影/别名/排序逐一比较。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_008|vm_name,status,vcpuSize,ramSize,diskSize|明细/标量|VM_NOVA.name equal {{name}}; FLAVOR.id equal {{flavorId from step 1}}|none / None|
|rb_010|vm_name,status,flavor_name,vcpuSize,ramSize,diskSize|明细/标量|VM_NOVA.tenantName equal {{tenantName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}; FLAVOR.id equal {{flavorId from step 1}}|none / None|
|rb_016|azoneName,vm_name,flavor_name,status|明细/标量|VM_NOVA.tenantName equal {{tenantName}}; VM_NOVA.logicalRegionName equal {{logicalRegionName}}; FLAVOR.id equal {{flavorId from step 1}}|azoneName / None|
|rb_043|vm_name,private_ips,flavor_name|明细/标量|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.status equal {{status}}; FLAVOR.id equal {{flavorId from step 1}}|none / None|

## F04 ECS规格分布与TopK

旧ID：rb_011、rb_012、rb_015。条件减少N=2。

**参数轴**：{"scope":["global","region"],"group":["flavor_config","tenant_flavor_config"],"order":["count_desc","none"],"top_k":["none","positive_integer"]}

**合法组合**：flavor_config=规格名称+vcpu+ram+disk；tenant_flavor_config=tenant+规格名称+vcpu+ram；top_k仅在用户明确TopK时启用；对应count_desc。

**不合法组合**：为统一粒度给15加diskSize；把所有规格分布固定截成10行；根matcher自动删除LIMIT。

**输出合同**：原规格配置键与tenant维度、COUNT别名、排序截断分别保留。013因原来缺1核2G筛选不并入。

**B配合**：B路径已允许明确TopK，根路径仍删LIMIT；选择正确集成路径；空VM或缺flavorId拒绝展开；不得根据原题默认top10，K来自用户意图。

**验证**：K=1/3/10/非法值；同规格名不同配置、同配置不同名称、租户分组；空依赖下0后续请求。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_011|flavor_name,vcpuSize,ramSize,diskSize,count|CLOUD_FLAVOR.name,CLOUD_FLAVOR.vcpuSize,CLOUD_FLAVOR.ramSize,CLOUD_FLAVOR.diskSize|FLAVOR.id equal {{flavorId from step 1}}|count DESC / 10|
|rb_012|flavor_name,vcpuSize,ramSize,diskSize,count|CLOUD_FLAVOR.name,CLOUD_FLAVOR.vcpuSize,CLOUD_FLAVOR.ramSize,CLOUD_FLAVOR.diskSize|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; FLAVOR.id equal {{flavorId from step 1}}|count DESC / 10|
|rb_015|tenantName,flavor_name,vcpuSize,ramSize,count|tenantName,CLOUD_FLAVOR.name,CLOUD_FLAVOR.vcpuSize,CLOUD_FLAVOR.ramSize|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; FLAVOR.id equal {{flavorId from step 1}}|none / None|

## F05 VM到宿主及物理服务器归属

旧ID：rb_018、rb_020、rb_027、rb_028。条件减少N=3。

**参数轴**：{"anchor":["vm_name","private_ip","region_status"],"depth":["host","physical_server"],"projection":["vm_name","privateIps","tenantName","azoneName","host_name","host_ip","server_name","server_id"],"order":["none","azoneName"]}

**合法组合**：host路径VM.hostId=HOST.id；physical_server再接HOST.serverId=SYS_X86Server.id；private_ip是contain；名称/region/status是equal；筛选均约束VM。

**不合法组合**：拿HOST.status替代VM.status；把IP匹配改equal而丢列表IP；将174的LEFT cluster支路无证混入。

**输出合同**：保留VM与HOST的原INNER关系与物理层可选扩展；投影粒度为原关联行。

**B配合**：物化固定有限路径，schema存在性检查；异常枚举歧义先拒绝或用明确状态，不猜训练参考。

**验证**：名称/IP/区域+状态3起点；VM无host、host无server、同名不同ID和缺列；不吞错算空成功。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_018|azoneName,vm_name,privateIps,tenantName,host_name|明细/标量|VM_NOVA.logicalRegionName equal {{logicalRegionName}}; VM_NOVA.status equal {{status}}|CLOUD_VM_NOVA.azoneName / None|
|rb_020|vm_name,privateIps,host_name,host_ip|明细/标量|VM_NOVA.privateIps contain {{privateIps}}|none / None|
|rb_027|vm_name,host_name,host_ip,server_name,server_id|明细/标量|VM_NOVA.name equal {{name}}|none / None|
|rb_028|vm_name,host_name,host_ip|明细/标量|VM_NOVA.name equal {{name}}|none / None|

## F06 弹性IP绑定VM关系

旧ID：rb_021、rb_041。条件减少N=1。

**参数轴**：{"anchor":["fixed_ip","region_binding_status"],"projection":["floating_ip","vm_name","privateIps","private_ips"],"filters":["fixedIpAddress","logicalRegionName","status"]}

**合法组合**：先EIP后VM，EIP.fixedIpAddress=VM.privateIps；固定IP与范围/绑定状态独立槽。

**不合法组合**：擅自假设IP列表等于单IP；status缺失时查全部EIP；把EIP状态填进VM.status。

**输出合同**：保留21/41列别名差异与绑定关系原粒度；列表IP连接本身存在数据语义风险。

**B配合**：验证真实绑定状态枚举和IP字段格式；复用B空依赖校验；多键长URL风险单列。

**验证**：单绑定/多个绑定/空fixedIp/多IP字段；实际API字段、操作符、HTTP状态和输出联合验证。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_021|floating_ip,vm_name,privateIps|明细/标量|FLOATING_IPS.fixedIpAddress equal {{fixedIpAddress}}; VM_NOVA.privateIps contain {{fixedIpAddress from step 1}}|none / None|
|rb_041|vm_name,private_ips,floating_ip|明细/标量|FLOATING_IPS.logicalRegionName equal {{logicalRegionName}}; FLOATING_IPS.status equal {{status}}; VM_NOVA.privateIps contain {{fixedIpAddress from step 1}}|none / None|

## F07 指定宿主VM计数

旧ID：rb_023、rb_026。条件减少N=1。

**参数轴**：{"group":["none","status"],"filters":["host_name","vm_status"],"count_alias":["total","count"]}

**合法组合**：HOST名称equal；hostId传VM；可选VM状态；status组或标量。

**不合法组合**：HOST空时移除hostId扩大VM；按HOST.status代替VM.status；宿主名称与ID混填。

**输出合同**：标量total与status/count分别返回；不额外输出宿主资源总量。

**B配合**：统一为已证明的HOST→VM紧邻依赖；两种原取数计划要做原生对照。

**验证**：同宿主多状态、无VM宿主、无宿主、重复名称、缺id。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_023|total|明细/标量|HOST.name equal {{name}}; VM_NOVA.hostId equal {{id from step 1}}; VM_NOVA.status equal {{status}}|none / None|
|rb_026|status,count|CLOUD_VM_NOVA.status|HOST.name equal {{name}}|none / None|

## F08 宿主机单源分布

旧ID：rb_048、rb_049、rb_053。条件减少N=2。

**参数轴**：{"scope":["global","filtered"],"group":["hypervisorType","azoneName","status"],"filters":["logicalRegionName"]}

**合法组合**：单个group；global无筛选；filtered区域必填。

**不合法组合**：把VM状态混入宿主状态；任何二维group。

**输出合同**：所选字段/count；不排序、不改变分组键。

**B配合**：闭合字段枚举；无占位符仍提取结构参数。

**验证**：三旧配置、区域缺值、全局/区域对照；三分组键独立。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_048|hypervisorType,count|hypervisorType||none / None|
|rb_049|azoneName,count|azoneName|HOST.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_053|status,count|status|HOST.logicalRegionName equal {{logicalRegionName}}|none / None|

## F09 宿主物理配置查询

旧ID：rb_031、rb_050、rb_051、rb_058。条件减少N=3。

**参数轴**：{"view":["details","architecture_count"],"projection":["host_name","ip_address","cpuModel","manufacturer","cpuArch","cpu_arch","total_vcpu","allocated_vcpu"],"filters":["host_name","logicalRegionName","azoneName"]}

**合法组合**：固定HOST.serverId=SYS_X86Server.id；details为宿主粒度，count仅按cpuArch。

**不合法组合**：拿SYS_X86Server自身cpuArch总数替代HOST关联计数；未关联物理机当成功空值；混入060错误状态来源。

**输出合同**：31/58保持各自配置列；50/51输出cpu_arch/count且只统计关联宿主。

**B配合**：输出grain与group保护；确认隐式补表不扩大起点范围；物理缺失不伪造。

**验证**：多个宿主共享server、缺server、无范围、两范围交叉；API筛选资源与SQLJOIN基数核查。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_031|host_name,cpuModel,manufacturer,cpuArch|明细/标量|HOST.name equal {{name}}|none / None|
|rb_050|cpu_arch,count|SYS_X86Server.cpuArch|HOST.azoneName equal {{azoneName}}|none / None|
|rb_051|cpu_arch,count|SYS_X86Server.cpuArch|HOST.logicalRegionName equal {{logicalRegionName}}; HOST.azoneName equal {{azoneName}}|none / None|
|rb_058|host_name,ip_address,total_vcpu,allocated_vcpu,cpu_arch|明细/标量|HOST.logicalRegionName equal {{logicalRegionName}}; HOST.azoneName equal {{azoneName}}|none / None|

## F10 宿主资源排名

旧ID：rb_056、rb_057。条件减少N=1。

**参数轴**：{"metric":["vcpu_allocation_rate","remaining_memory_mb"],"top_k":["positive_integer"],"filters":["logicalRegionName","azoneName"]}

**合法组合**：两个已定义指标降序；K明确提取；投影随指标选对应原始数值与派生列。

**不合法组合**：将剩余内存和分配率互换；随意删除LIMIT或默认K；总vCPU为0时伪造比率。

**输出合同**：56:name/ipAddress/allocatedVcpuCores/totalVcpuCores/allocation_rate；57对应总内存/已分配内存/remaining_memory。

**B配合**：B TopK保护；单位MB保留；零分母按SQLite NULL并披露。

**验证**：K变化/并列/零分母/NULL/区域与AZ；根与B流程差异不掩盖。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_056|name,ipAddress,allocatedVcpuCores,totalVcpuCores,allocation_rate|明细/标量|HOST.logicalRegionName equal {{logicalRegionName}}|allocation_rate DESC / 5|
|rb_057|name,ipAddress,totalVmemoryMB,allocatedVmemoryMB,remaining_memory|明细/标量|HOST.azoneName equal {{azoneName}}|remaining_memory DESC / 3|

## F11 物理服务器单源分布

旧ID：rb_052、rb_054、rb_063、rb_065、rb_066、rb_072。条件减少N=5。

**参数轴**：{"group":["cpuArch","manufacturer","logicalRegionName"],"filters":["logicalRegionName","productName","manufacturer"],"order":["none","count_desc"],"top_k":["none","positive_integer"]}

**合法组合**：单源S_X86Server；单group；厂家/型号/区域可联合筛选；整个Region需要上下文或显式区域，不能从默认实体猜。

**不合法组合**：052缺区域却当global；将cpuArch代替HOST关联架构分布；任意productName字符串声称真实泛化。

**输出合同**：原字段/count；66保留最多区域Top1与count倒序，不合并成全量。052/054严格执行重复包含在本族，不重复计减少。

**B配合**：052上下文合同；型号多词实体；字段可空与枚举；TopK使用B路径；保留旧052/054召回缺口作为负证据。

**验证**：各group×筛选，不做无意义笛卡尔测试；至少一个非空型号正例；只有一型号时声明泛化未测；原先重复合并召回缺口回归。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_052|cpuArch,count|cpuArch|S_X86Server.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_054|cpuArch,count|cpuArch|S_X86Server.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_063|logicalRegionName,count|logicalRegionName|S_X86Server.productName equal {{productName}}|none / None|
|rb_065|manufacturer,count|manufacturer|S_X86Server.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_066|logicalRegionName,count|logicalRegionName|S_X86Server.manufacturer equal {{manufacturer}}|count DESC / 1|
|rb_072|logicalRegionName,count|logicalRegionName|S_X86Server.logicalRegionName equal {{logicalRegionName}}|none / None|

**沿用源问题，不视为修复**：rb_052 整个Region需要上下文，默认region不能代替上下文解析。

## F12 设备类别分布

旧ID：rb_068、rb_073。条件减少N=1。

**参数轴**：{"group":["class_Name"],"filters":["assetStatus","logicalRegionName"]}

**合法组合**：可按状态、区域或两者筛选；明确提及条件必需。

**不合法组合**：未证scrapped=报废就默认填值；类别展示名和class_Name混换。

**输出合同**：class_Name/count；仍是设备，不是宿主或X86服务器计数。

**B配合**：公共状态枚举和资源归属须先补证；缺值停止。

**验证**：已证状态非空正例、未知中文状态拒绝、状态+区域AND。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_068|class_Name,count|class_Name|S_Device.assetStatus equal {{assetStatus}}|none / None|
|rb_073|class_Name,count|class_Name|S_Device.logicalRegionName equal {{logicalRegionName}}|none / None|

## F13 云服务部署节点明细

旧ID：rb_076、rb_077。条件减少N=1。

**参数轴**：{"projection":["node_name","node_id","host_name","mgmt_ip","host_class"],"filters":["cloud_service_indexName"],"dedupe":["projected_distinct"]}

**合法组合**：唯一CloudService→Service→DeployComponent→DeployInstance→DeployNode路径；indexName contain。

**不合法组合**：将节点类型替代实例类型；DISTINCT投影变化导致的去重粒度被忽略。

**输出合同**：76节点ID/宿主/IP；77节点名/host_class；各自DISTINCT键按投影保留。

**B配合**：名称角色独立；精调不得改关联键与去重合同。

**验证**：一节点多实例、同名异节点、无组件、缺管理IP和hostClass。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_076|node_name,node_id,host_name,mgmt_ip|明细/标量|S_CloudService.indexName contain {{indexName}}|none / None|
|rb_077|node_name,host_class|明细/标量|S_CloudService.indexName contain {{indexName}}|none / None|

## F14 卷按VDC容量统计

旧ID：rb_086、rb_087、rb_102。条件减少N=2。

**参数轴**：{"group":["vdcName"],"metrics":["count_sum","avg_max"],"filters":["logicalRegionName"]}

**合法组合**：region必填；count_sum=count+SUM(size)；avg_max=AVG(size)+MAX(size)。

**不合法组合**：只保留数量丢总容量；AVG与SUM合成无区别大输出；用volumeTypeId冒充类型名。

**输出合同**：count_sum:vdcName/count/total_size；avg_max:vdcName/avg_size/max_size。size单位原样，NULL按SQLite聚合。

**B配合**：保护指标闭集和别名；086/087词面合并仍需模型回归。

**验证**：不同VDC、NULL/0/不同大小卷，验证SUM/AVG/MAX；重复组与实体替换后真实预期重算。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_086|vdcName,count,total_size|vdcName|VOLUME.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_087|vdcName,count,total_size|vdcName|VOLUME.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_102|vdcName,avg_size,max_size|vdcName|VOLUME.logicalRegionName equal {{logicalRegionName}}|none / None|

## F15 VM与卷挂载明细

旧ID：rb_089、rb_090、rb_091、rb_094。条件减少N=3。

**参数轴**：{"anchor":["vm_name","volume_name"],"projection":["volume_name","size_gb","size","bootable","status","vm_name"],"order":["none","bootable","size_desc"],"top_k":["none","positive_integer"]}

**合法组合**：固定VM—R_VOLUME_MOUNTON_VM—VOLUME；起点与API名称角色一致；最大卷=size_desc+K；系统盘/数据盘按bootable原值展示，不扩大解释。

**不合法组合**：name不区分VM和卷；对无挂载卷伪造VM；用普通VM挂载卷证明GaussDB专用数据盘。

**输出合同**：各旧投影与别名、排序、最大一条单独保持。103每VM挂载数排名另留。

**B配合**：角色化name、TopK保护、多键查询长度风险；INNER行保留，缺挂载不改LEFT而改变回答。

**验证**：反向卷查询、多重挂载、相同卷名、无关系、bootable False、最大并列。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_089|volume_name,size_gb,bootable,status|明细/标量|VM_NOVA.name equal {{name}}|none / None|
|rb_090|bootable,volume_name,size|明细/标量|VM_NOVA.name equal {{name}}|CLOUD_VOLUME.bootable / None|
|rb_091|volume_name,size,status,vm_name|明细/标量|VOLUME.name equal {{name}}|none / None|
|rb_094|volume_name,size|明细/标量|VM_NOVA.name equal {{name}}|CLOUD_VOLUME.size DESC / 1|

## F16 单池容量与使用率明细

旧ID：rb_095、rb_097。条件减少N=1。

**参数轴**：{"projection":["name","totalCapacityGB","freeCapacityGB","provisionedCapacityGB","used_capacity","usage_rate","over_subscription_ratio"],"filters":["name","azoneName"],"order":["none","usage_rate_desc"]}

**合法组合**：逐池计算used=total-free；usage=100*(total-free)/total；over=100*provisioned/total。

**不合法组合**：allocated代替total-free；使用率均值当总体使用率；省略百分数系数100。

**输出合同**：95含provisioned与超配百分比；97按池使用率降序，不附多余列；保留ROUND2和零分母NULL。

**B配合**：指标名、单位和精调表达式保护；不以均值替代加权比值。

**验证**：容量不同池、零总量、负/NULL值，名筛选和AZ筛选。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_095|name,totalCapacityGB,freeCapacityGB,provisionedCapacityGB,used_capacity,usage_rate,over_subscription_ratio|明细/标量|STORAGE_POOL.name equal {{name}}|none / None|
|rb_097|name,totalCapacityGB,freeCapacityGB,used_capacity,usage_rate|明细/标量|STORAGE_POOL.azoneName equal {{azoneName}}|usage_rate DESC / None|

## F17 存储池分组容量汇总

旧ID：rb_096、rb_098、rb_104、rb_189。条件减少N=3。

**参数轴**：{"group":["azoneName","azoneName_storageProtocol","vendorName","none"],"metrics":["capacity_usage","capacity_over_subscription","total_free","count_allocated_free"],"filters":["logicalRegionName","azoneName"]}

**合法组合**：当前审核配对:AZ/capacity_usage；AZ+protocol/capacity_over_subscription；vendor/total_free；none/count_allocated_free；比率先SUM分子分母再相除，ROUND2；不做每池比率平均。

**不合法组合**：allocatedCapacityGB等同used_capacity；把AZ×protocol降为AZ一维；将池数按JOIN行计数。

**输出合同**：96的used=SUM(total)-SUM(free)；98的used=SUM(total-free)，NULL语义也不能强行统一；189独立allocated。各别名按原SQL。

**B配合**：成对group/metric闭集；复杂表达式保护；4KB测量；NULL与算术顺序保持，不能代数化简掩盖缺值。

**验证**：不同容量和NULL组合，验证两种SUM差异；零分母、空范围、协议粒度；新增组合必须另审。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_096|azoneName,total_capacity,free_capacity,used_capacity,usage_rate|azoneName|STORAGE_POOL.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_098|azoneName,storageProtocol,total_capacity,used_capacity,free_capacity,over_subscription_ratio|azoneName,storageProtocol|STORAGE_POOL.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_104|vendorName,total_capacity,free_capacity|vendorName|STORAGE_POOL.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_189|pool_count,total_capacity,allocated_capacity,free_capacity|明细/标量|STORAGE_POOL.azoneName equal {{azoneName}}|none / None|

## F18 GaussDB单源数量分布

旧ID：rb_105、rb_106、rb_143、rb_144、rb_150。条件减少N=4。

**参数轴**：{"group":["flavorCode","vdcName","engineVersion","haMode","engineName"],"metrics":["count","count_storage"],"filters":["logicalRegionName","vdcName","tenantName"]}

**合法组合**：count_storage仅vdcName；其余count；150保留待核租户角色。

**不合法组合**：tenantName与vdcName无证互换；配置存储SUM解释为实际存储池归属；count_storage丢SUM列。

**输出合同**：count:group/count；count_storage:vdcName/instance_count/total_storage，单位GB按dataVolumeSizeInGBs。

**B配合**：先105/106/143/144，150等租户/VDC合同核实再扩展；结构参数先于无占位符返回；保护原指标和分组。

**验证**：四首批配置表达式、region缺值；另以公共字段核实tenant/VDC、引擎枚举，不用封存反馈。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_105|flavorCode,count|flavorCode|GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_106|vdcName,instance_count,total_storage|vdcName|GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_143|engineVersion,count|engineVersion|GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_144|haMode,count|haMode|GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_150|engineName,count|engineName|GAUSSDB_INSTANCE.vdcName equal {{vdcName}}|none / None|

**沿用源问题，不视为修复**：rb_150 租户名称使用vdcName，角色关系待证。

## F19 GaussDB基本属性明细

旧ID：rb_142、rb_145、rb_146、rb_148、rb_155。条件减少N=4。

**参数轴**：{"projection":["name","engineName","engineVersion","haMode","flavorCode","dataVip","eip"],"filters":["name","logicalRegionName","vdcName","tenantName"]}

**合法组合**：每实例原粒度；dataVip和eip两个字段，按用户角色选；名称或区域/租户组合均显式取值。

**不合法组合**：业务VIP和EIP互换；无可用区字段就用区域代替151；无证把155租户转成VDC。

**输出合同**：每个旧属性集合精确保留，不能合并后总是返回所有列。151因AZ缺口独留。

**B配合**：B可用投影白名单，先验证155租户角色；不同视图输出差异不是SQL精调可随意消除的差异。

**验证**：按名、区域、租户+区域；缺dataVip/eip、有重复名字、未知属性。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_142|name,engineName,engineVersion,haMode,flavorCode|明细/标量|GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_145|engineVersion,haMode,flavorCode|明细/标量|GAUSSDB_INSTANCE.name equal {{name}}|none / None|
|rb_146|name,engineVersion,dataVip|明细/标量|GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_148|haMode,dataVip|明细/标量|GAUSSDB_INSTANCE.name equal {{name}}|none / None|
|rb_155|name,engineName,engineVersion,eip|明细/标量|GAUSSDB_INSTANCE.vdcName equal {{vdcName}}; GAUSSDB_INSTANCE.logicalRegionName equal {{logicalRegionName}}|none / None|

**沿用源问题，不视为修复**：rb_155 租户名称使用vdcName；eip不是dataVip。

## F20 共享网络清单与计数

旧ID：rb_110、rb_111、rb_112。条件减少N=2。

**参数轴**：{"view":["rows","count"],"count_alias":["total","count"],"filters":["shared","providerNetworkType","logicalRegionName"]}

**合法组合**：shared为显式布尔语义，True/False均合法值；本三原配置要求shared；rows固定三属性；count为无分组标量；providerNetworkType及region按实际提及启用。

**不合法组合**：把False当缺值；rows混入COUNT或给count增加group；providerNetworkType值用任意SQL拼接。

**输出合同**：rows:name/providerNetworkType/providerPhysicalNetworkSegId；111 total；112 count，别名分别保留。

**B配合**：保留布尔值类型并通过真实API兼容核实字符串/布尔接受口径；约束来源追踪，缺shared拒绝。

**验证**：True/False、vlan/其他合法值、region缺失/未知；25合同中的三种原配置。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_110|name,providerNetworkType,providerPhysicalNetworkSegId|明细/标量|NETWORK.shared equal {{shared}}|none / None|
|rb_111|total|明细/标量|NETWORK.shared equal {{shared}}; NETWORK.providerNetworkType equal {{providerNetworkType}}|none / None|
|rb_112|count|明细/标量|NETWORK.logicalRegionName equal {{logicalRegionName}}; NETWORK.shared equal {{shared}}|none / None|

## F21 弹性IP数量分布

旧ID：rb_113、rb_133。条件减少N=1。

**参数轴**：{"group":["vdcName","tenantName_status"],"filters":["logicalRegionName"]}

**合法组合**：region必填；VDC一维或tenant+status二维只能选择其中一个已审查粒度。

**不合法组合**：将133降为tenant一维；tenant和VDC等同；status分组时自动加某个status过滤。

**输出合同**：113:vdcName/count；133:tenantName/status/count。维度数量明确。

**B配合**：输出group和列名保护；辨别分组字段与筛选字段。

**验证**：一个租户多状态/多VDC对照；region失败拒绝。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_113|vdcName,count|vdcName|FLOATING_IPS.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_133|tenantName,status,count|tenantName,status|FLOATING_IPS.logicalRegionName equal {{logicalRegionName}}|none / None|

## F22 ELB监听器明细与协议分布

旧ID：rb_115、rb_116、rb_117、rb_119。条件减少N=3。

**参数轴**：{"view":["listener_rows","protocol_count"],"projection":["elb_name","elb_id","listener_name","listener_protocol","listener_port","protocol","port"],"filters":["elb_name_contain","logicalRegionName"]}

**合法组合**：固定ELB.id=LISTENER.elbId；protocol_count计监听器关联行，不是ELB个数；rows按原DISTINCT投影；含/不含ELB ID不能随意去掉。

**不合法组合**：把监听器数当ELB数；先JOIN展开再COUNT ELB而不去重；用后端节点AZ代ELB部署AZ。

**输出合同**：115/116/117三个属性/别名集合及DISTINCT保留；119为protocol/count。120 ELB本身计数独留。

**B配合**：目标grain=listener显式；投影/去重保护；ELB名称contain不改equal。

**验证**：一个ELB多监听器、同名监听器、无监听器、同协议多ELB；核对行重复。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_115|elb_name,elb_id,listener_name,listener_protocol,listener_port|明细/标量|ELB.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_116|elb_name,listener_name,protocol,port|明细/标量|ELB.name contain {{name}}|none / None|
|rb_117|listener_name,protocol,port|明细/标量|ELB.name contain {{name}}|none / None|
|rb_119|protocol,count|CLOUD_LISTENER.protocol|ELB.logicalRegionName equal {{logicalRegionName}}|none / None|

## F23 VM网卡及子网属性明细

旧ID：rb_121、rb_123。条件减少N=1。

**参数轴**：{"depth":["port","subnet"],"projection":["port_name","mac","ip","subnet_cidr","gateway","mac_address","port_status"],"filters":["vm_name"]}

**合法组合**：port层VM.resId=PORT.devId；subnet层再经R_PORT_IN_SUBNET连接SUBNET；名称筛选作用VM；121为扩展网卡明细，123为基础端口明细。

**不合法组合**：PORT.id等同VM.id；CIDR字段存在即认为122的CIDR输出已完成；跨层重复行擅自DISTINCT。

**输出合同**：保留121的IP/CIDR/gateway与123的MAC/status；原行粒度和别名分别保留；122缺CIDR不并。

**B配合**：有限路径物化；JOIN键公开schema验证，原表集合校验在物化后。

**验证**：多网卡、多子网关系、缺关系、devId/resId不匹配、无VM，观察缺列。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_121|port_name,mac,ip,subnet_cidr,gateway|明细/标量|VM_NOVA.name equal {{name}}|none / None|
|rb_123|port_name,mac_address,port_status|明细/标量|VM_NOVA.name equal {{name}}; VM_NOVA.name equal {{name}}; VM_NOVA.name equal {{name}}|none / None|

## F24 应用模块与组件实例清单

旧ID：rb_165、rb_166、rb_167、rb_180。条件减少N=3。

**参数轴**：{"target_level":["module","instance"],"projection":["module_name","status","instance_name","instance_id"],"dedupe":["none","projected_distinct"],"filters":["application_name"]}

**合法组合**：Application.id=Module.appId；Module.id=Instance.appModuleId；level决定实际grain；仅直接紧邻依赖；实例nativeId以instance_id输出时保持真实值。

**不合法组合**：模块一行当实例一行；把DISTINCT名称当实体去重；前一步空仍取全部模块/实例；依赖step1实际读step2。

**输出合同**：165 module_name/status；166 module_name/instance_name且DISTINCT；167 instance_name/module_name；180 instance_name/instance_id。顺序与去重须保留。

**B配合**：B已有紧邻依赖校验可复用，不能只加stop-on-empty元数据；统一取数计划前先做原API+SQL对照；167/180标识差异核实。

**验证**：模块无实例、同名模块/实例、应用无模块、缺id；下游请求数；四输出合同和去重键。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_165|module_name,status|明细/标量|Application.name equal {{name}}|none / None|
|rb_166|module_name,instance_name|明细/标量|Application.name equal {{name}}|none / None|
|rb_167|instance_name,module_name|明细/标量|Application.name equal {{name}}; Application.name equal {{name}}; Application.name equal {{name}}|none / None|
|rb_180|instance_name,instance_id|明细/标量|Application.name equal {{name}}; ApplicationModule.appId equal {{id from step 1}}; ApplicationModuleIns.appModuleId equal {{id from step 2}}|none / None|

## F25 中间件集群及成员查询

旧ID：rb_152、rb_153。条件减少N=1。

**参数轴**：{"view":["cluster_count","member_rows"],"filters":[],"projection":["cluster_name","instance_name","status"]}

**合法组合**：cluster_count仅基表；member_rows是Cluster.id=Middleware.parentId的成员关系；成员为空不把集群计数改为0。

**不合法组合**：按成员JOIN后行数当集群数；把cluster_count与实例count混用。

**输出合同**：153 total；152 DISTINCT cluster_name/instance_name/status；grain选择明确。

**B配合**：按view生成必要表集合；不借成员基数改变集群统计。

**验证**：零/多成员集群、同名不同ID、无成员场景和计数独立性。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_152|cluster_name,instance_name,status|明细/标量||none / None|
|rb_153|total|明细/标量||none / None|

## F26 虚拟防火墙查询

旧ID：rb_140、rb_141。条件减少N=1。

**参数轴**：{"view":["rows","vdc_count"],"projection":["name","status"],"filters":["name","logicalRegionName"]}

**合法组合**：rows每条VFW；vdc_count按VDC；字段全为VFW直接属性。

**不合法组合**：将软件VFW与物理Router/Switch计数混合；count视图返回明细行。

**输出合同**：140 name/status；141 vdcName/count。

**B配合**：有限view；区域/名称条件角色区分。

**验证**：同名不同VDC、region无匹配、两种输出形状。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_140|name,status|明细/标量|VFW.name equal {{name}}|none / None|
|rb_141|vdcName,count|vdcName|VFW.logicalRegionName equal {{logicalRegionName}}|none / None|

## F27 OBS桶清单与租户分布

旧ID：rb_099、rb_101。条件减少N=1。

**参数轴**：{"view":["rows","tenant_count"],"filters":["logicalRegionName"],"projection":["name","bucketName","managedStatus"]}

**合法组合**：region必填；rows为桶粒度，tenant_count按tenantName。

**不合法组合**：桶数量代表桶容量；将不完整100的总容量能力算入。

**输出合同**：99 name/bucketName/managedStatus；101 tenantName/count；100缺容量保持单独。

**B配合**：只支持已存在属性，不新增容量猜测。

**验证**：同租户多桶、NULL租户、region缺值、列表和计数对照。

**旧ID→新参数配置**（每行的API/SQL和完整条件证据见FULL_MAPPING.json）：

|旧ID|输出列|分组|过滤角色|截断/排序|
|---|---|---|---|---|
|rb_099|name,bucketName,managedStatus|明细/标量|OBS_BUCKET.logicalRegionName equal {{logicalRegionName}}|none / None|
|rb_101|tenantName,count|tenantName|OBS_BUCKET.logicalRegionName equal {{logicalRegionName}}|none / None|

## 保留单例与未恢复能力

保留单例不是认定永不能合并；是目前没有足够关系/粒度证据，或源合同缺少题意能力。不能为了数量收益把只返回一部分资源的多资源题当成其单资源族。可在缺口补齐后再重新归族。

|旧ID|现状|
|---|---|
|rb_013|提及1核2G，原SQL只有配置分布，未实施明确配置筛选|
|rb_014|独有取数路径/结果语义，本轮原样保留：规格为{{name}}的ECS实例目前有多少台|
|rb_019|UNION异类资源输出；当前根流程可能拒绝，区域与列完整性须原生验证|
|rb_022|独有取数路径/结果语义，本轮原样保留：查询部署节点IPbba98a99对应的部署节点名称和所属云服务|
|rb_024|独有取数路径/结果语义，本轮原样保留：{{name}}集群下宿主机和虚拟机的对应关系|
|rb_025|独有取数路径/结果语义，本轮原样保留：{{name}}集群下有多少台宿主机，每台宿主机上跑了多少虚拟机|
|rb_030|独有取数路径/结果语义，本轮原样保留：查询ECS{{name}}关联的镜像信息|
|rb_032|独有取数路径/结果语义，本轮原样保留：查询集群{{name}}下所有宿主机列表及资源总量|
|rb_033|独有取数路径/结果语义，本轮原样保留：集群{{name}}下宿主机的IP和虚拟化类型，每台宿主机上跑了多少虚拟机|
|rb_034|HOST→VM一对多后SUM宿主vCPU可能重复累计，须基数证据|
|rb_035|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}可用区{{azoneName}}中集群{{name}}下宿主机、VM及挂载云硬盘的端到端拓扑|
|rb_036|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下KVM虚拟化类型的集群有多少个，包含多少台宿主机|
|rb_045|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下各VDC的ECS实例数量、云硬盘数量和云硬盘总容量|
|rb_046|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下ECS数量、云硬盘数量和VPC数量|
|rb_047|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}所有VDC中各VDC的ECS数量、云硬盘数量和VPC数量|
|rb_055|物理架构/AZ统计的是关联VM行；不可解释为物理机数|
|rb_059|独有取数路径/结果语义，本轮原样保留：查询宿主机{{nativeId}}的IP和资源配置，上面跑了多少虚拟机|
|rb_060|重复HOST API覆盖且status作用HOST；题意运行VM状态角色未证|
|rb_061|独有取数路径/结果语义，本轮原样保留：查询部署节点{{name}}的管理IP信息|
|rb_062|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下各VDC的管理虚拟机名称、IP和所属云服务|
|rb_064|独有取数路径/结果语义，本轮原样保留：查询厂商为Huawei的服务器列表，包括主机名、IP地址、CPU型号、CPU架构|
|rb_067|题意超过80%，SQL无对应WHERE阈值|
|rb_069|hostName/hostIpAddress等字段稀疏，执行器可能吞缺列为空|
|rb_070|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下交换机数量和路由器数量|
|rb_071|使用真实NULL保留稀疏字段是现有修复，不证明字段业务值可恢复|
|rb_078|原API无区域，云服务无logicalRegionName；范围映射未证|
|rb_079|原API无区域，部署节点区域关系待证|
|rb_080|独有取数路径/结果语义，本轮原样保留：查询部署节点{{name}}关联的管理虚拟机信息|
|rb_081|type_name为N/A常量，未证明真实卷类型名称|
|rb_082|原SQL按状态计数，未输出容量最大卷|
|rb_083|原SQL标量总数，未输出类型分布|
|rb_084|后一步同表覆盖前步，输出计数不是占比|
|rb_085|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}可用区{{azoneName}}中可启动云硬盘列表|
|rb_088|独有取数路径/结果语义，本轮原样保留：查询VDC{{vdcName}}在区域{{logicalRegionName}}中的云硬盘列表及容量|
|rb_092|独有取数路径/结果语义，本轮原样保留：云硬盘{{name}}当前是否已挂载|
|rb_093|pool_name为N/A，专用数据盘/存储池关系未证|
|rb_100|原SQL只有桶数，无总容量|
|rb_103|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下挂载云硬盘数量最多的前5台ECS，返回ECS名和挂载数量|
|rb_107|独有取数路径/结果语义，本轮原样保留：查询GaussDB实例{{name}}使用的ECS实例|
|rb_108|原SQL只有VPC数，没有子网/VM清单|
|rb_109|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下各VDC的VPC数量|
|rb_114|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下所有未绑定EIP的列表|
|rb_118|独有取数路径/结果语义，本轮原样保留：查询ELB{{name}}关联的弹性IP|
|rb_120|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下ELB数量|
|rb_122|原SQL只有网卡数，没有请求的子网CIDR|
|rb_124|独有取数路径/结果语义，本轮原样保留：查询ECS{{name}}的网卡关联的安全组|
|rb_125|独有取数路径/结果语义，本轮原样保留：查询子网{{name}}下有哪些网卡端口|
|rb_126|原SQL未消费规则表，规则方向不约束端口数；长GET风险|
|rb_127|独有取数路径/结果语义，本轮原样保留：查询安全组{{name}}关联的端口列表及端口所属的ECS|
|rb_128|无消费者ROUTER name查找与全局安全组问题冲突，B有受控裁剪但原评分有隐藏条件|
|rb_129|原SQL只有安全组数量，无规则总数|
|rb_130|原SQL子网计数粒度/步骤依赖须核，未输出EIP数；不因step1文本假设可回溯|
|rb_131|原SQL只输出子网，缺VPC与EIP相关输出|
|rb_132|原SQL只列VPC，无子网数量|
|rb_134|原SQL计已用端口，无完整IP使用率分母|
|rb_135|原SQL只安全组数量，缺其他资源|
|rb_136|原SQL只有名称/CIDR，没有使用率或剩余IP|
|rb_137|原SQL只有CIDR，没有子网数量|
|rb_138|原SQL只有名称/CIDR，没有IP总量及已分配量|
|rb_139|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下网络节点列表|
|rb_147|按实例名GROUP时任取node_name，不等于列出所有节点名称；同名粒度待核|
|rb_149|独有取数路径/结果语义，本轮原样保留：查询业务地址为690b8fb9的GaussDB实例名、主机名和所属租户|
|rb_151|缺可用区筛选，资源无直接AZ字段，不能用区域替代|
|rb_154|独有取数路径/结果语义，本轮原样保留：查询中间件实例按管理状态分布|
|rb_156|两个资源分组的UNION结果角色与区域覆盖待核；不改评分器|
|rb_157|UNION标量列别名在SQLite由首段确定，原生结果契约须明确|
|rb_158|与161分别用id/ref_clusterId和nativeId/clusterId，不能当同一关系路径|
|rb_159|独有取数路径/结果语义，本轮原样保留：查询CCE工作负载列表|
|rb_160|独有取数路径/结果语义，本轮原样保留：查询CCE集群{{name}}下的Pod列表|
|rb_161|与158关联键不同，需公共字段关系和非空证据|
|rb_162|独有取数路径/结果语义，本轮原样保留：查询ModelArts推理服务{{name}}及关联资源池和节点|
|rb_163|独有取数路径/结果语义，本轮原样保留：查询ModelArts推理模型列表|
|rb_164|独有取数路径/结果语义，本轮原样保留：查询区域{{logicalRegionName}}下ModelArts推理服务按状态分布|
|rb_168|只输出ECS按AZ数量，缺卷/VPC|
|rb_169|只输出卷明细，缺VM规格输出|
|rb_170|只输出卷数，缺ECS/GaussDB|
|rb_171|只输出VPC数，缺其他网络资源|
|rb_172|只输出ECS数量，缺卷数量容量与规格分布|
|rb_173|只输出安全组数量，缺VPC/子网/EIP/ELB|
|rb_174|保留LEFT集群/宿主输出，异常状态语义仍待核|
|rb_175|只输出卷容量，缺IP/云服务/规格|
|rb_176|只输出最多租户排名，缺VM IP和挂载卷|
|rb_177|只输出最大容量VDC，缺存储池详情|
|rb_178|只按集群计ECS数，无最多选择及宿主/运行VM明细|
|rb_179|只按VDC计ECS数，无最多选择及异常VM|
|rb_181|最大端口数不证明最高IP使用率，缺端口IP/MAC明细|
|rb_183|只列卷明细，无最多租户过滤|
|rb_185|只输出卷，缺ECS/IP及VPC|
|rb_186|未按AZ筛ELB，且只ELB数量，监听器/成员缺失|
|rb_187|只输出VM关联，缺实例和节点清单，租户角色待核|
|rb_188|只设备总数，无交换机/存储设备数|
|rb_190|服务未按region筛且只服务数，缺池/节点数|
|rb_191|只vCPU/内存聚合，未输出卷指标|
|rb_192|只子网名称，缺VPC归属及子网/EIP计数|
|rb_193|AZ与ELB关系未证，只列ELB，缺监听器和成员数|
|rb_194|只输出卷，缺VM与安全组清单|
|rb_195|只宿主明细，缺VM数量与状态分布|
|rb_196|只GaussDB数，缺中间件/OBS数|
|rb_197|只交换机数，且未显式区域，缺路由器/VFW数|
|rb_198|只EIP清单，缺VM IP/宿主机|
|rb_199|只CCE集群清单，缺节点/VM数量|
|rb_200|只卷容量，缺vCPU/GaussDB节点数|

## 验收顺序与边界

1. 先无网络物化和API条件/SQL/输出闭合集比较，再合成反例；source模板中已有默认实体仅作离线对照输入，不能新增为运行时默认。
2. 以原execute+原服务验证真实非空、合法空、缺键、缺列、长GET及请求计数。每个新实体的参考结果重新执行，不沿用旧答案；错误不能被当成空结果相等。
3. 重建BM25索引、保留有贡献词面、做改写/实体替换/相似资源难负例；它们不是答案正确率。052/054旧召回负结果不能丢弃。
4. B按固定训练150范围做真实选择/填参/精调配对；训练封存50限制保持。任何真实模型请求由主任务按既有预算授权独立安排，本任务没有调用。
5. 模板JSON必须逐条容量实测；候选metadata是惰性的，旧api+sql只是基准，正式可用性以B物化与原执行证据为准。官方深度未确认前不声称合规。
6. 每批独立固定源码、参数映射、模型/数据版本、输出和回滚；不能仅以N减少或本地评分器吞错高分验收。

**未运行**：真实模型、原服务/执行器、train150评分、封存50、官方黑盒、正式总分、正式资源与深度认证。已完成的无网络物化验证另见VALIDATION.json，不能冒充上述项目。
