# 开发脚本

从仓库根目录执行 `python scripts/文件名.py`。这些工具共用根 `implementation/`、`datasets/`、`experiments/` 和 `.env.local`，不复制查询实现或原始数据。

| 用途 | 脚本 |
|---|---|
| 训练预检与运行 | `train_live.py`、`train_prompt_probe.py` |
| 固定训练回放 | `train_replay.py` |
| 训练分析与问题定位 | `analyze_training.py`、`analyze_training_v2_coverage.py`、`analyze_prompt_probe.py`、`audit_training_failures.py`、`probe_training_field_contracts.py` |
| 环境与数据检查 | `check_env.py`、`prepare_data.py` |
| 交接打包 | `build_team_handoff.py` |
| 固定训练集加载 | `training_data.py`，供同目录脚本导入 |
| 历史评估/重建 | `run_whitebox.py`、`replay_sql.py`、`analyze_whitebox.py`、`make_training_split.py`、`resume_training_v2.py` |

日常开发仅使用固定150训练题。历史全白盒与一次性划分/补测工具保留用于原协议复现，不作为默认回归；本次没有重新划分数据或运行留出评估。目录移动后旧计划的源哈希失效，须重新预检，不能绕过原来源检查。
