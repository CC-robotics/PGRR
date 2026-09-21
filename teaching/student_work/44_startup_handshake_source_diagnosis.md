# 第 7 类启动握手源码诊断

范围：本地源码检查；未重新运行仿真，未改算法、超时或冻结证据。

## 已确认的判定含义

`episode_logger_node.py::_sample` 在收到 odom/lidar 后，以 odometry 时间为基准等待完整的 `_episode_started` 信号。20 秒内信号未到，就写入 INVALID_RESET，detail 为 `NavigateToPose did not activate within the startup deadline`。内部启动脚本明确传入 20 秒（仿真时间）和 90 秒（墙钟时间）两个限值。

该文案比实际条件窄：`_on_status` 会记录导航是否曾经激活，但不会设置 `_episode_started`；后者由 `_on_episode_start` 接收。故此 detail **不能单独证明导航从未激活**。

actor controller 的启动顺序为：

1. 观察到 TaskGenerator reset 和导航 active。
2. 完成机器人复位与里程计稳定检查。
3. 收到新鲜的权威 Gazebo 行人位置。
4. 完成代价地图清理，再确认机器人仍在配置起点。
5. logger ready 后发布 experiment started，释放行人路线。

源码依据：`scenario_actor_controller_node.py` 的 `_update_startup_gate`、`_advance_startup_gate`、`_release_experiment`；`episode_logger_node.py` 的 `_on_status`、`_on_episode_start`、`_sample`。

## 日志恢复访问后的明确检查点

对原第 7 类 runtime log 按时间顺序检查以下消息，不只查看清理时的 ERROR：

- `observed authoritative TaskGenerator reset`
- `navigation activated; waiting for episode logger handshake`
- `startup gate waiting for authoritative Gazebo pedestrian poses`
- `startup gate ready: robot reset confirmed and costmaps cleared`
- `episode handshake complete; released actor routes`
- 复位、odom 稳定、costmap clear 失败及 `startup timeout` 的上下文。

若出现 navigation activated 而没有 handshake complete，则优先定位后续门控；若没有 activation 消息，再结合 action status 日志检查导航启动。缺失消息不自动等于事件没发生，还要核对日志完整性。

原 INVALID_RESET 保留。若需要复跑，使用独立 `_retry01` episode ID，并先检查该 ID 所有输出不存在；不覆盖原文件，也不先修改限值。当前 /tf_static QoS 警告与失败之间没有已证实因果关系。

## 场景机制源码核查

运行控制器读取 `cyclic_goals`，不是凭场景标题或 `once` 推断运动。`ActorRoute.pose_at` 对 cyclic 路线闭合并取模，对非 cyclic 路线到终点后保持位置。因此第 8 类当前循环路线不能称为“精确一次性、按机器人到达触发的横穿”。

上述仅确认期望路线的实现。实际运动还经过更新、避让与 Gazebo 状态确认；碰撞终止和路线插值均不能替代真实轨迹核验。

## 2026-09-08 原始日志核查结果

WSL 日志访问恢复后，已读取保留的第 7 类 runtime/status 日志。启动过程存在以下可重复核查的证据：

- actor controller 成功读取两个确定性行人路线；
- 随后至少四次报告 `Gazebo entity services are not ready`；
- 日志中没有出现 TaskGenerator reset、navigation activated、startup gate ready 或 handshake complete；
- status 日志同时记录 Fast DDS 共享内存端口 `open_and_lock_file failed`，之后在外层清理时退出；
- 初次检查时，WSL 报告 `docker` 命令不可用；随后复跑脚本预检能够找到 CLI，但 `docker version` 仍无法连接 Server。Docker Desktop Engine/该发行版集成尚未恢复到可运行状态。

所以，这一条 INVALID_RESET 应归为**模拟器/中间件启动异常**，而不是 Base 导航失败、第 7 类几何导致的失败或 PGRR 优势证据。`/tf_static` QoS 警告仍不能单独认定为根因。

## 尚未完成

独立 `_retry01` 复跑需要先恢复 Docker Desktop 对 Ubuntu-22.04 的 WSL 集成。为避免无效运行，复跑脚本先检查 Docker client/server，再检查所有目标输出不存在。脚本已通过 `bash -n`，并实际验证会在 Server 不可用时、生成任何实验输出前安全退出。PGRR 功能回合仍待该运行边界恢复。现有结论不构成新实验结果，也不支持八类场景上的方法优越性。
