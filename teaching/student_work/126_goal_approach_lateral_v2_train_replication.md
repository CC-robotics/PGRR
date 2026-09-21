# 目标附近侧向干扰 v2：训练内复现

## 本轮完成了什么

在不改变 15 米路线、一次性横穿事件、90 秒时限、PGRR checkpoint 和算法阈值的
前提下，按预声明计划补跑 seed 97101 和 97102。它们与已完成的 seed 97100 一起
组成三组 Base/PGRR 成对实验。

| 重复 | seed | Base | PGRR | PGRR事件链 | 原目标恢复 |
|---:|---:|---|---|---|---|
| r00 | 97100 | COLLISION | GOAL_REACHED | 激活后释放 | 是 |
| r01 | 97101 | COLLISION | GOAL_REACHED | 激活后释放 | 是 |
| r02 | 97102 | COLLISION | GOAL_REACHED | 激活后释放 | 是 |

三个 Base 的碰撞均记录为 `privileged robot-human overlap`。三个 PGRR 均完成事件
释放、恢复/重新加入和原目标恢复后到达；因此预声明的至少 2/3 门槛以 3/3 通过。
本轮没有基础设施失败或重试。r00 首次 Base 的零样本基础设施失败仍与其唯一重试
分别保留，没有被删除或替换。

## 当前边界

这证明该固定设计在三个训练种子上可复现，使其成为“训练内复现候选”。它尚未
经过独立 validation，不能计为第 2 个最终确认场景，也不能写成论文的新结论。
下一步应先冻结独立 validation 的新种子和 2/3 晋级规则，再运行，不能根据结果
继续修改场景。

## 可复查证据

- 计划：`configs/experiments/pgrr_goal_approach_lateral_v2_train_replication_plan.yaml`
- 运行证据：`outputs/student/goal_approach_lateral_v2_replication/runtime/`
- 机器汇总：`outputs/student/goal_approach_lateral_v2_replication/replication_summary.json`
- 人读汇总：`outputs/student/goal_approach_lateral_v2_replication/replication_summary.md`
- 汇总 SHA-256：`32C77F826D3E20C9B4BF40EA2CAA046F85A0657E59DBAD95FE366B3C78BA3E01`

