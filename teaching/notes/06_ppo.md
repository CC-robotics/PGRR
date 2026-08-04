# 第 6 讲：Action-Masked PPO 与失败降级

## 为什么不从随机策略开始

恢复动作会影响真实闭环安全。随机 PPO 容易在早期反复 WAIT、BACKUP 或选择危险方向。
PGRR 的可选 PPO 从 DAgger actor 初始化，并在早期加入逐步衰减的 BC 正则。

## 高层 RecoveryEnv

一次 step 选择一个恢复动作并执行约 0.5 s，然后读取新观测、action mask、分解 reward
和终止原因。终止包括退出恢复、碰撞、恢复超时、到达原目标或不可恢复。训练环境必须
区分 `terminated` 与时间限制 `truncated`。

## Reward 分解

典型项包括目标进展、退出失败、到达目标、安全距离、个人空间、平滑性、动作切换、
重接路径和超时。每一项单独记录，才能发现：

- 一直 WAIT 获得低碰撞但全部 timeout；
- 连续 BACKUP 增加局部 clearance 却远离目标；
- 高频切换利用短时 reward；
- 触发/终止 bug 让策略提前获得 escape reward。

Action mask 是环境约束；被 mask 的动作不应进入采样分布。安全 supervisor 的紧急停止
优先级高于策略。

## 诚实的降级路径

PPO smoke 仅证明代码能运行，不能支持“RL 提升性能”。只有多 seed 的足量训练和固定
closed-loop validation 改善才可把 PPO 写入主贡献。若 PPO 退化，主模型应保持 DAgger，
把 PPO 作为负面消融或未来工作。

## 本周练习

不要求大训练。读取一次 smoke log，画出各 reward 项、WAIT 比例、恢复时长和终止类型。
提出一个 reward-hacking 假设，并说明需要什么对照实验验证。若运行：

```bash
make train-ppo-smoke SEED=0
```

报告必须注明训练步数、seed、初始化 checkpoint 和“smoke 不作为论文结论”。
