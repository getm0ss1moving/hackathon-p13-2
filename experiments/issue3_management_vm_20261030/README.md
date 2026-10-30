# 管理 VM：独立默认关闭的明细候选

**A侧局部合同可供B接入评审；未通过完整原题、真实B或官方验收。`full_answer_certified`固定false。** 本包不改bootable、132、默认198、B或官方组件，不注册、不关闭issue，也不与r5或其它候选混包。

发布基线说明：本包追加在B的`b00e85a`之后，保留其当前132 strict＋r4根入口，不回切198。下文198属于A冻结阶段的历史默认值；本次不修改B当前任何运行默认。

先读[逐模板中文B交接](../../docs/handoffs/B_A_ISSUE3_MANAGEMENT_VM.md)、[CONTRACT](CONTRACT.json)及[SOURCE_CLOSURE](SOURCE_CLOSURE.json)。candidate.py与合同均保持受审字节；公开清单只覆盖两份原文件、文档和必要合成复放，不冒称原9文件owner归档。

|项目|闭合合同|
|---|---|
|管理字段|VM原生JSON bool `management=true`；字符串`"true"`和数字1拒绝。本地投影management=1只是准备编码，与bootable的原生字符串合同不同|
|父域/作用域|仅显式region筛管理VM，其它CI取完整上下文；VDC ID/名称为来源身份/显示字段，不支持命名VDC过滤或VDC总容量汇总|
|服务与卷|每VM一行，服务按CloudService.id、卷按VM＋volume引用独立去重成集合，不展开服务×卷，不用SUM(DISTINCT size)|
|IP|两列多值原始文本保留，不取首地址、不互补空、不以IP连接服务；普通IP问法要求both_raw，不宣称已有IP对象codec|
|未知与容量|缺VDC/规格/服务/卷/IP仍保留父VM与引用；未知owner/脏容量保留subtotal并令完整量NULL，真实无记录挂载与未知分别处理|

独立17/17场景通过，20个HTTP/schema/载荷子项嵌套；owner92和bootable未运行或计入。发布ZIP4成员与源码/合同哈希已核，原owner9项清单仅做hash核验；本次未读原生记录、未重算原生统计。发布ZIP SHA-256 为 `e27f6aab111e53f73e6a4ca8d7663def5d6800ee2a7455ad7f2098a092379e92`。来源与范围见[SOURCE_PROVENANCE](SOURCE_PROVENANCE.json)及[独立摘要](evidence/INDEPENDENT_RESULTS.summary.json)。

## 公开合成复放

```sh
python3 -B scripts/verify_a_issue3_management_vm_synthetic.py --output /tmp/a-management-vm-check-new
```

从仓库根运行，输出须全新且在仓库外，标准库与内存SQLite即可。复放17项纯合成场景、20嵌套子项；地址使用文档网段，正常长度样例使用合成Example-R。完整性检查限实际交付闭包，不重跑完整owner/原生审计，也不与独立17相加。结果摘要见[PUBLISH_VERIFICATION](evidence/PUBLISH_VERIFICATION.json)。无模型、服务、B运行、原生SQL或官方评分调用，没有原生对象、原题或答案上传。

B仍需新增family registry/card/unified_prepare、可信请求/schema/完整分页和跨CI一致性，实际加载typed `A_MANAGEMENT_VM_DETAILS`投影，不能将SQL直接放到原CI或`_empty`占位表。现场VDC/规格/服务/卷字段缺失未被补造；IP角色/多值codec、容量物理单位、部署关联与更宽服务所有权、实际最终封装/官方深度仍待裁定。

保留guess与真实空/失败的区别，不能据error=None宣称完整答案。实际N变化0；潜在独立注册+1或受审扩族+0需另核，不自动保持132，也不代表满分或原问题全部解决。
