# 八类最小配对试运行：第 4 类结果

2026-09-11 完成“狭窄走廊迎面相遇”训练场景的 Base/PGRR 配对。开始前 Docker Desktop 和 WSL 后端处于停止状态，预检在创建 episode 前安全退出；启动现有 Docker 后直接复用镜像，没有重新下载，也没有产生残缺算法结果。

| 方法 | 结果 | 样本数 | 终止时物理目标距离 | 终止细节 |
|---|---|---:|---:|---|
| Base | COLLISION | 218 | 16.908 m | privileged robot-human overlap |
| PGRR | PLANNER_FAILURE | 502 | 22.252 m | recovery_sequence_timeout |

Base 的碰撞细节明确是机器人与行人重叠，因此本场景确实检验了动态行人迎面冲突。PGRR 没有记录碰撞，但也没有完成导航；它几乎退回到初始位置附近，最后因恢复序列超时成为规划器失败。因此正确结论是：**该单例中 PGRR 把动态行人碰撞转化为规划失败，并没有解决任务。**

PGRR 共记录 34 个决策事件：WAIT 20 次、BACKUP 9 次、CONTINUE 5 次；没有选临时子目标，也没有恢复原目标。状态在最初十几秒反复经过 `EMERGENCY_STOP`、`RECOVERY` 和 `REJOIN`，随后停留在紧急停止，最终触发 `recovery_sequence_timeout`。

这暴露出两个后续研究问题：

1. 狭窄走廊中只使用 WAIT/BACKUP 是否缺少能够绕行或有方向地退出冲突区的动作；
2. 安全避碰与任务完成必须分开报告，不能把“没有碰撞”自动算作成功。

机器可读结果位于 `outputs/student/eight_family_pilot/pair_results/f03_narrow_corridor_head_on_deadlock.json`。当前只完成 4/8 对，仍属于开发诊断，不能用于总体优越性或统计显著性结论。
