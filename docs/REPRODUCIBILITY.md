# 复现索引与材料保留说明

本索引记录 `simple/official-starter` 的材料快照 `04d9ed48f3285a663a3dde2ce77420df38ed771e`，包括相对 `aecdc09` 的四个重放提交及随后交付提交。现有项目团队获准在当前私有仓库保留这些实验输入、历史结果和脚本以便复现；不删除或回退这些材料。之前待批准的清理提案已被此保留决定取代，不应应用。

本次只增加索引，不重跑模型或服务、不改写原始结果。原网络/TLS/权限提示的确切原因仍未确认；保留材料不会解除其他联网、模型或发布的安全暂停。本次获准的索引文档发布单独进行，不使用证书校验绕过。

## 版本、评分和验证范围

|记录|实际源码/模型|已完成|不能据此声称|
|---|---|---|---|
|旧 20 题模型记录|源码 `d534a08709738f3cf83ccda78ae0a05727adac84`；记录的请求配置为 `deepseek-chat`，53 次响应的模型名均为 `deepseek-flash`；TLS 校验为真|20 题、53 次 HTTP 尝试，原评分合计 **75.5/100**，总 token 51,505|不是最新 A、不是 200 题、不是正式总分；请求名与响应名不同不得隐去，未完整记录的模型参数不能自行补全|
|文档词频缓存独立验收|基线 `3b99aaf524062a36b4dd052167aa33fd18d29a70`，父版本 `1a720071beceb25b33ba19781b8c776af8e77fcd`，缓存版本 `1928514a1f2c722286ecb98463ad6425b4100dc7`；无模型|1,075 输入 × 6 个 top_k，共 6,450 次一致性比较；另 2,016 次边界比较；各版 3,225 次本机 retrieve 计时|不是检索正确性全覆盖、模型端到端分数、未见泛化或正式硬件达标|
|历史隔离 199 合并候选|历史记录的本地 HEAD `5755b93435270a01d0df96c9faf777da60217a40`；生产仍为 200；候选文件及输入由脚本 LOCKS 校验|1,075 条离线比较；原生固定参数替换对照；负区域控制单列|没有真实选择器配对分数。历史候选还合并过展示文本，与后来“仅删 rb_087”的候选不同，不能混用生成法或哈希|
|同步后集成回执|记录 HEAD `01f48f5479e0666a237810be144a62fa64d624ac`，同步基线 `aecdc09`|保存的 20 题输出经原评分器重算；保护文件、语法、CLI 和报告写入的限定检查；新增模型请求为 0|重算历史输出不等于同步后源码重新答题|
|另存本地：旧 A 双遍|`d154d77275142544d2ae96391455f77dcac583e6`，Flash、非思考，200 模板|200 题 × 2，553.9 / 557.9，逐题两遍平均后合计 **555.9/1000**；开发 490.95/900，留出 64.95/100|这不是旧 20 题结果；原模型日志评分均值不等于真实黑盒或官方总分|
|另存本地：后续 A 首遍|`4949f6d41e8f62259d06236365b92be20798ba6a`，Flash、非思考，200 模板|200 题首遍 **548.7/1000**|第二遍未完成，不能与 555.9 混成同版双遍，不能把之后修复版本归入此分数|

最后两行来自现有本地评分汇总，不属于本次 `04d9ed4` 材料包；本次没有另上传它们的逐题日志。另有不完整批次也不能补入分母。所有分数均需保留版本、模型、计时和 SDK/官网口径边界；无真实 BB 结果，不能计算真实官方总分或宣称黑盒提升。

这 1,075 条输入及白盒 200 题此前已被检查过，固定 180/20 分组也不能重新称为真正未见黑盒。它们可用于复现与已见数据诊断；不能在运行时按题号、完整问题或实体匹配保存答案，不能将这些结果作为在线缓存替代真实执行。

## 保留文件与完整性

下表为 `04d9ed4` 中相对可信基线变化的全部十二个文件。本次只核对字节与已发布 commit 一致，不改内容。根 README/TEAM 属历史说明，遇到过时“只在本地”等表述，以本索引的材料保留决定与精确版本范围为准。

