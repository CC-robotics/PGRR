# PGRR 学生作业索引

七项作业对应 `student/reproduce` 中七处 `TODO(student)`。先阅读同周讲义，再运行本项
小测试；不要一次性改动所有模块。完整教师实现只留在 `teacher/reference`。

| 作业 | 文件 | 主要测试 | 交付 |
|---|---|---|---|
| 1 A* | `planning/astar.py` | `test_astar.py` | 路径图、边界测试 |
| 2 恢复子目标 | `action_space.py` | `test_action_space.py` | 25 动作示意图 |
| 3 失败规则 | `failure/rules.py` | `test_failure_rules.py` | 触发时间序列 |
| 4 专家代价 | `planning/costs.py` | `test_planning_expert.py` | 候选代价对比 |
| 5 BC | `ramp_ml/bc.py` | `test_ramp_ml.py` | smoke checkpoint/metrics |
| 6 消融 | `offline_policy_ablation.py` | `test_offline_policy_ablation.py` | CSV 与解释 |
| 7 论文图 | `make_figures.py` | paper artifact tests | 矢量 PDF |

所有作业还需通过 `tests/student/test_student_tasks.py` 中对应公共契约。提交 PR 时附：运行
命令、退出码、图、口头提纲、一个失败案例。不得修改测试掩盖错误。
