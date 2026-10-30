# F18参数组合：免费静态复核与最小建议

本次先静态复核F18运行时代码及固定train150既有响应，再仅在本地提示Schema增加已审定组合约束；没有新模型/服务请求、50或全200读取，也没有源码远端发布。证据见`experiments/a180_runtime_port_20261030/F18_SCHEMA_REVIEW.json`。

## 证据

v6按规格分布的真实响应为`group=flavorCode, metrics=count`，得5；v11同一group却为`metrics=count_storage`，得0并拒绝`unreviewed_metric_group`。过滤器和required_filters相同。运行时和A原始R5合同一致，拒绝正确，不能放宽成所有分组与所有指标的笛卡尔积。

当前没有名为`_family_output_schema`的函数；Schema在`_match_family_candidate`内构造。F18已有文字说明：vdcName对应count_storage，其余三个分组对应count。问题不是完全缺少提示，而是Schema中的group/metrics仍为独立枚举，语法上允许8组，只有4组获审定。该Schema只是普通提示中的文本，没有配置提供方结构化输出强制执行。

## 可审查的局部差异，已仅在本地应用

仅在已有Schema构造后，为F18加入以下条件；不增加结构参数，不改原过滤器、运行时物化或语义接地逻辑。

```python
if family == "F18":
    schema["oneOf"] = [
        {"properties": {
            "group": {"enum": ["flavorCode", "engineVersion", "haMode"]},
            "metrics": {"const": "count"},
        }},
        {"properties": {
            "group": {"const": "vdcName"},
            "metrics": {"const": "count_storage"},
        }},
    ]
```

根Schema原有required仍要求group和metrics。两分支不重叠，保留全部4种合法组合，排除另外4种组合；不通过删除缺失筛选或改写指标“修复”模型响应。运行时拒绝仍为最后保障。

## 已完成的免费控制与限制

- 穷举4×2组合：实际物化仅接受规格/引擎版本/高可用模式的count和VDC的count_storage；建议分支成员关系逐项与这4组一致。
- 4个实体替换正例通过现有接地及物化；7个负例继续拒绝：区域否定、OR、缺区域、null区域、未知顶层键、缺metric、不支持的筛选字段。
- 没有安装依赖；本轮验证了const/enum分支的穷举成员关系，没有运行完整JSON Schema验证器，也没有证明提供方模型会遵守该建议。

同期EIP小集的一个F01回归也因独立枚举联动失败而拒答：`total_active`配`count_alias=total`不在现有合同内。该事实独立保留，本建议仅覆盖F18，不顺带改动F01或扩大输出合同。下一次真实验证需另行协调，不把离线回放作为新模型成绩。

本地候选已按上述最小差异实现：相对37f7407，仅_match_family_candidate函数改变；EIP、接地、物化及语义检查函数AST均未变化。281项免费检查通过，实际生成Schema等于本次审查提案。候选记录见`experiments/a180_runtime_port_20261030/F18_SCHEMA_CANDIDATE.json`。当前父账本在重新办理通知前已closed（包括9次未分配额度），没有重开额度或启动真实API验证；本地候选尚无新真实模型成绩。
