# 132 strict＋R5：B提交候选

本版从 main `4abe75e`继续构建，底层A交付为`72e6062`来源闭包。发布包的确切提交、工作树状态和逐文件哈希见`SUBMISSION_MANIFEST.json`；正式v2包在提交完成后重新构建。入口仍为 `implementation/runbook_system.py` 中的 `RunbookQuerySystem`。解压即可使用，不依赖Git历史、原开发目录或本机虚拟环境。

完整源码和开发工具在main；可直接部署的精简运行包及校验文件见[v2发布页](https://github.com/getm0ss1moving/hackathon-p13-2/releases/tag/b132-r5-submission-v2-20261031)。历史报告里的“本地未提交”和旧ZIP哈希描述运行当时的快照，发布状态以此页及Release为准。

包内没有密钥、白盒/黑盒题集、参考答案、原始数据库或训练日志。`experiments/`内文件是运行时必须校验的模板/合同源码及指纹闭包，请整体保留，不能只复制implementation。

## 在评测机安装和检查

```bash
unzip submission.zip
cd submission
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# 完全离线：检查来源、132模板、R5索引、SQLite JSON功能；0模型调用
.venv/bin/python -B scripts/check_submission.py
```

Python至少3.10，推荐3.11。系统需有`ps`和`lsof`，用于既有A合同的本地只读数据来源核验；Linux缺少lsof时由评测机管理员安装。

模型由评测环境通过进程环境提供，沿用原API变量：

```bash
# 使用评测机提供的密钥、端点和指定模型；不要把密钥写进源码。
export DEEPSEEK_API_KEY='评测环境提供的值'
export DEEPSEEK_BASE_URL='https://评测环境提供的兼容端点'
export DEEPSEEK_MODEL='评测环境指定模型'
# 本地开发默认是deepseek-flash；明确环境配置始终优先。
# 数据服务按主办方实例运行于127.0.0.1:8080后，做只读检查，0模型调用：
.venv/bin/python -B scripts/check_submission.py --server
```

若`--server`报原生来源核验失败，说明当前进程看不到原版data_server.py、原数据或本机服务PID，不能将该环境称为已适配；保留错误输出给B。本候选尚未在真实评测机验证，独立API容器/受限进程权限需要另做适配，不能靠关闭来源校验冒充通过。

## 调用入口

评测程序直接导入：

```python
import sys
sys.path.insert(0, 'implementation')
from runbook_system import RunbookQuerySystem
system = RunbookQuerySystem()
output = system.query('评测程序传入的问题')
```

该入口现在会自动加载`configs/whitebox200_a132.env`中的已验收特性，不必依赖开发启动器。外部已设置的环境值优先；不载入本机.env.local。thinking默认关闭、SDK重试0、输出上限1024token；不把开发用的450次进程预算带到评测机截断尾部题目。

单题命令行试跑（会调用真实模型）：

```bash
RUNBOOK_MAX_LLM_CALLS=3 .venv/bin/python -B implementation/runbook_system.py '评测程序传入的问题'
```

主办方若提供原始用例文件，可将其放于包根后使用原只读评测入口：

```bash
.venv/bin/python -B implementation/quick_eval.py 200
# 黑盒须由主办方提供真实文件，本包没有黑盒题集：
.venv/bin/python -B implementation/blackbox_eval.py 100
```

## 验证范围

开发本轮六道失败题011/030/069/086/130/163各5分，18请求0失败；后续CTE候选四道194/252/256/289及控制005/033各5分，13请求0失败，题目阶段HTTP404为0。每批源码分别冻结，不能相加成全200或推算新总分。可选VOLUME_TYPE初始化探测仍有404，已与题目请求分开。

后续补充：OBS空参数/误拒答恢复、GaussDB旧view合同恢复和ECS/VDC默认类型标签。真实小集066/148/150/156/158各5分，15请求0失败；相关离线42项通过。修前066/148/158本次复测也均5分，不能声称已复现原829.2日志的根因。

057地址完整token成员管线已接入为显式候选，`RUNBOOK_ISSUE4_ADDRESS=0`默认关闭。它要求真实逐token contain候选与完整同地域VM上下文，保留未知，且不认证EIP所有权。原参考空结果/状态大小写及所有权语义仍待C/A裁定，不用该候选回填旧分数。地址及共享读取器离线50项通过。

官方四文件保持既有授权指纹，executor未修改；evaluator仅保留用户已授权的三处修订。模板仍132，R5检索未升级r6。本包没有新的完整200成绩，也没有复合问题泛化证明。本轮最大内存/时延并非所有题均满足正式限制，298此前有接近/超过2GiB的记录；上线资源验收须看评测机实测。

## 复制优化及回退

当前本地代码新增`RUNBOOK_JSON_COPY_MODE=fast`，训练计划显式记录该模式，`--json-copy-mode standard`可作对照；直接运行可用环境变量`RUNBOOK_JSON_COPY_MODE=standard`回退。此变体仅在B加载A模块时绑定已锁定的纯复制函数，A文件原始pin、canonical/prepare/recheck流程不改，不是A新发布版本。

冻结收据的新进程单次普通计时：161为13.55→10.62秒，298为42.15→34.54秒，全部结果行和未知状态与保存的完整原生输出一致。此为离线本地计算测量，不是新模型成绩、HTTP端到端时延或评测机达标证明；298离线回放峰值仍超过2GiB。此前GitHub v1包保留，本版v2包含已验证的复制优化。