|相对路径|SHA-256|
|---|---|
|[README.md](../README.md)|`6413c8ef62150211fe08c9243f8deb2682d13b4c3f1cc2bf621332bf7ac12723`|
|[TEAM.md](TEAM.md)|`6a3d7348f01079cc6d2aa19d052dfaf7e7c74f52ba022a95a86949d4df18ad7f`|
|[experiments/a_cache_acceptance_20261029/queries.json](../experiments/a_cache_acceptance_20261029/queries.json)|`37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0`|
|[experiments/a_cache_acceptance_20261029/result.json](../experiments/a_cache_acceptance_20261029/result.json)|`71f310538ca2e6e105b13dcc39b05258e30c94b47b1822a29cac0d21a34c990c`|
|[experiments/a_cache_acceptance_20261029/verify.py](../experiments/a_cache_acceptance_20261029/verify.py)|`e04af37f75eafe6365a0464c25eb3db78cb512869128bf23696b1a1eec408746`|
|[experiments/a_merge_086_check_20261029.json](../experiments/a_merge_086_check_20261029.json)|`536d7e3ad5ca8a5278946cb090ab64ebf8a6e4a45883b4e41b57e77c44abd272`|
|[experiments/a_merge_086_check_20261029.jsonl](../experiments/a_merge_086_check_20261029.jsonl)|`30cffe6870afbf36eb088030d2cae1bffcc7a1afa2c049e73e122ccd47b5509a`|
|[experiments/a_merge_086_check_20261029.py](../experiments/a_merge_086_check_20261029.py)|`6cba053eb587e4375ffceb61a73b9e6b440819b8e08a71853371ef17799e8eb1`|
|[experiments/a_merge_086_negative_region_20261029.json](../experiments/a_merge_086_negative_region_20261029.json)|`b3f9f61a58517826c8e80497f903024975b99312e3c6df5860f0bfd50ff84dce`|
|[experiments/integration_20261030/README.md](../experiments/integration_20261030/README.md)|`0604ebfd689ef9d5b3ca35b1b46de52fb0762874462113e5219a5e206b5ad5d3`|
|[experiments/integration_20261030/receipt.json](../experiments/integration_20261030/receipt.json)|`caf6e5451a74aa6dc645be9364eb3b16ce23faeabbc752de2c35aaaa95ac182e`|
|[experiments/integration_20261030/verify_delivery.py](../experiments/integration_20261030/verify_delivery.py)|`55c35267cf40a30edae8328e94402f95efc52274622a8be9bce54d8e95517ea4`|

其他既有参考材料包括 [旧模型原记录](../experiments/round3/model20.json)、[旧模型汇总](../experiments/round3/model20_summary.json)、[该轮冻结清单](../experiments/round3/manifest.json)、[分组](../experiments/round3/groups.json) 和 [既有复现说明](../experiments/round3/README.md)。这些参考文件没有被本次重新写入。

缓存输入 SHA 为 `37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0`。缓存结果中记录的原脚本 SHA 为 `a1581595531f9a5bf34285fe56a9d5d8eedd1b453ec9a9cce735341dedffb95b`；当前交付脚本 SHA 为 `e04af37f75eafe6365a0464c25eb3db78cb512869128bf23696b1a1eec408746`，后来只为归档输入与安全退出调整过路径/保护，不能称脚本逐字未变。

旧 20 题原记录 SHA 为 `e9f76a1f47ccff0ea8bfb61abcb572f98770c7c3f46e433742b6b8437fddf92e`；汇总为 `dda9b84ff03dbb9849167598ca950676ddddc7c9bb80b7a71e932f98eb0e92ee`。记录的 implementation 文件 SHA 已逐项对照其源码 commit，不用当前模型配置替换历史配置。

236 份受保护文件与官方原始 `d79c316` 相同；按相对路径到 SHA-256 的键排序紧凑 UTF-8 JSON，清单哈希为 `28993ff1f813e7a1b20c274ee9e07bca09d9c6f84a07bb8114fd09da2962ebb2`。评分器、执行器、服务及数据均不由本次修改。

## 如何核对与复现

先使用已有 Python 3.11 环境及项目已装依赖，不需要安装新库；缓存验证只用标准库和 Git，原生执行依赖见现有 requirements 与服务说明。以下只读命令核对留存材料，不调用模型或服务：

```sh
# 在仓库根目录执行；快照固定，不受随后分支更新影响。
git log --oneline aecdc09..04d9ed48f3285a663a3dde2ce77420df38ed771e
python3 - <<'PY'
from pathlib import Path
import hashlib
paths = [
    'experiments/a_cache_acceptance_20261029/queries.json',
    'experiments/a_cache_acceptance_20261029/result.json',
    'experiments/a_merge_086_check_20261029.json',
    'experiments/a_merge_086_check_20261029.jsonl',
    'experiments/a_merge_086_negative_region_20261029.json',
    'experiments/integration_20261030/receipt.json',
]
for name in paths:
    print(hashlib.sha256(Path(name).read_bytes()).hexdigest(), name)
PY
```

### 缓存比较：未来离线复测命令，本次未运行

当前生产模板经过后续修复，直接运行历史 `verify.py` 会在源码前置检查退出 2，且不会写新结果。这是保护历史版本的行为。可在私有临时 worktree 放置历史业务版本及已归档的验证输入，再写新输出；不要修改主工作区或覆盖 result.json：

