# r4 独立检索门禁通过

结论：两版均PASS_INDEPENDENT_FROZEN_RETRIEVAL_SCOPE。先用r4对应原132v1数组重放已发布1148，再运行独立方首次执行前冻结的18条有限边界对照；没有用owner的552条作为独立证明，没有修改任何预期/候选/其他实现。

## 结果与冻结版本

每版1166条、4种top-k共4664比较。默认None：1016/1016支持目标family和来源profile召回，误空0；161/161复合逐句目标、公开profile与原文字符span完整；150/150不支持请求在公开、来源profile、义务证据三个入口均空，失败0。

原1148的1006支持/159复合/142负例全过。新18为10支持（含未引用名称里的成本/性能/动作词、单命令否定、同view双实体）和8明确含肯定变更的负例，全部通过；限定声明的语法合同，不外推任意未标示实体/省略/未知语法完备性。新18 SHA a8ac6379c4dd92a273b5e48d2614abdc321832a6b98ca6d1bdeab7686999941d。

普通603×四top-k对同132原引擎的公开/source向量各2412/2412相同。132唯一活动owner、200来源profile、054/087别名、400主文档/统计、42命名view184正控制都保持。strict11/enhanced22属性卡另测44/88比较全相同且目标召回。2/3/4句完整和5句预算弃权控制均过。完整义务结论只用于None，k=1/5可以依合同截断。

- 接口SHA e3211cec60bf5cb73a879a55c7384430914f08d51a26a0527a9904f69f6e8e1f。
- strict模块99d15b6995aa8a731354b02811c3613fc4c92c4a9c1d3a900f8ae393d7814802；原132数组4d790887d487f3f371d8597b517a7e2b2bda1898c591b0e8123b11b79637aac5。
- enhanced模块dbaf4381493907a8f3b19d14344700884f8b9c1d9703f573c4385b216d4fcedc；原132数组3806aaa7248861c826263d2779dde3f4209e2238e3c7e33227b3e13bca468f9e。

组合SHA、补丁、精确预期和无源漂移见REVIEW_RECEIPT.json/INPUTS.json/frozen；该收据不是SQL/业务或整包验收。

## 最小运行闭包及体积

minimal-runtime/strict和enhanced各只有两份运行必需文件：runbook_retriever.py＋templates132.json。代码仅stdlib，报告/映射/补丁/B formatter不是检索运行依赖；打包后重新核对hash，并分别做132、普通名称、原漏复合、肯定变更空四项smoke全过。调用RunbookRetriever(items).retrieve / retrieve_profiles / retrieve_obligations，B仍须消费profile_ids与obligation_spans以保留同family多view/多实体。两种引擎和元数据不能混配。

同1148条相对独立r3、同formatter：0条canonical/列表/可选证据增长，列表平均-1.527 UTF-8字节。observed source最多15、canonical最多14。实际模型token未测。893唯一问法交错两轮，本机strict P95 3.64ms/max4.60ms、enhanced P95 3.73ms/max4.66ms，仅检索调用；索引初始化单样本见收据，不是官方硬件认证。

## F03 compact 只读差分单独通过

r4-compact-readonly-diff/SUMMARY.json绑定compact接口SHA ff0c4508212930d60a7317864192d46bf4deadc28700e1fda6bfd7a00becaef0。每版只有family_f03_spec变化，字段为examples/parameter_contract/examples_from；全部检索view/attributes、原生API/SQL/资源及各命名view合同不变。使用相同r4模块构造索引后，递归比较全部实例状态（含属性子索引、native能力字段）完全相同，因此这是检索状态等价证据，不是另一次compact整包/B执行回归。

compact数组strict a3f6a0d3ea12be6555025e37e4a0189f259a2da6766124160f90b94fcce88ef3；enhanced897798c3ee26bfc6fba2b625b6e7e820146ac49db7d2fb299b68a5d15701466b。全132最大紧凑UTF-8单item字节3751/3986；ASCII转义紧凑口径4435/4612，不同序列化不能混称同一4KB结论。官方序列化与深度仍未认证，B需要prompt_metadata适配。本次最小闭包保持原132数组，没有悄悄换成compact。

## 原200及整包提交边界

本轮未重跑实际200。历史真实200代码+数组直接对照仍在r2-full-independent-v1/direct-actual200，来源与完整SHA在本收据中保留。其603×4为2368/2412相同、44全部11属性通道×4差异；本轮同132原引擎2412全等传递保持这一精确差异，不称本轮新200直接执行，也不称200题端到端测过。

可以把本固定检索闭包交集成者进入B最终联调/整包冻结。没有擅自写共享main或push；后续提交由唯一集成者按既有用户授权处理。B选择/抽参/精调/SQL/原生执行、多义务字段消费、COUNT空占位、失败/缺列/分页、F03提示适配仍待对应owner。官方CPU环境、索引限制、2GB峰值、所有模板4KB/深度、端到端时限未全部验证，不能把本通过写成整包可提交或官方总分达标。没有模型/服务/SDK/200题/封存50操作。
