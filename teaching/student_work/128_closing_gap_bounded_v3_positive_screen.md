# 有限时间多行人收口：v2 诊断与 v3 正向筛选

## 场景设计

本轮把双行人收口改成明确的有限事件：机器人路线为 15 米，冲突区后保留 5 米；
两名行人在机器人接近时同步启动，约 3.11 秒到达最窄位置，事件在 3 秒时释放，
随后两人继续向路线两侧离开。场景没有静态障碍，seed 固定为 98200。

## v2 负结果与诊断

v2 的行人终点只离路线 1.7 米。Base 动态碰撞；PGRR 虽看到两个事件完整释放，
却在释放后反复进入恢复，最终 `TIMEOUT`，距目标仍有 5.72 米。这不是路线太长造成
的假阴性，而是终点行人仍持续干扰局部规划，因此 v2 不晋级。

## v3 唯一机制修正

v3 只把两名行人的最终路线净空从 1.7 米扩大到 3.5 米。以下项目全部不变：seed、
15 米机器人路线、行人起点和速度、触发条件、3 秒活动期、90 秒时限、checkpoint
和算法阈值。

| 方法 | outcome | 样本数 | 物理终点距离 |
|---|---|---:|---:|
| Base | COLLISION | 414 | 5.184 m |
| PGRR | GOAL_REACHED | 892 | 0.183 m |

PGRR 的两个行人事件均完整记录“激活—释放”，恢复状态经历应急停止、等待/后退、
恢复、重新加入和回到正常状态，并记录一次原目标恢复。它在 90 秒合法时限内到达，
但仅余约 0.8 秒裕量，因此后续复现很重要，不能凭这一组直接写入论文。

## 当前判定

v3 通过单种子训练筛选，可进入预声明的三种子训练复现；当前独立确认场景数量仍
为 2/8。不得基于这次结果挑选有利种子、延长时限或调整算法阈值。

## 证据

- 配置：`configs/experiments/pgrr_closing_gap_bounded_v3_train_r00.yaml`
- v2 证据：`outputs/student/closing_gap_bounded_v2_screen/runtime/`
- v3 证据：`outputs/student/closing_gap_bounded_v3_screen/runtime/`
- 汇总：`outputs/student/closing_gap_bounded_v3_screen/screen_summary.json`
- 汇总 SHA-256：`E71CC6185F62A2B1BDD1B5ABA3F020628E754A3A3B26A8CA2D6728F29FCAB87C`