```sh
# 在原仓库根目录；使用既有虚拟环境，不联网、不安装。
REPO_DIR="$PWD"
REPO_PYTHON="$REPO_DIR/.venv/bin/python"
PRIVATE_REPLAY_DIR="$(mktemp -d)"
git worktree add --detach "$PRIVATE_REPLAY_DIR/cache" 1928514a1f2c722286ecb98463ad6425b4100dc7
mkdir -p "$PRIVATE_REPLAY_DIR/cache/experiments/a_cache_acceptance_20261029"
for file in verify.py queries.json; do
    git show "04d9ed48:experiments/a_cache_acceptance_20261029/$file" > "$PRIVATE_REPLAY_DIR/cache/experiments/a_cache_acceptance_20261029/$file"
done
(
    cd "$PRIVATE_REPLAY_DIR/cache"
    "$REPO_PYTHON" experiments/a_cache_acceptance_20261029/verify.py --output "$PRIVATE_REPLAY_DIR/cache-rerun.json"
)
```

原始 result.json 保留，不以新时延覆盖旧值。新报告的脚本 SHA、环境和计时必须重新记录；预热、操作系统调度和硬件都会使数值不同。现有候选输出全等不代表得分提升。

### 199 候选：有额外私有依赖，尚非异机一键复现

`experiments/a_merge_086_check_20261029.py` 的 `LOCKS` 规定五个输入。当前本机 `.a-vocab-gt4hyfg2/` 中逐个文件存在且哈希匹配，但除 queries 的归档副本外，不能据此宣称其余输入已经发布到远端：

|私有目录内文件|脚本锁定 SHA-256|
|---|---|
|`queries.json`|`37bf913bfe3c25ed8950634792a16549a780aca8f1f71026aa5b5cad06f440a0`|
|`candidate_merge_086_items.json`|`7aa441b426f3d5e1ae3160cb347285b70be4240337231fc662d12ce73f2a55a8`|
|`strict_capability_raw.jsonl`|`69ef2a4ad0431af01e542a37b68b7c3b03f685f7aa08332c832981fc23d5c6d6`|
|`strict_capability_result.json`|`4bf890f58b7e1a0f8b774b40d58b14616d81b446f461c1e6fe02416075b47bce`|
|`merge_086.json`|`40f533958e35938331b80b1fff8022d1e5ffab02c5e81080da318bb350c821c3`|

原入口命令为 `python experiments/a_merge_086_check_20261029.py`。它不调用模型，但会访问原本地服务；只有安全暂停解除、历史源码及五项输入完整、输出 `.json/.jsonl` 均为新路径时才可复测。当前目录已有历史结果，脚本会拒绝覆盖；当前生产源码也不同，不能直接使用它并宣称复现成功。移机时须由材料持有人在私有环境补齐上述输入，不能用聚合结果反向伪造。

负区域 JSON 是后续追加控制记录，其 core-run、prefix 与完整 JSONL 哈希含义不同；应按 JSON 内 `raw_hash_scope_note` 检查，不能把追加后的完整文件 SHA 当作原核心段 SHA。它没有独立发布的命令行 runner；其中保存的源码当作历史材料阅读，不自动执行。没有在本次重跑此前 1,075 条或原生请求。

### 集成与历史评分：重放不是新答题

`python experiments/integration_20261030/verify_delivery.py` 是当时的离线入口。它会拒绝覆盖现有 receipt.json，且根目录依赖原本机路径；换机器不能原样一键运行。后续适配应另存新脚本、新回执并明确差异，保留原件。它默认阻止网络，导入未改评分器对历史输出重算，没有执行新模型。

`experiments/round3/run_model_baseline.py` 是历史收费采集器，不是当前获准重跑的入口：原采集器包含对 system/评分函数的运行时记录包装；即使只用于记录，也不应在固定模块不得运行时替换的当前约束下重新使用。保留它供追溯，不把它当作新的合规成绩依据。需要新模型测试时，应另行固定实现、次数、预算和原生评估链，不运行旧脚本消耗费用或覆盖证据。

`python experiments/round3/reproduce_offline.py` 会先核对原冻结清单；共享源码已改变时应退出 2，不覆盖原结果。它通过后仍可能启动本地服务，所以“零模型”不等于“零网络”；当前安全暂停下不执行。完整源码/输入/结果哈希是判断同一次实验的依据，文件存在或脚本退出不能代替业务验收。

## 本次核验与使用边界

- 已核验：仓库仍为私有，远端分支与 `04d9ed4` 相同；十二个材料本地字节与该 commit 一致；相关五个提交的 21 个唯一文本 blob（含旧 20 题参考材料）作限定凭据检查，未命中本机已配置秘密或所选密钥/令牌/私钥模式。未导出任何秘密值；这不是未知或编码秘密的完全排除证明。
- 已核验：本机私有依赖的存在和锁定哈希、保存的模型请求/响应模型名及评分版本；236 保护文件未变。
- 未运行：任何新的模型、原生服务、完整白盒/黑盒、时延比较、工作流 CI 或上述复测命令；不把静态核验冒充业务 PASS。
- 原始材料只供团队离线开发和复现，不进入运行时按题查答案；最终赛题提交包按官方要求另定，不因保留授权就将整个 experiments 或秘密配置打包提交。
- 不保存或提交密钥、令牌、认证头、账户余额或新增凭据。作者/committer 字段不证明实际 pusher 身份，也不据此给既有操作作恶意定性。
