# 74. 三层掩码跨场景复核结果

## 实际完成的工作

在不改模型、触发阈值或安全规则的前提下，新增并运行了四个非冻结 PGRR
诊断回合：斜向切入的 train/validation，以及狭窄走廊对向相遇的
train/validation。validation 场景使用独立 seed，未生成 held-out test。

为了不混淆“诊断失败”和“恢复未触发”，校验器现在分别输出
`runtime_valid` 与 `trace_status`。五个纳入汇总的回合运行链均有效。

## 五个回合的结果

| 场景与 split | outcome | 样本 | 三层轨迹 | 解释 |
|---|---|---:|---:|---|
| 前导行人停止 train | TIMEOUT | 896 | 110 | 完整 |
| 斜向切入 train | TIMEOUT | 893 | 0 | 始终 NORMAL，未触发恢复 |
| 斜向切入 validation | TIMEOUT | 895 | 0 | 始终 NORMAL，未触发恢复 |
| 狭窄走廊 train | PLANNER_FAILURE | 498 | 49 | 完整 |
| 狭窄走廊 validation | TIMEOUT | 896 | 0 | 未触发恢复 |

所有 outcome 都被保留。`Episode PASS` 只表示采集与终止记录链完成，不表示
导航到达目标。

## 触发阳性回合中的分层结果

两个 train 回合共得到 159 次完整决策轨迹：

- 地图/连通性层首次清空：0 次；删除候选实例总数 0。
- 可观测 LiDAR 层首次清空：134 次；删除候选实例总数 3309。
- 路径走廊层首次清空：25 次；删除候选实例总数 30。
- 走完三层后仍保留临时子目标：0 次。

因此，“可观测 LiDAR 是首要候选清空层、路径走廊是次要层”已经在两个不同
train 场景中重复出现，不再只是一个 lead-stop 回合的偶发现象。

## 仍然不能下的结论

两个 validation 回合都没有触发恢复，所以 validation 上没有产生可用于分层
归因的样本。当前不能说该现象已经跨 split 泛化，也不能据此修改 LiDAR 安全
距离或路径走廊阈值。五个回合中没有 GOAL_REACHED，也不能形成性能优势结论。

## 可复现制品

- 聚合报告：`outputs/student/eight_family_pilot/mask_trace_replication_summary.json`
- 聚合脚本：`scripts/student/summarize_mask_trace_replication.py`
- 单回合校验脚本：`scripts/student/validate_mask_trace_smoke.py`
- validation 场景编译入口已支持显式 `--split validation`，但拒绝 test。

## 下一步判断

继续随机增加 validation 回合的收益很低。下一步应先做 trigger coverage 审计：
检查验证场景为什么始终 NORMAL，区分“交互没有真正形成危险”与“触发器漏检”。
在不调阈值的情况下，优先选择或生成一个按现有规则能够触发恢复的 validation
场景，再谈跨 split 的 mask 归因。
