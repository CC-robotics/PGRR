# 107 事件状态机核心实现

## 本步实际执行了什么

在 `ramp_core.scenario` 中实现了与恢复策略分离的纯 Python 一次性事件状态机。它尚未接入 ROS 或修改现有场景运行，只负责把已冻结的配置语义变成可单测的确定性状态转换。

## 状态与行为

- `pre_event`：先观察触发距离高于“阈值 + 滞回量”，完成武装；
- 距离随后下降到阈值以内时，只触发一次并进入 `active_event`；
- 活跃时长达到配置值后进入 `released`；
- `released` 不会再次触发；
- reset 会清除武装、触发时间和历史时钟；
- 支持机器人—行人距离和机器人—目标距离两种触发量；
- 拒绝负数、非有限输入、非法持续时间和倒退的仿真时间。

要求先“从远到近”完成武装，可避免行人在 reset 时已经处于触发区却被静默当成一次合法事件。

## 验证

8 项测试通过，覆盖完整三阶段转换、一次性释放、两类距离触发、非法初始近距离、reset、时间单调性和配置边界；Ruff 通过。

## 边界与下一步

状态机位于场景控制命名空间，没有接入策略观察，也没有更改任何恢复算法。下一步先增加配置到状态机规格的纯 Python 适配和确定性轨迹探针，再考虑 ROS actor controller 的最小接线。

## 工件

- `packages/ramp_core/ramp_core/scenario/events.py`
- `packages/ramp_core/ramp_core/scenario/__init__.py`
- `tests/unit/test_scenario_event_state_machine.py`
