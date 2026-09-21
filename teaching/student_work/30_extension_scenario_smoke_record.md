# PGRR extension v1：新场景 smoke 编译记录

日期：2026-09-04  
状态：**配置、Arena JSON schema、静态路径和预览图检查通过；不是 ROS 运行或实验结果。**

## 目的

在不触及 `moderate_v6`、最终模型或 held-out test 的前提下，验证两个老师指定的
场景族至少各有一个 train 条件能够：

1. 从独立 `pgrr_extension_v1` 配置生成 Arena JSON；
2. 通过基本的场景 schema/边界检查；
3. 通过静态障碍物下的 A* 可达性检查；
4. 生成一张可人工检查的预览图。

## 运行命令

```powershell
python scripts/student/compile_extension_train_validation.py `
  --config configs/experiments/pgrr_extension_v1_train_validation.yaml `
  --output-root outputs/student/extension_scenario_smoke `
  --limit 2

python scripts/student/compile_extension_train_validation.py `
  --config configs/experiments/pgrr_extension_v1_train_validation.yaml `
  --output-root outputs/student/extension_scenario_smoke `
  --family occluded_side_emergence --limit 1
```

## 已生成的 smoke 制品

| 场景 | split | seed | JSON SHA-256 | 说明 |
|---|---|---:|---|---|
| `diagonal_cut_in_corridor_low_train_r00` | train | 91000 | `beef63854fa03a097a3975a61c243ec9b4ce51a48704d2df2d90191ceb61b4a7` | 斜向切入走廊原型 |
| `diagonal_cut_in_corridor_low_train_r01` | train | 91001 | `e9813d79e0f94d69461fd03562261098ba11de83c7bbe340a492e1d5ea138eac` | 斜向切入走廊原型 |
| `occluded_side_emergence_low_train_r00` | train | 91100 | `de14828a2d671690bab467dedf5bb3b423121548533e0a61af55dedcfc40550f` | 遮挡 shelf 后突现原型 |

制品根目录：`outputs/student/extension_scenario_smoke/`。每一次 smoke 都使用独立
`smoke_manifest_<family>_<limit>.json`，避免后来运行的场景族覆盖先前的哈希记录。

## 人工预览结论

`occluded_side_emergence` 预览中包含：

- 水平 shelf 形成的约束通道；
- 从通道一侧伸出的竖直遮挡 shelf；
- 机器人起点、终点和避开遮挡 shelf 的静态 A* 路径；
- 一条从遮挡侧横向进入通道的行人路线。

因此它已适合作为下一阶段 Arena/ROS smoke 的输入候选。

## 必须保留的限制

- 几何字段的状态为 `smoke_only_not_a_frozen_experiment_protocol`；
- 这里只验证了静态路径，不验证动态行人行为、LiDAR 可见性或恢复策略；
- 没有生成 validation 以外的结果，更没有生成或运行 held-out test；
- `pgrr_extension_v1` 的正式参数范围、场景数量、训练和统计协议冻结前，不可写入论文结果部分。

## 与论文素材的关系

现阶段可以把预览图作为**任务设置示意图候选**，并据此完善方法/实验设置描述；
不能把它放在主结果图中，也不能由其推断 PGRR 优于任一基线。
