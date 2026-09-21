# 新增场景的数据划分：执行前检查清单

这份清单依据现有 `moderate_v6` 的结构整理，但服务于**独立学生扩展实验**。它不是对发布 benchmark 的修改。

## 已完成的准备

- 建立了只作模板用的 `11_independent_experiment_split_template.yaml`。
- 模板显式禁止引用 `moderate_social_navigation_v6`，并保留现有六类 episode 终止原因。
- 模板把划分单位固定为 `scenario_id + seed`，而不是一帧帧随机分配。
- 模板规定五个方法使用相同 condition key，保证后续可以做配对比较。

## 教授确认后才能填写的项目

1. 新增的正式场景族；
2. 训练、验证、保留测试各自的 seed 范围和重复次数；
3. 哪些场景属于训练覆盖，哪些场景完全保留做泛化测试；
4. 正式评估终点、效率指标和统计检验。

## 每次运行前的最低检查

- [ ] 新的 `scenario_id` 在三个 split 中只出现一次；
- [ ] 训练阶段不读取 validation/held-out 的 episode；
- [ ] 所有方法的场景、seed、起终点、行人轨迹和障碍物参数一致；
- [ ] 每个场景 JSON、配置和代码版本都记录 SHA256/commit；
- [ ] `SIMULATOR_FAILURE` 和 `INVALID_RESET` 与算法终点分开记录；
- [ ] 新结果输出至独立学生目录，绝不覆盖 `outputs/moderate/final/`。

## 为什么这样做

如果一个场景的不同帧同时进入训练和测试，模型可能只是“见过相似瞬间”，而不是学会了在新交互中恢复。按完整场景和随机种子分开，才能更可信地说明新实验测的是泛化能力。

