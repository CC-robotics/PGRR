# 作业二：RecoveryObservationBuilder 的可抽取边界

范围：对 `ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py` 的只读审计；未修改节点代码。

## 推荐抽取的纯计算职责

当前 `_observation()`（约第 778 行）将以下输入组合为 `RecoveryObservation`：

| 输入类别 | 当前来源 | 可抽取后应作为 Builder 输入 |
|---|---|---|
| 机器人姿态/速度 | `_world_pose()`、最新 odom/twist | `Pose2D`、`Velocity2D` |
| 目标与路径 | `_goal`、`_path` | 原始目标、任务路径 |
| LiDAR 历史 | `_lidar_stack` | 最近 5 帧标准化扫描 |
| 进度/转角历史 | `_distance_history`、`_angular_history` | 最近 10 个历史值 |
| 失败状态 | `_effective_failure()` | `FailurePrediction` |

建议新对象只负责：

```text
build(pose, velocity, goal, task_path, lidar_history,
      distance_history, angular_history, failure) -> RecoveryObservation
```

它内部可以继续调用已有的 `navigation_path_or_goal()` 和 `select_local_path_waypoints()`，但不得改变补齐规则：LiDAR 仍为最近 5 帧，两个历史序列仍为最近 10 个值。

## 不应随 Builder 一起抽取的内容

| 留在 ROS 节点 | 原因 |
|---|---|
| `_on_odom`、`_on_scan`、`_on_path` 等 subscriber callback | 直接处理 ROS 消息与时间戳 |
| `_subscribe`、参数声明、publisher | 属于 ROS 适配层 |
| `_goal_preempted` 和任务路径缓存的写入时机 | 与临时目标/原目标恢复的 ROS 生命周期耦合 |
| `_action_mask`、`_select_decision`、`_execute` | 分别是决策约束、策略选择和动作执行，应留给下一阶段协调器 |

## 抽取后必须新增的等价测试

1. 用固定 pose、goal、path、scan 历史与 failure 构造旧节点的观测；
2. 用相同输入调用新 Builder；
3. 逐字段比较：`lidar`、`goal_polar`、`path_waypoints`、`robot_velocity`、`failure`、`progress_history`、`angular_velocity_history`；
4. 重点验证空路径回退至 goal、LiDAR 不足 5 帧时的复制补齐、历史不足 10 项时的零/首值补齐行为；
5. 确认输出仍满足学习侧既有形状契约：LiDAR `(5,180)`、状态编码 `(53,)`。

## 为什么先拆它

观测构造是“ROS 输入”到“核心恢复逻辑”的边界。先把它变成可单测的纯 Python 对象，可以降低后续新增场景、离线回放和 DAgger 数据诊断的成本，同时不触碰动作阈值、状态机或最终模型选择。

