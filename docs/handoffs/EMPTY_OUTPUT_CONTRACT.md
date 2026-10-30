# 未支持查询的空输出合同

用户要求未支持时不显示解释。本次只修改我方runbook_system最终输出层，未改matcher识别逻辑、固定执行器/评分器、数据或服务。

[官网](https://www.chaspark.com/#/races/competitions/1326646677767008256)3.3把接口细节交给SDK，4.1要求结构化查询结果；网页没有明定未支持时的null/空数组/空字符串类型。因此沿用原SDK的字典封装及result=None，JSON序列化为null，不把整个返回值改成空字符串或数组，也不省略既有字段。

|状态|matched_runbook|result|error|内部区分|
|---|---|---|---|---|
|无法可靠匹配/不支持的计划|null|null|null|diagnostics保留阶段、原因；对外不打印解释|
|查询成功但0行|命中名称|columns、rows=[]、row_count=0对象|null|execution完成，保留真实列名|
|查询成功且有行|命中名称|原结果对象或原多结果列表|null|execution完成|
|真实执行异常|原命中状态|原失败结果|原错误|不能吞掉异常改称未支持|

未支持仍保持matched_runbook=None，原评分器照常给0分。不能只将result清空而保留命中名称：固定评分器可能把它与空标准答案判为正确；合成反例已记录，但没有利用该行为提高分数。成功0行不得改成未支持，执行器既有缺列吞错风险也未被本轮修复或包装成成功。

单次CLI未支持时正常退出、答案stdout严格为空，不打印标题、命中、诊断或错误；交互CLI不打印该次答案，保留原输入提示。成功、成功0行、真实错误及多SQL的CLI表现与原版相同。内部日志/评分报告继续保留审计信息，未改官方评价原因字符串。

SDK字典中的diagnostics按既有C/B接口保留，它是内部诊断字段。当前用户CLI已经隔离；其它前端应只呈现output['result']，不能直接显示整个SDK字典。若外部调用者自行渲染完整字典，内部原因仍可见，本次没有声称隐藏这种调用方行为。

独立61项合成检查使用真实固定execute处理无API/无资源表的SQL，并正常调用evaluate_case；未monkeypatch固定模块，无模型/HTTP请求。另有6项可移植合同测试：

```bash
python3 -m unittest discover -s tests -p test_empty_output_contract.py -v
```

正常句式模板外、部分不支持复合和歧义仅是输出层fixture（由测试matcher引用返回None），不能称已识别这些问题。识别能力由检索/语义任务另行验证。摘要见[EMPTY_OUTPUT_VALIDATION.json](EMPTY_OUTPUT_VALIDATION.json)。
