# Issue3 P0：三个组合合同的默认关闭增量

**本包可供 B 接入评审，保持默认关闭。未替换132、默认198或B运行实现，未注册新能力；A合同通过不代表B端到端、真实空schema来源或官方合规通过。**

三个 profile 的完整源码/合同最小闭包共6文件，均保留受审原字节。tenant_lists、vdc_network采用 `p0-r2-zero-pages`；vdc_counts保持原版。源R2 manifest SHA-256 为 `46db8ee6963c16e4d7f786f8d6da285e612fd8466d469480fc31a1e1297e49fd`，本包是明确的最小子集，不冒称该16文件owner归档。[MINIMAL_B_HANDOFF](MINIMAL_B_HANDOFF.json)给出全部6项路径和哈希，[B中文交接](../../docs/handoffs/B_A_ISSUE3_P0_COMPOSITIONS.md)给出接入门禁。

|profile|当前 A 状态|完整输出与边界|
|---|---|---|
|vdc_counts|原独立35/35，源码未改，本次未导入/复测|VM、卷、GaussDB**实例**分别计数，以三源VDC名称桶并集连接；名称不证明权威唯一VDC身份|
|tenant_lists R2|独立19项局部验收覆盖，真空误拒修复|VM、安全组、卷三个身份/名称清单；tenantName标签选集不证明唯一租户；未明示区域时不得加区域|
|vdc_network R2|独立19项局部验收覆盖，真空误拒修复|VPC名称、子网CIDR、EIP独立标量；VDC与区域均显式，不能推导VPC父子/AZ/EIP绑定关系|

R2仅将两个回执验证条件扩展为：成功零总量且完整单个第一页时，可选 `totalPageNo` 接受整数0、1或省略；非空仍严格ceil，布尔/浮点/字符串/NULL/矛盾页数、失败、缺源、缺列、截断、重复身份仍拒绝。原两项合法真空误拒由独立19/19检查闭合，94个边界子项不另加；不将35与19相加冒充新全量验收。旧104项的102通过/2失败记录保留在来源说明中，未重写成一次全过。

## 公开合成复放

```sh
python3 -B scripts/verify_a_issue3_p0_synthetic.py --output /tmp/a-issue3-p0-check-new
```

从仓库根执行，输出目录须全新且在仓库外，Python标准库和内存SQLite即可。脚本核公开manifest与自身哈希、全部6文件指纹，复放适配后的19项/94子项。两个历史输入用新合成字面值替代；旧prepare对照改为冻结的合成plan哈希，文档网段仅为合成CIDR。不上传原生记录、原题或答案。vdc_counts只做哈希/语法核验，不执行它，也不重跑owner或完整旧审查套件。

本机实际复放摘要在 [PUBLISH_VERIFICATION](evidence/PUBLISH_VERIFICATION.json)，原独立验收摘要与旧反例闭包在 `evidence/`。源码合同中保留的“pending independent”字段属于冻结历史声明，当前验收以本README、独立矩阵及收据为准。

B仍须证明真实请求/范围/HTTP成功、schema来源和收齐分页；仅 `ok=True`、schema_source字符串或caller flags不能认证来源。必须加载preflight投影和真正零行typed表，不能将 `_empty` 占位当0或1；传播未知名称/CIDR/身份与局部不完整状态。实际最终封装、4KB作用边界和官方深度口径仍未解，禁止截断实体/SQL/义务。无模型、服务、B链、官方执行器或评分器调用，实际N变化0，issue保持开放。
