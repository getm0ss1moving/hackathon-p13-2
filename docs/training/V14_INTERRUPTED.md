# v14完整训练尝试中断

本轮计划为固定150题连续一次，deepseek-flash，thinking=disabled，最多450次请求/1024输出token/SDK重试0，不含封存50。

运行中另一个用户授权的目录整理任务把根开发脚本迁至scripts/，旧冻结source路径消失，发送/返回后的来源检查触发FileNotFoundError，程序停止。完成15/150，原计时分69、满质量14；这些只能描述已完成前缀，不是150成绩，也不与后续补测相加。请求事件33，SDK响应身份无不符；最后一个响应在源码检查失败后未提取usage，token总量不完整。旧450上限已关闭，剩余417不复用，未自动重试。

证据为experiments/train150_v14_full_plan.json、live.jsonl及budget.json（相同前缀）；原计划/记录不重写成新路径。四官方文件仍与d79c316一致：implementation/quick_eval.py、blackbox_eval.py、evaluator.py、runbook_executor.py。当前核验命令为`.venv/bin/python scripts/check_official_integrity.py`。开发训练入口现为`.venv/bin/python scripts/train_live.py`。目录稳定后须重新冻结、重新独立运行完整150，不直接续接旧记录冒充连续单轮。

本轮新增代码及官方入口恢复均未由本聊天暂存、提交或推送。700目标仍未达到。

随后发现A的2707ff9（等价模板去重与检索别名）及5d56726已进入共享main，再由d912b48整理目录。固定模板库从200收为198，模板/检索源码哈希变化；v15新预检在只读门禁停止，模型请求0次。不能只改哈希放行，须验证A差异并重新做训练回放与来源接入。四个官方测试文件仍与原件一致。本聊天未做Git写操作；他人的已授权提交不回滚。
