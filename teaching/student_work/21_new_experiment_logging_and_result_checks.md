# 作业四准备：新实验的日志字段与结果检查顺序

日期：2026-08-28  
状态：只读参考现有 `collect_results.py`、`summarize_moderate.py` 与最终 summary schema；未收集新数据。

## 1. 为什么日志设计先于实验

一次仿真结束后，如果只留下“成功/失败”，论文很难说明失败原因、也难以做公平的 paired comparison。PGRR 的恢复行为还涉及触发、动作掩码、临时目标与重新加入原路径，因此日志必须能回答：

- 这是哪个确定条件？
- 结果是什么，是否属于算法指标？
- PGRR 是否触发，做了何种恢复？
- 安全、完成、效率和动作平滑性分别怎样？

## 2. 每个 logical episode 的最小记录字段

| 类别 | 最少字段 | 作用 |
|---|---|---|
| 条件身份 | `episode_id`, `logical_episode_id`, `scenario_id`, `family`, `density`, `split`, `seed`, `replicate`, `condition_key` | 同一条件可在不同方法间一一配对。 |
| 方法与版本 | `source_policy`, `planner_id`, `project_commit`, `arena_commit`, `config_sha256`, `scenario_sha256` | 防止不同代码或配置的结果混在同一表。 |
| 终止结果 | `outcome`, `outcome_detail`, `included_in_algorithm_metrics`, `exclusion_reason` | 明确成功、碰撞、超时等结果如何计入。 |
| 尝试溯源 | `physical_attempt_count`, `excluded_attempt_count`, `excluded_attempts_json` | 保留每一次物理尝试，不把失败静默丢掉。 |
| 效率与任务 | `episode_duration_s`, `navigation_time_s`, `path_length_m`, `progress_m`, `spl` | 报告完成代价。 |
| 安全与社会距离 | `min_lidar_m`, `min_human_distance_m`, `personal_space_violation_ratio`, `discomfort_time_s`, `emergency_stop_count` | 不能只报碰撞。 |
| 恢复行为 | `recovery_trigger_count`, `recovery_success_rate`, `recovery_duration_s`, `intervention_ratio` | 解释 PGRR 实际是否介入、介入代价如何。 |
| 平滑性 | `mean_abs_angular_jerk_rad_s3` | 衡量转向是否更急、更不平滑。 |
| 原始证据 | `raw_sha256`, `metadata_sha256`, `outcome_sha256` | 将汇总表绑定到原始流与终止记录。 |

现有实现中的结果收集逻辑可参见：
`scripts/evaluate/collect_results.py`；现有 summary 中已经包含完成、碰撞、超时、规划失败和上述多数连续指标。

## 3. 终止类别与重试规则

| 终止类别 | 是否属于算法结果 | 处理原则 |
|---|---|---|
| `GOAL_REACHED` | 是 | 保留。 |
| `COLLISION` | 是 | 保留，不可因结果不好而重试。 |
| `TIMEOUT` | 是 | 保留。 |
| `PLANNER_FAILURE` | 是 | 保留；是否作为推断终点要预先定义。 |
| `SIMULATOR_FAILURE` | 否，基础设施异常 | 可按预先定义规则重试，但须保留原尝试。 |
| `INVALID_RESET` | 否，复位异常 | 可按预先定义规则重试，但须保留原尝试。 |

这一区分很关键：**算法失败不能重跑挑选更好的一次；基础设施异常可以受控重试，但不能消失在日志中。**

## 4. 新实验结果生成后的检查顺序

1. 检查每个 `episode_id` 唯一，且 run manifest 没有不完整 task；
2. 检查每一方法具有相同的 `condition_key` 集合，无重复、无缺失、无额外条件；
3. 检查所有方法使用同一项目提交、已锁定配置和正确的新 benchmark 输出目录；
4. 检查全部 6 类终止结果都有显式计数，即使某些计数为零；
5. 把 `SIMULATOR_FAILURE`、`INVALID_RESET` 与算法结果分开呈现，并报告排除/重试原因；
6. 对预先声明的终点做 paired 统计；对探索性指标标注“描述性”，不要事后把它说成显著性结论；
7. 在图表旁同时放安全、完成和效率/平滑性指标，避免只展示有利的一面。

## 5. 写论文时可以使用的结果结构

```text
表 1：各方法的 GOAL / COLLISION / TIMEOUT / PLANNER_FAILURE（条件配对）
表 2：共同成功条件上的时间、路径长度、SPL、最小人距、角 jerk
图 1：代表性配对轨迹（Base 与 PGRR，同一 condition_key）
图 2：PGRR 触发—掩码—临时动作—rejoin 的时间线
附录：完整 manifest、配置/原始日志哈希、全部终止类别与重试记录
```

## 6. 与现有最终发布的边界

此清单是未来独立实验的记录规范。不要用它向
`outputs/moderate/final/` 添加或替换行；新 benchmark 应单独保存原始数据、manifest、结果表和统计文件。
