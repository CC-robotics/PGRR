# 八类最小配对试运行：第 8 类结果

2026-09-11 完成“目标附近横穿”训练场景的 Base/PGRR 配对。当前场景是一名行人在目标附近持续循环横穿，不是带遮挡、事件触发的一次性突然出现。

| 方法 | 结果 | 样本数 | 终止时物理目标距离 | 终止细节 |
|---|---|---:|---:|---|
| Base | COLLISION | 777 | 3.630 m | privileged robot-human overlap |
| PGRR | TIMEOUT | 898 | 4.610 m | configured episode timeout |

Base 在接近目标阶段与动态行人碰撞。PGRR 没有碰撞，但也失去了完成机会并超时。PGRR 只记录 10 个决策：WAIT 4 次、BACKUP 5 次、CONTINUE 1 次；没有临时子目标，也没有原目标恢复事件。

正确解释是：PGRR 在目标附近采取了保守避让，但没有重新获得通往目标的稳定进展。该单例再次说明终点附近不能只检查碰撞，还必须检查“避让后是否真正完成”。

机器可读结果位于 `outputs/student/eight_family_pilot/pair_results/f07_goal_approach_lateral_interruption.json`。
