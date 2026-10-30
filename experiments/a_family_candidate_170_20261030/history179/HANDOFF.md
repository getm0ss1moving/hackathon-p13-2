# 179条隔离候选：F27与已发布180库的组合交接

本包是数据、词袋索引和移植参考，不是已启用的生产系统。生产保持198条。发布负责人可以独立发布本目录；B适配不阻塞资料交接。不要将私有生成的完整模板JSON或原始问句一起上传。

## 版本与逐项调整

- 基于已发布180包 `7b7271e3ab322914244f9047eb985174c2a92d9f`，其198源固定在 `099b5bfc5545d98f81e46a4a7b6244623c29ef8c`。
- 只将 `rb_099` 与 `rb_101` 合为 `family_f27`。其余178条（包括首批6族、071修复和既有绑定）逐对象相同。
- 数量180→179：实际179个唯一可执行模板ID，172个继承模板加7个参数族。200个文字视图、400份索引文档是召回表示，不是隐藏的200个执行模板。完整ID映射见 `179_ID_MAP.json`。

|原能力|新参数|保留输出与限制|本轮依据|
|---|---|---|---|
|099：指定区域OBS桶列表|`scope=filtered, view=rows`；必需 `filters.logicalRegionName` 与同名 `required_filters`|固定列 `name,bucketName,managedStatus`；不支持任意投影/名称过滤|原API/SQL逐对象相等；3组SQLite数据对照|
|101：指定区域按租户统计OBS桶|同上，`view=tenant_count`|`tenantName, COUNT(*) AS count`；保留重复记录、NULL租户与空字符串租户；不是唯一桶计数|原API/SQL逐对象相等；3组SQLite数据对照|
|旧检索措辞|两份text-only views挂到F27|099锚定098，101锚定100；F14的102仍锚定101，跨族锚点初始化正常|400文档顺序、token与BM25统计相同|
|历史别名|054→052、087→F14保持|不改旧R5合同、不增加旧ID执行分流|原R5八冻结文件相同；25合同用合成实值物化一致|

F27只接受一个明确区域的等值筛选及上述两种视图。SUM/容量、全局范围、租户或名称等额外筛选、任意输出、多视图单调用不在当前声明范围内。桶ID唯一性、全量分页与数据库真实空表行为未证明；请勿将SQLite的预建空表测试当作原SDK空表通过。

## 离线结果及边界

- 517条既有已曝光检索输入加8条合成输入，共525条，k=None/1/5/10共2100对；180输出将099/101归为F27并按首出现去重后，与179的ID顺序、tier、score、coverage差异0。不是原ID逐项相同，也不是新的盲测或模型得分。
- 完整400文档的顺序、词袋、TF/DF/IDF、阈值tau与平均长度保持相同；未采用向量索引。
- F27两视图×空/正常/重复+NULL+空字符串三组共6组SQL/API对照通过，6种非法结构配置均被拒绝；只测试纯函数与SQLite，没有调用模型、服务、200题或封存集。
- 复合检索只是候选覆盖验证。请求“桶列表及按租户计数”需要同一个F27的两次不同参数调用；一个族命中不能算两项答案。跨资源组合、部分不支持请求仍由B识别/选择/编排；本包不证明组合端到端完成。
- 完整库单条紧凑JSON最大2562字节，字典/列表层级最大7，含外层数组8。字节低于4KB；官方深度算法未明，深度风险仍在，不能据此宣称正式提交合规。
- 延迟数字仅为本机本次525个None-k检索样本，见JSON；不含模型、API、SQL，不推断端到端超时分。

## B接入门禁

`F27_on_first_R5_final.patch`精确应用到旧R5 matcher（SHA以MANIFEST为准）后得到已复审的最终F27 matcher。本轮做了apply-check、应用和输出字节比较，均成功；**对已发布B v18 matcher的apply-check失败，未应用、未改B**。必须由B移植闭合参数、全句语义核对与两视图物化到最新helper，不能覆盖v18 matcher/system。纯物化参考 `materialization_reference.py`仅供核验，不是新运行时适配器。

B需完成：

1. 选择/填参协议显式给出F27、scope、view、filters、required_filters；提取失败不转全局查询，不省略语义必需条件。
2. 复合义务允许同族两次实例化，保留每个义务和结果；处理与其他族组合及部分不支持情况，不能仅凭族去重丢掉义务。
3. 不支持/不可靠匹配沿用当前官方提交输出层的空结果契约；内部区分unsupported与成功0行，内部原因不作为对外“拒答”文字返回。
4. 移植后先做198回退与179原生SDK/服务验证，再在同B/C/模型配置下重测。固定150训练/50封存边界；原回放缺family_fill，不能当179完整协议测试。
5. 本包无179真实模型分数，不继承640/750或其他版本历史分。分页、桶唯一性和容量属于未证明能力，不自行补造事实。

## 复现（仓库内相对路径；输出使用新的私有目录）

发布建议目录 `experiments/a_family_candidate_179_20261030/`。先保证本仓库保留已发布180包与其固定Git对象。下面会创建新的本地私有目录，不改生产或B。

```sh
python3 scripts/build_a180_candidate.py --repo . --output /tmp/a180-f27-base-new
python3 experiments/a_family_candidate_179_20261030/build_179_candidate.py --base180 /tmp/a180-f27-base-new/templates180.private.json --f27 experiments/a_family_candidate_179_20261030/F27_CANDIDATE.json --retriever /tmp/a180-f27-base-new/candidate180/implementation/runbook_retriever.py --output /tmp/a179-f27-new
python3 experiments/a_family_candidate_179_20261030/verify_179_public.py --base180 /tmp/a180-f27-base-new/templates180.private.json --candidate179 /tmp/a179-f27-new/templates179.private.json --retriever /tmp/a179-f27-new/candidate179/implementation/runbook_retriever.py
```

公开可复制测试是8条合成输入×4个k、6组SQL/API和6非法配置；2100对完整输入仍保留本地，输入文件hash见MANIFEST，不在新包重复复制。`templates179.definitions.json`用固定源码引用保存172条继承项，7个新族定义与独立文字索引引用分开；实际完整179模板由构建器展开到私有目录。

回滚：生产未切换，无需回滚生产。丢弃某个新建隔离目录即可停止候选使用；保留已冻结证据，不覆盖既有目录。后续是否启用179须由B适配后的原生/模型验证决定；理论少1模板只在其他项不变时数量项+1，不是实测总分提升。

## 本次交付范围

本次无Git提交/推送；交给唯一发布负责人。没有更改生产、B代码、固定执行器/评估器、服务器或数据，没有付费、共享服务或全200评估。已发布180包、旧A与历史证据均保留。MANIFEST给出全部可发布文件hash；私有完整模板、原始输入、逐题日志与本机路径不在该目录。
