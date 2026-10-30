# 具名 VPC：子网与 EIP 独立双计数候选

**单独默认关闭的A合同交付，供B接入评审；不改旧next、P0、132、默认198、B或官方组件，不关闭issue。** A侧局部验收通过，B实际来源、typed-empty及完整业务仍未验收，057及其他能力未混入。

先读[逐模板中文B交接](../../docs/handoffs/B_A_ISSUE3_NAMED_VPC.md)、[完整合同](CONTRACT.json)和[源码/合同闭包](SOURCE_CLOSURE.json)。两份原始源码/合同均保持受审字节，文档调整为实际公开路径和可用的最小复放命令；公开MANIFEST只声明本次实际交付，不冒称原owner全归档。

|项目|合同|
|---|---|
|名称/区域|精确VPC名称必需；区域显式可选，无默认区域；同名按all_matching_parent_ids或reject_multiple_parent_ids处理|
|输出|逐匹配VPC ID返回已解析/引用/未解析子网数与已知EIP数，独立聚合后LEFT JOIN父对象，防止扇出|
|身份/关系|同区域nativeId→PORT→关系→SUBNET；EIP.routerId指向ROUTER.id；跨区相同nativeId合法，同区多解拒绝|
|空/未知|零子项父保留四个0，零匹配与真正空为零行；未知或未解关系不冒充完整计数，失败不转0|
|取数方案|五路完整目录，无跨步骤依赖占位；B改为动态缩小请求需另证消歧、覆盖、全局未知排除与当前输入绑定|

独立15/15场景通过，26个状态/schema/分页子项嵌套，owner27套件未运行。已核发布ZIP4成员、owner归档与checkpoint、11项原manifest及12份源文件。发布ZIP SHA-256 为 `7d8e8b55454d8fb98069fee4aa00cb623ede4ba70541774a33b51e0ea7a48022`；它与原owner ZIP `fe5fa16a…c4c065`是两个不同产物。[独立证据](evidence/INDEPENDENT_RESULTS.json)与[SOURCE_PROVENANCE](SOURCE_PROVENANCE.json)保留准确指纹。

## 公开最小复放

```sh
python3 -B scripts/verify_a_issue3_named_vpc_synthetic.py --output /tmp/a-named-vpc-check-new
```

从仓库根运行，输出目录须全新且在仓库外，标准库与内存SQLite即可。脚本核公开源码/合同/文档及自身哈希，复放15项/26嵌套子项；源审计范围为本次公开闭包，不重跑owner27或完整归档审计，也不与独立结果相加。实际摘要在[PUBLISH_VERIFICATION](evidence/PUBLISH_VERIFICATION.json)。没有模型、服务、B运行、原生SQL或官方评分调用，未复制原生对象、原题或答案。

真实PORT重复仍拒绝，canonical输入路径未实现；EIP空routerId、未知/目录外关系可能使图保守partial。B须保留这些诊断并证明真实请求/HTTP/schema/完整分页与typed-empty投影，不能把guess空或error=None当成功。最终B外壳字节、正式深度和业务权威仍待确认。实际N变化0，未来独立注册+1或扩既有profile+0需另审，不能自动声称仍为132。

上一批next里“192双count未含”是当时冻结范围；本增量现交付该A侧合同，旧包不改写，B完整业务仍未完成。057、多IP token匹配、全量EIP→VM、部署AZ和VM层级不在此profile。
