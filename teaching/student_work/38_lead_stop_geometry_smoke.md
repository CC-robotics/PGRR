# 第 6 类场景：前方行人移动后停住几何 smoke

状态：已完成训练集单例 JSON、静态检查、预览和一次 Arena Base smoke。

## 场景机制与近似边界

行人起始于机器人前方 10 m 处，同向移动至走廊中段 x=16 m 后在终点停止。它用于观察 Base 是否在跟随对象停止后冻结、超时或发生不安全绕行。

当前 Arena 场景 schema 以 waypoint 为主，因此这里的“突然停住”被实现为**一次性路线到达终点后停住**，而不是精确的外部事件时钟。Arena smoke 需要检查实际停止时刻；在确认前不能声称它模拟了特定时延的急停。

## 单例

- scenario：`lead_pedestrian_sudden_stop_low_train_r00_s91500`；
- split / seed：`train` / `91500`；
- JSON：[场景文件](../../outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_train_r00_s91500.json)；
- 预览：[顶视图](../../outputs/student/eight_family_geometry_draft/previews/lead_pedestrian_sudden_stop_low_train_r00_s91500.png)；
- SHA-256：`f78abe2a9bcb6428cd8528234dfefd07dd05cd4a51d635b69c9dc8d4b43e837a`。

第 3–6 类编译器与八类协议审计共 5 项单元测试通过。没有训练、没有 held-out test、没有 PGRR 效果结论。

## Arena Base smoke

运行 ID：`pgrr_extension_smoke_leadstop_train_r00_base`。Arena 输出：

```text
Episode PASS ... policy=base outcome=COLLISION samples=419 monitor_status=143
```

这条记录表明该近似场景在 Arena 中可执行，且 Base 最终碰撞。它不确认精确的“急停时刻”，也不能代替 PGRR 与对照模型的成对比较。
