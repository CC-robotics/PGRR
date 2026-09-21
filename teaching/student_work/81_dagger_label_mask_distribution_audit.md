# DAgger 标签与动作掩码分布审计

## 做了什么

新增只读工具 `scripts/student/analyze_dagger_label_mask_distribution.py`，检查 HDF5 中的
专家动作、有效动作数、失败类型、margin 和 predicted success，并为每份文件核对
SHA-256。输出为
`outputs/student/dagger_diagnostic/label_mask_distribution.json`。没有训练、导出模型、
修改 checkpoint 或读取冻结 test。

## 首先发现的可复现性边界

三份可用文件中只有较晚的 iteration-5 训练集与 manifest 哈希一致：

| 审计对象 | 可用文件 | manifest 期望哈希一致 |
|---|---|---:|
| selected iteration-3 的本地别名 | `data/processed/dagger_coverage_train.h5` | 否 |
| later iteration-5 | `data/processed/dagger_sequence_wait_aligned_train.h5` | 是 |
| 本地 shared-validation copy | `data/interim/multiscenario_safety_aligned_validation.h5` | 否 |

manifest 指向的 iteration-3 文件名
`data/processed/dagger_coverage_safety_aligned_train.h5` 当前并不存在。因此报告明确设置
`canonical_comparison_ready=false`。下面的分布只能描述当前可用副本，不能冒充严格的
selected-vs-later canonical 对照。

## 当前可用副本显示的强分布变化

| 数据 | 样本 | WAIT | 临时子目标 | 有效动作中位数 |
|---|---:|---:|---:|---:|
| iteration-3 本地别名 | 1387 | 32.4% | 6.4% | 6 |
| iteration-5（哈希一致） | 2002 | 75.6% | 12.9% | 1 |
| validation 本地副本 | 399 | 91.0% | 4.8% | 2 |

三份数据的专家动作都在各自行 mask 内。iteration-5 的训练标签明显更偏向 WAIT，且
每条样本可选动作集合更窄。这说明“后续候选不如前一个”至少可能同时受到标签分布和
动作可行域变化影响；不能只凭轮数把现象命名为模型过拟合。iteration-3 的 margin
还出现约 `1e6` 的高位值，而 iteration-5 中位 margin 为 0，也提示 margin 语义或
sentinel 需要另行核对。

## 严谨结论

当前可以说：较晚的 canonical iteration-5 训练集高度 WAIT-heavy，且 mask 更窄；这
是覆盖/标签变化假设的直接证据。当前不能说：它已经证明第二轮 DAgger 过拟合，或已
完成与 selected iteration-3 的严格数据对照。后者必须先找回 manifest 对应哈希的
iteration-3 与 validation 文件，或更新一份经过审计的新 provenance 决议。

