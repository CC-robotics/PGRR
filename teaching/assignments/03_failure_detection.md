# Assignment 3：Freeze 与 Oscillation

实现 `detect_freeze` 和 `detect_oscillation`。只能用函数参数中的可观测历史，不得引入
行人真值。窗口不完整时返回 0；达到目标抑制 freeze；oscillation 先 deadband 再统计
符号翻转，并同时要求低进展。

验收：

```bash
pytest tests/unit/test_failure_rules.py -q
```

新增时间戳边界、到达目标静止和近零角速度噪声测试。生成一张三联图：距离/位移、角
速度、四类 failure score。口头解释 freeze 与 deadlock 的区别。失败案例选一次误触发，
说明是窗口、阈值还是观测噪声造成。
