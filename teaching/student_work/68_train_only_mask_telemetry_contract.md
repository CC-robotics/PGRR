# 68. Train-only 逐层动作掩码遥测契约

更新日期：2026-09-11

## 为什么需要它

现有日志只能看到部分后期规则，无法精确区分地图、LiDAR 和路径走廊分别删除了
哪些临时子目标。近似回放虽然能复现 27/46 次零候选事件，但也有 5 次误删，
不能承担因果归因。因此未来开发运行应直接记录每一层的输入和输出动作 ID。

## 已完成的代码

新增纯 Python `MaskTraceRecorder`，但**尚未接入 ROS 节点**。它具有以下约束：

- 默认 `enabled=False`；关闭时不保存任何 transition；
- 输入、输出掩码必须是固定的 25 维；
- 每个阶段名只能出现一次；
- 默认要求上一层输出与下一层输入完全连续；
- 任何重新放行动作必须通过 `allowed_additions` 明确声明；
- 返回的是输出掩码的副本，不会原地修改算法使用的数组；
- 可以输出结构化字典或紧凑的 `pre/post` reason 片段。

## 建议记录的阶段

未来只在新的 train-only 开发配置中按实际顺序记录：地图/连通性、原始扫描、
路径走廊、特殊动作授权、rejoin、yield、closing-side、near-field、side
commitment、停滞与重复预算、net retreat、recurrent escape 和最终安全回退。

正式接入前必须满足两个回归条件：

1. 诊断关闭时，决策 action、mask、reason 和既有日志逐项不变；
2. 诊断开启时，action 和最终 mask 不变，只增加新的可解析遥测。

## 对论文的作用

如果后续新 train/validation 运行采集了逐层信息，论文可以报告“候选动作在何层
被排除”的描述性统计，并明确区分安全约束导致的合法收缩与策略在可选动作中的
偏好。当前冻结结果和现有八类 pilot 没有这些字段，不能回填或虚构。

## 下一步

不依赖 ROS 的接入前等价性夹具已经完成：四种合成输入在记录器关闭和开启时，
每层 mask 与最终动作均一致，详见 `69_mask_trace_equivalence_gate.md`。默认关闭的
三层 ROS 接入及 221 项离线回归也已经完成，详见
`70_minimal_ros_mask_trace_integration.md`。下一步是仅在非冻结 train-only smoke
中显式开启一次，验证真实日志字段；不能用于回填旧结果。

产物：

- `packages/ramp_core/ramp_core/recovery/mask_trace.py`
- `tests/unit/test_mask_trace.py`
