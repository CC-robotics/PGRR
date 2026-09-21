# 69. 掩码遥测接入前等价性门槛

更新日期：2026-09-11

## 已执行的检查

将 `MaskTraceRecorder` 接到纯 Python 三层合成回放夹具中，分别在记录器关闭和
开启时运行以下四种输入：开放环境、地图局部封闭、全方向近距离 LiDAR、窄路径
走廊。

每种输入均逐项比较：

- 地图层后保留的临时子目标；
- 扫描层后保留的临时子目标；
- 走廊层后保留的临时子目标；
- 最终确定性选择的动作 ID。

## 结果

四种输入在记录器关闭和开启时，每层结果及最终动作均完全一致。关闭时记录
0 个 transition；开启时每种输入记录 3 个连续 transition。由此验证纯记录器
在当前合成边界内没有改变掩码或选择结果。

这只是接入前门槛，不等于 ROS 节点等价性已经成立。ROS 中还有特殊动作授权、
yield、closing-side、停滞预算和安全回退等更多阶段，需要在最小接入补丁后继续
做关闭/开启 A/B 测试。

## 下一步

默认关闭的最小 ROS 接入补丁及 221 项离线回归已经完成，见
`70_minimal_ros_mask_trace_integration.md`。下一步只在非冻结 train-only smoke
中显式开启一次，检查真实 ROS 决策日志是否完整包含三层记录；仍不运行正式训练
或最终评测。

证据：

- `tests/unit/test_replay_upstream_mask_layers.py`
- `outputs/student/eight_family_pilot/upstream_mask_layer_replay.json`
