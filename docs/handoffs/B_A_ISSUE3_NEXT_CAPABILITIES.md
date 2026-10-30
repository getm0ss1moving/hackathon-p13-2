# A→B：Issue3 next 四组能力逐模板交接

**本批默认关闭，供B接入评审；132、默认198、B实现和官方组件不变。** [候选主包](../../experiments/issue3_next_capabilities_20261030/README.md)提供冻结源码、合同、合成复放和实际交付manifest。下文源码/合同SHA为原冻结来源；容量排名合同仅`exclusive_root`本机路径脱敏，实际交付SHA见[SOURCE_CLOSURE](../../experiments/issue3_next_capabilities_20261030/SOURCE_CLOSURE.json)，全部运行源码保持原字节。

本文目标位置为仓库 `docs/handoffs/B_A_ISSUE3_NEXT_CAPABILITIES.md`；当前为最小独立复验后的默认关闭源码交付，交唯一publisher按用户授权提交main；不切默认。四组通用能力、六个视图合同均为默认关闭候选，实际运行库N变化0；没有改发布132、P0、B、官方入口、原数据或参考。不能把新完整义务混入“132基本等价”验收，也不能按题号、原句或实体路由。

最小纯源码/合同闭包共8文件，精确路径与SHA256见本文末及 `experiments/issue3_next_capabilities_20261030/SOURCE_CLOSURE.json`。它不是原owner全量测试包的缩减manifest；完整冻结包及原manifest仍保留。所有模块仅用stdlib，运行时不查训练答案或冻结数据白名单。

## 公共接入步骤

1. 根据完整用户义务选择一个闭集view/profile，绑定所有显式范围与角色。额外资源、AZ、列表、数量或排名义务不在合同内就拒绝；无region的请求不能继承其他题的region。
2. 按build给出的真实资源/method/条件/分页取数，由B可信宿主生成请求绑定、成功状态和schema收据。ok/schema_verified/callable/UUID不是来源认证；不能由模型JSON伪造它们，不能删除已有HTTP失败证据。资源与每页已声明HTTP必须精确int非bool且2xx；矛盾成功、缺字段、失败、重复ID、截断及未知状态不得变成空成功。
3. 调用该模块预检，严格处理ValueError/Unsupported或status=blocked。加载预检的新投影与声明typed schema；成功真空要真正0行，官方_empty占位不得COUNT成1。不能只搬SQL却仍装原始行。
4. 执行完整SQL，保留列序、身份粒度、summary行及所有未知诊断；精调不得删除稀疏列、将列表改count，或因API列资源就放过SQL漏义务。prepared来自B本次可信预检，不能接受模型构造的prepared对象。
5. 真空、没有已知匹配、未解关系、未知数值和请求失败分别传播。local graph/display/scope_max等标志只描述本次已验证输入域，不证明实时原子源或完整原题；known-only不宣称全域最大，NULL不改0。
6. 最后量B实际发送外壳的精确编码字节与深度。静态占位core、展开api_call+sql、完整本地metadata及最终外壳是四个边界；不得截断字段/SQL凑4096。本地compact UTF-8门禁和简单深度算法不代表正式规则已通过。

## 1. network_hierarchy：VPC→子网→VM

**用途/变体：** `hierarchy_rows`给层级明细，`parent_counts`给每VPC已知计数。支持global、name-only、显式region和name+region；不支持EIP、AZ归属、VDC三资源独立清单或额外输出。同名多身份全部保留，不LIMIT1。目录总量与selected总量JOIN前分别计算；无选中父时SQL输出summary_only，不是伪VPC。

**参数：** 必需`view:str enum`；可选`vpcName:str`、`logicalRegionName:str`，exact、非空、无默认；其余键拒绝。它不采用旧family的`filters/required_filters`封装。

**范围/键/基数：** name仅筛SQL父集合，为目录唯一性保留完整相关目录；显式region下推有该字段的API并在SQL关联保留。ROUTER.nativeId=router PORT.devNativeId须同region；PORT.id→R_PORT_IN_SUBNET.portId→SUBNET.id；另一份关系/PORT别名以PORT.devId=VM.resId且同region。VPC-子网、子网-VM均可能多对多；按distinct身份独立计数，跨子网同VM不相加。PORT双角色命中、多解、跨区或冲突拒绝。

