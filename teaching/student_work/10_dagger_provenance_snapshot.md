# DAgger 训练记录：只读溯源快照

生成日期：2026-08-28  
范围：只读取已提交的 `metrics.json` 与 `data/manifests/*.json`；不读取、修改或生成最终评测数据。

## 已检查的两份候选记录

| 记录目录 | manifest iteration | 数据集样本数 | episode 数 | 最佳验证 epoch | 最佳验证 loss | 最佳验证 top-1 | checkpoint |
|---|---:|---:|---:|---:|---:|---:|---|
| `coverage_safety_aligned` | 3 | 1387 | 12 | 25 | 0.1784 | 0.9223 | `checkpoints/dagger/coverage_safety_aligned/best.onnx` |
| `sequence_wait_aligned` | 5 | 2002 | 14 | 20 | 0.1706 | 0.9223 | `checkpoints/dagger/sequence_wait_aligned/best.onnx` |

两个记录使用相同的验证数据路径：
`data/interim/multiscenario_safety_aligned_validation.h5`。

最终发布入口仍指向：`checkpoints/final/best.onnx` →
`checkpoints/dagger/coverage_safety_aligned/best.onnx`。因此，不能只根据表中某一个离线数值就重新解释或替换最终模型。

## 当前可得与不可得的数据

| 数据 | 仓库中可读 | 当前能做的工作 |
|---|---|---|
| `metrics.json` 的逐 epoch 指标 | 是 | 绘制/比较训练和验证曲线，定位最佳 epoch |
| manifest 中的样本数、episode 数、哈希、checkpoint | 是 | 做溯源表、核对输入与模型绑定 |
| 原始 HDF5 数据集和 DAgger shard | 当前工作区未检出 | 暂不能统计动作标签、mask 可行动作数、逐样本 regret |
| 冻结 `moderate_v6_test` | 不作为诊断输入 | 不用于模型选择、阈值选择或补充训练 |

## 结论边界

这份快照说明：候选训练数据规模、最佳 epoch 和离线验证摘要均已具备可追溯记录；但原始 HDF5 未随当前工作区提供。因此下一步可以安全地继续做**曲线与 manifest 的只读分析**，而“动作类别/掩码分布诊断”需等拿到对应 HDF5 或由教授确认数据获取方式后再执行。

