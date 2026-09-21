# Crossing-flow v2 独立 validation 结果

## 运行前冻结内容

训练内3/3复现完成后，先冻结以下内容再运行validation：

- 独立种子：`96000`、`96001`、`96002`，与train seeds完全不重叠；
- 场景几何：起点`(5,12)`、终点`(20,12)`，路线15 m；
- 最后冲突点后重新加入路段：6 m；
- 90 s时限、同一checkpoint、同一恢复阈值；
- 晋级条件：至少2/3配对为Base未到达且PGRR到达；
- validation结果对本设计具有终局性，不允许根据结果继续调场景；
- 未生成或使用冻结`moderate_v6`测试。

预声明协议位于
`configs/experiments/pgrr_advantage_screen_crossing_v2_validation_plan.yaml`。

## 独立结果

| 重复 | seed | Base | Base样本 | PGRR | PGRR样本 | 正向配对 |
|---:|---:|---|---:|---|---:|---|
| r00 | 96000 | `COLLISION` | 268 | `GOAL_REACHED` | 757 | 是 |
| r01 | 96001 | `COLLISION` | 266 | `GOAL_REACHED` | 820 | 是 |
| r02 | 96002 | `COLLISION` | 280 | `GOAL_REACHED` | 807 | 是 |

实际为3/3正向配对，高于预声明的2/3门槛。三次Base均由
`privileged robot-human overlap`终止；PGRR最终物理目标距离分别为0.262 m、
0.195 m和0.218 m。六次validation运行均一次得到有效结果，没有产生重试artifact。

## 恢复机制核对

- r00：`NORMAL -> RECOVERY -> REJOIN -> NORMAL`，原目标恢复1次；
- r01：两轮`RECOVERY -> REJOIN`，原目标恢复2次；
- r02：包含`EMERGENCY_STOP`和两轮恢复/重新加入，原目标恢复2次。

三条validation轨迹主要选择WAIT、BACKUP和CONTINUE，没有选择21个临时子目标中的
某一个。这仍符合PGRR动作空间和失败触发恢复定义，但论文表述应为“恢复管理器选择
恢复动作并重新加入原任务”，不能声称validation成功依赖临时子目标。

## 当前结论边界

Crossing-flow v2现在是第一个完成train复现和独立validation的新场景：

- train-only复现：3/3正向配对；
- independent validation：3/3正向配对；
- 独立验证通过的新场景：`1/8`。

它可以作为“中等密度连续横穿流中，PGRR相对Base表现出稳定安全/完成优势”的场景级
证据候选。由于validation只有3个配对且这里只验证一个场景机制，不能单独支持跨场景
的一般优越性或统计显著性；最终论文仍需八个不同场景及预先约定的整体汇总方法。

机器可读汇总：
`outputs/student/advantage_scenario_screen_v2_validation/validation_summary.json`。