**输出/粒度：** hierarchy为VPC×子网引用×VM/未解端点行，零子项父/无VM子网保留；count为每VPC ID一行。catalog/selected/count为整数，显示/引用/状态为text或NULL；summary_only除总量/row_kind外为NULL。unknown_*是声明的诊断行/参考槽计量，不是未知真实对象总数。

- hierarchy列：`catalog_vpc_count`, `selected_vpc_count`, `row_kind`, `vpc_id`, `vpc_name`, `region_name`, `subnet_reference_id`, `subnet_id`, `subnet_name`, `subnet_cidr`, `subnet_link_status`, `vm_port_reference_id`, `vm_reference_res_id`, `vm_id`, `vm_name`, `vm_link_status`
- count列：`catalog_vpc_count`, `selected_vpc_count`, `row_kind`, `vpc_id`, `vpc_name`, `region_name`, `referenced_subnet_count`, `resolved_subnet_count`, `unresolved_subnet_count`, `has_unknown_subnet_link`, `known_vm_count`, `unknown_vm_endpoint_count`

**空/未知/失败/分页：** `prepare(params,receipts)`→(typed tables,diagnostics)，收据每CI为ok、exact request、schema/schema_verified和完整pages；页为ok/pageNo/pageSize/totalNum/totalPageNo/objList，真空页totalPageNo0或1。任何同CI重复ID拒绝；不同关系ID同业务端点可去重。NULL/空白外键投影为未知；未进入层级行的未知端点也诊断。图完整与显示值完整分开，business_complete仅本地限制。

**现场门禁/验证/N：** PORT两重复键仅时间戳不同，限定投影相同已有独立幂等证据，但candidate仍严格拒绝。未实现canonical来源路径，不能任选一条或改raw total证明完整。网络独立18/18仅针对严格唯一输入域；B取数/typed-empty/最终外壳未验收。潜在独立注册+1或审定扩族；实际0。

## 2. ranked_vdc_pool HTTP-R2：容量最大VDC→池详情

**用途/不支持：** 显式region内按VOLUME.size精确合计选全部并列最大vdcId，再列所用池详情。不是数据库专用盘用途、不是VDC池配额/共享池分摊；不支持global、额外AZ/tenant条件、其他排名指标或单胜者猜选。

**参数：** 必需`logicalRegionName:str`、`tie_policy='all_ties'`、`unknown_owner_policy:enum[reject,known_only]`、`unknown_size_policy:enum[reject,known_only]`；没有可选项，也不接受额外profile键。源size最多6小数且有整数刻度上限；逗号/指数/符号/单位/过细小数不暗转或四舍五入。

**范围/键/基数：** VOLUME及POOL API同region/equal，SQL保持region；按region+原生vdcId身份聚合，vdcName只显示。已知键在该源对应TEN_VDC.nativeId，不是目录内部id/resId；没有猜补空owner。每卷一个后端引用，VOLUME.attachBackendId=STORAGE_POOL.id；一个池可服务多卷/多VDC。先按卷身份SUM，再distinct池引用，不能SUM(DISTINCT值)或按pool.vdcName归属。

**输出/粒度：** 每胜出VDC×distinct池引用一行；没有已知池引用保留占位状态。volume/count/unknown计数是int；已知/完整size为精确decimal text，完整量可NULL；池容量为未转换raw text/NULL。整池属性不当VDC独占容量。

输出列：`logical_region_name`, `vdc_id`, `vdc_name`, `volume_count`, `known_volume_size_source_units`, `unknown_size_volume_count`, `total_volume_size_if_complete_source_units`, `unknown_backend_volume_count`, `referenced_pool_id`, `pool_id`, `pool_name`, `pool_state`, `pool_total_capacity_raw`, `pool_free_capacity_raw`, `pool_allocated_capacity_raw`, `pool_provisioned_capacity_raw`

