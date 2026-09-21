# 第 7 类 PGRR 功能回合结果

日期：2026-09-09。用途：仅验证恢复链路是否能运行，不作为八类正式比较、论文性能数字或调参依据。

## 运行身份

- episode：`student_v78_bottleneck_cross_flow_merge_medium_train_r00_s91610_pgrr_function02`
- policy：PGRR
- checkpoint：`checkpoints/final/best.onnx`，WSL 中有效链接到 validation-chosen `coverage_safety_aligned/best.onnx`
- SHA-256：`78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2`
- 推理环境：Python 3.10 venv，NumPy 2.2.6，ONNX Runtime 1.23.2，CPUExecutionProvider

## 回合结果

- outcome：TIMEOUT
- sample count：935
- physical goal distance：13.053542600402478 m
- localized goal distance：13.064151763916016 m
- 没有发生碰撞终止，但不能据此从一个回合推断 PGRR 优于 Base。

## 恢复链路证据

`scripts/student/analyze_recovery_trace.py` 对保留 JSONL 的汇总结果：

- 39 次相邻不同的决策事件；
- 11 次含 ONNX 决策理由的事件；
- 动作事件包含 SUBGOAL_0 ×1、WAIT ×14、BACKUP ×13、CONTINUE ×11；
- 3 次 `recovery_action_complete`；
- 3 次 `original_goal_restored`；
- episode logger 始终保留同一个任务级原始 goal。

关键时间链：

- 38.5281 s 首次进入 EMERGENCY_STOP；
- 40.0599 s 进入 RECOVERY；
- 49.5171 s 进入 REJOIN，50.0832 s 回到 NORMAL 并记录 `original_goal_restored`；
- 71.0955 s 选择 SUBGOAL_0；
- 77.5557 s 进入 REJOIN，80.5527 s 回到 NORMAL并再次记录原目标恢复。

代码路径核对：action ID 0 小于 WAIT_ACTION_ID(21)，属于 21 个临时子目标之一；`_execute` 会调用 planner adapter 的 `set_recovery_goal` 并将 `_goal_preempted` 置真。进入 REJOIN 时会调用 `restore_original_goal`，之后发布 `original_goal_restored`。因此本回合已经验证“触发—恢复动作—临时子目标—重接原目标”的功能链路。

## 当前结论与问题

功能链路成立，但该场景中恢复十分频繁，最终超时且未明显接近目标。这是值得后续用多重复、预注册协议检验的效率/完成率问题；当前不能改阈值，也不能把单次 Base 碰撞和单次 PGRR 超时包装成优越性结论。
