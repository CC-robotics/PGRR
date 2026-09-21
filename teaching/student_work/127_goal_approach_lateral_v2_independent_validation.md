# 目标附近侧向干扰 v2：独立 validation

## 结果

训练复现通过后，先冻结新种子 98100、98101、98102 和至少 2/3 的晋级门槛，
再生成明确标注为 `validation` 的场景并运行 Base/PGRR 成对比较。

| 重复 | seed | Base | PGRR | PGRR事件链 | 原目标恢复 |
|---:|---:|---|---|---|---|
| r00 | 98100 | COLLISION | GOAL_REACHED | 激活后释放 | 是 |
| r01 | 98101 | COLLISION | GOAL_REACHED | 激活后释放 | 是 |
| r02 | 98102 | COLLISION | GOAL_REACHED | 激活后释放 | 是 |

结果为 3/3 合格配对，超过预声明的 2/3 门槛。三个 Base 均记录为动态人机
重叠碰撞；三个 PGRR 均有完整的一次性事件链、恢复过程和原目标恢复记录。
六次有效仿真都没有基础设施重试。

首次批运行在完成 r00 后，因为后续 `ROS_DOMAIN_ID=233` 超出启动器允许的
0--232 范围而在 r01 仿真启动前被拒绝；该错误没有生成 outcome。修正为合法
domain 后从 r01 续跑，没有重跑或覆盖 r00，也没有改变任何实验参数。

## 结论边界

该固定机制现在完成三组训练配对和三组独立 validation 配对，可计为四场景优化
计划中的第 2 个独立确认场景。它提供“目标接近阶段一次性侧向横穿”这一机制的
场景级证据，但三组配对本身不授权一般优越性或统计显著性结论，也没有使用冻结
的 `moderate_v6` 测试集。

## 证据

- 预注册计划：`configs/experiments/pgrr_goal_approach_lateral_v2_validation_plan.yaml`
- 运行证据：`outputs/student/goal_approach_lateral_v2_validation/runtime/`
- 机器汇总：`outputs/student/goal_approach_lateral_v2_validation/validation_summary.json`
- 人读汇总：`outputs/student/goal_approach_lateral_v2_validation/validation_summary.md`
- 汇总 SHA-256：`4B8C5A5EB31F63996DDAB248A55893C3D59034B21F7522C253372C20613AD400`

