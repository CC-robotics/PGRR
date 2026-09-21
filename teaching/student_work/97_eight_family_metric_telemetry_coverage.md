# 97 八类场景指标与日志字段覆盖审计

## 本步完成了什么

新增 `scripts/student/audit_eight_family_metric_telemetry.py`，读取第 96 步生成的八类算法—场景—指标矩阵，逐项判断指标是：

- 日志中直接存在；
- 可由已有字段计算；
- 同时有直接值和可重建值；
- 已有输入字段，但仍需要先确定论文中的操作定义。

生成物：

- `outputs/student/paper_design/eight_family_metric_telemetry_coverage.json`
- `outputs/student/paper_design/eight_family_metric_telemetry_coverage.md`

## 审计结果

八类矩阵共提出 20 个不同指标：

- 3 个直接记录：GOAL_REACHED、COLLISION、TIMEOUT；
- 14 个可从时间戳、位姿、速度、恢复状态、恢复动作和原因字段派生；
- 1 个既有直接终局字段也可从轨迹重建：最终目标距离；
- 2 个尚需确定操作定义：`minimum_clearance_m` 与 `deadlock_duration_s`。

`minimum_clearance_m` 的数据并非完全缺失：日志同时包含最近障碍物距离和特权的最近行人距离。问题是论文必须先确定它指“距所有障碍物的最小距离”“距行人的最小距离”，还是两者分别报告。

`deadlock_duration_s` 也不是简单缺字段。时间戳、速度、目标进展和恢复状态都已存在，但还需要预先定义低速阈值、进展窗口、危险是否持续以及最短持续时间，才不会在看到结果后临时改变判定标准。

## 验证

- 3/3 聚焦单元测试通过；
- Ruff 通过；
- 生成 JSON 可完整解析；
- 20/20 指标均被分类，没有未知指标；
- 本步没有运行 Arena、训练或评测，也没有触碰冻结测试和最终证据。

## 解释边界

“可派生”表示现有 telemetry schema 有足够字段，并不表示每个未来回合的派生表已经生成。正式 pilot 仍必须保存原始 JSONL 和 outcome JSON，并运行统一收集脚本。机制指标只能说明恢复链路在哪里启动或停滞，不能单独证明因果关系。

## 下一步

在不使用冻结测试集的前提下，为 `minimum_clearance_m` 和 `deadlock_duration_s` 写出候选操作定义及敏感性分析方案，供确认后冻结；同时可以把已经确定的 18 个指标接入八类 pilot 的统一结果收集 schema。
