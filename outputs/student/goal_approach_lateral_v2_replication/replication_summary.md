# 目标附近侧向干扰 v2 训练内复现汇总

| 重复 | seed | Base | PGRR | 事件链 | 原目标恢复 | 合格配对 |
|---:|---:|---|---|---|---|---|
| r00 | 97100 | COLLISION | GOAL_REACHED | 完整 | 是 | 是 |
| r01 | 97101 | COLLISION | GOAL_REACHED | 完整 | 是 | 是 |
| r02 | 97102 | COLLISION | GOAL_REACHED | 完整 | 是 | 是 |

预声明门槛为至少 2/3 合格配对；实际为 3/3，训练内复现门槛通过。

这里只完成训练场景复现。尚未执行独立 validation，不能据此写成论文中的新场景结论。
