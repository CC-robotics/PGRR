# 第 3 讲：可观测失败检测

## 信息边界

正式检测器只使用 LiDAR 时序、机器人速度、目标进展、规划器命令和状态。仿真器中的
行人 ID、真实速度和未来轨迹只能生成训练标签或 Oracle 上界，不能进入测试观测。

## Freeze

默认条件为：目标距离大于 1 m，完整 3 s 窗口内位移小于 0.15 m，并且至少一半
窗口中规划器请求线性运动，或报告 `NO_VALID_CONTROL/ABORTED`。已经到达目标必须
抑制 freeze。只看瞬时速度会把正常短暂停车误判为失败。

Assignment 3 中窗口必须覆盖配置时长的至少 95%，与参考 detector 的 `_covers`
语义一致。进度、位移和 command fraction 是三个不同量，不能混用。

## Oscillation

在 4 s 窗口中，对角速度应用 deadband 后统计符号改变；变化次数至少 6 且目标进展
少于 0.2 m 时触发。单次正常转向只有一次符号变化，不应触发。接近零的噪声必须先
移除，否则会产生大量假翻转。

## Collision risk 与 Deadlock

碰撞风险结合制动距离、前向/宽扇区 LiDAR、TTC 和闭合趋势，并带短时 latch；这部分
在学生 starter 中保留。deadlock 需要完整窗口、近障碍、低位移、低进展和低速，也
保留为对照。四类分数最终组成 `FailurePrediction`。

安全停止距离：

```text
d_stop = v^2 / (2 a_brake) + v * latency + margin
```

它是工程安全过滤，不构成形式化无碰撞证明。

## 测试设计

- 正常直行不触发；
- 到达目标后静止不触发 freeze/deadlock；
- 2.5 s 短停不满足 3 s 窗口；
- sustained abort 可作为 motion request 证据；
- deadband 内抖动不计数；
- 交替大角速度且无进展触发 oscillation；
- 时间戳倒退必须报错或 reset，不能悄悄混窗。

运行：

```bash
pytest tests/unit/test_failure_rules.py tests/unit/test_failure_labels.py -q
```

作图时在同一时间轴显示目标距离、位移、角速度、阈值和触发时刻，避免只给一个最终
标签而无法审计。
