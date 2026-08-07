# Assignment 5：Action-Masked Behavior Cloning

实现 `ramp_ml.bc.run_epoch`。训练与 validation 共用函数，`optimizer=None` 时不得反向
传播。使用已有 loss helper，clip gradient norm 1.0，并按样本数累计七个指标。

验收：

```bash
pytest tests/unit/test_ramp_ml.py tests/unit/test_hdf5_schema.py -q
```

增加空 loader 和最后一个不完整 batch 的测试。用 smoke 配置训练，保存 loss/accuracy/
regret 曲线、checkpoint hash 和 seed。验证 invalid rate 为零。失败案例可以是过拟合、
mask shape 错误或类别不平衡；不要只展示最佳 epoch。
