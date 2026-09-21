# 65. 上游三层动作掩码合成回放

更新日期：2026-09-11

## 做了什么

使用 `ramp_core` 中与运行时相同的三个纯 Python 函数，构造四个确定性输入，
逐层记录 21 个临时子目标还剩多少。整个过程不启动 ROS/Arena、不载入模型，
也不修改任何阈值。

| 合成输入 | 地图层后 | LiDAR 层后 | 路径走廊层后 | 说明 |
|---|---:|---:|---:|---|
| 开放对照 | 21 | 21 | 21 | 三层均不误删开放空间候选。 |
| 地图局部封闭 | 0 | 0 | 0 | 地图终点/线段/连通性足以删掉全部临时子目标。 |
| 全方向近距离 LiDAR 返回 | 21 | 0 | 0 | 地图允许，但 LiDAR 安全检查删掉全部临时子目标。 |
| 0.20 m 窄路径走廊 | 21 | 21 | 3 | 地图和扫描允许，走廊只保留沿路径的三种半径。 |

## 说明了什么

这个夹具证明三层是可以被独立检查的，也证明地图层和 LiDAR 层各自都能在
合理的极端合成条件下把 21 个临时子目标全部删除。路径走廊层会显著压缩方向
多样性，但在机器人位于直线路径中心的本夹具中仍保留 3 个正前方子目标。

它还不能说明八类真实场景中的 46 次事件具体由哪层造成，因为真实 episode
日志尚未保存每层掩码，也不一定包含完整的地图/路径快照。不能把合成结果写成
“PGRR 真实失败原因已经证明”。

## 下一步

字段审计已经完成：60 个学习决策均有 180 维重采样 LiDAR、位姿和全局路径，
可以进行带边界说明的近似扫描/走廊回放；地图快照、原始 LaserScan 几何和
任务走廊专用路径未保存，不能进行精确三层回放。详见
`66_real_log_replay_field_audit.md`。

产物：

- `scripts/student/replay_upstream_mask_layers.py`
- `outputs/student/eight_family_pilot/upstream_mask_layer_replay.json`
- `outputs/student/eight_family_pilot/upstream_mask_layer_replay.csv`
- `tests/unit/test_replay_upstream_mask_layers.py`
