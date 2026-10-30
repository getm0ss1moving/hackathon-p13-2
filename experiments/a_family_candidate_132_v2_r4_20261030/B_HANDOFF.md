# A→B：132v2 compact＋r4联调交接

|责任|已做/待做|
|---|---|
|A已完成|132/唯一ID、39固定源归并和200文字profile映射；12改动族原文prepare闭包；F03重复metadata无损精简与必需adapter；严格/增强分离；r4两版独立1166检索门禁通过。|
|B必做|新增132 manifest/预检和family/view注册；选择与填参两处prompt_item；消费profile_ids/obligation_spans，按原子保留同族多view/多实体/范围；严格schema、精确列序、精调和执行完整性。|
|B仍未解|原3“仅依次输出”、礼貌前后缀、选择卡natural_views、schema/view/dispatch兼容；COUNT空占位、缺列/失败/分页/依赖；真实模型/原生全链未测。|
|C/官方待定|实际4KB序列化和深度算法、空COUNT参考、AZ节点量词和专用池角色、TopK/容量/NULL/分页政策。|

## 版本与默认

本隔离包默认strict r4；enhanced显式可选，不把11/22卡混配。两版在冻结控制均通过，strict有更宽的紧凑字节余量；没有真实模型评分证明哪版更优。根默认198不变，不覆盖B最新代码或旧候选。

## B读取方式

使用retrieve(query,top_k=None)取得活动canonical ID。retrieve_profiles返回原文字profile证据，retrieve_obligations给原文字符跨度和每句候选。Candidate新增profile_ids/obligation_spans。B需消费这些证据并分别选择view、抽参、prepare全部原子；不能只按family ID去重、不能把删除的旧profile ID当执行对象或参数答案。top_k=1/5可能按合同截断义务。

unified_prepare只覆盖12个新增/改动族，先handles_item，其他14旧族与106固定项沿B原路由。保留family_f10/family_f17_safe item.id；materialize不能代替完整原文prepare。精确_expected_result_columns、JOIN/DISTINCT/排序/API条件及依赖必须保留。

## metadata adapter必须接入

F03 compact的examples由同对象retrieval_views描述引用。选择提示与填参schema/示例两处都用prompt_metadata.prompt_item临时恢复；未接时examples=0，不能称提示无损。恢复后全文与旧metadata相等；不要把恢复后的大对象写回或导出提交库。

## 验证边界

r4独立1166在原132v1数组执行，compact版另有全部检索实例状态等价证据。本封装复制精确代码/数组，不新增整轮或模型测试。1016支持、161复合是嵌套口径，不能把161另加为新题。原132普通603×4为2412全同；历史200模板实现为2368/2412同、44属性通道差异。本轮未重跑历史200，更没跑200题端到端评分。

本机strict P95约3.64ms、P99约4.19ms；enhanced约3.73/4.25ms，只是检索调用，不是官方硬件、端到端4/6秒或2GB峰值认证。负例150通过不外推任意未见语义完备性。

F03紧凑UTF8为3549/3986B；其他编码仍可能超限，深7/外8未认证。COUNT和原语法缺口未因检索通过解除。当前不是官方整包可提交包，生产默认不切。B新实验需另锁完整flags、源码、评分器、数据边界及预算，不拼旧632.8/三题15/15为新成绩。
