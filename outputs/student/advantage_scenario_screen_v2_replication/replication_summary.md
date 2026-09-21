# Crossing-flow v2 训练内复现汇总

| 重复 | seed | Base | PGRR | Base样本 | PGRR样本 | 正向配对 |
|---:|---:|---|---|---:|---:|---|
| r00 | 95010 | COLLISION | GOAL_REACHED | 271 | 757 | 是 |
| r01 | 95011 | COLLISION | GOAL_REACHED | 408 | 805 | 是 |
| r02 | 95012 | COLLISION | GOAL_REACHED | 264 | 710 | 是 |

预声明门槛：至少2/3正向配对；实际 3/3，训练内复现门槛通过。

r02 的首次PGRR启动在0样本处发生INVALID_RESET；原始证据已保留，同场景、同seed仅重试一次后得到表中有效结果。

这只证明该场景通过train-only复现门槛。独立validation尚未执行，因此不能作为论文中的已验证新场景，也不授权一般优越性结论。
