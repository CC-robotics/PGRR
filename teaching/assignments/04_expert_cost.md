# Assignment 4：专家 Progress/Rejoin 代价

实现 `RolloutCostTerms.progress_contribution` 和 `rejoin_contribution`。输入项是未加权惩罚，
先钳制为非负，再乘对应权重。不要更改 collision 硬惩罚或其余项。

验收：

```bash
pytest tests/student/test_student_tasks.py::test_student_progress_and_rejoin_cost_terms \
  tests/unit/test_planning_expert.py -q
```

新增负输入钳制测试。选一个无行人和一个 head-on 特权状态，画 25 个候选动作代价，
标记 mask 和最优/次优 margin。失败案例说明 progress 权重过大或 rejoin 权重过大分别
会导致什么行为。
