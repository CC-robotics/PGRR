# Crossing-flow / medium 首个快速筛选锚点

## 本步完成了什么

按照 `120_fast_pgrr_advantage_scenario_discovery.md` 的快速漏斗，先从冻结结果中
差异最强的 `crossing_flow / medium` 单元出发，生成了一个**新的 train-only、固定
seed、非循环**场景。它不是从冻结测试集中挑一条重跑，也不进入正式论文结果。

- 场景 ID：`crossing_flow_medium_anchor_v1_train_r00_s95010`
- 随机种子：`95010`
- 机器人：从 `(5, 12)` 到 `(26, 12)` 直行；
- 动态行人：2 名，从上下两个方向一次性穿越机器人路线，穿越后继续离开；
- 方法配对：同一 JSON、同一 seed，计划只运行 Base 与已选定 PGRR checkpoint；
- 输出目录：`outputs/student/advantage_scenario_screen/`。

## 离线门槛结果

生成器和预检均已实际运行，而不是仅写设计：

- 静态路径存在，离散路径长度为 211 个网格；
- 有 1 名行人与机器人名义到达交点的时间差落在预设 8 s 冲突窗口内；
- 两名行人离开后分别提供约 6.2 m 的路线释放余量；
- 代表性恢复位置的 21/21 个临时子目标均通过静态可行性检查；
- 无 held-out test 被生成；
- 场景文件 SHA-256：`719fcb4ce9710895b95d3e8932f4fef21816258b05bd2271188f6fcc5f76b8d7`；
- `ready_for_single_seed_runtime_pair=true`。

生成器修复了一个跨 Windows/WSL 的可复现性问题：现在哈希取自实际落盘字节，
而不是哈希写入前的 LF 字符串。因此 WSL 对同一文件的校验值完全一致。3 项单元
测试和 Ruff 检查通过。

## 已准备的真实配对运行

`scripts/student/run_crossing_flow_anchor_pair.sh` 已完成，并通过 WSL 语法检查与
dry-run 预检。脚本默认 `DRY_RUN=1`，固定场景与 checkpoint 哈希，拒绝覆盖任何
已有 episode，并在真实运行后将精确的 outcome、轨迹和日志复制回当前工作区。

计划 episode：

- `pgrr_advscreen_crossing_medium_train_s95010_base`
- `pgrr_advscreen_crossing_medium_train_s95010_pgrr`

## 固定单对真实结果

Docker 恢复后，已按预检方案实际执行一次同场景、同 seed 配对：

| 方法 | 结局 | 样本数 | 终点物理距离 |
|---|---:|---:|---:|
| Base | `COLLISION`（robot-human overlap） | 272 | 14.639 m |
| PGRR | `TIMEOUT` | 900 | 3.917 m |

PGRR 在 25.708 s 进入恢复，在 37.196 s 恢复原目标，共记录 10 次决策：5 次
BACKUP、2 次 WAIT、3 次 CONTINUE；没有使用临时子目标。它避免了 Base 的早期
人机碰撞并继续接近目标，但在 90 s 内仍未到达。

## 结论与诚实边界

- 这是一个有效负结果，不是八个目标场景中的合格项；
- 它能说明“本次 PGRR 避免碰撞并取得更多进展”，但不能说明“PGRR 完成任务”；
- 按预先写好的停止规则，不换 seed、不延长超时、不调阈值，也不围绕本场景继续
  塑形；
- 新八场景目标仍为 `0/8`，下一步转向另一个独立机制。

原始 JSONL、metadata、outcome 和运行日志均保存在
`outputs/student/advantage_scenario_screen/runtime/`。
