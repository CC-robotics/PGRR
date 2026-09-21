# Lead-stop validation TIMEOUT 只读诊断

## 问题

材料 83 证明了 validation 回合确实进入 selector，但真实结果仍是 TIMEOUT。
本步不改算法，只回答：“机器人卡在什么过程里，现有证据能支持到什么程度？”

## 可复现结果

脚本 `scripts/student/diagnose_validation_timeout.py` 对原始 JSONL 和 outcome
做哈希绑定，并得到：

- 第一次离开 NORMAL：41.925 秒，进入 EMERGENCY_STOP；
- 第一次触发前朝原目标前进：9.886 米；
- 触发后机器人实际又走了 5.931 米，但朝原目标只净前进 0.430 米；
- 共有 4 个有界恢复周期，4 个周期结束时都没有比周期开始更接近原目标；
- 四周期合计原目标进度为 -1.512 米，即周期内部总体在倒退；
- 191 个 selector 行中，172 行启用了 directional-yield，并把最终动作集合约束为
  WAIT/BACKUP；对应实际动作是 BACKUP 141 次、WAIT 31 次；
- 另外 19 行未启用该约束，全部选择 REPLAN；
- 15 行在 path-corridor 后仍有临时子目标，这些临时子目标没有被下游删除，但
  15 行最终仍全部选择 REPLAN；
- 191 行中临时子目标实际被选择的次数为 0。

机器可读报告位于
`outputs/student/eight_family_pilot/leadstop_validation_timeout_diagnosis.json`；
两项专用单元测试、证据台账测试和 Ruff 均通过。

## 通俗解释

机器人前半程本来走得比较正常。遇到行人后，恢复管理器不是没有工作，而是
多次在“停一下、后退、重新规划、短暂回到主任务”之间循环。它在后半程走了
不少路，但这些运动大多没有转化为朝终点的净前进，最后耗尽 90 秒。

这还揭示了两个需要分开验证的候选机制：

1. 大多数决策中，可观测的 directional-yield 规则只留下 WAIT/BACKUP；
2. 少数仍有临时子目标可选的决策中，策略仍选了 REPLAN，而没有执行临时子目标。

## 结论边界

可以说：TIMEOUT 与“恢复周期无净进度”和“最终动作集中在 WAIT/BACKUP/REPLAN”
同时出现，下一步值得做受控、非冻结的机制区分。

不能说：directional-yield、BACKUP、REPLAN、动作 mask 或模型中的任何一个已经被
证明是 TIMEOUT 的原因。这里只有一个 validation 回合，没有受控消融；因此不改
阈值，也不把这组数据写成正式性能结论。

## 对后续作业的价值

- 作业二：把“状态周期、原目标进度、最终可选动作、实际动作”定义成纯 Python
  诊断接口，便于后续模块化和回归测试。
- 作业三/论文：增加一条诚实的负面结果链路——恢复被触发且诊断完整，但没有
  转化为完成任务；证据台账已自动加入允许表述与禁止推论。
