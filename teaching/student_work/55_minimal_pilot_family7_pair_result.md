# 八类最小配对试运行：第 7 类结果

2026-09-11 完成“瓶颈横向人流”训练场景的 Base/PGRR 配对。该场景由货架形成狭窄通道，两名行人在通道内循环横穿；当前没有独立控制的人流到达率或汇入相位。

| 方法 | 结果 | 样本数 | 终止时物理目标距离 | 终止细节 |
|---|---|---:|---:|---|
| Base | COLLISION | 420 | 12.438 m | privileged robot-human overlap |
| PGRR | TIMEOUT | 898 | 13.684 m | configured episode timeout |

Base 明确与动态行人碰撞。PGRR 未记录碰撞，但没有通过瓶颈并到达目标，仍是“碰撞转化为超时”，不是导航成功。

PGRR 共记录 38 个决策事件：WAIT 14 次、BACKUP 9 次、CONTINUE 13 次，并各选择 1 次 `SUBGOAL_0` 和 `SUBGOAL_2`；恢复原目标 3 次。相比第 5 类，策略开始使用方向性临时子目标，但两个孤立的子目标决策仍不足以形成稳定通行。

机器可读结果位于 `outputs/student/eight_family_pilot/pair_results/f06_bottleneck_cross_flow_merge.json`。该结果独立于先前第 7 类功能 smoke，不复用旧 episode。
