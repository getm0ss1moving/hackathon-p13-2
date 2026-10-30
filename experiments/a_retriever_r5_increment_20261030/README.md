# r4→r5：独立默认关闭的检索增量

**当前main根库为B已接入的132 strict compact＋r4，本提交保持该入口和所有B代码不变，不自动切r5。** 只交付strict/enhanced r5引擎、精确r4增量补丁、复现与B交接；不改模板/prepare/参数，不混管理VM、bootable或新日志修复。

已核根源码：132项，`runbook_items.py`为`6e2fc4a1…c80970c`，根r4引擎为`99d15b69…7814802`，与strict增量受审基底一致；完整根文件指纹见[ROOT_B_BASELINE](ROOT_B_BASELINE.json)。这证明源码补丁基底匹配，**不等于r5与当前compact数组/B全链已验收**。独立r5收据绑定原132v1数组；实际B数组/module/adapter/配置组合仍需B另锁、联调。

独立33项义务粒度专项通过，原14个单统计各保持一个目标；原1166回归支持1016误空0、复合161完整、150负例三入口空。普通603×4排名向量2412同原132基线；历史200**模板实现**仍2368/2412相同、44属性差异，未新跑200题或模型。33与1166是不同范围，不拼成业务题成绩。

先读[中文B交接](../../docs/handoffs/B_A_R5_RETRIEVAL_INCREMENT.md)、[接口](INCREMENT_INTERFACE.json)和[实际交付manifest](MANIFEST.json)。独立门禁与来源摘要保持原字节。源11文件overlay manifest SHA-256为`37dc0721cb68597961a42b397fd8bc27822f653b22a2fa20da6b20a0ad255b2f`；[SOURCE_CLOSURE](SOURCE_CLOSURE.json)记录全部原文/脚本归档位置。归档说明中的“默认198/未Git”是源封装历史阶段，不代表当前main。

## 最小补丁复现

从仓库根运行，输出必须全新且在仓库外。strict可使用当前根r4源码；enhanced使用已发132v2+r4对应精确模块。脚本只复制源码到新目录、`git apply --check/apply`并核r5哈希，不建Git库、不改根文件、不提交、不跑检索/模型/API/SQL。

```sh
python3 -B scripts/reproduce_a_r5_delta.py --variant strict --base-module implementation/runbook_retriever.py --output /tmp/a-r5-strict-replay-new
python3 -B scripts/reproduce_a_r5_delta.py --variant enhanced --base-module experiments/a_family_candidate_132_v2_r4_20261030/runbook_retriever.enhanced.py --output /tmp/a-r5-enhanced-replay-new
```

实际两版最小重放摘要见[evidence/PUBLISH_PATCH_REPLAY](evidence/PUBLISH_PATCH_REPLAY.json)，未重跑33/1166完整私有控制。展开数组仍沿[132重建说明](../a_family_candidate_132_v2_r4_20261030/LOAD.md)在本地生成，接口中的private数组路径是生成产物引用，不是本仓库内公开文件。

单目标的`retrieve_obligations=[]`不是不支持；B应走普通检索。真正多目标要保留按序profile和Unicode字符span，完整义务限`top_k=None`。r5不补region；召回rb052不证明无区域输入已获得全域统计。COUNT/API/schema/分页、F03 adapter、真实B链、官方4KB/深度/时延/资源与模型token均不能由此检索验收替代。
