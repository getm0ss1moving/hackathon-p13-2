# B隔离接入：四项必须同步

本提案尚未应用，默认关闭。先核[SOURCE_CLOSURE](SOURCE_CLOSURE.json)和实际目标源码；旧SHA不匹配时先对照并重新冻结，不能覆盖B的新修复。

1. 模块：`family_volume_rows`旧SHA `bb6f0dace53f6ce6d47244c784a15265501a477da123892ffd86e353f23f4138` → 新SHA `56c6a58c9b8108cb7c0545e1c2da9e5ad00a35101d007f4b8415b703d05514d0`。
2. registry及绑定：按family选择并test旧`module_sha256`，通过后再替换，见`REGISTRY_PATCH.json`；重锁实际受影响manifest、数组与组合绑定。不能整份覆盖旧registry，不能声称旧132哈希仍适用。
3. schema：使用`CONTRACT.json.parameter_schema`，只让bootable目标字段接受bool/大小写true-false字符串。prepare统一成原生小写字符串；region/AZ/VDC逐字保留，不全局转换bool。
4. 选择卡：按`FAMILY_CARD_PATCH.json`先test旧枚举`['True','False']`，再replace为`['true','false']`；其他字段不动，test失败就停止对照。

必须调用`prepare_candidate(full_question,item,parsed,diagnostics)`验证完整原文，不能用结构materialize代替。API仍为VOLUME GET，四列name/size/status/bootable与SQL不变；required_filters保留region/AZ/bootable三项。原生响应值不修改，管理VM合同不在此包。

公开复放见README；原owner71套件仅引用，未纳入或重跑。两份受审源码和CHANGES.patch支持内存精确差异检查。原生类型证据只有聚合，不读取其所列文件；SOURCE_LOCK原指纹作为来源记录，不把历史运行组件哈希强加给当前B。

参考AZ争议仍交C，真实取数/分页/schema/typed-empty/失败状态、完整B链和最终封装仍门禁。保留query→_query猜空包装与guess/原始失败区分，不能将error=None当真实空或业务成功。不自动启用、不改132或默认198。
