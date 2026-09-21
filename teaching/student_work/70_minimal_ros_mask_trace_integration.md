# 70. 三层掩码遥测的最小 ROS 接入

更新日期：2026-09-12

## 本次实际改动

已把 `MaskTraceRecorder` 接入 `recovery_manager_node.py` 的真实
`_action_mask()` 调用链，记录顺序固定为：

1. `map_connectivity`：地图与连通性检查；
2. `observable_scan`：当前可观测 LiDAR 扫描检查；
3. `path_corridor`：任务路径走廊检查。

新增 ROS 参数 `enable_upstream_mask_trace`，默认值为 `false`。Arena 单回合启动链
也新增经过 `0/1` 校验的环境变量 `RAMP_ENABLE_UPSTREAM_MASK_TRACE`，默认值为 `0`。
默认关闭时记录器
不产生 transition，决策原因字符串原样返回；显式开启时，只把三层的 `pre/post`
动作 ID 附加到 `RecoveryDecision.reason`，动作 ID、置信度和最终 mask 不被修改。

三层记录在 REPLAN、WAIT、CONTINUE 的最终可用性处理之前结束，避免把特殊动作的
授权混入“21 个临时子目标为何消失”的诊断问题。

## 已执行验证

- Python 语法编译通过；
- 相关 Ruff 检查通过；
- 扩大回归共 `222 passed`；
- 两个 Arena Bash 启动脚本经 LF 规范化后的 `bash -n` 检查通过；
- `git diff --check` 通过，仅有既有 Windows 换行符提示；
- 四个生产核心合成夹具继续满足 trace 开/关时逐层 mask 与最终动作一致。

新增静态接入测试还检查：参数确实默认关闭、三个记录阶段顺序正确、关闭时原因
保持不变、开启时复用原动作 ID 与置信度。

## 结论边界

这是源代码接入和离线回归通过，不是一次新的 Arena 运行。尚未验证 ROS 消息中的
原因字符串长度、真实消息时序或八类 train-only 场景的逐层输出。因此不能说完整的
ROS 运行时等价性已经证明，更不能把该遥测追溯应用到冻结的 600-episode 证据。

## 下一步

下一项安全工作是在一个非冻结 train-only smoke 中把
`RAMP_ENABLE_UPSTREAM_MASK_TRACE=1`，运行单个已有场景，确认决策日志确实出现三个
阶段且动作执行链正常。启动参数入口已经打通；运行仍须使用新的 episode ID，且不
改变任何掩码阈值。

证据文件：

- `ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py`
- `packages/ramp_core/ramp_core/recovery/mask_trace.py`
- `tests/unit/test_recovery_manager_mask_trace_integration.py`
- `tests/unit/test_replay_upstream_mask_layers.py`
- `scripts/arena/run_baseline_episode.sh`
- `scripts/arena/run_baseline_episode_inner.sh`
