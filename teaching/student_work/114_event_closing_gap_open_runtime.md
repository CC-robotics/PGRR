# 114 开放空间 closing-gap 真实配对运行

本轮实际运行了 train-only 候选 `closing_gap_open_release_v1_train_r00_s91410`，Base 与 PGRR 使用完全相同的场景 JSON、种子 91410、90 s 时限和默认算法设置。未使用冻结测试集，也未修改恢复阈值或模型。

## 结果

| 方法 | outcome | 样本数 | 物理终点距离 | 事件转换数 |
|---|---:|---:|---:|---:|
| Base | TIMEOUT | 895 | 2.151 m | 4 |
| PGRR | TIMEOUT | 897 | 2.067 m | 4 |

两个行人都分别记录了 `pre_event_to_active_event` 和 `active_event_to_released`，共四次转换；因此“接近触发、穿越、随后恢复路线”的运行语义已经在两种方法下真实发生。这不是启动失败、事件未触发或静态墙碰撞造成的无效回合。

## 判定

该候选不晋级为论文核心案例。原因不是场景无效，而是 Base 与 PGRR 都在终点附近超时，PGRR 没有到达目标，且两者终点距离仅相差约 0.084 m，不能支持“PGRR 优于 Base”的案例级结论。

按照预设纪律，保留这组负结果，不更换种子、不调整算法阈值，也不继续围绕同一几何做结果导向微调。下一步应筛选一种不同的动态交互机制。

## 证据

- `outputs/student/event_controlled_candidates/runtime_closinggap_s91410/runtime_gate_summary.json`
- 同目录下 Base/PGRR 的 `.outcome.json`、`.metadata.json` 与 `.jsonl`
- 场景：`outputs/student/event_controlled_candidates/generated/arena/map_empty/closing_gap_open_release_v1_train_r00_s91410.json`