**空/未知/失败/分页/版本：** preflight/prepare(params,snapshots)返回ready_for_typed_sql或blocked；每CI有ok/schema_source/columns/pages，每页currentPage/pageSize/totalNum/totalPageNo/request/objList。原两HTTP503+okTrue失败已在资源/页统一修复，三HTTP别名均严格2xx；声明success非True、error失败/未知均拒绝。projection_contract为v3-source-rechecked；prepared保留本次原始收据证据，execute_prepared再走同一新预检并核canonical投影/参数/诊断。旧prepared仅改tag不能复用。该证据是B本次内部输入，不是静态模板、历史数据pin或来源认证。

B必须加载size_scaled整数刻度等验证投影；空卷人口无winner，不造容量0的VDC。未知owner/size在reject下阻塞；known_only是已知下界leader，scope_max_certified=false，未知owner还使完整总量NULL。池链接缺失/未解保留。pool_link_complete只代表链接；attribute_values_complete才表示请求raw属性值非空，仍不等同业务单位正确。旧complete_winner_pool_details为deprecated链接别名，不能总结成属性全知。

**现场门禁/验证/N：** 3650卷缺vdcId且无权威替代归属；不以池/tenant/project/name或挂载链回填。旧独立20/22的两失败属于同一HTTP问题；新修订owner36/36＋根7/7仅作来源记录。旧HTTP两失败、状态矩阵和prepared改tag/补失败证据绕过已独立关闭；本轮HTTP7项，不重跑旧22项、不把20/22改成新22/22。SQL/参数/数值算法未改。潜在独立profile+1或审定扩族；实际0。

## 3. cluster_ranked_hosts：最多ECS集群→宿主vCPU与active VM行

**用途/参数：** 必需profile='cluster_max_vm_host_running_details'、filters:object、tie_policy='all_ties'、unknown_rank_policy:enum[reject,known_only_with_diagnostic]、details_population:enum[all_hosts_all_active_VMs,winner-cluster-only_active_VMs]。filters仅允许global{}、AZ-only、region-only、region+AZ的exact非空字符串；无region不补。不能任意替换CPU字段/状态枚举/排名指标。

**范围/键/基数：** 四API取global context，排名条件只作用VM rank子集，不能用排名AZ过滤唯一VM数据后丢掉跨AZ明细。VM.clusterId→CLUSTER.id且region一致，不是nativeId；先COUNT DISTINCT rank VM再选全部最大cluster ID。CLUSTER.id→M.source_Instance_Id，M.target_Instance_Id→HOST.id；cluster-host多对多，HOST→VM按hostId一对多。host身份先去重独立SUM，再LEFT active VM列表，不让VM数量放大CPU；同名cluster分开。

**值语义/输出：** 文档定义HOST.totalVcpuCores为vCPU核数，VM小写status='active'为运行中，固定实现这两个角色。unknown/other/NULL/未证状态不当已知nonrunning。每胜出cluster×host引用×active VM一行；无active VM宿主保留。complete CPU为整数或NULL；known sum为已知下界，unknown_host_vcpu_count是distinct引用槽的未知CPU计量（NULL槽不证明实际未知宿主个数）。未解析host仍保留引用及已证指向它的VM；无法放入已证host集合的known active行在补充诊断保留，不能丢后称全列表。

输出列：`cluster_id`, `cluster_name`, `cluster_logical_region_name`, `rank_vm_count`, `reference_host_id`, `host_id`, `host_name`, `host_vcpu_raw`, `known_cluster_host_vcpu`, `unknown_host_vcpu_count`, `complete_cluster_host_vcpu`, `running_vm_id`, `running_vm_name`, `running_vm_status`, `host_link_status`

**空/未知/失败/分页/B投影：** snapshot结构同rank组，但page.request为global context请求；成功空页0/1、完整分页、唯一ID、schema与typed-empty必需。B必须加载rank_eligible/rank_cluster_id/is_running/status_known、HOST.vcpu_known和CLUSTER.host_graph_complete等重算投影。execute_prepared不信可变derived flags。未知rank人口可能改winner，known-only不认证max。rank域只声明为有观察VM引用的cluster，未解决空人口下零VM目录最大值政策。排名scope与两个details_population必须保留差别。

