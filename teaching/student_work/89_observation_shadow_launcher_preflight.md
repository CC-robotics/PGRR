# 89. Observation shadow 启动器与运行前门禁

## 本步完成了什么

本步把作业二的 observation shadow 从“ROS 节点中已有默认关闭参数”推进到“标准 Arena 启动器可以显式开启，但仍不改变控制结果”。

- `scripts/arena/run_baseline_episode.sh` 读取 `RAMP_ENABLE_OBSERVATION_SHADOW`，默认值为 `0`，并且只接受 `0/1`。
- `scripts/arena/run_baseline_episode_inner.sh` 把 `0/1` 转换为 ROS 参数需要的 `false/true`，再传给恢复管理器。
- 新增 `scripts/student/preflight_observation_shadow_smoke.py`，在真实运行前拒绝冻结路径、test split 和重复 episode ID。
- 预检还会静态确认：ROS 参数默认关闭，标准启动器确实转发开关，旧 observation 仍是唯一权威返回值。

## 实际验证

- 21 个相关单元测试通过。
- Ruff 检查通过。
- 两个 Bash 启动脚本均通过 `bash -n` 语法检查。
- `git diff --check` 无补丁格式错误；仅出现 Windows 的 LF/CRLF 提示。
- 已为非冻结 train 场景生成机器可读预检：
  `outputs/student/refactor_baseline/observation_shadow_smoke_preflight.json`。

预检对象是 `lead_pedestrian_sudden_stop_low_train_r00_s91500`，使用新的 episode ID `pgrr_observation_shadow_leadstop_train_r00_20260913`。结果为 `ready=true`、`diagnostic_only=true`、`authoritative_path_changed=false`。

## 结论边界

本步没有运行 Arena，也没有产生策略效果或运行时等价性结论。它只证明一次非冻结诊断 smoke 的启动链路和安全门禁已准备好。冻结 `moderate_v6`、`outputs/moderate/final`、最终 checkpoint 和算法阈值均未改动。

## 下一步

将本步涉及的最小文件同步到 WSL 运行镜像，构建 overlay，然后只运行一次已经预检的非冻结 train smoke。运行后应把 shadow 汇总和 episode outcome 一起保存，并验证即使候选 observation 不一致，控制路径仍由旧 observation 决定。
