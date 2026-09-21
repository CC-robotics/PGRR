# 作业二：PGRR 模块地图与首个重构范围

日期：2026-08-27  
状态：代码结构审计完成；尚未修改参考算法源码。

## 1. 当前结构的真实分层

```text
configs/ YAML
    │ 参数、场景、模型路径、动作与失败规则
    ▼
ROS 节点层（ros_ws/src/ramp_ros）
    │ 接收 LiDAR / odom / path / map / failure，发布临时目标与恢复决策
    ▼
核心决策层（packages/ramp_core）
    ├─ failure/          可观测失败规则
    ├─ state_machine.py  恢复状态机
    ├─ action_space.py   固定 25 个恢复动作
    ├─ action_mask.py    几何、LiDAR、路径等可执行性约束
    ├─ recovery/         启发式策略、恢复选项与安全约束
    └─ planning/         A*、短时 rollout、特权规划专家
    ▼
学习层（packages/ramp_ml）
    ├─ datasets.py       HDF5 → 训练样本
    ├─ recovery_policy.py 网络结构与掩码 logits
    ├─ losses.py         BC 损失
    ├─ bc.py             训练指标
    └─ inference.py      ONNX 在线推理
```

## 2. 代码规模审计

| 文件/模块 | 行数 | 当前职责 | 判断 |
|---|---:|---|---|
| `action_space.py` | 78 | 25 个动作的固定编号与坐标转换 | 小且稳定，不应先改 |
| `action_mask.py` | 205 | 地图/LiDAR/路径约束 | 边界清晰，可作为独立单测对象 |
| `state_machine.py` | 333 | NORMAL、RECOVERY、REJOIN 等状态转换 | 核心行为，先不改 |
| `recovery/options.py` | 1367 | 有界后退、等待预算、侧向承诺等恢复约束 | 规则多，适合后续分文件，但风险较高 |
| `ramp_ml/datasets.py` | 97 | HDF5 特征构造 | 接口清楚，应保持 schema 不变 |
| `ramp_ml/inference.py` | 146 | ONNX 输入编码与动作选择 | 接口清楚，应保持输入 `(5,180)`、`(53,)`、`(25,)` 不变 |
| `recovery_manager_node.py` | 2004 | ROS 输入、观测、掩码、决策、执行、发布与遥测 | 第一优先级的结构问题 |

`recovery_manager_node.py` 约有 40 多个私有方法。它不是“代码写错”，而是一个总控节点承担了过多职责，造成阅读、测试和后续新增场景时的维护成本较高。

## 3. 推荐的首个重构：只拆边界，不改变算法

建议从 `recovery_manager_node.py` 中抽取两个**纯 Python 协调对象**，ROS 节点保留订阅、发布和参数读取：

```text
RecoveryManagerNode（保留 ROS）
    ├─ 接收 ROS 消息、保存最新传感器状态
    ├─ 调用 RecoveryObservationBuilder
    ├─ 调用 RecoveryDecisionCoordinator
    └─ 发布 RecoveryDecision / 临时目标

RecoveryObservationBuilder（新模块）
    ├─ 组合 LiDAR 历史、目标、路径、速度、规划器状态
    └─ 产出固定的 RecoveryObservation

RecoveryDecisionCoordinator（新模块）
    ├─ 计算动作 mask
    ├─ 叠加恢复预算与安全约束
    ├─ 调用 heuristic / expert / ONNX policy
    └─ 输出 CoreRecoveryDecision 与可解释遥测
```

这样做的目的不是改变 PGRR 的决定，而是把“ROS 通信”和“可单元测试的决策逻辑”分开。

## 4. 不可改变的兼容性契约

首个重构必须保持下列内容完全不变：

- 25 个动作的编号、顺序、半径、角度和特殊动作语义；
- LiDAR `(5,180)`、状态 `(53,)`、动作 mask `(25,)` 的 ONNX 输入接口；
- ROS topic、frame、参数名、`use_sim_time` 行为；
- YAML 配置键和默认值；
- 随机种子、HDF5 schema、checkpoint 路径；
- 已冻结的 `outputs/moderate/final/` 及其任何结果。

## 5. 推荐的实施顺序（待教授确认后执行）

1. 在独立学生分支创建最小重构提交，不在 `main` 上直接改。
2. 记录重构前测试：动作 mask、状态机、恢复选项、`recovery_manager_ros_smoke`。
3. 先抽取 `RecoveryObservationBuilder`，保持输入输出逐字段一致，并新增单元测试。
4. 再抽取 `RecoveryDecisionCoordinator`，先使用原方法的同一逻辑，不改阈值与顺序。
5. 重新运行离线测试、Arena recovery manager smoke，并比较同一输入下的动作 ID、临时目标和 reason。
6. 只有结果一致时，才把这次重构视为作业二的第一阶段完成。

## 6. 需要教授确认的决策

1. 上述“观测构造 + 决策协调 + ROS 适配”是否是认可的重构边界？
2. 是否优先抽取观测构造，还是优先将 `recovery/options.py` 拆为 `budget/side_commitment/stall_guard` 等文件？
3. 重构验收是否以“同一输入输出完全一致 + 测试通过”为标准，还是允许同时做小幅算法改动？
4. 未来新场景的配置是否应独立于现有 `scenario_catalog_moderate_v6.yaml`，例如创建 `configs/experiments/student_extension_*.yaml`？