**现场门禁/验证/N：** 870个VM集群引用未知、34条关系host目标未解、32条HOST记录缺CPU；不是同一人口可相加的数。缺CPU/host图不完整使完整总量NULL，未知状态使运行列表不完整；C的population/并列/unknown政策仍待，B未接。owner17/17＋根侧相关4场景仅作来源记录；本轮6个代表性独立场景通过，另共享健康/schema控制通过，不声称完整业务验收。潜在独立小族+1，实际0。

## 4. vm_eip_host：tenant VM地址/宿主与已知端口EIP

**用途/参数：** 必需view:enum[native_ip_host_rows,known_port_eip_host_rows]、tenantName:exact非空str；可选logicalRegionName:str，其余键拒绝。native view只VM/HOST，port view再加PORT/FLOATING_IPS。不支持将属性替代完整EIP对象、私网IP字符串JOIN、猜external/internal过滤或child tenant必须等于父tenant。

**范围/键/基数：** tenant限制VM父域；无region不加。native VM API可直接tenant条件；port view为验证(region,resId)目录唯一取宽VM context，SQL再筛父tenant，不能把它当未保留scope。host按VM.hostId→HOST.id并同region，LEFT保父；EIP.portId→PORT.id、PORT.devId→VM.resId并同region。VM多PORT/EIP保留多行，HOST单目标须唯一；任何同CI重复ID拒绝。

**输出/粒度：** native每VM一行，privateIps/floatingIp原生raw属性text/NULL；host未解保留引用与NULL状态，不INNER丢父。port每VM×known EIP ID一行，无known匹配也保父，不说实际无EIP。isInternal JSON bool规范为true/false文本、原生文本保留，两角色不删。地址文本不证明对象关联。

- native_ip_host_rows列：`vm_id`, `vm_name`, `logical_region_name`, `private_ips_raw`, `native_floating_ip_raw`, `host_reference_id`, `host_id`, `host_name`, `host_ip`, `host_link_status`, `native_ip_status`

- known_port_eip_host_rows列：`vm_id`, `vm_name`, `logical_region_name`, `private_ips_raw`, `native_floating_ip_raw`, `host_reference_id`, `host_id`, `host_name`, `host_ip`, `host_link_status`, `native_ip_status`, `vm_reference_res_id`, `binding_port_id`, `eip_id`, `eip_address`, `eip_internal_role_raw`, `eip_link_status`

**空/未知/失败/分页：** prepare/preflight返回typed tables及diagnostics；receipt为ok、exact request、schema/schema_verified、pages(ok/pageNo/pageSize/totalNum/totalPageNo/objList)。成功真空0/1，未知host/resId/port及未解端点不当无对象；原生属性NULL保留。相同私网IP不串绑、floatingIp文本不补port绑定。两view均固定full_eip_binding_status=unsupported_authority_and_coverage，declared_view_values_complete只描述该有限view，不能抬为完整EIP业务。

**现场门禁/验证/N：** host引用79未解/870未知，port源2重复键；完整EIP端口角色/覆盖仍未权威闭合。native view无需PORT，可单独交接属性与host父域；需要完整EIP列表的原问不能自动降级该view。owner21/21＋根侧相关4场景仅作来源记录；本轮5个代表性独立场景通过，另共享健康/schema控制通过；完整EIP权威关系仍不支持。若审定向既有VM-host族增2view潜在净0；若独立注册潜在+1，实际0。

## 验证、传输和发布状态

各CONTRACT是具体schema/入口/输出/分页的权威机器说明；本表不引入新DSL。合成正反例覆盖同名异ID、跨region、并列、未知改变winner、CPU/容量乘法、零子项、HTTP矛盾、旧prepared改tag、NULL/缺键、重复/分页和长字段。owner与独立、不同版本的测试计数不相加成成绩。没有读原封存答案/参考SQL/评分，没有运行200、业务API/模型评测、原生SQL、B或官方执行器。

