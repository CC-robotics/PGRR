# 110 默认关闭的 ROS 事件控制接线

## 本步实际执行了什么

在不改变默认运行行为的前提下，将已验证的纯 Python 事件状态机接入 ROS actor controller，并增加独立的事件转移遥测、episode 结果记录和启动器显式开关。事件状态没有进入 recovery manager 或策略观察路径。

## 实现内容

- 新增纯 Python `ScenarioEventController`，严格解析场景内的 `ramp_event_control` 映射；
- actor controller 新增 `enable_event_control=false`，未显式开启时不加载事件映射；
- 开启后只接受非循环 actor 路线、已知 actor 和显式命令；
- 事件只在实际机器人和实际 actor 位姿新鲜时推进，位姿缺失或过期时保持当前路线时钟；
- TaskGenerator reset 和 episode release 都会重置事件状态机；
- 事件激活/释放通过 `/ramp/scenario_events` 发布为有界 JSON；
- episode logger 对日志做 schema 与容量检查，并只写入 outcome 的 `scenario_events` 字段；
- 外层和容器内启动器只接受 `RAMP_ENABLE_EVENT_CONTROL=0/1`，默认值为 0。

## 验证结果

- Ruff：通过；
- Python 编译：通过；
- 事件状态机、运行时适配、ROS 静态接线和既有 baseline profile：`38 passed`；
- 接线前检更新为：前提 `8/8`、运行时接线 `6/6`；
- 两个 Shell 启动器在 WSL 中对规范化 LF 输入执行 `bash -n`：通过。

Windows 工作树中的启动脚本当前为 CRLF，因此直接从 Windows 挂载副本执行 `bash -n` 会在旧函数定义处报 `\r`；只读去除行尾 CR 后语法通过。本步没有改写全文件行尾，避免制造与功能无关的大差异。

## 边界

本步没有生成带 `ramp_event_control` 的可执行场景，没有同步 WSL 运行副本、构建 ROS overlay 或启动 Arena/Gazebo。因此 `6/6` 表示源码接线齐全，不表示真实 actor 行为已经验证。

## 下一步

先生成两个 train-only 事件锚点的可执行 JSON，并做纯 Python schema、配对公平性、非循环路线、终点离开机器人路径以及默认关闭兼容性验证。通过后才同步 WSL、构建 overlay 并运行事件行为冒烟测试。

## 工件

- `packages/ramp_core/ramp_core/scenario/runtime.py`
- `ros_ws/src/ramp_ros/ramp_ros/nodes/scenario_actor_controller_node.py`
- `ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py`
- `scripts/arena/run_baseline_episode.sh`
- `scripts/arena/run_baseline_episode_inner.sh`
- `tests/unit/test_scenario_event_runtime.py`
- `tests/unit/test_event_control_ros_wiring_integration.py`
- `outputs/student/anchor_feasibility/event_control_ros_wiring_preflight.json`
