# 离线重建与显式加载

从仓库根运行，Python 标准库即可；输出目录必须全新且在仓库外。先按 [160 构建说明](../a_family_candidate_160_20261030/BUILD.md)重建固定 160，模板文件 SHA-256 必须为 `477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182`。

```sh
python3 -B scripts/build_a132_v2_r4_candidate.py --base160 /tmp/a160-stages-new/templates160.private.json --output /tmp/a132-v2-r4-private-new
```

构建器先核公开 manifest、自身哈希和固定基底，再生成两版 132 数组/Python 导出、13 份族 JSON，验证全部 57 项源指纹、12 prepare 源指纹、400 主文档、11/22 属性卡及 F03 同对象 metadata 无损恢复。`BUILD_REPORT.json` 是本次重建证据；此最小复核不重跑私有 1166 控制，也不执行模型、SQL/API 或 B 全链。

公开 `REVIEW_INTERFACE.json`、registry 和最小运行闭包的相对路径，以**生成的私有目录**为根。在那里显式加载 strict 配对数组与引擎，enhanced 必须同时替换两者。用 importlib 加载模块前登记 `sys.modules`，构造 `RunbookRetriever(items)`。源加载说明归档于 [evidence/SOURCE_LOAD.md](evidence/SOURCE_LOAD.md)。

完整多义务使用 `retrieve(query, top_k=None)`，保留 `retrieve_profiles`/`retrieve_obligations` 或候选中的 `profile_ids`/`obligation_spans`；跨度是原文 Unicode 字符位置。两处提示边界使用 `prompt_metadata.prompt_item` 临时恢复，禁止将恢复后的大对象写回模板库存。

`unified_prepare.handles_item` 为 True 才走 12 个变更族的完整原文 prepare；False 继续 B 原有 14 族与 106 固定项路由，不能当“不支持”空返回。需要 B 新增 132 预检、schema/view 注册和完整执行适配；本命令不安装这些适配，不自动启用候选。
