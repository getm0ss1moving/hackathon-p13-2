> 发布范围：这是源51f0aad、200条模板的设计快照，尚未通过生产接入验收。正文中的根/B双目录比较属于旧时点；当前main已统一根目录，严格去重后为198条（054→052、087→086）。本文不改生产。实体示例在本发布副本中用参数占位，完整机器接口/原始证据仍由本地实施与独立审查任务保留；本目录不提供可执行候选。

# 首批可并行实现接口（设计交接，未接入生产）

设计来源固定为 `51f0aaddbd143f69a8823a915c1862d41f034868` 的200模板；远端main只读核实已前进到直接子提交 `ad45ecc`（评分文档修正）。本机旧shared checkout不切换、不修改。生产模板SHA256为 `34ac7400c905c9da3657038f9f7bc40a80f07e6ba43ef70eca6e4ca3197d1a35`。

## 立即可分配的六族

|设计族|原ID|参数轴|减少N（条件值和输出等价后）|
|---|---|---|---:|
|F01 ECS计数/分布|001/002/003/004/005/007/017/044/074/184|scope；筛选region/tenant/VDC/AZ/status/management；group=none/status/AZ/management/tenant/VDC；metrics=count/total_active/status_counts；排序/标签|9|
|F08 宿主机分布|048/049/053|scope；region筛选；group=hypervisorType/AZ/status|2|
|F14 卷按VDC容量统计|086/087/102|region必需；metrics=count_sum/avg_max|2|
|F18 数据库分布（先不含150）|105/106/143/144|region必需；group=flavorCode/VDC/engineVersion/haMode；metrics=count/count_storage|3|
|F20 共享网络查询|110/111/112|shared布尔值必需；region/providerNetworkType可选且显式提取；view=rows/count；count别名保持|2|
|F21 弹性IP分布|113/133|region必需；group=VDC/tenant_status；tenant_status为明确二维合同|1|

六族覆盖25个原ID，条件化算术N为181（不是已通过的生产N）。F01自身覆盖10条，不以001/002/003为边界。所有映射、原始API/SQL、必要条件、输出列及参数配置会写入 `FIRST_BATCH.json` 与 `FULL_MAPPING.json`。设计不读取白盒200或封存50题，不调用模型。

## B接入位置和返回接口

1. BM25选择族后，在已有matcher内提取**结构参数**及实体参数。结构枚举必须受族白名单约束；不使用任意SQL参数，不增加执行DSL/框架。不按oldID或完整题文路由，oldID映射只作离线迁移验收。
2. 即使基准sql没有占位符，也须先处理族结构参数；根matcher目前的“没有占位符立即return”会令分组选择失效。`family_*`元数据本身不会执行。
3. 区分用户未提条件与明确条件提取失败：`scope=global`只可由明确全局意图决定；`scope=filtered`必须给出全部`required_filters`值。失败拒答，不回填其他实体、不删条件放宽。False/0不是缺值。
4. 根据闭合枚举在matcher内物化**普通**`api_call`与`sql`；再走原SQL精调、B现有投影/粒度保护和原execute。只发送实际启用的API条件，条件语义为AND，合法重复条件可以去重。元数据不得交固定executor解释。
5. 对精调结果保护已选group、指标、列名、排序和Top-K；F01的status分布与AZ分布各一维，禁止用AZ×status替代。F21的tenant_status则明确是二维，不可降为一维。
6. 先并行实现F01、F08、F14/F18、F20/F21；各组只改自己认领的独立候选文件，再由集成者收口。根matcher与B/implementation/matcher是两个不同当前版本，不覆盖B train-only修改。

## 阻塞与风险

首批没有新增关联依赖，避免把空依赖支持当成现成能力。F01保留原active/stopped/other计数表达式；“异常”状态语义仍须依据公共字段合同确认，不把error一律映射为stopped。F20布尔类型须保持而非靠字符串真值判断。所有实体默认值只保留在离线原合同证据，不作为新族运行时默认。

原生API容器本身可超过按dict/list计数的深度4，增加浅层合同不能宣称解决官方深度口径。每族候选会逐条测UTF-8紧凑JSON字节数；设计映射JSON不是比赛提交JSON，不能把它的大小或深度拿来作正式合规结论。

当前已做静态源码核查；原服务执行、模型选择/填参/精调、训练150/封存50、正式黑盒与总分均**未运行**。独立离线物化脚本仅证明25种原合同能由闭合结构参数表达，不证明模型能正确选参。
