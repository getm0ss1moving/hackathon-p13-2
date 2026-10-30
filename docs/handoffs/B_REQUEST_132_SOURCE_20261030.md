# A同学：B接入132所需源码交付

用户已明确要求B从仓库下载最新132并在其上优化。B已核对远端main（fea24c5）、simple/official-starter（02fec79）、codex/a180-train150（10f2f70），以及Releases和两个PR：没有找到132源码包或可下载构建产物。最新A_POST170_FALSE_EMPTY_CAUSES仍明确“132未正式交付，本次不发布模板、解析器或检索补丁”。当前不能把原因说明或49轮廓CSV当成132实现。

请将以下源码及固定交接提交到既有仓库，给出提交SHA和仓库相对路径；若已发布在其他位置，请直接给固定可访问的源码位置：

1. 132模板定义/构建链及strict/enhanced选择说明，普通clone可复建到已有数组hash；无需上传私有展开库或业务数据。
2. REVIEW_INTERFACE.json、FAMILY_ROUTE_REGISTRY.json、unified_prepare.py，以及26个family所需纯函数模块及其依赖；F02 natural_views和新view、F03 per_view_keys/top_k必须完整。
3. B选择卡、模型参数schema、view/prepare dispatch所需的机器可读合同；新增11族不要只列名称。
4. 正常问法/礼貌包装/明确投影正例，以及额外义务、错实体/角色、缺参数、真空与错误的负控制；说明245条合成证据中可公开复现的输入与未决问题。
5. F03超4KB及COUNT业务门禁的现状：保留原始限制、来源与待解决项，B在实际源码基础上处理，不把它们隐去。

B当前已发布提交fea24c5，保留327行matcher增量和默认猜空策略；接入时以此增量适配，不用旧0c82f0d完整matcher覆盖。B会先修已证的选择卡额外元数据兼容问题；实际132 dispatch/参数抽取须等源码合同，不猜造26族或新view。

本请求只请A交付自身模板/纯函数/构建资料，不请A改B的matcher/system，不授权新增模型测试，不改官方评估、执行器或数据。B继续在现有main本地开发，不新建分支；后续提交推送按用户当次指令处理。
