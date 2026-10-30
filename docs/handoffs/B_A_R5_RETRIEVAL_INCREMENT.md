# A→B：r5义务粒度检索增量

**当前main默认为132 strict compact＋r4，根源码已核；本次只追加默认关闭r5包，不替换B根引擎、matcher/system/issue3、模板或官方组件。** [候选主包](../../experiments/a_retriever_r5_increment_20261030/README.md)提供两版完整模块、从r4精确补丁、复现及冻结接口。

## 基底与配对

根132导出SHA `6e2fc4a1050e61b24744d8ae4e7ea93f7795d84d674a916d6b17453f0c80970c`；canonical compact数组SHA `a3f6a0d3ea12be6555025e37e4a0189f259a2da6766124160f90b94fcce88ef3`。根strict r4 SHA与补丁基底一致，详见[ROOT_B_BASELINE](../../experiments/a_retriever_r5_increment_20261030/ROOT_B_BASELINE.json)。B实际源码后续变化时重新核hash，不强打补丁或覆盖新修复。

|版本|r4基底SHA-256|r5模块SHA-256|
|---|---|---|
|strict|`99d15b6995aa8a731354b02811c3613fc4c92c4a9c1d3a900f8ae393d7814802`|`b5a1c943fcf4785aa40c39e4905fbbdba2719eed9d458b391c127657b348f3d6`|
|enhanced|`dbaf4381493907a8f3b19d14344700884f8b9c1d9703f573c4385b216d4fcedc`|`b3294dcd7672d2ccf283bc79712b85509e877bf89527344830d3434ee9e7bd6e`|

独立r5运行绑定**原132v1数组**（strict`4d790887…637aac5`、enhanced`3806aaa7…a468f9e`）；当前B使用compact数组。此发布没有新跑r5＋compact完整回归或B原生链。若B选择r5，先锁实际数组/module、F03 metadata adapter、配置/flags及源码组合，再有界联调，不能冒用旧配对验收。默认不自动选择；显式采用本增量时推荐strict，增强版须单独配对。

## 已验范围与开销

独立33项专项通过：原14个单统计仍各一个目标并召回rb052，其余8项及11个新独立控制核profile/跨度顺序与边界。原1166回归支持1016误空0、复合161完整、150负例三个入口为空；普通603×4向量2412精确相同。历史200模板实现仍2368/2412同、44属性差异，未新跑200题、答案或模型。

原1166相对r4候选/列表/可选证据没有增长；33项中新语法最多+2候选、+1056 UTF-8字节，不能泛称全部0增长。实际模型token、官方CPU/2GB/4KB/时间/分数未测。发布者只在全新副本实际重放strict/enhanced补丁并核完整r5哈希，不重跑完整私有33/1166。

## B必须保留的语义

- CPU架构类型与各类数量可属于一个统计目标。单目标`retrieve_obligations`返回空列表是正常合同，应继续普通检索；不能当不支持，也不能因BM25局部视图有两项而执行两次。
- 真正多资源、双实体、AND及“以及查询”按序保留`Candidate.profile_ids`、`obligation_spans`及`retrieve_obligations`。按原文Unicode字符跨度逐项选view、抽参、prepare，不能按family ID吞掉义务。完整覆盖只对`top_k=None`成立。
- 四子问强profile并集20超15预算时三个入口全空；不自动放宽预算或静默删一项。未知维度/区域/每台明细邻近控制只证明不能误折叠，不证明对应新业务能力已支持。
- **未补region。** rb052原生区域条件/default_params未改。缺region输入可召回它，仍须B执行缺参/范围政策，不能按本机默认区域跑完后称全域统计成功。
- 保留既有F03两个提示边界metadata adapter、原文prepare/全部API与列义务。COUNT/失败/缺列/分页、序列化和深度仍按B/官方门禁分别验证；检索通过不等于业务或官方整包通过。

保留B的`query→_query`猜空包装及guess/原始失败证据，不据`error=None`判真实空或执行成功。不混管理VM、bootable、新50答案或未验日志修复，不改变现有r4/132数组或默认入口，不关闭issue。
