# Assignment 1：确定性 8 邻接 A*

实现 `ramp_core.planning.astar.astar`。要求使用 octile heuristic、禁止斜穿障碍角、
相同优先级确定性 tie-break、无路径返回空列表，并正确重建含起终点的路径。

验收：

```bash
pytest tests/unit/test_astar.py \
  tests/student/test_student_tasks.py::test_student_astar_finds_gap_without_corner_cutting -q
```

新增至少两个测试：`start == goal` 和完全封闭 goal。提交一张 10x10 以上栅格路径图，
用不同符号表示占据、探索到的节点和最终路径。口头解释 heuristic 为什么不高估。

失败案例：构造只有斜角接触的两个自由格，说明未检查 corner cutting 会发生什么。
