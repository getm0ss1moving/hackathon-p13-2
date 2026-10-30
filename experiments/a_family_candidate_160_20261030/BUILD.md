# 160离线重建与公开解析复核

所有命令从仓库根执行，输出必须是全新的仓库外私有目录，不覆盖B或生产。Python标准库和git即可；不启动模型、服务、SDK或评分器。

## 先生成固定170起点

按[已发布170交接](../a_family_candidate_170_20261030/B_A170_HANDOFF.md)中的五步命令生成`/tmp/a170-final-new/templates170.attributes.private.json`与`candidate170/implementation/runbook_retriever.py`。起点模板必须为f77c7542…c9c664c，检索器befff58a…ef4f24；任何漂移先重新冻结，不能去掉hash断言。

## 170→166→164→160

```sh
python3 -B experiments/a_family_candidate_160_20261030/base160/stage166/build_166_candidate.py --base170 /tmp/a170-final-new/templates170.attributes.private.json --references experiments/a_family_candidate_160_20261030/base160/stage166/FAMILY_DEFINITIONS.references.json --retriever /tmp/a170-final-new/candidate170/implementation/runbook_retriever.py --output /tmp/a160-chain166-new
python3 -B experiments/a_family_candidate_160_20261030/base160/build_164_160.py --base166 /tmp/a160-chain166-new/templates166.private.json --single experiments/a_family_candidate_160_20261030/base160/sources/single/CANDIDATES.json --count experiments/a_family_candidate_160_20261030/base160/sources/count/FAMILY_CANDIDATE.json --retriever /tmp/a170-final-new/candidate170/implementation/runbook_retriever.py --output /tmp/a160-stages-new
python3 -B experiments/a_family_candidate_160_20261030/verify_public160.py --templates160 /tmp/a160-stages-new/templates160.private.json --retriever /tmp/a160-stages-new/candidate160/implementation/runbook_retriever.py --output /tmp/a160-public-check-new
```

160目标模板hash为477741d28773cff55d69c9542eb26c60c5bbf47fdadfc5e12069c0f73499d182，164为d87bea245903470b606e5bf947090b48ec7a5a626b7eca4341e1cf8397c9fdcb。构建只生成A数据/索引，没有装入完整B。

公开verify检查160唯一ID、200文字映射/别名、400+11索引、源码清单；在新的私有目录重放single_table_families.py精确补丁fc71c51f…6bb506→04098b71…ed6576，再复核公开四条ASCII裸复杂名及四项负控制。源码补丁只作用于该私有副本，不能直接贴最新matcher。此公开复核不执行27组SQL、原51/70/41或2148+204完整私有回归，也不认证COUNT业务。

完整源验收需要原保留的私有fixture；没有这些输入不能宣称异机复现全部162项。本包保留其hash和必要聚合证据，原题/资产和展开库不上传。COUNT空占位1、缺列吞错、missing objList/失败/分页完整性及两物理CI非空原生证据仍需B/官方协作。
