# A反馈落实：离线profile、复制优化与人口审计

基于已发布main `4abe75e`。本次只读A的Issue #4全部5条评论及B既有原生收据；连接的Gmail三次项目查询未找到邮件。新工作是本地未提交的B执行变体，不是A的新发布。没有新增模型、业务HTTP请求或评分调用，不回填旧全量；GitHub v1 ZIP不变。

## 性能结果

同一冻结输入、同一B代码、每组独立新进程各运行一次；改变的只有`standard/fast`复制模式。先后普通计时，不带profiler：

|路径|标准复制秒|快复制秒|耗时下降|标准/快复制峰值MiB|
|---|---:|---:|---:|---:|
|161层级|13.546|10.620|21.60%|1856.77 / 1844.27|
|298 VM/EIP|42.153|34.536|18.07%|2213.77 / 2167.42|

这些是离线执行测量，排除了历史HTTP与模型时延，收据读取/JSON解析另列。每组n=1，不作显著性或真实评测机达标声明。298离线峰值仍超过2GiB；冻结JSON重新解码也会影响对象共享与峰值，不能把回放内存直接当真实评测机数值。

profiler诊断：161标准总34.413秒、deepcopy累计23.930秒；298标准总105.950秒、deepcopy累计58.527秒，`consumer.encoded`累计30.259秒。快模式在profiler下分别17.685/60.940秒。累计函数耗时彼此重叠，不相加；profiler放大Python函数调用开销，实际收益以上面的普通计时为准。

prepare/recheck保留：主包`prepare_local`2次、`recheck_prepared`1次；consumer的`prepare_tenant_view`2次、`recheck_tenant_prepared`1次。动态重复加载模块的pstats行不能作为完整provider调用计数；原provider加载和recheck代码未改，已有PORT冲突/类型/来源反例继续通过。

## 具体实现及边界

- `implementation/runbook_copy.py`：仅对原生JSON容器提供深复制快路径，原子类型原样保留，共享引用/循环引用保留；非JSON对象、非字符串键或外部memo整体回退标准库。没有把deepcopy改成浅复制。
- B加载A模块时，先运行原始源码pin检查，再绑定该纯复制原语；A原始文件和公开manifest均未修改。consumer后续导入provider/legacy的原loader仍逐次运行。执行变体是B维护的`B_JSON_container_deepcopy_v1`，不能冒称原A代码未加变体运行。
- B自己的原始收据复制也使用该实现。原始收据、canonical、prepare、recheck、typed SQL及全部结果守恒检查保留，未缓存校验结果。
- `experiments/b_issue4_copy_runtime_20261031/SOURCE_MANIFEST.json`锁定复制实现。B运行时来源闭包、提交包及训练源码冻结包含它；训练计划记录`RUNBOOK_JSON_COPY_MODE`。
- 本地公共配置为fast。统一启动器或训练入口均支持`--json-copy-mode standard`；直接类入口可用环境变量`RUNBOOK_JSON_COPY_MODE=standard`回退。C应使用同一B入口及显式配置。

161保留20391行A明细；298保留1182行目录、429行A关联明细，428已证关联与754未证目录对象仍区分。所有未知和business_complete=false不升级，目录扩展表仍不写回A prepared对象。候选与原保存完整输出相等；另用规范JSON哈希复核，区分true/1/1.0等类型。

## 261：身份/名称与一对多明细

原生区域VM人口2830。下表为原始键存在性，未将missing改写为真实NULL或租户：

|tenantId状态|tenantName状态|VM数|
|---|---|---:|
|empty|empty|615|
|missing|empty|1|
|missing|missing|861|
|present|empty|31|
|present|missing|1|
|present|present|1321|

未知tenantId为1477；SQL投影后的NULL tenantName桶862来自861个双缺失加1个已知ID/缺名称，不能自动成为一个真实租户。

已知leader320台VM：35台无挂载保留1行，另外285台对应611个不同挂载端点对；合计611+35=646行。按每台VM输出行数分布为1行52台、2行234台、3行18台、4行8台、5行8台。646−320=326来自一对多，不应去重压回320。

1843的粒度是：全部区域VM人口中，卷端点不在本区域卷人口内的不同`(vmId,volumeId)`对；不是VM数，也不是只统计leader。leader子集未解析对数为0。捕获的全量挂载关系4546条、不同端点对4546个；关系表本身没有按region筛选，1843的作用域来自VM/卷人口。上述结论不认证1477个未知owner下的全域winner，仍保留partial/unknown。

## 192：1078→539→462

JOIN键依次为`ROUTER.nativeId=PORT.devNativeId`、`PORT.id=R_PORT_IN_SUBNET.portId`、`R_PORT_IN_SUBNET.subnetId=SUBNET.id`；身份对为`(ROUTER.id,SUBNET.id)`。

- 未限定父/PORT/SUBNET同region时1078行；其中539行为跨父region连接，另539行满足三个CI的region相等。
- 同region的539行对应539个不同父/PORT/关系/子网键、539个不同父/PORT/子网键；此选中JOIN中重复PORT原始观测和同端点平行关系各贡献0个额外行。
- 其中385个父子网对各连1个PORT、77个父子网对各连2个不同PORT：`539=385+2×77`，`462=385+77`。
- 因此77是不同PORT路径的多重性，不是2条PORT重复观测。770个引用对=462个已解析+308个未解析，后者不改0。不能据此认定两region是别名或重复人口。

## 同轮完整输出归档生效版本

复制优化与归档修复是不同阶段。归档实现首次发布于`4abe75e`；此前已经在base `72e6062`＋未提交B源码冻结的三个实际run中生效：

- `b_final_integration_20261031/case161`
- `b_final_integration_20261031/case251`
- `b_final_integration_20261031/case298`

各run的source.zip、source map、原始输出相对路径与SHA单独保留，不能把这些run写成完全等同于4abe75e源码的单轮评估。旧live只有前三行预览的记录不补造；本次独立native快照回放也不算历史同轮输出。

## 产物和复现

`scripts/profile_frozen_issue4.py`读取`--capture-dir`，在socket层禁止网络，逐精确请求回放既有收据，不跳过源数据/结果核验。`--profile`另保存pstats，`--copy-mode`显式选择实现。所有结果在`reports/b_a_feedback_profile_20261031/`；共享摘要在`experiments/b_issue4_copy_runtime_20261031/VALIDATION_SUMMARY.json`。

快路径47项检查、67项收尾检查、9项入口检查各自通过，有重叠不相加；均0网络/模型。本地新候选包完成来源/索引/配置离线检查，尚未进行新模型或评测机验收。后续热点是consumer严格JSON检查和重复编码，需保留全部原生类型/循环/来源校验后再做单点优化；不以缓存prepared、删除未知或丢明细追性能。
