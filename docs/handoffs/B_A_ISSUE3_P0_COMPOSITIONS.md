# A→B：Issue3 P0 三组合合同增量

**请 B 阅读[六文件合同包](../../experiments/issue3_p0_compositions_20261030/README.md)和[最小闭包](../../experiments/issue3_p0_compositions_20261030/MINIMAL_B_HANDOFF.json)。本次单独发布默认关闭资料，不修改132、198默认、B实现或官方组件，不自动启用新模型测试，不关闭issue。**

源R2 manifest为 `46db8ee6963c16e4d7f786f8d6da285e612fd8466d469480fc31a1e1297e49fd`；独立最小收据为 `32c76bdb5aff49f533c506f74709b6edd37b850bf8b961b55f9afe71d363566c`。公开6份原字节源码/合同：两个R2增量各2文件，未改vdc_counts原2文件。不是原16文件归档，也不混入[前一Issue3包](B_A_ISSUE3_CONTRACTS.md)或132数组。

## 验证结论

R2独立19/19通过、94边界子项嵌套其中，闭合tenant_lists与vdc_network的成功零总量 `totalPageNo=0` 两项误拒。扩展仅作用于成功、空objList、完整单一第一页；0/1/省略等价，其他页号/页数/成功状态/schema/缺源/重复ID检查保留，非空仍严格ceil。

vdc_counts原独立35/35，源码和合同未改；本轮不导入或复测它，不与19合并成新全量成绩。旧独立104项的2个失败记录没有重写。公开另提供19项/94子项合成复放，使用新字面值和冻结的合成prepare哈希，不传播历史输入记录；这不是完整owner归档复验，也没有模型或原生执行成绩。

## B 必须保留的完整义务

- **VDC三计数**：VM、VOLUME、GAUSSDB_INSTANCE独立聚合；以三源VDC名称域UNION连接，不用原始表JOIN造成扇出，不以NODE替代INSTANCE。NULL、空串和空白名称桶分开，不能称权威唯一VDC；未知桶需保留诊断。
- **租户三清单**：VM、安全组、卷都输出身份与名称，按CI保留同名不同ID及跨CI相同ID。未明示区域不得加默认区域；显式区域应同时绑定三源API/投影/SQL。tenantName标签不能推断唯一tenantId；未知显示名保留行并标不完整。
- **VDC网络清单**：显式VDC与区域都执行，VPC名称、子网CIDR与EIP标量均保留；一个分支为空不能抹掉其他资源。不推断父子、AZ、VM/EIP绑定。未知或非法CIDR、未知VPC名保留并传播不完整状态。

## B/官方门禁仍未解除

B可信宿主需从实际抓取证明精确请求、成功状态、完整分页、原生schema及真空schema来源。tenant_lists/vdc_network局部回执不含权威请求/schema来源；A不能凭 `ok=True`、静态schema或随意callback认证。vdc_counts的request/columns/schema_source结构检查也不等于来源认证。

先preflight，再装其投影与真正零行typed表；拒绝 `_empty` 占位，失败/缺列/缺页/未知不能转换成业务0。最新B的 `query→_query` 猜空包装应保留并单列猜测、原始失败原因，不能据 `error=None` 声称COUNT或真实空验证通过。完整原文义务、请求绑定、诊断传播、实际最终字节封装和官方深度仍由B验证；不截断实体、SQL或范围，不改评分口径。

三个profile不等于运行模板净增，实际默认198/160/132变化均0。后续是否注册或吸收旧组合需独立核全旧视图/映射并重算N，本包没有自动做这些决策。
