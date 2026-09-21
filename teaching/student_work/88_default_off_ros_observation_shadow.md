# 作业二：默认关闭的 ROS observation shadow 接入

## 完成内容

将已验证的 `RecoveryObservationBuilder`、`ObservationShadowComparator` 和有界
汇总器最小接入 `RecoveryManagerNode._observation()`：

- 新参数 `enable_observation_shadow` 默认值为 `False`；
- 旧 inline `RecoveryObservation` 仍先构建并作为唯一返回值；
- comparator 关闭时不会执行 builder candidate；
- 开启时，candidate 使用同一次回调中已经快照的 pose、velocity、path、LiDAR、
  history、base action、planner status 和 failure prediction；
- 比较结果只进入常量内存汇总器，不影响动作、状态机或返回 observation；
- candidate 接口中没有 privileged humans 或 simulator truth。

## 回归与结构证据

新增三项静态 ROS 接入测试，检查默认关闭、权威返回顺序和非特权输入。联合
builder、comparator、mask trace、ROS 参数与 observation 测试后，共 38 项通过；
Ruff 通过，AST 结构审计也能解析当前节点。

为避免覆盖作业二的“改造前”基线，原报告已恢复并保持：

- pre-shadow：1873 行、52 方法、observation seam 95 行，SHA-256 `e22d...778c7`；
- after-shadow：1898 行、52 方法、observation seam 115 行，SHA-256 `ad5c...47a4`。

当前结构另存为
`outputs/student/refactor_baseline/recovery_manager_structure_after_shadow.json`，
没有覆盖
`outputs/student/refactor_baseline/recovery_manager_structure.json` 的改造前含义。

## 边界

本步只完成默认关闭的代码接入，标准 Arena wrapper 还不能开启该参数，也没有
运行 ROS/Arena shadow smoke。因此不能声称真实消息、callback timing、日志开销
或运行时等价性已经验证。默认配置下算法、动作和冻结证据保持不变。
