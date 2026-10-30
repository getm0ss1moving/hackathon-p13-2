# 显式加载：默认strict r4，可选enhanced

先核MANIFEST和REVIEW_INTERFACE。CANDIDATE_CONFIG默认不激活；当B明确选择本隔离包时默认variant=strict。读取对应templates132.strict.private.json及runbook_retriever.strict.py；选enhanced必须同时换对应数组/engine，不能混用。

可用importlib.util.spec_from_file_location加载模块，执行前登记sys.modules；显式构造RunbookRetriever(items)。检索纯本地stdlib，无模型/服务配置。完整义务使用retrieve(...,top_k=None)，并保留retrieve_profiles/retrieve_obligations或Candidate.profile_ids/obligation_spans的证据；start/end是原文Unicode字符偏移，不是byte或token。

选择提示逐项prompt_item(item)，填参时也用prompt_item(selected)临时读取examples/parameter_contract；不写回库存。unified_prepare先handles_item，True再以完整原文/parsed调用prepare_candidate，False走B原路由；不要把未处理旧路由误当空业务。

B必须新增132 manifest/预检，不能直接复用只认160/170/180的入口或放宽旧哈希。先接schema、原文prepare、精调和精确列合同；这份加载说明不授权新增模型/服务调用、生产切换或比赛提交。
