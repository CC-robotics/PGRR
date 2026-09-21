# 作业二：决策协调器的最小拆分边界（只读设计）

日期：2026-08-28  
状态：设计材料；**未修改运行代码、参数、模型或任何最终证据**。

## 1. 为什么这里值得拆

`ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py` 中的
`_select_decision(...)`（约第 1331 行）同时承担了两种职责：

1. 根据观测、故障分数和动作掩码，协调专家策略或 BC 策略；
2. 保存 ROS 节点内的运行状态，例如连续等待次数、退让次数、让行锁存、日志。

第一项是较容易测试的“决策规则”；第二项与真实 ROS 生命周期和命令执行紧密相连。
因此，不能把整个函数直接搬走。合理的第一步是只提炼**不发布 ROS 消息、不读写 ROS 回调对象**的规则协调层。

## 2. 建议提取的纯决策边界

候选模块名：`ramp_core.recovery.decision_coordinator`。

它的输入应是已经准备好的普通数据：

- `RecoveryObservation`、`Pose2D`、`FailurePrediction`；
- 初始动作掩码（由规划、地图和 LiDAR 过滤后得到）；
- 明确的 `DecisionMemory`：连续 WAIT/BACKUP/REPLAN 计数、进度参考、让行锁存、侧向承诺、退让保护器状态；
- 已配置好的数值阈值和策略选择器。

输出应是：

- `CoreRecoveryDecision`；
- 更新后的 `DecisionMemory`；
- 仅供记录的约束遥测文字或结构化字段。

在此边界内可逐步整理的逻辑包括：

- `constrain_rejoin_actions`、重复 WAIT/BACKUP/REPLAN 限制；
- 退让距离上限、停滞子目标限制与安全 WAIT 回退；
- BC 让行时的方向约束、临近障碍半径、侧向承诺与 recurrent escape；
- 调用 `policy.select_action(observation, mask)`，并让所有限制在调用前完成。

## 3. 必须暂时留在 ROS 节点中的内容

以下内容不要随第一次重构移动：

- `_action_mask(...)`（约第 992 行）：它直接读取节点持有的地图、激光和 planner adapter；
- `_expert_decision(...)`（约第 1059 行）：它使用仅训练/标注可用的特权行人状态；
- `_execute(...)`（约第 1620 行）及动作完成判断：它会设置目标、控制命令和原始目标恢复；
- 订阅回调、参数读取、发布器、`get_logger()`、时钟和 Nav2 adapter。

这条边界可防止“为了让代码好看”而意外改变安全掩码、临时目标执行或回归原始目标的语义。

## 4. 关键不变量（重构前后必须完全一致）

1. 动作 ID 和顺序不变：21 个临时目标 + `WAIT`、`BACKUP`、`REPLAN`、`CONTINUE`，总数 25。
2. 每次选策略前，掩码都经 `ensure_safe_wait_fallback(...)` 处理；空掩码只能回落到 WAIT，绝不能重新放开平移动作。
3. 模型输入输出契约不变：观测堆叠形状 `(5, 180)`，当前掩码 `(53,)`，动作数 25。
4. 学习策略只读取部署可观测量；特权行人状态只能由 expert 路径使用。
5. `BACKUP`、子目标、`REPLAN` 的已有上限和“进度后才重置计数”的规则保持不变。
6. `_execute` 仍由节点负责，临时恢复结束后仍恢复原始任务目标。

## 5. 建议的最小回归测试顺序

先不改主节点，先在纯 Python 层构造固定输入。每一组输入应比较“现有逻辑”和“抽出的协调器”的：

| 场景 | 要断言的结果 |
|---|---|
| 正常 BC 恢复 | 相同的最终可行动作 ID 集、同一策略选择结果 |
| 高碰撞风险 | 回归动作受限，WAIT 始终可用 |
| 连续 WAIT 达预算 | 不再错误允许重复 WAIT；若无安全逃离动作，保持 WAIT 回退 |
| 连续 BACKUP/REPLAN 达预算 | 预算限制与原逻辑一致 |
| 单侧接近人流 | 方向掩码和侧向承诺的结果一致 |
| recurrent escape | 只在已有合法横向/重规划逃离动作时收紧掩码 |
| expert 路径 | 缺失特权信息时仍安全返回 WAIT |

完成这些合成测试、并复跑现有
`tests/unit/test_action_mask.py`、`test_state_machine.py`、`test_recovery_options.py`
和 `tests/ramp_ml` 后，才适合请教授确认是否实施第一次代码迁移。

## 6. 当前结论

目前的节点不是“功能重复”，而是把安全规则、运行记忆和 ROS 执行混在同一处。建议的模块化目标是让**规则可单测**，不是改变 PGRR 的动作、阈值、数据集或冻结测试。正式实施前应由教授确认模块边界与优先级。
