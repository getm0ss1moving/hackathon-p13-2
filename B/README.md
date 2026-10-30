# B已合并到仓库根目录

A/B/C现在使用同一套根目录代码，请从[根README](../README.md)进入。

- 查询实现：`../implementation/`，不再保留B源码副本。
- 训练脚本：仓库根的`train_live.py`、`train_replay.py`、`train_prompt_probe.py`。
- 测试：`../tests/`；C报告工具仍在`../C/`。
- 固定训练集：`../datasets/whitebox_150_50_v1/`。
- 训练文档：[TRAINING.md](../docs/training/TRAINING.md)；历史来源和实验记录迁到`../experiments/`，历史字节和哈希不改写。

本机此目录可能残留Git忽略的旧虚拟环境、原数据副本、封存50题和历史报告；它们未删除或上传，也不再用作运行时代码来源。封存文件仍不允许用于开发。迁移前的完整已提交B项目可从Git提交`51f0aad`恢复；本次前未提交成果已额外保存到仓库外本机备份。
