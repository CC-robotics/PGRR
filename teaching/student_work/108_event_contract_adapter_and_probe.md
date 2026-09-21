# 108 事件契约适配与确定性轨迹探针

## 本步实际执行了什么

将已校验 YAML 中两个 variant 的 train/validation 参数适配为核心事件状态机规格，并用离线探针实际运行四条确定性状态轨迹。探针只模拟事件状态，不启动 ROS、Gazebo 或策略。

## 结果

- 共运行 2 个事件 × 2 个 split = 4 条轨迹；
- 4/4 都严格出现一次 `pre_event_to_active_event`；
- 4/4 都在配置时长后出现一次 `active_event_to_released`；
- 释放后再次离开/进入阈值不会重复触发；
- train 与 validation 的停止时长、触发距离等分离参数被正确读取；
- 静态隔离检查未发现事件核心导入 `ramp_core.observations` 或 `ramp_core.recovery`；
- 适配器、状态机与探针共 12 项测试通过，Ruff 通过。

## 边界

这些是离线确定性状态轨迹，不是机器人仿真结果。它们证明配置能够驱动状态机且不会直接接入策略观察，但尚未证明 ROS actor 会执行命令、转移日志会被 episode logger 保存，或释放后实际路线可通行。

## 下一步

先为 ROS actor controller 设计最小、默认关闭的接线预检：明确所需源码、配置入口、日志字段、reset 清理和失败关闭行为。预检通过前不修改运行时。

## 工件

- `packages/ramp_core/ramp_core/scenario/contract.py`
- `scripts/student/probe_event_control_contract.py`
- `outputs/student/anchor_feasibility/event_controlled_anchor_offline_traces.json`
- `tests/unit/test_event_contract_adapter_and_probe.py`
