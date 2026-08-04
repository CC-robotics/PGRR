# Assignment 6：离线 Action-Mask 消融

实现 `evaluate_predictions`，再恢复 CLI 中对保留 validation dataset 和三个 checkpoint
的遍历。每个模型同时计算 mask enabled 和 disabled-offline，后者不得部署。

验收：

```bash
pytest tests/unit/test_offline_policy_ablation.py -q
python scripts/evaluate/offline_policy_ablation.py --output outputs/student/ablation.csv
```

CSV 必须带 checkpoint/dataset SHA256、样本数和七个指标。增加空数据、错误 shape、每行
无合法动作测试。画 invalid rate 与 regret 对比图。失败案例解释为何关闭 mask 的高 top-1
不代表安全策略更好。
