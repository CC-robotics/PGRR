# 64. 运行时动作掩码调用链静态审计

更新日期：2026-09-11

## 已确认的真实执行顺序

本轮直接解析 `recovery_manager_node.py`，核对运行时实际调用顺序，而不是根据
函数名称猜测。学习策略拿到动作掩码前，主要经历以下过程：

1. `compute_action_mask`：根据地图终点占用、运动线段、连通性和已知行人位置
   检查 21 个临时子目标；
2. `apply_observable_scan_mask`：用 LiDAR 检查运动方向和扫掠区域；
3. `apply_path_corridor_mask`：限制临时动作不能无界偏离原任务路径；
4. 设置 `WAIT/CONTINUE` 等特殊动作状态；
5. `constrain_rejoin_actions`：危险仍高时关闭 `CONTINUE/REPLAN`；
6. 已记录的让行、关闭侧、近场半径和侧向承诺约束；
7. 停滞、重复重规划、重复后退、累计后退和等待预算约束；
8. 已记录为 `pre→final` 的循环逃逸约束；
9. 空掩码安全回退，然后才把掩码交给 ONNX 策略。

静态审计共固定 18 个函数调用阶段，并绑定当前源文件 SHA-256。若今后调用
被删除、重复或换序，审计器和单元测试会失败。

## 对“46 次上游收缩”的进一步定位

补齐 `bc_recurrent_escape` 使用的 `pre→final` 日志格式后，重新分析的结果仍为：

- 46 次在第一条已记录的 `bc_yield_mask` 之前就只剩 `WAIT/BACKUP`；
- 3 次由 `bc_closing_side` 完成收缩；
- 1 次由 `bc_yield_mask` 完成收缩。

代码语义还能再排除一项：`constrain_rejoin_actions` 只关闭
`CONTINUE/REPLAN`，不删除 21 个临时子目标；特殊动作赋值同样不会删除它们。
因此，这 46 次中临时子目标的消失必然发生在以下三层之一或其组合：

1. 地图/线段/连通性检查；
2. LiDAR 方向和扫掠安全检查；
3. 全局路径走廊检查。

目前日志没有保存这三层各自的 `pre/post`，所以还不能说具体是哪一层，更不能
把“为了安全而屏蔽”直接叫作算法错误。

## 新发现的遥测盲区

关闭侧约束与循环逃逸约束之间还有六道规则没有逐层日志。现有日志只能比较
关闭侧的输出与循环逃逸的输入，从差异中发现“中间发生了变化”，但不能继续
区分是哪一道规则。八类日志中发现 1 次这样的差异，它删除的是 `WAIT/BACKUP`
并保留 `SUBGOAL_0`，没有造成只剩 `WAIT/BACKUP`，因此不改变本轮主结论。

## 下一步安全工作

下一步用纯 Python 合成地图、LiDAR 和路径输入，分别调用前三层并输出每层保留
的动作。目标是建立可控的“逐层回放夹具”，先解释什么几何条件会把所有临时
子目标删掉，再决定是否需要新的 train/validation 消融。此时仍不修改 ROS
运行时、不放宽安全规则、不训练模型、不读取或调整冻结测试集。

产物：

- `outputs/student/eight_family_pilot/runtime_mask_pipeline_audit.json`
- `outputs/student/eight_family_pilot/runtime_mask_pipeline_audit.md`
- `scripts/student/audit_runtime_mask_pipeline.py`
- `tests/unit/test_audit_runtime_mask_pipeline.py`
