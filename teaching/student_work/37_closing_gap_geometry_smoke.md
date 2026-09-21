# 第 5 类场景：多行人关闭通行间隙几何 smoke

状态：已完成训练集单例 JSON、静态检查、预览和一次 Arena Base smoke。

## 场景机制

机器人沿宽走廊前进时，两名行人从上下两侧同步向中线移动。它们起始时之间约有 1.94 m 间隙，随后缩小到 0.20 m；因此难点来自动态可通行空间消失，而不是地图本身不可达。

## 单例与验证

- scenario：`closing_gap_multi_pedestrian_medium_train_r00_s91410`；
- split / seed：`train` / `91410`；
- JSON：[场景文件](../../outputs/student/eight_family_geometry_draft/generated/arena/map_empty/closing_gap_multi_pedestrian_medium_train_r00_s91410.json)；
- 预览：[顶视图](../../outputs/student/eight_family_geometry_draft/previews/closing_gap_multi_pedestrian_medium_train_r00_s91410.png)；
- SHA-256：`5a2414181449947c3c5c25582d92b0bb52bea3688758888ff4b8be7a180cb8a2`。

第 3–5 类编译器与八类协议审计共 4 项单元测试通过。该产物只生成 train JSON；没有训练、没有执行 Arena、没有生成 held-out test。

## 后续解释边界

后续 Arena smoke 只能验证运动脚本是否按预期执行；公平比较 Base、启发式恢复、Uniform BC 与 PGRR 前，不能从该几何预览推断任何方法效果。

## Arena Base smoke

运行 ID：`pgrr_extension_smoke_closinggap_train_r00_base`。Arena 输出：

```text
Episode PASS ... policy=base outcome=COLLISION samples=348 monitor_status=143
```

这说明记录器完整保存了一个真实的碰撞终止回合。它显示 Base 在此 train 单例上有困难，但不构成 PGRR 的比较结论。
