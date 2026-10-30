# B：132源码获取与接入准备

> 状态更新（2026-10-31）：以下为源码发布前的历史准备记录。A已在db5ccb9发布132闭合源码，B已重建、接入并完成150＋17＋33覆盖；main又同步至ec1e338。当前结果与修复见[最新B交接](../handoffs/B_A132_PROGRESS_20261031.md)，不再处于缺132源码状态。

2026-10-30。用户要求从GitHub下载最新132并在其基础上优化。目前还没有取得132源码；没有用160改名、删条目或按报告猜造132。

## 已核实的来源

仓库为getm0ss1moving/hackathon-p13-2。已fetch并检查全部3个远端分支：main=fea24c5、simple/official-starter=02fec79、codex/a180-train150=10f2f70；分支树中无132构建链、REVIEW_INTERFACE、unified_prepare或FAMILY_ROUTE_REGISTRY。Releases为0；现有两个PR分别为starter和180，没有132源码附件。当前工作区连同忽略的本地构建输出也未找到132源码。

main上的A_POST170_FALSE_EMPTY_CAUSES明确说明132未正式交付，只发布原因与49轮廓统计，不发布模板、解析器及检索补丁。该说明有源码/数组SHA256，不能代替实际构建输入、26族helper和dispatch合同。

已按用户先前对A协作的授权，在[现有交接Issue补充源码请求](https://github.com/getm0ss1moving/hackathon-p13-2/issues/3#issuecomment-6526859006)，要求固定提交/路径、构建链、26族纯函数、注册/schema/view合同及可复现正反控制。请求正文见[所需源码清单](../handoffs/B_REQUEST_132_SOURCE_20261030.md)。尚未收到该请求的源码回复。

## 不依赖132包的先行修复

A指出F02增加natural_views后，旧选择卡因为只接受scope/profiles/types而整段丢弃已有已审配对说明。已用合成元数据复现：1个测试方法中的3种元数据形状均丢失旧卡片附录。

最小修改仅在F02选择卡容忍natural_views这一新增描述键；已有profiles继续逐项核验scope、资源、输出、筛选及排序。没有读取、渲染或执行未知natural_views内容，没有据此注册新view；F19及其他未知键保持旧拒绝。该修复保留当前已支持能力的选择提示，不等于完整132接入。

先复现的命令：

```sh
/Users/phyll1s0/contest/hackathon/hackathon-p13-2/.venv/bin/python scripts/run_training_checks.py \
  --output-dir reports/b132_source_check_20261030/reproduce_card \
  --test-module test_training_132_selector_compat.SelectorMetadataCompatibilityTests.test_f02_natural_view_metadata_keeps_verified_core_pairs_visible
```

原版本1个方法、3个失败子例、0错误。修复后命令：

```sh
/Users/phyll1s0/contest/hackathon/hackathon-p13-2/.venv/bin/python scripts/run_training_checks.py \
  --output-dir reports/b132_source_check_20261030/card_fix \
  --test-module test_training_132_selector_compat \
  --test-module test_training_selector_cards
```

16项通过、0失败/错误/网络/模型请求。包含旧配对显示、不扩展未审别名、错误核心profile继续不展示、未知顶层键继续拒绝及F19边界。只为当前改动运行相关检查，没有重跑全量题或无关免费套件。

## 待源码到位后的实际工作

1. 保全当前160激活文件，校验固定源码与构建输入，私有展开132，确认实际132唯一模板及26族、strict/enhanced选择。
2. 以当前B发布代码增量接入新的family/view/schema/prepare分派；保留猜空策略、真实失败诊断、预算、原SQL精调和API执行链。
3. 处理A已报告的礼貌包装、有限投影语法、per_view_keys/top_k、完整多义务覆盖；先做声明支持正例和真不支持负例，不删除合同校验来消除未答。
4. 检查F03容量及COUNT边界，保留未决项。冻结可执行源码后，只选择原失败训练题进行小量Flash验收，再按问题范围迭代；不自动跑全部150/50/200。

本轮main保持本地开发，没有创建新分支、切换132或修改官方评估/执行器/数据。160展开文件原字节保留；新增模型及业务服务请求均0，无132真实模型成绩。新修复、测试与本说明尚未提交或推送；上一次已发布提交仍为fea24c5。
