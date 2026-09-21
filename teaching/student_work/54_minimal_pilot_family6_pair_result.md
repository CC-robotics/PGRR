# 八类最小配对试运行：第 6 类结果

2026-09-11 完成“前导行人移动后停止”训练场景的 Base/PGRR 配对。本场景当前实现是行人前进约 6 m 后在终点保持，并非独立事件控制器触发的瞬时急刹。

| 方法 | 结果 | 样本数 | 终止时物理目标距离 | 终止细节 |
|---|---|---:|---:|---|
| Base | COLLISION | 446 | 11.570 m | privileged robot-human overlap |
| PGRR | TIMEOUT | 898 | 11.791 m | configured episode timeout |

Base 明确与动态行人碰撞。PGRR 没有记录碰撞，但最终位置与 Base 碰撞位置相近，仍未越过前导行人的阻塞并到达目标。正确表述是：**该单例中 PGRR 避免了追尾式动态碰撞，但将失败转化为停滞超时。**

PGRR 共记录 28 个决策事件：WAIT 6 次、BACKUP 9 次、CONTINUE 12 次、`SUBGOAL_0` 1 次；恢复原目标 4 次。与第 5 类相比，它确实尝试了一个临时子目标，但没有产生持续的净目标进展。

这提示后续论文分析应把“碰撞规避”和“阻塞后的通行能力”作为两个不同指标，并增加恢复后的净目标进展、恢复占用时间和重复触发次数。当前 pilot 禁止据此现场调阈值；算法改进应在另一个明确的 train/validation 开发阶段进行。

机器可读结果位于 `outputs/student/eight_family_pilot/pair_results/f05_lead_pedestrian_sudden_stop.json`。当前完成 6/8 对；Base 为 4 次 COLLISION、2 次 TIMEOUT，PGRR 为 5 次 TIMEOUT、1 次 PLANNER_FAILURE，双方均无 GOAL_REACHED。该计数仍只是开发诊断。
