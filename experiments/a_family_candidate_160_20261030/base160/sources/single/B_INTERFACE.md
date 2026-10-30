# B接入说明：两个独立单表候选

本包没有修改B的matcher/system或生产。只交付可复制的纯函数增量与两个被动item，实际N收益0。不要把整个旧matcher拷回主库，也不要把被动item未物化交给固定SDK。完整代码仅依赖copy/json/re。

## 入口与解析JSON

入口为`prepare_single_table_candidate(question, selected_item, parsed, diagnostics=None)`。成功返回普通item，其中resources/api_call/sql已闭合；未支持或错误参数返回None，原因只写内部diagnostics。它不检索、不选模板、不执行SQL、不调用模型，也不决定官方最终响应格式。

family_f10的JSON须恰含：metric、direction、top_k、filters、required_filters。metric只有vcpu_allocation_rate/remaining_memory_mb，direction只有desc，top_k是1..2147483647整数且不能是bool，filters支持region/AZ至少一项。

family_f17_safe的JSON须恰含：view、filters、required_filters。view只有az_usage/vendor_capacity；region必需，AZ/vendor可选AND。没有order/limit/任意投影/SQL键。required_filters必须恰好覆盖全部filters且不重复。过滤值来自当前原文；不读旧默认实体，不把tenant映射VDC。

当前B继续使用自己的模型选择/必要填参/精调入口和预算。模型产生的参数交prepare校验；本包的`infer_parameters`用于有限语法的原文独立核对与离线诊断，不证明真实模型能抽对，也不替换B的模型选择链。

示例（在本包根目录；仅运行纯函数，不触发模型或服务）：

```python
from candidate.single_table_families import CANDIDATES, prepare_single_table_candidate
question = '区域region_new下vCPU分配率最高的前7台宿主机'
parsed = {'metric': 'vcpu_allocation_rate', 'direction': 'desc', 'top_k': 7,
          'filters': {'logicalRegionName': 'region_new'},
          'required_filters': ['logicalRegionName']}
item = prepare_single_table_candidate(question, CANDIDATES[0], parsed, {})
assert item is not None
assert item['sql'].endswith('ORDER BY allocation_rate DESC LIMIT 7')
```

## 必须保留的合同

- CPU率为CAST(allocatedVcpuCores AS FLOAT)/totalVcpuCores，输出比值，不乘100；内存为totalVmemoryMB-allocatedVmemoryMB，仍是原字段单位。两种排序键均降序；K来自问题，不拿5/3当缺值默认。
- AZ池汇总先SUM，再相减和ROUND百分数；厂商汇总仅总/空闲容量三列。allocatedCapacityGB不等total-free，storageProtocol不等磁盘类型；不接098/189缺口。
- 名称空串、不同id同名、缺指标/NULL和原列序保留，不DISTINCT、不补0、不删未知对象。成功0行、未支持、SQL缺列错误分别处理。
- 同族多个指标或多个范围义务不能按family ID去重丢掉。本helper一调用只支持一个已证明view；多义务由B拆分并完整保留，不能只执行半句。

## 精调与接口边界

保留B现有SQL精调入口。`refined_contract_unchanged(prepared, refined)`只做resources/api_call/sql精确一致检查，不调用精调。任何变动（包括格式变动）都会返回False，故它不是SQL语义等价判定器。B可按已有保护策略保留已物化规范SQL；不能执行改列、改公式、换排序或丢API条件的结果，也不应因纯格式差异无故把本可回答请求弃权。

筛选值仅进API，不拼SQL。SQLite LIMIT仅使用已验证整数，资源、公式、列和排序键都由枚举生成。OLD_TO_NEW仅作离线迁移，不能装成题号/原题/实体查表。

## A与协调者仍需做什么

RETRIEVAL_HANDOFF只给四份原公开文本视图的引用和hash；没有重建真实170/160 BM25。A保留原视图统计与默认retrieve协议，验证完整库召回和竞争；索引文字卡不计执行N。协调者核对与9族/batch4无交集后，才可把4条换2族。

B还需在最新精确基底增量移植、原生正常/空/缺字段/复合义务验证，之后按原任务授权的模型与固定训练边界验收。本包未调用模型、HTTP或原execute/评分器，不能把这些离线结果称完整B接入。SDK空表缺列和分页仍是原有限制，未被本helper修复。


## 引号投影修订r2及独立审查后的接入补充

此版只在投影标记识别前保护完整引号范围。引号内的返回/输出/显示/列出属于实体值；引号外的真实列清单仍须按原列序与字段闭集核对。prepare入口、参数JSON、API、SQL和两个被动item均不变。旧d2c7947c版本已冻结，不用旧包的构建脚本覆盖本修订。

必须通过prepare后才能执行，不能直接使用被动item的默认LIMIT/未填占位符。B执行后还必须检查规范预期列：HOST_COLUMNS[metric]或POOL_COLUMNS[view]的完整有序列表。上游独立审查在8个空/缺字段场景观察到固定SDK返回error=None且result为columns=[]、rows=[]、row_count=0；这不是成功的排名或容量结果。请沿现有B诊断/输出策略处理缺列，不能只看error为None就记为业务零行。完整SDK结果是读取的上游证据，本次未重跑其transport替身或改固定SDK。

DESC LIMIT K没有二级排序，边界并列对象的稳定顺序/选择未保证；不新增ALL TIES或稳定身份排序。非法容量字符串仍可能经SQLite成为0，分页、完整性和真实模型抽参未证。保留同族多义务、原SQL精调入口、完整库BM25与原生验收要求。
