# r6：精确义务跨度，默认关闭候选

**仅为独立候选交付，不修改B或main默认，不加入已冻结2c6ddfd全量基线。** 两版源码保持独立验收字节，只修义务区间两端空白：区间内按Python str.isspace收缩start/end，再以原文切片生成text；不改内部空白、Unicode字符、profile、顺序或预算，不全局find。

strict SHA `a236235e98ebcceeb372577fe85fa3d3baa26d7a58edb0775c579d9e4fccca52`；enhanced SHA `76bbcd817d2f3ff4b8748061a8134a33f5693bc5d04ee6519d385cac1b6ba8b9`。坐标为原始Python str码点，左闭右开，必须满足`query[start:end] == text == text.strip()`；重复文本仍须保持准确出现位置。

独立每版50/50相同输入集通过，另12种本地严格验证器负控制拒绝；这些负控制不是新增查询数或B验证器能力。owner1148/49/54/978仅引用，未由独立审查或本次发布审查重跑。没有模型分数、原生执行或全量认证。

原受审数组为132v1 strict/enhanced各自固定SHA，私有数组不随包上传。B `2c6ddfd`目前为compact132＋strict r5，不能把其配对验收自动套给r6。采用前需另锁真实数组/引擎/适配器和B来源清单；不混版、不关旧哈希校验。

见[逐项B兼容说明](../../docs/handoffs/B_A_R6_EXACT_OBLIGATION_SPANS_20261031.md)及`R6_INTERFACE.json`。最小运行闭包仍是同版模块＋外部本地数组；本包是源码/增量补丁/证据交接，不是整项目替换包。

最小发布复现只跑两版精确delta、AST范围与六条合成分段控制，不读数组、不运行B初始化或模型：

```sh
python3 -B scripts/verify_a_r6_release_smoke.py --r5-source-root experiments/a_retriever_r5_increment_20261030 --output /tmp/a-r6-release-smoke-new
```

输出必须全新且在仓库外。独立50/12证据与发布最小检查分开记录，不拼成新业务成绩。本候选不自动注册或启用；是否已推送以Git提交为准，最终公开闭包见本轮Issue4交接。
