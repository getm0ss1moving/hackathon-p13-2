# 给B的最小接口增量（尚未集成）

仅供B在当前根implementation/runbook_matcher.py中审查合入纯函数；本任务没有该文件补丁，也没有替换任何B源码。保持B现有候选顺序、选择/填参预算、SQL精调、聚合与官方输出链路。

1. A侧仅添加一条family_next_n28候选，并在最终获准的隔离库移除046/047/070/109/120五条活跃执行项。先核对最新基线漂移及ID交集；不在每次请求展开五条旧执行模板。五张检索视图仅映射到这一候选，不计作执行N。
2. B抽取六参数。示例结构（entity必须从当前问题获取）：

```json
{"resource_set":["ROUTER"],"group":"vdcName","layout":"single_grouped","metric":"count_rows","filters":{"logicalRegionName":"<当前问题地区>"},"required_filters":["logicalRegionName"]}
```

3. 在既有matcher调用`prepare_count_candidate(original_atomic_question,item,parsed,diagnostics)`。成功返回完整普通item；失败None并记录内部unsupported_or_ungrounded，不能伪装成API成功0行。`materialize_count_family`只验证结构，不自行证明文字；不要绕过prepare直接把模型JSON交物化器。
4. SQL精调流程继续存在；本闭合合同不开放新的列/函数/标签/别名/筛选/分组/关联。精调后必须验证所有原输出与API范围义务，最小保护是与受控物化出的API/SQL完全一致；偏离则按B现有失败出口处理，不写执行器兜底。
5. 同族不同view、不同地区及多个原子义务必须保留列表，不能按family_id去重成一个。原子分割只有在B证明覆盖原问题全部义务后可用；不能把本helper拒绝的完整请求截成可回答片段并遗漏剩余部分。该全局覆盖逻辑与组合测试仍由B负责，本包未实现。
6. 不支持返回的业务序列化沿用官方空结果出口；执行成功0行、字段缺失和不支持在内部可区分。SDK现有缺列分支返回空且error=None，不能只看error=None就叫正常成功。

集成后要实际重跑：五合同显隐式改写、完整库BM25召回竞争、多view/多范围、真实选择/抽参、正常与真空API、分页、精调保护及最终SDK出口。S_Switch/S_Router缺非空原生样本；不能用合成正例称现场资源完整。正式模型比较必须冻结相同A/B/C/模型配置并按既有150训练/50封存规则由协调者授权，未测不得引用旧640/750或其他版本分数。

本文件不增加DSL、自动适配器、服务、网络调用或执行器。候选函数文件是待放入既有matcher的审查输入，不应作为新执行服务或替代SDK。
