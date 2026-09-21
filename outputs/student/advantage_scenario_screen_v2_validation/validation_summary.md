# Crossing-flow v2 独立 validation 汇总

| 重复 | seed | Base | PGRR | Base样本 | PGRR样本 | 正向配对 |
|---:|---:|---|---|---:|---:|---|
| r00 | 96000 | COLLISION | GOAL_REACHED | 268 | 757 | 是 |
| r01 | 96001 | COLLISION | GOAL_REACHED | 266 | 820 | 是 |
| r02 | 96002 | COLLISION | GOAL_REACHED | 280 | 807 | 是 |

预声明门槛为至少2/3正向配对；实际为 3/3。

validation期间产生的重试artifact数量：0。

该结果确认一个新场景通过独立validation，但不构成PGRR在任意场景中普遍优于Base的结论，也不替代完整统计评估。
