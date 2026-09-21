# 第 4 类场景：狭窄走廊对向相遇几何 smoke

状态：已完成训练集单例的 JSON 编译、静态可达性检查、顶视预览和一次 Arena Base smoke。

## 意图

两排货架形成 1.60 m 宽的单车道式走廊。机器人向右行驶，一名行人从右侧沿同一中心线向左行驶。静态地图中起终点保持连通；困难只在两者动态相遇时出现，适合观察 Base 是否 freeze/deadlock，以及 PGRR 是否能安全等待、后退或重新规划。

## 单例与边界

- scenario：`narrow_corridor_head_on_deadlock_low_train_r00_s91300`；
- split：`train`，seed：`91300`；
- JSON：[场景文件](../../outputs/student/eight_family_geometry_draft/generated/arena/map_empty/narrow_corridor_head_on_deadlock_low_train_r00_s91300.json)；
- 预览：[顶视图](../../outputs/student/eight_family_geometry_draft/previews/narrow_corridor_head_on_deadlock_low_train_r00_s91300.png)；
- SHA-256：`e1ce2d7db543b3c72c39324f7f8528949a82fa0392d9b6e9e1cb0923c17277b9`；
- 该 JSON 仅用于 smoke，不生成 held-out test，不包含模型结果。

## 验证

第 3 / 第 4 类编译器与八类协议审计共 3 项单元测试通过。预览显示静态 A* 路径连通，货架没有直接阻断机器人；动态对向行人使该类成为真正的交互挑战，而不是不可达地图。

## Arena Base smoke

运行 ID：`pgrr_extension_smoke_headon_train_r00_base`。Arena 运行器输出：

```text
Episode PASS ... policy=base outcome=COLLISION samples=199 monitor_status=143
```

`PASS` 表示 Arena 和记录链路完整，`COLLISION` 是该回合的真实结果。该结果证明这个 train 单例能使 Base 遭遇动态交互困难；它不比较 PGRR，不能提前宣称 PGRR 会胜出。
