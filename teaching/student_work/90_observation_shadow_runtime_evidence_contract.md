# 90. Observation shadow 运行证据契约

## 完成内容

为了让下一次真实 Arena smoke 不只是“跑过”，本步补上了可机器验证的运行证据出口。

- 启用 shadow 时，`RecoveryManagerNode.destroy_node()` 在正常销毁前输出一次 `observation_shadow_summary=<JSON>`。
- 汇总只有计数、逐字段最大误差和 mismatch 数，不保存逐样本 observation。
- 未启用 shadow 时不输出该汇总。
- 新增 `scripts/student/validate_observation_shadow_smoke.py`，把 runtime log 和 outcome JSON 联合验证。

验证器要求：恰好一个可解析汇总、比较次数大于零、全部比较等价、mismatch 为零、逐样本保存数为零、权威路径未改变，并且不存在已知恢复管理器致命错误。episode 的 `GOAL_REACHED/COLLISION/TIMEOUT/...` 只被如实记录，不参与 observation 等价性是否通过的判断。

## 验证结果

- 22 个相关单元测试通过。
- Ruff 通过。
- `git diff --check` 无补丁格式错误，仅有 Windows 换行提示。

## 边界

这是运行证据的格式和判定契约，不是 Arena 运行结果。尚未声称真实消息上等价，也没有用导航成败评价此次模块化重构。

## 下一步

建立带 SHA-256 的最小同步清单，确认 WSL/Arena 使用的节点、两个核心模块和两个启动脚本与当前工作区完全一致，然后才允许执行一次非冻结 train smoke。
