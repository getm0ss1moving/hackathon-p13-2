# B提示：保留执行义务，未补region

- 33专项只修检索义务粒度。CPU架构类型及各类数量是同一个统计目标；一个目标的retrieve_obligations返回[]，不能误判不支持，也不能因BM25局部视图有两个就执行两项。
- 真正多资源/双实体/AND/“以及查询”保留按序profile和原文字符span。B须消费Candidate.profile_ids、obligation_spans及retrieve_obligations，分别选择view/抽参/prepare，不能按family ID吞义务。完整覆盖结论只对top_k=None。
- 四子问强profile并集20超过15预算时三个入口全空，不能自行放宽或静默丢一个义务。未知新维度/区域/每台明细的相邻控制只证明不应误折叠，不代表业务能力通过。
- r5没有填参数或补region。rb052的原生区域条件/default_params未改；缺region的输入召回rb052，不证明已得到全域统计。B仍需执行缺参/范围政策，不能沿本机默认区域运行后称全域成功。
- 保留现132v2的F03 prompt_metadata adapter两处接入义务，以及语法误空、COUNT/失败/缺列/分页和官方序列化/深度门禁。检索增量通过不是整包业务通过，不修改B/模板来拼成绩。
- 原1166相对r4候选/列表/可选证据0增长；专项33中新语法最多+2候选/+1056UTF8字节，不能泛称全部0增长。实际模型token未测。

## 补丁复现（只在新私有副本）

```sh
python3 reproduce_delta.py --variant strict --base-module ../a_family_candidate_132_v2_r4_20261030/runbook_retriever.strict.py --output /tmp/r5-patch-replay-NEW
```

脚本先核r4基底/patch SHA，复制到新的implementation子目录，再git apply --check/apply并核r5完整SHA。它不创建Git仓库、不commit/push、不写原B或模板、不跑检索/模型/API；本次封装没有执行该脚本。独立审查已实际应用补丁、退出0且产物SHA一致。

直接加载完整r5模块无需应用patch，但必须锁对应数组/adapter/B配置。待唯一publisher决定提交；本包默认关闭，不切换根默认198。
