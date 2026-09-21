# 八类最小配对试运行：第 3 类结果

2026-09-09 完成“反复双向交叉”训练场景的 Base/PGRR 配对。

Base 原始启动因等待必需 ROS topic 超时，被明确记录为 `SIMULATOR_FAILURE`，样本数为 0。按照预先约定的规则保留原记录，并以新 ID `_retry01` 重试。收集器只把有效重试用于方法配对，但同时保存两个 attempt 的哈希和顺序。

| 方法 | 用于配对的结果 | 样本数 | 终止时物理目标距离 |
|---|---|---:|---:|
| Base retry01 | TIMEOUT | 922 | 1.319 m |
| PGRR | TIMEOUT | 918 | 13.908 m |

两种方法都未在 90 秒内到达目标，因此不存在完成率优势。更重要的是，Base 已接近目标，而 PGRR 仍远离目标，当前单例中 PGRR 的任务进度明显更差。

PGRR 并非没有启动：轨迹中有 56 个决策事件，包括 WAIT 22 次、BACKUP 12 次、CONTINUE 20 次、REPLAN 1 次和 `SUBGOAL_0` 1 次；恢复原目标 4 次。它频繁进入紧急停止、恢复和重新汇入。这支持一个开发诊断：**反复交叉可能造成恢复反复触发，使机器人忙于避让和重入而无法稳定向目标推进。**

这是算法弱点证据，不应删除，也不能在当前 pilot 中据此调整阈值。后续可把“单位时间触发次数、恢复占用时间、净目标进展”加入新研究的验证指标，但任何算法修改都必须在重新定义的 train/validation 实验中完成。

机器可读结果：`outputs/student/eight_family_pilot/pair_results/f02_recurrent_bidirectional_crossing.json`。当前最小 pilot 完成 3/8 对，仍不支持总体优越性结论。
