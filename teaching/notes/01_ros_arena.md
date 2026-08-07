# 第 1 讲：ROS2、Arena 与可复现运行

## 两个环境为什么分开

Arena/ROS2 运行时依赖系统安装的 ROS2 Humble、Gazebo 插件、消息类型和工作空间
overlay。离线数据处理依赖 PyTorch、pandas、HDF5 和统计包。把 apt 安装的 ROS
Python 包塞进 Conda 容易产生 Python ABI、`PYTHONPATH` 和动态库冲突。因此：

- 在线：退出 Conda，source ROS 和 Arena overlay；
- 离线：只激活 `ramp-offline`，不 source ROS；
- 交换：HDF5、Parquet、JSON、YAML、ONNX/TorchScript。

出现 `ROS_DISTRO was set to ... before` 时先停下来检查环境，而不是继续叠加 source。

## ROS2 导航数据流

PGRR 观察 `/scan`、里程计、TF、全局路径、规划器状态和 base planner 命令。Goal mux
保存原始 PointGoal，在恢复期间发送临时子目标，然后恢复原目标。所有节点使用
`use_sim_time`，所以窗口长度必须按消息时间戳计算，不能用墙钟时间。

关键检查：

```bash
ros2 topic echo /clock --once
ros2 topic hz /scan
ros2 topic echo /odom --once
ros2 run tf2_ros tf2_echo map base_link
```

具体 topic 和 frame 由配置或 remap 决定；上面只是典型名字。

## 一次 episode 的生命周期

1. 仿真 reset，并验证起点/目标有效；
2. 固定 seed 生成行人初态；
3. 发送原始目标并记录每步 telemetry；
4. 失败检测器更新，状态机可能进入 RECOVERY；
5. 终止时写入明确 outcome；
6. 清理节点和仿真进程，检查持续崩溃。

合法终止包括 `GOAL_REACHED`、`COLLISION`、`TIMEOUT`、`PLANNER_FAILURE`、
`SIMULATOR_FAILURE`、`INVALID_RESET`。后两类可以从算法指标排除，但数量不能隐藏。

## 第一次 demo

先执行 `make preflight` 和 `make smoke`，再选择一个静态场景运行 Base planner。
保存命令、commit、profile、scenario、seed 和退出码。截图只能辅助说明，JSONL 日志才是
数值证据。

## 常见错误

- TF 可见但时间不一致：检查 `use_sim_time` 和 `/clock`；
- LiDAR 无数据：检查 namespace、QoS 和实际 topic；
- 目标发送成功但不动：检查 planner action 状态和底盘命令；
- reset 后沿用旧历史：每 episode 调用 detector/state-machine reset；
- 从 RViz 手动拖目标：不满足自动复现要求。

## 口头解释提纲

解释“为什么在线和离线环境必须隔离”“消息时间为何影响失败窗口”“模拟器失败为何
不能计成算法失败”。