局部core典型实测：network hierarchy/count global3079/3498B；HTTP-rank约2219B；cluster global/AZ约1938/1961B；VM native/port tenant-only约1012/1720B。输入不同字节会变；详见各BYTE/LENGTH_BOUNDARIES，含静态占位、full metadata与长字段实测。显式条件形状一般dict深5/list也计深7，global context可为2/3；官方算法未知。prepared原收据证据不是静态core，其真实传输若发生必须另外量。最终B外壳尚未验收。

用户已授权完成后main交付B。当前只准备默认关闭源码/合同/文档，唯一publisher可按本次受限独立结论提交默认关闭源码/文档；本owner不push，不切默认。若全独立注册四组潜在+4；扩族/吸收源需统一重算，不能按六view算六条或承诺仍132。CCE解析VM仍缺证，若将来只做引用数必须命名referenced，不能伪称resolved。VPC AZ/数据库专用用途/ELB部署AZ不造关系。

## 精确源码闭包

- `experiments/issue3_next_capabilities_20261030/modules/network_hierarchy/candidate.py`
  SHA256 `9a8a967094181e384ba82d2ae4efaab33b6040426aeab21b19a3711f57db9f0a`
- `experiments/issue3_next_capabilities_20261030/modules/network_hierarchy/CONTRACT.json`
  SHA256 `b6691014ede0304a6e7de05f7a639d010d85b96b37eb629e677dd87fedbec19c`
- `experiments/issue3_next_capabilities_20261030/modules/ranked_vdc_pool_http_r2/candidate.py`
  SHA256 `35c53fe7fa1bba7413355ab4f0142e98d9c14ed0c2922a0d59974a16ffe53443`
- `experiments/issue3_next_capabilities_20261030/modules/ranked_vdc_pool_http_r2/CONTRACT.json`
  SHA256 `bd3457c4b9fc76ec6fe566f99c425bebada0d735abb21c8fa6177f8cd377c952`
- `experiments/issue3_next_capabilities_20261030/modules/cluster_ranked_hosts/candidate.py`
  SHA256 `67af606d9cb272236245d76a1ca72e500a0bef38e843c49b96d8dd12efaf3433`
- `experiments/issue3_next_capabilities_20261030/modules/cluster_ranked_hosts/CONTRACT.json`
  SHA256 `2a66e2fa4aa2cc302632eaaef150ae47bcfe78296544021a58cebab9093f621f`
- `experiments/issue3_next_capabilities_20261030/modules/vm_eip_host/candidate.py`
  SHA256 `1e750166c9c6040ae0f5c2caf5407605476e29f05bf450c6b90b6a6a18ab15c4`
- `experiments/issue3_next_capabilities_20261030/modules/vm_eip_host/CONTRACT.json`
  SHA256 `adf365af483e4431e62ad804f96f5cd4ad4cc4a2c84279c9da236bd0ed2f90ff`

## 最小独立复验收据及未合入范围

本轮19/19通过：HTTP7、cluster6、VM5、共享健康/schema1；HTTP矩阵38子例未叠加。网络前版18/18仅引用，不与本轮或owner计数相加。三ZIP及manifest已核，8源码/合同与live一致。prepared原收据重验不认证来源，B不能接受模型构造prepared。

192双count、057增量未合入此闭包，不能称已完成。当前只允许按用户授权提交默认关闭源码/合同/本文档，未批准生产/参赛启用、默认切换或132修改。现场缺失、B可信来源/装载、C人口/单位政策、typed-empty、最终封装及正式深度门禁全部保留。

## 本次发布复放说明

公开脚本只使用新合成fixture和当前8文件闭包：两个旧HTTP失败使用等价新合成输入，prepared用当前预检对象去掉原证据模拟旧标签对象，再验证补入失败证据也被拒绝；未导入旧legacy模块或复制历史输入。网络18/18仅引用旧收据，不在本轮复测；本轮独立19/19与公开适配复放不重复加总。B实际可信来源、schema/分页、typed-empty、原文义务及官方最终封装仍未通过。
