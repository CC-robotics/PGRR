# 94. Observation shadow 候选异常隔离

## 发现的问题

observation shadow 虽然默认关闭且旧 observation 始终作为返回值，但显式开启后，候选 Builder 若抛出异常，异常原本会从比较器向上传播并中断恢复管理器。这意味着一个“只用于诊断”的模块仍可能改变真实控制路径，不符合 shadow 的安全边界。

## 实际修改

`ObservationShadowComparator.compare()` 现在只捕获候选构建与比较阶段的普通 `Exception`，不会捕获 `KeyboardInterrupt`、`SystemExit` 等进程控制信号。发生异常时：

- 不向 ROS 控制路径重新抛出；
- 返回一次不等价的诊断结果；
- 只记录有界的异常类型名称，不保存异常消息或 observation；
- accumulator 增加 `candidate_error_count` 和 `last_candidate_error_type`；
- `authoritative_path_changed` 仍明确为 `false`。

这不会把异常伪装成等价：现有 smoke 验证器会因为 mismatch 非零而拒绝该运行证据，但旧 observation 可以继续驱动控制器。

## 验证结果

- 23 个 observation builder/shadow/ROS 集成与验证器测试通过。
- Ruff 通过，`git diff --check` 无格式错误。
- 回归用例实际让候选抛出 `RuntimeError`，确认异常未逃逸，累计器记录 1 次错误且不保存逐样本数据。
- 预检哈希已刷新，更新通过白名单同步器同步到 WSL，最终再次达到 5/5 匹配。

## 结论边界

该修改只增强显式诊断路径的故障隔离，不改变默认关闭状态、旧 observation、策略、阈值或冻结证据。由于 Docker WSL integration 仍未恢复，尚未构建 overlay 或运行 Arena。
