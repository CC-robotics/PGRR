# 八类最小配对试运行：第 5 类结果

2026-09-11 完成“双行人中心线关闭”训练场景的 Base/PGRR 配对。

Base 首次启动时 Nav2 lifecycle 响应超时，必需 topic 未在等待窗口内就绪，因此记录为 `SIMULATOR_FAILURE`、0 样本。日志清理完成后，以 `_retry01` 新 ID 重试并获得有效算法结果；原失败和有效重试均保留。

| 方法 | 用于配对的结果 | 样本数 | 终止时物理目标距离 | 终止细节 |
|---|---|---:|---:|---|
| Base retry01 | COLLISION | 381 | 13.070 m | privileged robot-human overlap |
| PGRR | TIMEOUT | 899 | 14.196 m | configured episode timeout |

Base 的碰撞明确是机器人与动态行人重叠。PGRR 没有发生碰撞，但也没有穿过中心区域并到达目标。因此本单例只能说明“动态碰撞转化为超时”，不能说明导航成功。

PGRR 共记录 41 个决策事件：WAIT 13 次、BACKUP 11 次、CONTINUE 17 次；恢复原目标 5 次，但没有选择 21 个临时子目标中的任何一个。恢复链反复完成和重入，却未形成足够的净目标进展。这与第 4 类一起提示：当前策略在强阻塞下主要依赖等待和后退，可能缺少有方向地绕开或退出冲突区的动作选择。

机器可读结果位于 `outputs/student/eight_family_pilot/pair_results/f04_closing_gap_multi_pedestrian.json`。当前完成 5/8 对；Base 为 3 次 COLLISION、2 次 TIMEOUT，PGRR 为 4 次 TIMEOUT、1 次 PLANNER_FAILURE，双方均无 GOAL_REACHED。由于每类仅一个训练样例，这些计数只用于开发诊断，不是论文性能结论。
