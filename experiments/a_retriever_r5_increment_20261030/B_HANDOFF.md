# B入口：r5检索义务粒度增量

请读[完整中文B交接](../../docs/handoffs/B_A_R5_RETRIEVAL_INCREMENT.md)与[README](README.md)。当前根默认132 strict compact＋r4保持，r5默认不应用；root strict基底哈希匹配不等于B/compact全链已验收。

本增量只修单目标/多义务划分，未补region、参数或业务能力。B保留单目标普通检索回退、多目标按序profile/字符跨度、同族多view/多实体及`top_k=None`完整义务。不得将空obligations当不支持，不得将缺region的召回当全域统计。

实际补丁重放命令在README，维护脚本统一位于仓库`scripts/reproduce_a_r5_delta.py`。源overlay原B说明、README和原脚本分别归档于`evidence/`及`source/`，保持原文和指纹；其中198/未推送状态是历史来源描述。
