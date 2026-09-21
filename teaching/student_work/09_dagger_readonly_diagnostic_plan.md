# DAgger：只读诊断计划（不调参、不使用冻结测试）

## 已落实的第一步

新增只读脚本：`scripts/student/analyze_dagger_metrics.py`。

它读取各轮已有的 `metrics.json`，输出：

- 数据量、epoch 数；
- 最低验证 loss 及其 epoch；
- 最高验证 top-1 及其 epoch；
- 最后一轮训练/验证 loss 和 top-1。

运行示例（在离线 Python 环境中）：

```bash
python scripts/student/analyze_dagger_metrics.py \
  checkpoints/dagger/coverage_safety_aligned/metrics.json \
  checkpoints/dagger/sequence_wait_aligned/metrics.json \
  --output-dir outputs/student/dagger_diagnostic
```

该命令只读已有 JSON，并在 `outputs/student/` 写摘要；不会训练、导出、覆盖模型，也不会打开冻结测试集。

摘要现在还会自动给出两种 gap：

- `loss gap = validation loss - training loss`；
- `top-1 gap = training top-1 - validation top-1`。

它们用于定位“训练与验证表现是否渐行渐远”的位置；单个正 gap 只是诊断线索，**不是**过拟合或闭环优越性的证明。

## 接下来可以继续完成的诊断清单

| 检查 | 想回答什么 | 需要的数据 | 结果如何解释 |
|---|---|---|---|
| 训练/验证曲线 | 是否存在明显泛化差距？ | 每 epoch 的 loss、top-1 | 训练持续改善而验证持续恶化，才支持“可能过拟合”假设 |
| 动作类别分布 | 新数据是否集中到少数动作？ | HDF5 labels | 类别失衡更像覆盖问题，不等于模型容量过大 |
| mask 可行动作数 | 任务是否从简单选择变成极难选择？ | HDF5 mask | 可行动作数变化会改变 top-1 的可比性 |
| 专家 regret | 错误动作的代价是否变大？ | HDF5 / metrics | 高 regret 的少量错误可能比普通 accuracy 更重要 |
| 分场景失败类型 | 哪些交互导致闭环退化？ | 新验证场景 telemetry | 用于提出场景级改进，而不是全局盲调 |

## 当前严谨结论

仓库已明确：最终采用验证选择的 `coverage_safety_aligned` checkpoint；后续候选没有被提升为最终模型。当前我们只能说“**后续候选在验证选择中不占优**”。

是否是过拟合、数据覆盖失衡、标签变化或训练配置差异，需要依次完成上述只读检查和独立验证后才能判断。
