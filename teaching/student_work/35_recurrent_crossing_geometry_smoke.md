# 第 3 类场景：连续双向交叉行人几何 smoke

日期：2026-09-05  
状态：已完成 JSON 编译、静态检查、预览和一次 Arena Base smoke；未训练，未用于任何效果比较。

## 场景意图

机器人沿货架走廊从左向右行驶。两名行人以相反方向循环横穿走廊，使机器人可能出现反复减速、停走或局部规划方向反复切换。该场景针对的是 PGRR 的 `oscillation` 触发与“避免重复选择无效恢复动作”的能力。

## 本次单例

- family：`recurrent_bidirectional_crossing`；
- split / density / repeat：`train` / `medium` / `r00`；
- seed：`91210`，来自 `91000 + 100 × 2 + 10 × 1 + 0`；
- 两名动态行人：一名由走廊南侧向北侧循环，另一名反向循环；
- 测试集：未生成。

## 产物

- JSON：[recurrent_bidirectional_crossing_medium_train_r00_s91210.json](../../outputs/student/eight_family_geometry_draft/generated/arena/map_empty/recurrent_bidirectional_crossing_medium_train_r00_s91210.json)
- 预览：[recurrent_bidirectional_crossing_medium_train_r00_s91210.png](../../outputs/student/eight_family_geometry_draft/previews/recurrent_bidirectional_crossing_medium_train_r00_s91210.png)
- SHA-256：`71db22252cf8528b2ac908de1c1bbede4bde67bb960f4d24ad00e70b5143608a`

## 验证

`tests/unit/test_compile_recurrent_bidirectional_crossing_smoke.py` 与八类协议审计测试均通过（2 passed）。预览中，机器人路径、货架、两名行人起始位置和终点均处于地图边界内。

## 解释边界

## Arena Base smoke

运行 ID 为 `pgrr_extension_smoke_recurrent_train_r00_base`。Arena 运行器输出：

```text
Episode PASS ... policy=base outcome=TIMEOUT samples=818 monitor_status=143
```

这表示 JSON 已被 Arena 读取并完整地产生终止结果；Base 在 90 秒配置时限内没有到达目标。`PASS` 指运行器合格，`TIMEOUT` 才是 episode 的真实结局。

循环行人的实际动力学表现仍需通过后续轨迹与触发日志进一步确认。本次 smoke 不能声称它已稳定造成振荡，也不能声称 PGRR 优于任何对照。
