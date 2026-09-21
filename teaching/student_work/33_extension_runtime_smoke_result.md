# PGRR Extension v1：Arena 最小运行记录

日期：2026-09-04  
范围：仅 `pgrr_extension_v1` 的**训练集**单场景运行；不是最终评测，也不使用或修改冻结的 `moderate_v6_test`。

## 运行目的

验证新场景 JSON 能被已固定的 Arena / ROS2 环境读取并实际启动，且能输出 episode 遥测与终止结果。该运行不用于比较 Base、BC 或 PGRR 的性能。

## 输入

- 场景：`diagonal_cut_in_corridor_low_train_r00_s91000`
- 划分：`train`
- 种子：`91000`
- 地图：`map_empty`
- 策略：`base`（经典规划器基线）
- 配置超时：90 s（模拟时间）
- 场景 JSON SHA-256：`f267a116b5f76f70557b19aa5a39319252e533abb6a303cfd279b9edcd5c99a0`

## 实际产物与结果

在 WSL 项目副本 `~/PGRR-online` 中，运行产生：

- `data/raw/pgrr_extension_smoke_diagonal_train_r00_base.jsonl`：900 条遥测记录；
- `data/raw/pgrr_extension_smoke_diagonal_train_r00_base.metadata.json`：输入、地图、种子和提交信息；
- `data/raw/pgrr_extension_smoke_diagonal_train_r00_base.outcome.json`：终止结果。

终止结果为：

```json
{
  "outcome": "TIMEOUT",
  "detail": "configured episode timeout",
  "sample_count": 900,
  "physical_goal_distance_m": 2.4273648317388705
}
```

末条遥测时间戳为 89.91 s，未标记碰撞。`TIMEOUT` 是该单次训练 smoke 的正常可记录终止类别，**不是性能结论**，也不能据此判断新方法优劣。

## 复现边界

这次只复制了一个已编译的训练场景 JSON 到 WSL 副本；没有同步或覆盖 Windows 主工作区的任何公开最终证据、checkpoint、阈值或测试场景。后续若重跑，应使用唯一 episode ID，并把容器日志写到挂载目录 `/workspace/outputs/student/...`，避免相对路径日志随一次性容器删除。

## 第二个训练场景：遮挡后侧向出现

同一运行环境中还执行了第二个训练场景：

- 场景：`occluded_side_emergence_low_train_r00_s91100`
- 划分 / 种子：`train` / `91100`
- 策略：`base`
- episode ID：`pgrr_extension_smoke_occluded_train_r00_base`

终端的运行器摘要为：`Episode PASS ... outcome=COLLISION samples=485`。

这里的 `PASS` 只表示脚本完整地产生了终止结果；`COLLISION` 是保留下来的真实 episode outcome。它说明该场景能够暴露基线在动态遮挡交互中的困难，因而适合作为后续 train/validation 研究场景；但单个 episode 不能用来声称 PGRR 优于基线。
