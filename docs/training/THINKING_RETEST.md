# 思考模式与超时复测

2026-10-30通过`git ls-remote`确认GitHub main为`d912b48c3119469dbdbae325581696a61dc117fa`。已提交代码支持关闭thinking，但matcher默认、训练CLI默认和`.env.example`均为`provider_default`，没有显式关闭。B此前的低时延实验均传`--thinking-mode disabled`，不能据此说团队默认配置已关闭。本次发布已将三处默认统一为`disabled`；固定150复测以[协议](C_RETEST_PROTOCOL_V18.md)和configs/train150_v18.env为准。

## 使用GitHub当前版本的即时设置

普通查询、官方入口或C诊断入口读取进程环境，启动复测进程前设置：

```sh
export RUNBOOK_THINKING_MODE=disabled
```

如果使用`d912b48`的`scripts/train_live.py`，**必须显式加`--thinking-mode disabled`**。该版本CLI默认会覆盖进程环境，只有export不够。训练预检命令如下，未带`--run`不发模型请求：

```sh
.venv/bin/python scripts/train_live.py --thinking-mode disabled
```

正式运行沿原预算及冻结计划流程。`setup.sh`不会自动加载`.env`；普通查询入口也不会自动读取`.env.local`。不要只编辑配置文件却没有导出变量。当前本地默认修复后，不传mode也显式关闭；若外部环境设置了`provider_default`，普通入口仍尊重该显式设置。训练CLI以其显式参数或默认值为准。

## 已验证范围

新增/更新合成测试覆盖：环境未设置时默认关闭、实际SDK JSON包含`thinking.type=disabled`、训练默认不再把disabled覆盖回provider_default、显式provider_default仍不发送额外字段、冻结模式与请求不一致时停止。测试使用Mock/内存HTTP，不发真实模型请求；没有新时延成绩。

历史同源4题对照（旧评分器，时间字段仍可用于定位）：provider_default P95=9.85秒、3个length截断；disabled P95=3.15秒、0截断。另一次disabled原已过117题回归P95=2.53秒。这是历史特定源码/模型/环境的观测，不能保证同学的所有TLE都由thinking造成。

复测应记录实际请求模式、finish_reason、select/fill/refine模型耗时与execute_seconds。请求显式关闭的证据是计划和请求中的mode/body；reasoning字段缺失不等于观测到0 token。若模式已关闭仍超时，按这些阶段继续定位。官方评分器、时延阈值、执行器没有为此修改；历史实验和已冻结计划不重写。
