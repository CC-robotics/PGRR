# 作业二：观测 shadow 的有界汇总器

## 完成内容

在默认关闭的 observation shadow comparator 之后，新增
`ObservationShadowAccumulator`，为未来非冻结 ROS shadow 运行准备一个不会随
episode 长度无限增长的汇总层。

它只累计：

- 总比较数、完全等价数和不等价数；
- 诊断关闭时跳过的次数；
- metadata 不一致次数；
- 七个数组字段各自的不一致次数；
- 七个字段观测到的最大绝对误差。

它不保存逐样本 observation，报告固定写明 `stored_per_sample_records=0` 和
`authoritative_path_changed=false`。因此以后即使在长回合中开启诊断，也不需要
把 LiDAR 历史等大数组全部留在内存中。

## 验证

- 合成的 disabled、exact、mismatch 三种结果能正确累计；
- 仅 `base_action` 偏差时，只增加该字段 mismatch；
- 32 例 observation builder 等价性探针已接入汇总器；
- 结果为 32/32 equivalent、0 mismatch、七字段最大误差均为 0；
- 相关测试共 12 项通过，Ruff 通过。

机器可读结果仍为
`outputs/student/refactor_baseline/observation_builder_equivalence.json`。

## 边界

该汇总器尚未接入 ROS，也没有写运行日志。它只完成了低内存、非权威、默认关闭
的离线接口。ROS callback 一致性和实际日志开销仍需后续非冻结 smoke 验证。
