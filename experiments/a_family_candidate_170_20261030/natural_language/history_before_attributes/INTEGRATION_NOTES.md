# 冻结自然语言增量：接入边界

公开接口为 `prepare_natural_candidate(question, item, parsed, frozen_prepare, diagnostics)`，parsed只含view、filters、required_filters。view从原输出合同决定列、列序、filtered范围与原排序，不默认实体。成功是原API/SQL普通item，失败None；现有B出口负责官方空结果，内部原因不作为对外解释文字。

此版新增的是通用输出意图片段所有权、紧邻实例名称/角色证据与自然问句规范化。显式列、筛选、范围、排序限制不能被默认view替换，否定/OR/额外能力须保留供校验，不能删词后扩大查询。引号实体内的“容量/ECS/或”等词按实体处理。批次3闭合物化器79815020…未改。

源码：natural_view_candidate.py；9个view合同：VIEW_CONTRACTS.json；组合到B的纯模块：runbook_family_views.py。后者将自然原型与原闭合物化函数放在同一模块，供B既有选择后分支调用，不是新执行器。

latest_main_F02_F19_view_adaptation.patch只针对B matcher源SHA1e7cc2ff…902b63e，基底记录7b7271e3。私有重放经apply-check与apply后得到matcher829a7e41…927fc5a和模块55d732ab…6ed065e。共享B未动。若最新main已经变化，B/发布负责人必须重新核对，不能整文件覆盖或盲打补丁。

该补丁只适配F02/F19，不等于170库全部9族都已接通B。首批六族及F27的材料保留在已发布180包/history179，需要B在同一配置里完成移植和组合适配，不能把它们的参数化容器未物化即交SDK。

证据分开看：OWN_SUMMARY70为我方同70例重跑70/70，参数由测试提供；PRODUCER_160/CONTROLLED_MATCHER为实现方报告；UPSTREAM_INDEPENDENT8为独立小审报告。937受控尝试的模型/schema为mock，非真实模型或SDK成绩。真实170检索当前38/46，8项缺失阻塞上传。

全部70原题/逐项诊断不附本包。完整复验使用本地保留的CASES70.private.json（hash48ad5322…e33b）及根验收目录，不能声称未持私有fixture的异机已重现70。模板数据构建可按根HANDOFF完全离线重放。
