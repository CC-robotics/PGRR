# 八类 Base/PGRR 最小开发试运行总结

## 完成情况

八个固定训练场景均完成一组 Base/PGRR 配对，共 16 个有效算法 episode。另有 2 个 Base 启动尝试因 ROS topic/lifecycle 未就绪被记录为 `SIMULATOR_FAILURE`，随后使用独立 `_retry01` ID 成功重试；原失败没有被删除或替换。

| 汇总项 | Base | PGRR |
|---|---:|---:|
| GOAL_REACHED | 0 | 0 |
| COLLISION | 6 | 0 |
| TIMEOUT | 2 | 7 |
| PLANNER_FAILURE | 0 | 1 |

Base 的 6 次碰撞中，5 次明确为机器人与动态行人重叠，1 次为静态场景几何碰撞。PGRR 在这 6 个配对中均未记录碰撞，但没有任何一次到达目标。

## PGRR 实际做了什么

PGRR 在 7/8 个场景中进入恢复状态，共记录 235 个决策事件、4 次临时子目标决策和 19 次原目标恢复。它并不是“没有启动”，而是大部分时间使用 WAIT、BACKUP 和重复重入；方向性子目标出现得很少，最终没有恢复完成性。

## 可以诚实得出的结论

这批单例展示了清晰的开发诊断：PGRR 在困难场景中表现得更保守，能把若干碰撞转化为非碰撞终止，但当前场景/策略组合没有证明“恢复并完成任务”。安全和完成性必须分开评价。

不能把 6 对“Base 碰撞、PGRR 未碰撞”写成总体优越性，因为：每类只有一个 train 样例；PGRR 全部未成功到达；没有 Heuristic/Uniform BC 对照；没有独立验证或测试重复；也没有统计检验。

## 当前决策

原协议要求最小 Base/PGRR 配对健康后才进入 Heuristic/Uniform BC 阶段。由于双方 0 次 GOAL_REACHED，健康条件显然未满足，因此暂停比较器运行。现在继续跑另外两个方法只会扩大一个尚未校准的开发实验，不能回答老师要求的“PGRR 能处理、其他方法较差”。

下一步应先做只读的失败模式量化：恢复状态占用比例、重复触发率、恢复前后净目标进展、临时子目标使用率，并据此提出新的 train/validation 改进方案。不能修改冻结 `moderate_v6` 测试、最终 checkpoint 或已发布阈值。

机器可读汇总位于 `outputs/student/eight_family_pilot/minimal_pair_summary.csv` 和 `minimal_pair_summary.md`。
